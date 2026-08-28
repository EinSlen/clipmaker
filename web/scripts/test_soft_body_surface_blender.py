"""Fast integration regressions executed inside Blender, without rendering."""

import importlib.util
import math
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
    OBSTACLES, SHAPES, obstacle_specimen_depth_offsets, obstacle_specimen_offsets,
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

    def test_peer_contact_uses_closed_volume_even_with_reversed_faces(self):
        from mathutils.bvhtree import BVHTree
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        mesh = bpy.context.object.data
        vertices = [vertex.co.copy() for vertex in mesh.vertices]
        for reverse in (False, True):
            faces = [tuple(reversed(face.vertices)) if reverse else tuple(face.vertices) for face in mesh.polygons]
            tree = BVHTree.FromPolygons(vertices, faces)
            shape, report = renderer.constrain_visible_skin(
                [(0, -.04, 0)], [(0, 0, -.2)], [Vector((0, .7))] * 2,
                self.variant, tree, verify_closed_volume=True)
            self.assertEqual(report["inside_contacts"], 0)
            self.assertEqual(report["corrected_vertices"], 1)
            self.assertGreaterEqual(shape[0][2], .507)
            _shape, report = renderer.constrain_visible_skin(
                [(0, -.04, .7)], [(0, 0, .2)], [Vector((0, 0))] * 2,
                self.variant, tree, verify_closed_volume=True)
            self.assertEqual(report["inside_contacts"], 1, "real inside anchors still fail")

    def test_final_subdivided_vertices_are_checked_and_kept_outside(self):
        self.box_surface()
        box = bpy.context.object
        surface = renderer.ObstacleSurface((box,))
        body = renderer.add_mesh("Test subdivided skin", [
            (-0.1, -0.1, 0.08), (0.1, -0.1, 0.08), (0.1, 0.1, 0.08), (-0.1, 0.1, 0.08),
        ], [(0, 1, 2, 3)], self.material)
        subdivision = body.modifiers.new("Render subdivision", "SUBSURF")
        subdivision.levels, subdivision.render_levels = 1, 3
        before = renderer.inspect_rendered_surface(body, surface, 1, 2)
        self.assertEqual(before["issues"], ["rendered-skin-inside-obstacle"])
        self.assertGreater(before["maximum_penetration"], 0.019)
        renderer.add_final_surface_contact(body, surface.final_contact_targets())
        after = renderer.inspect_rendered_surface(body, surface, 1, 2)
        self.assertEqual(after["issues"], [])
        self.assertEqual(after["maximum_penetration"], 0)
        self.assertEqual(after["frames_checked"], 2)
        self.assertEqual(after["subdivision"], 3)
        self.assertGreater(after["vertices_checked"], 8)
        self.assertEqual(subdivision.levels, 1, "the viewport level is restored")
        body.location.z = 1
        depsgraph = bpy.context.evaluated_depsgraph_get()
        free_mesh = body.evaluated_get(depsgraph).to_mesh()
        try:
            self.assertTrue(all(abs(vertex.co.z - 0.08) < 1e-6 for vertex in free_mesh.vertices),
                            "free flight must not be snapped toward an obstacle")
        finally:
            body.evaluated_get(depsgraph).to_mesh_clear()

    def test_final_contact_target_follows_the_animated_obstacle(self):
        self.box_surface()
        box = bpy.context.object
        box.location.x = 0
        box.keyframe_insert("location", frame=1)
        box.location.x = 2
        box.keyframe_insert("location", frame=31)
        surface = renderer.ObstacleSurface((box,))
        targets = surface.final_contact_targets()
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].hide_render)
        for frame in (1, 15, 31):
            bpy.context.scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            expected = box.evaluated_get(depsgraph).matrix_world.translation
            actual = targets[0].evaluated_get(depsgraph).matrix_world.translation
            self.assertLess((actual - expected).length, 1e-6)

    def test_final_contact_groups_static_targets_without_filling_the_gap(self):
        import numpy as np
        from soft_body_render_contact import possible_inside_vertices
        self.box_surface()
        first = bpy.context.object
        second = first.copy()
        bpy.context.collection.objects.link(second)
        second.location.x = 2
        surface = renderer.ObstacleSurface((first, second))
        targets = surface.final_contact_targets()
        self.assertEqual(len(targets), 1)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        candidates = possible_inside_vertices(np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 0, 1]]),
                                             surface.objects, depsgraph)
        self.assertEqual(candidates.tolist(), [True, False, True, False])

    def test_rotating_gear_teeth_do_not_pull_free_skin_up_to_a_corner(self):
        # Exact native frame-60 regression: a sharp tooth's nearest corner
        # used to classify a point 1.8 units below it as inside, teleporting
        # the final smoothed skin even though the physics spine was sound.
        variant = variant_for_seed(910105, "twin-gears")
        renderer.add_obstacle_geometry(self.material, self.material, variant, 60, 30)
        teeth = tuple(obj for obj in bpy.context.scene.objects if " tooth " in obj.name)
        self.assertEqual(len(teeth), 32)
        surface = renderer.ObstacleSurface(teeth)
        x, y, z = -0.23887897, -0.03319658, 1.91055274
        body = renderer.add_mesh("Free skin below gear", [
            (x, y, z), (x + 0.00001, y, z),
            (x + 0.00001, y + 0.00001, z), (x, y + 0.00001, z),
        ], [(0, 1, 2, 3)], self.material)
        renderer.add_final_surface_contact(body, surface.final_contact_targets())
        report = renderer.inspect_rendered_surface(body, surface, 60, 60)
        self.assertEqual(report["issues"], [])
        self.assertLess(report["maximum_correction"], 0.0001,
                        "a body in free fall must not be snapped to a distant gear tooth")

    def test_two_visible_bodies_cannot_pass_through_each_other(self):
        # Genuine overlaps must still fail after the concave-normal fix.
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

    def test_closed_volume_check_handles_holes_and_reversed_face_normals(self):
        from mathutils.bvhtree import BVHTree
        bpy.ops.mesh.primitive_torus_add(major_radius=0.6, minor_radius=0.2,
                                        major_segments=32, minor_segments=16)
        mesh = bpy.context.object.data
        vertices = [vertex.co.copy() for vertex in mesh.vertices]
        for reverse in (False, True):
            faces = [tuple(reversed(face.vertices)) if reverse else tuple(face.vertices) for face in mesh.polygons]
            tree = BVHTree.FromPolygons(vertices, faces)
            self.assertTrue(renderer.point_inside_closed_surface(tree, Vector((0.6, 0.0, 0.0))))
            self.assertFalse(renderer.point_inside_closed_surface(tree, Vector((0.0, 0.0, 0.0))))
            self.assertFalse(renderer.point_inside_closed_surface(tree, Vector((0.75, 0.75, 0.0))))

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

    def test_v_stairs_fifty_percent_visible_bodies_do_not_interpenetrate(self):
        # Production seed 910104 contains 50%, not the 55% used by the old
        # extended audit. Check the complete simultaneous take before any
        # expensive full-subdivision inspection/rendering.
        variant = variant_for_seed(910104, "v-stairs")
        frames, softness, stage = 159, 50, 2
        renderer.add_receiver(self.material, self.material, variant)
        renderer.add_obstacle_geometry(self.material, self.material, variant, frames, 30, ((stage, 1, frames),))
        surface = renderer.ObstacleSurface(bpy.context.collection.objects)
        simulations = renderer.simulate_specimens(softness, frames, 30, variant, stage)
        depths = obstacle_specimen_depth_offsets(variant.obstacle.key)
        objects = []
        for index, offset in enumerate(obstacle_specimen_offsets(variant.obstacle.key)):
            body, _events, quality = renderer.add_capsule(
                self.material, softness, 1, frames, frames, 30, variant, stage,
                index, offset, depths[index], 0.045 if index == 0 else -0.045,
                3, surface, simulations[index],
                tuple((simulation, depths[other]) for other, simulation in enumerate(simulations) if other != index),
            )
            self.assertEqual(quality["issues"], [])
            objects.append(body)
        intersections = renderer.inspect_specimen_intersections(objects, 1, frames)
        self.assertEqual(intersections["issues"], [], intersections)

    def test_parallel_depth_lanes_do_not_collide(self):
        first = {"radius": 0.25, "points": [Vector((0.0, 0.0))]}
        second = {"radius": 0.25, "points": [Vector((0.0, 0.0))]}
        renderer.resolve_specimen_contacts((first, second), (-1.15, 1.15))
        self.assertEqual(tuple(first["points"][0]), (0.0, 0.0))

    def test_extended_audit_includes_actual_seed_percentages(self):
        spec = importlib.util.spec_from_file_location("audit", ROOT / "audit-soft-body-3d.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        stages = variant_for_seed(910104, "v-stairs").stages
        self.assertEqual(stages, (0, 25, 50, 75, 100))
        selected = audit.select_audit_stages(stages, {0, 25, 55, 75, 100}, True)
        self.assertEqual(selected, ((0, 0), (1, 25), (2, 50), (2, 55), (3, 75), (4, 100)))
        self.assertEqual(audit.select_audit_stages(stages), tuple(enumerate(stages)))

    def test_extended_audit_rejects_overlapping_visible_specimens(self):
        spec = importlib.util.spec_from_file_location("audit", ROOT / "audit-soft-body-3d.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        sample = renderer.simulate_chain(0, 0, 30, self.variant, 0)[0]
        # Two deliberately identical bodies: this is invalid regardless of
        # whether both have independently passed the obstacle-only checks.
        report = audit.audit_specimen_contacts(renderer, self.variant, ([sample, sample], [sample, sample]), 0, 0, 30)
        self.assertEqual(report["frames_checked"], 1)
        self.assertTrue(report["issues"], report)

    def test_grid_actual_presets_keep_every_contact_and_body_in_frame(self):
        spec = importlib.util.spec_from_file_location("audit", ROOT / "audit-soft-body-3d.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        for seed, softness, frames, stage in ((910105, 15, 180, 1), (910103, 85, 210, 3)):
            with self.subTest(seed=seed, softness=softness):
                variant = variant_for_seed(seed, "peg-grid")
                simulations = renderer.simulate_specimens(softness, frames, 30, variant, stage)
                for simulation in simulations:
                    self.assertEqual(renderer.simulation_quality(simulation, variant)["issues"], [])
                framing = renderer.inspect_simulation_framing(simulations, variant, 30)
                self.assertEqual(framing["issues"], [], framing)
                contacts = audit.audit_specimen_contacts(renderer, variant, simulations, softness, stage, 30)
                self.assertEqual(contacts["frames_checked"], frames)
                self.assertEqual(contacts["issues"], [], contacts)

    def test_grid_throat_is_solvable_for_every_partly_soft_shape(self):
        left, right = renderer.static_obstacle_circles("peg-grid")[:2]
        opening = right[0].x - left[0].x - left[1] - right[1]
        for shape in SHAPES:
            with self.subTest(shape=shape.key):
                self.assertLess(opening, 2 * shape.radius, "rigid specimens still meet a real obstruction")
                for softness in (0.15, 0.25, 0.45, 0.55, 0.85, 1.0):
                    self.assertGreater(opening, 2 * shape.radius * renderer.obstacle_collision_radius_scale(softness, "peg-grid"))

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

    def test_compression_actual_mid_preset_has_clearance_and_two_stable_attempts(self):
        for seed in (910103, 910104, 910105):
            variant = variant_for_seed(seed, "compression-ring")
            left, right = renderer.obstacle_circles(1.72 / 2, variant)
            opening = right[0].x - left[0].x - left[1] - right[1]
            diameter = 2 * variant.shape.radius * renderer.obstacle_collision_radius_scale(0.45, "compression-ring")
            self.assertGreater(opening, diameter)
            self.assertLess(opening, 2 * variant.shape.radius, "the rollers must still visibly squeeze the body")
        # Exact seed/preset missed by the old 0/25/55/75/100 audit.
        variant = variant_for_seed(910105, "compression-ring")
        for stage in (2, 7):
            with self.subTest(stage=stage):
                simulation = renderer.simulate_chain(45, 108, 30, variant, stage)
                quality = renderer.simulation_quality(simulation, variant)
                self.assertEqual(quality["issues"], [], quality)
                self.assertGreaterEqual(quality["minimum_segment_ratio"], 0.96)
                self.assertLessEqual(quality["maximum_segment_ratio"], 1.04)
                self.assertEqual(renderer.inspect_simulation_framing([simulation], variant, 30)["issues"], [])

    def test_pressure_and_gears_remain_stable_and_visible_at_a_soft_impact(self):
        for obstacle, seed in (("compression-ring", 910104), ("twin-gears", 910105)):
            with self.subTest(obstacle=obstacle):
                variant = variant_for_seed(seed, obstacle)
                simulation = renderer.simulate_chain(75, 115, 30, variant, 3)
                self.assertEqual(renderer.simulation_quality(simulation, variant)["issues"], [])
                self.assertEqual(renderer.inspect_simulation_framing([simulation], variant, 30)["issues"], [])

    def test_rigid_triple_stair_misses_stay_in_the_portrait_composition(self):
        variant = variant_for_seed(910105, "stair-cascade")
        simulations = renderer.simulate_specimens(0, 120, 30, variant, 0)
        self.assertEqual(renderer.inspect_simulation_framing(simulations, variant, 30)["issues"], [])

    def test_daily_stair_final_descent_reaches_the_outlet_before_the_cut(self):
        variant = variant_for_seed(734193085, "stair-cascade")
        simulations = renderer.simulate_specimens(100, 240, 30, variant, 4)
        framing = renderer.inspect_simulation_framing(simulations, variant, 30)
        self.assertEqual(framing["issues"], [], framing)
        self.assertTrue(all(body["observed"] for body in framing["outlet"]["bodies"]))
        for simulation in simulations:
            self.assertEqual(renderer.simulation_quality(simulation, variant)["issues"], [])
        # Same trajectories cut at the old six-second duration: no numerical
        # collision defect, but the slow bodies have not reached the outlet.
        premature = renderer.inspect_simulation_framing([trace[:181] for trace in simulations], variant, 30)
        self.assertIn("unfinished-stair-descent", premature["issues"])

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

    def test_static_v_stairs_motion_does_not_depend_on_the_future_cut(self):
        def prefix(frame_count):
            ticks = renderer._chain_ticks(0, frame_count, 30, self.variant, 0,
                                          obstacle_specimen_offsets("v-stairs")[0], 0.045)
            # Observe exactly four physical seconds in two longer timelines.
            # Stop the generator instead of simulating an irrelevant tail.
            for _ in range(4 * 240):
                state = next(ticks)
            points = [point.copy() for point in state["points"]]
            ticks.close()
            return points

        short, long = prefix(144), prefix(240)
        for first, second in zip(short, long):
            self.assertLess((first - second).length, 1e-6,
                            "a future edit must not change friction on static stairs")

    def test_downward_exit_is_not_confused_with_side_escape_or_teleport(self):
        class Trace(list):
            pass

        rest = 2.0 * self.variant.shape.cylinder_half / 40
        def falling_trace(offset_x=0.0, initial_y=8.0):
            trace = Trace()
            for frame in range(61):
                height = initial_y - frame * 0.8
                trace.append(([Vector((offset_x + (index - 20) * rest, height))
                               for index in range(41)],))
            # Synthetic low-speed physics telemetry isolates the envelope rule.
            trace.physics_samples = [(index / 240, 1.0, 0.0, offset_x, initial_y - index * 0.1)
                                     for index in range(481)]
            return trace

        trace = falling_trace()
        report = renderer.simulation_quality(trace, self.variant)
        self.assertGreater(report["maximum_coordinate"], 25)
        self.assertEqual(report["issues"], [])
        for invalid in (falling_trace(offset_x=26), falling_trace(initial_y=26)):
            self.assertIn("left-scene-before-cut", renderer.simulation_quality(invalid, self.variant)["issues"])
        trace.physics_samples[-1] = (2.0, 1.0, 0.0, 0.0, -100.0)
        self.assertIn("solver-teleport", renderer.simulation_quality(trace, self.variant)["issues"])
        trace = falling_trace()
        trace[1][0][0].x = math.nan
        self.assertIn("non-finite-coordinate", renderer.simulation_quality(trace, self.variant)["issues"])
        trace = falling_trace()
        trace[1][0][10].x += rest * 0.5
        self.assertIn("constraint-tear", renderer.simulation_quality(trace, self.variant)["issues"])

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
