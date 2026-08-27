"""Fast integration regressions executed inside Blender, without rendering."""

import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from soft_body_variants import (
    OBSTACLES, obstacle_specimen_depth_offsets, obstacle_specimen_offsets,
    stage_motion_for, variant_for_seed,
)
from soft_body_framing import project_point

spec = importlib.util.spec_from_file_location("soft_body_renderer", ROOT / "blender-soft-body-slide.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class SurfaceContactTests(unittest.TestCase):
    def setUp(self):
        renderer.reset_scene()
        self.variant = variant_for_seed(910103, "v-stairs")
        self.material = renderer.material("Test surface", (0.5, 0.5, 0.5, 1.0))

    def box_surface(self):
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        box = bpy.context.object
        box.dimensions = (1.0, 1.0, 0.2)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return renderer.ObstacleSurface((box,)).at_frame(1)

    def constrain(self, target, anchor_z=0.3):
        return renderer.constrain_visible_skin(
            [target], [(0.0, 0.0, -0.2)],
            [Vector((-0.1, anchor_z)), Vector((0.1, anchor_z))],
            self.variant, self.box_surface(),
        )

    def test_cosmetic_fold_stops_above_the_actual_mesh(self):
        shape, report = self.constrain((0.0, -0.04, 0.05))
        self.assertGreaterEqual(shape[0][2], 0.107)
        self.assertEqual(report["corrected_vertices"], 1)
        self.assertEqual(report["inside_contacts"], 0)

    def test_a_ray_cannot_skip_through_a_thin_obstacle(self):
        shape, report = self.constrain((0.0, -0.04, -0.3))
        self.assertGreaterEqual(shape[0][2], 0.107)
        self.assertEqual(report["corrected_vertices"], 1)

    def test_free_skin_is_not_changed(self):
        target = (0.0, -0.04, 0.2)
        shape, report = self.constrain(target)
        for actual, expected in zip(shape[0], target):
            self.assertAlmostEqual(actual, expected, places=6)
        self.assertEqual(report["corrected_vertices"], 0)

    def test_an_inside_spine_is_reported_not_hidden(self):
        _shape, report = self.constrain((0.0, -0.04, 0.3), anchor_z=0.0)
        self.assertEqual(report["inside_contacts"], 1)

    def test_two_visible_bodies_cannot_pass_through_each_other(self):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.5)
        first = bpy.context.object
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.5, location=(0.5, 0.0, 0.0))
        second = bpy.context.object
        report = renderer.inspect_specimen_intersections((first, second), 1, 2)
        self.assertEqual(report["issues"], ["specimens-interpenetrate"])
        self.assertGreater(report["maximum_penetration"], 0.1)
        second.location.y = 1.5
        report = renderer.inspect_specimen_intersections((first, second), 1, 2)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["frames_checked"], 2)

    def test_equal_mass_specimens_resolve_contact_without_receiver_steering(self):
        def state(x, previous_x):
            return {"points": [Vector((x, 10.0))], "previous": [Vector((previous_x, 10.0))],
                "radius": 0.25, "rest": 1.0, "variant": self.variant,
                "time": 0.0, "dt": 1 / 240, "softness": 0.55,
                "trial_duration": 7.0, "phase": 0.0, "collision_radii": [0.25], "coupled_impacts": [0.0]}
        first, second = state(-0.20, -0.21), state(0.20, 0.21)
        renderer.resolve_specimen_contacts((first, second), (0.0, 0.0))
        self.assertGreaterEqual((second["points"][0] - first["points"][0]).length, 0.4999)
        self.assertAlmostEqual(first["points"][0].x + second["points"][0].x, 0.0)
        self.assertLess(first["points"][0].x - first["previous"][0].x, 0.0)
        self.assertGreater(second["points"][0].x - second["previous"][0].x, 0.0)
        self.assertGreater(first["coupled_impacts"][0], 0.0)

    def test_parallel_depth_lanes_do_not_collide(self):
        first = {"radius": 0.25, "points": [Vector((0.0, 0.0))]}
        second = {"radius": 0.25, "points": [Vector((0.0, 0.0))]}
        renderer.resolve_specimen_contacts((first, second), (-1.15, 1.15))
        self.assertEqual(tuple(first["points"][0]), (0.0, 0.0))

    def test_coupled_solver_uses_one_clock_at_preview_and_production_rates(self):
        preview = renderer.simulate_specimens(55, 1, 5, self.variant, 2)
        native = renderer.simulate_specimens(55, 6, 30, self.variant, 2)
        for first, second in zip(preview, native):
            self.assertEqual(len(first.physics_samples), len(second.physics_samples))
            for a, b in zip(first[-1][0], second[-1][0]):
                self.assertLess((a - b).length, 1e-6)

    def test_quarter_soft_moving_ramp_does_not_stretch_at_a_fast_impact(self):
        variant = variant_for_seed(910105, "moving-slide")
        # Preserve the original high-energy repro, independently of the
        # gentler authored ramp used for publication now.
        variant = replace(variant, ramp=replace(variant.ramp, slope=0.17, lip_rise=0.94))
        simulation = renderer.simulate_chain(25, 115, 30, variant, 1)
        quality = renderer.simulation_quality(simulation, variant)
        self.assertEqual(quality["issues"], [])
        self.assertGreaterEqual(quality["minimum_segment_ratio"], 0.96)
        self.assertLessEqual(quality["maximum_segment_ratio"], 1.04)

    def test_portrait_projection_matches_blender_for_every_camera(self):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
        for obstacle in OBSTACLES:
            variant = variant_for_seed(910103, obstacle.key)
            camera = renderer.add_camera(variant)
            bpy.context.view_layer.update()
            for position in ((-2.0, -1.15, 6.0), (2.7, 1.15, 2.5), (0.0, 0.0, 0.0)):
                expected = world_to_camera_view(scene, camera, Vector(position))
                actual = project_point(position, obstacle)
                self.assertAlmostEqual(actual[0], expected.x, places=5)
                self.assertAlmostEqual(actual[1], expected.y, places=5)

    def test_pipe_glass_uses_the_exact_continuous_collision_path(self):
        variant = variant_for_seed(910104, "pipe-bend")
        segments = renderer.obstacle_segments(variant)
        renderer.add_obstacle_geometry(self.material, self.material, variant, 1, 30)
        for side in range(2):
            walls = segments[side::2]
            for first, second in zip(walls, walls[1:]):
                self.assertEqual(first[1], second[0])
            curve = bpy.data.objects[f"Continuous glass pipe wall {side + 1}"].data
            self.assertTrue(curve.use_fill_caps)
            self.assertEqual(curve.splines[0].type, "POLY")
            visible = [(point.co.x, point.co.z) for point in curve.splines[0].points]
            expected = [walls[0][0], *[wall[1] for wall in walls]]
            self.assertEqual(visible, expected)

    def test_pipe_cap_contact_from_outside_is_not_reported_as_inside(self):
        variant = variant_for_seed(910104, "pipe-bend")
        renderer.add_obstacle_geometry(self.material, self.material, variant, 1, 30)
        wall = bpy.data.objects["Continuous glass pipe wall 2"]
        tree = renderer.ObstacleSurface((wall,)).at_frame(1)
        anchor = Vector((0.5000838637, -0.04, 2.8064873219))
        target = Vector((0.82, -0.04, 2.925))
        direction = (target - anchor).normalized()
        hit, normal, _face, _distance = tree.ray_cast(anchor, direction, 0.5)
        self.assertIsNotNone(hit)
        self.assertLess(normal.dot(direction), 0.0)
        shape, report = renderer.constrain_visible_skin(
            [tuple(target)], [(0.0, 0.0, 0.0)],
            [Vector((anchor.x, anchor.z))] * 2, variant, tree,
        )
        self.assertEqual(report["inside_contacts"], 0)
        self.assertEqual(report["corrected_vertices"], 1)
        self.assertLess((Vector(shape[0]) - anchor).length, (hit - anchor).length)

    def test_second_attempt_restarts_the_visible_ramp_clock(self):
        variant = variant_for_seed(910103, "moving-slide")
        ramp = renderer.add_ramp(
            self.material, self.material, variant, 240, 30, ((2, 1, 120), (7, 121, 240)),
        )
        bpy.context.scene.frame_set(121)
        expected = renderer.ramp_position(0.0, variant, 4.0, stage_motion_for(variant, 7).ramp_phase_offset)
        self.assertAlmostEqual(ramp.location.x, expected, places=5)
        bpy.context.scene.frame_set(150)
        expected = renderer.ramp_position(29 / 30, variant, 4.0, stage_motion_for(variant, 7).ramp_phase_offset)
        self.assertAlmostEqual(ramp.location.x, expected, places=5)

    def test_every_family_has_a_clear_spawn(self):
        for obstacle in OBSTACLES:
            for seed in (910103, 910104, 910105):
                with self.subTest(obstacle=obstacle.key, seed=seed):
                    renderer.reset_scene()
                    variant = variant_for_seed(seed, obstacle.key)
                    material = renderer.material("Spawn test", (0.5, 0.5, 0.5, 1.0))
                    renderer.add_receiver(material, material, variant)
                    if obstacle.key == "moving-slide":
                        renderer.add_ramp(material, material, variant, 1, 30, ((0, 1, 1),))
                    else:
                        renderer.add_obstacle_geometry(material, material, variant, 1, 30)
                    surface = renderer.ObstacleSurface(bpy.context.collection.objects).at_frame(1)
                    base, _faces = renderer.capsule_geometry(variant)
                    for offset, depth in zip(obstacle_specimen_offsets(obstacle.key), obstacle_specimen_depth_offsets(obstacle.key)):
                        points, impact, nodes, *_rest = renderer.simulate_chain(55, 0, 30, variant, 0, offset)[0]
                        shape = renderer.skin_capsule(base, points, 0.55, impact, nodes, 0, variant)
                        _shape, report = renderer.constrain_visible_skin(shape, base, points, variant, surface, depth)
                        self.assertEqual(report["inside_contacts"], 0)
                        self.assertEqual(report["corrected_vertices"], 0, "body starts intersecting an obstacle")

    def test_v_stairs_spawn_and_outer_steps_fit_portrait_frame(self):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
        camera = renderer.add_camera(self.variant)
        bpy.context.view_layer.update()
        positions = [Vector((x, 0.0, z)) for segment in renderer.obstacle_segments(self.variant) for x, z in segment[:2]]
        for offset in obstacle_specimen_offsets("v-stairs"):
            points = renderer.simulate_chain(55, 0, 30, self.variant, 0, offset)[0][0]
            positions.extend(Vector((point.x, 0.0, point.y + self.variant.shape.radius)) for point in points)
        for position in positions:
            projected = world_to_camera_view(scene, camera, position)
            self.assertGreater(projected.x, 0.025)
            self.assertLess(projected.x, 0.975)
            self.assertGreater(projected.y, 0.06)
            self.assertLess(projected.y, 0.91)

    def test_all_spawned_capsules_fit_below_the_label(self):
        for obstacle in OBSTACLES:
            for seed in (910103, 910104, 910105):
                with self.subTest(obstacle=obstacle.key, seed=seed):
                    renderer.reset_scene()
                    variant = variant_for_seed(seed, obstacle.key)
                    scene = bpy.context.scene
                    scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
                    camera = renderer.add_camera(variant)
                    bpy.context.view_layer.update()
                    base, _faces = renderer.capsule_geometry(variant)
                    for offset, depth in zip(obstacle_specimen_offsets(obstacle.key), obstacle_specimen_depth_offsets(obstacle.key)):
                        points, impact, nodes, *_rest = renderer.simulate_chain(55, 0, 30, variant, 0, offset)[0]
                        shape = renderer.skin_capsule(base, points, 0.55, impact, nodes, 0, variant)
                        for x, y, z in shape[::16]:
                            projected = world_to_camera_view(scene, camera, Vector((x, y + depth, z)))
                            self.assertGreater(projected.x, 0.02)
                            self.assertLess(projected.x, 0.98)
                            self.assertGreater(projected.y, 0.06)
                            self.assertLess(projected.y, 0.91)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceContactTests))
    raise SystemExit(0 if result.wasSuccessful() else 1)
