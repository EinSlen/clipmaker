"""Fast deterministic tests for every procedural game engine."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import re
import tempfile
import unittest
import wave
from pathlib import Path

from game_variants import (
    GAME_CLASSES,
    SOCIAL_FOOTER_CENTER_Y,
    SOCIAL_HOOK_CENTER_Y,
    SOCIAL_RESULT_CENTER_Y,
)
from soft_body_variants import (
    AIR_RETENTION_PER_SECOND,
    PHYSICS_HZ,
    AUTO_OBSTACLE_KEYS,
    OBSTACLES,
    SHAPES,
    deformation_response,
    natural_ramp_exit_time,
    obstacle_collision_radius_scale,
    obstacle_drag_retention_per_second,
    obstacle_specimen_depth_offsets,
    obstacle_specimen_offsets,
    ramp_motion_state,
    solver_timing,
    stage_attempt_frame_spans,
    stage_frame_spans,
    stage_motion_for,
    stage_selection_for,
    supported_body_damping,
    variant_for_seed,
)
from soft_body_framing import inspect_simulation_framing
ROOT = Path(__file__).resolve().parents[1]
PREMIUM_IDS = ("soft-body-slide",)
ENGINE_IDS = ("ball-escape", *GAME_CLASSES)
RENDERER_PATH = Path(__file__).with_name("render-ball-escape.py")
RENDERER_SPEC = importlib.util.spec_from_file_location("render_ball_escape", RENDERER_PATH)
assert RENDERER_SPEC and RENDERER_SPEC.loader
RENDERER = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(RENDERER)
BallEscape = RENDERER.BallEscape
PREMIUM_RENDERER_PATH = Path(__file__).with_name("render-premium-3d.py")
PREMIUM_RENDERER_SPEC = importlib.util.spec_from_file_location(
    "render_premium_3d", PREMIUM_RENDERER_PATH
)
assert PREMIUM_RENDERER_SPEC and PREMIUM_RENDERER_SPEC.loader
PREMIUM_RENDERER = importlib.util.module_from_spec(PREMIUM_RENDERER_SPEC)
PREMIUM_RENDERER_SPEC.loader.exec_module(PREMIUM_RENDERER)
FINALIZER_PATH = Path(__file__).with_name("finalize-premium-3d.py")
FINALIZER_SPEC = importlib.util.spec_from_file_location(
    "finalize_premium_3d", FINALIZER_PATH
)
assert FINALIZER_SPEC and FINALIZER_SPEC.loader
FINALIZER = importlib.util.module_from_spec(FINALIZER_SPEC)
FINALIZER_SPEC.loader.exec_module(FINALIZER)


def build(game_id: str, seed: int = 424242):
    difficulty = 24 if game_id == "laser-dodge" else 48
    arguments = (270, 480, 12, 5.0, difficulty, seed, "neon", "CAN IT FINISH?")
    if game_id == "ball-escape":
        return BallEscape(*arguments)
    return GAME_CLASSES[game_id](*arguments)


def run_ball_escape(*, seed: int, fps: int, duration: float = 10.0, rings: int = 8, until: float | None = None):
    game = BallEscape(270, 480, fps, duration, rings, seed, "neon", "WILL IT ESCAPE?")
    end_time = duration if until is None else until
    for frame_index in range(round(end_time * fps) + 1):
        game.update(min(end_time, frame_index / fps))
    # Exercise the exact same timestamp for render rates that do not divide it.
    game.update(end_time)
    return game


def run_shape_tunnel(*, seed: int, fps: int, duration: float = 15.0, layers: int = 200):
    game = GAME_CLASSES["shape-tunnel"](
        270, 480, fps, duration, layers, seed, "neon", "WILL IT ESCAPE?"
    )
    for frame_index in range(round(duration * fps) + 1):
        game.update(min(duration, frame_index / fps))
    game.update(duration)
    return game


class GameCatalogTests(unittest.TestCase):
    def test_frontend_catalog_matches_python_engines(self):
        source = (ROOT / "src" / "lib" / "game-catalog.ts").read_text(encoding="utf-8")
        catalog_ids = tuple(re.findall(r"\bid:\s*['\"]([a-z-]+)['\"]", source))
        self.assertEqual(catalog_ids, (*ENGINE_IDS, *PREMIUM_IDS))
        self.assertEqual(len(catalog_ids), len(set(catalog_ids)))


class SocialLayoutRegressionTests(unittest.TestCase):
    def test_all_2d_hooks_and_payoffs_use_the_shared_safe_zone_contract(self):
        # Use the largest 2D hook font as a conservative bounding box.  Its top
        # remains comfortably below the first 8% of a native vertical frame.
        largest_hook_height = 1080 * 0.055
        hook_top = SOCIAL_HOOK_CENTER_Y - largest_hook_height / (2.0 * 1920)
        self.assertGreaterEqual(hook_top, 0.08)
        self.assertLessEqual(SOCIAL_RESULT_CENTER_Y, 0.82)
        self.assertLessEqual(SOCIAL_FOOTER_CENTER_Y, 0.88)

        variant_source = (ROOT / "scripts" / "game_variants.py").read_text(encoding="utf-8")
        renderer_source = RENDERER_PATH.read_text(encoding="utf-8")
        # Base/Organic/Laser/Boss share the same hook coordinate, while Ball
        # imports and uses it from the renderer module.
        self.assertGreaterEqual(
            variant_source.count("self.height * SOCIAL_HOOK_CENTER_Y"),
            4,
        )
        self.assertIn("self.height * SOCIAL_HOOK_CENTER_Y", renderer_source)
        self.assertGreaterEqual(
            variant_source.count("self.height * SOCIAL_RESULT_CENTER_Y"),
            3,
        )
        self.assertGreaterEqual(
            variant_source.count("self.height * SOCIAL_FOOTER_CENTER_Y"),
            3,
        )


class SoftBodyVariantTests(unittest.TestCase):
    def test_requested_preview_softness_is_exact_even_between_presets(self):
        variant = variant_for_seed(910105, "moving-slide")
        self.assertNotIn(55, variant.stages)
        self.assertEqual(stage_selection_for(variant, 55), ((55,), (2,)))
        self.assertEqual(stage_selection_for(variant), (variant.stages, (0, 1, 2, 3, 4)))
        for invalid in (-1, 101, 55.5):
            with self.assertRaises(ValueError):
                stage_selection_for(variant, invalid)

    def test_framing_blocks_sustained_side_exits_and_empty_comparisons(self):
        variant = variant_for_seed(910103, "moving-slide")
        def frames(position, count=61):
            return [([position],)] * count
        visible = frames((0.0, 3.0))
        self.assertEqual(inspect_simulation_framing([visible], variant, 30)["issues"], [])
        sideways = inspect_simulation_framing([frames((-20.0, 3.0))], variant, 30)
        self.assertIn("body-left-camera-side", sideways["issues"])
        self.assertIn("empty-comparison-tail", sideways["issues"])
        lower_exit = frames((0.0, 3.0), 45) + frames((0.0, -20.0), 16)
        self.assertEqual(inspect_simulation_framing([lower_exit], variant, 30)["issues"], [])
        self.assertIn("empty-comparison-tail", inspect_simulation_framing(
            [frames((0.0, -20.0))], variant, 30)["issues"])

    def test_framing_keeps_a_multi_body_take_while_a_specimen_finishes(self):
        variant = variant_for_seed(910103, "v-stairs")
        visible = [([(0.0, 3.0)],)] * 61
        finished = [([(0.0, -20.0)],)] * 61
        report = inspect_simulation_framing([visible, finished], variant, 30)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["frames_checked"], 60)
        with self.assertRaises(ValueError):
            inspect_simulation_framing([visible], variant, 30)
        with self.assertRaises(ValueError):
            inspect_simulation_framing([visible, finished[:-1]], variant, 30)

    def test_obstacle_attempt_spans_cover_every_frame_without_empty_tails(self):
        for obstacle in OBSTACLES:
            for softness in (0, 25, 50, 75, 100):
                spans = stage_attempt_frame_spans(101, 330, 30, obstacle.key, softness)
                self.assertEqual(spans[0][0], 101)
                self.assertEqual(spans[-1][1], 330)
                for previous, following in zip(spans, spans[1:]):
                    self.assertEqual(previous[1] + 1, following[0])
                self.assertTrue(all(end >= start for start, end in spans))
                self.assertGreaterEqual(spans[-1][1] - spans[-1][0] + 1, 27)

    def test_multi_body_references_use_their_observed_stage_rhythm(self):
        for obstacle in ("stair-cascade", "v-stairs", "peg-grid"):
            spans = stage_frame_spans(900, 5, obstacle)
            self.assertEqual(
                tuple(end - start + 1 for start, end in spans),
                (120, 180, 210, 210, 180),
            )

    def test_minimum_preview_gives_every_stage_a_visible_frame(self):
        for count in range(5, 25):
            for obstacle in (None, "peg-grid"):
                spans = stage_frame_spans(count, 5, obstacle)
                self.assertTrue(all(start <= end for start, end in spans))
                self.assertEqual(sum(end - start + 1 for start, end in spans), count)

    def test_multi_body_labels_and_cut_repairs_use_the_same_clock(self):
        value = PREMIUM_RENDERER.build_video_filter(30.0, (0, 25, 55, 75, 100), "peg-grid")
        self.assertIn("10.000", value)
        self.assertIn("17.000", value)
        with tempfile.TemporaryDirectory() as directory:
            frames = Path(directory)
            for boundary in (121, 301, 511, 721):
                for index in (boundary, boundary + 1):
                    (frames / f"frame_{index:04d}.png").write_bytes(str(index).encode())
            self.assertEqual(PREMIUM_RENDERER.repair_stage_cut_frames(frames, 900, 5, (), "peg-grid"), (121, 301, 511, 721))

    def test_native_preflight_requires_every_body_and_rejects_failed_surfaces(self):
        variant = variant_for_seed(910103, "v-stairs")
        quality = []
        for stage, (softness, (start, end)) in enumerate(zip(variant.stages, stage_frame_spans(900, 5, "v-stairs")), start=1):
            for body in (1, 2):
                quality.append({"stage": stage, "softness": softness, "attempt": 1, "body": body,
                    "start_frame": start, "end_frame": end, "issues": [], "surface": {"inside_contacts": 0},
                    "framing": {"frames_checked": end - start + 1, "maximum_empty_seconds": 0,
                                "maximum_side_exit_seconds": 0, "issues": []},
                    "inter_body_contact": {"issues": [], "frames_checked": end - start + 1}})
        payload = {"preflight_schema": 3, "obstacle": "v-stairs", "stages": list(variant.stages),
            "fps": 30, "duration": 30, "attempt_quality": quality}
        self.assertEqual(PREMIUM_RENDERER.validate_motion_preflight(payload, variant, 900, 30), quality)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            PREMIUM_RENDERER.validate_motion_preflight({**payload, "attempt_quality": quality[:-1]}, variant, 900, 30)
        with self.assertRaisesRegex(ValueError, "surface"):
            PREMIUM_RENDERER.validate_motion_preflight({**payload, "attempt_quality": [{**quality[0], "surface": {"inside_contacts": 1}}, *quality[1:]]}, variant, 900, 30)
        with self.assertRaisesRegex(ValueError, "Missing"):
            PREMIUM_RENDERER.validate_motion_preflight({}, variant, 900, 30)
        with self.assertRaisesRegex(ValueError, "Missing"):
            PREMIUM_RENDERER.validate_motion_preflight({**payload, "preflight_schema": 2}, variant, 900, 30)
        for invalid in (None, {"issues": [], "frames_checked": 120},
                        {"issues": [], "frames_checked": 120, "maximum_empty_seconds": 1.5, "maximum_side_exit_seconds": 0}):
            with self.assertRaisesRegex(ValueError, "framing"):
                PREMIUM_RENDERER.validate_motion_preflight({**payload,
                    "attempt_quality": [{**quality[0], "framing": invalid}, *quality[1:]]}, variant, 900, 30)

    def test_fast_obstacles_repeat_during_long_levels(self):
        for obstacle in ("moving-slide", "pipe-bend", "twin-gears", "compression-ring"):
            self.assertGreater(
                len(stage_attempt_frame_spans(1, 230, 30, obstacle, 100)),
                1,
            )

    def test_obstacle_receivers_remain_inside_the_vertical_camera(self):
        for obstacle in OBSTACLES:
            variant = variant_for_seed(910104, obstacle.key)
            half_width = obstacle.camera_scale * (1080 / 1920) * 0.5
            self.assertLessEqual(
                abs(variant.receiver.x - obstacle.camera_target_x)
                + variant.receiver.outer_radius,
                half_width,
                obstacle.key,
            )

    def test_peg_payoff_and_pipe_resets_have_enough_physical_time(self):
        peg_quarter = stage_attempt_frame_spans(1, 115, 30, "peg-grid", 25)
        self.assertGreaterEqual((peg_quarter[0][1] - peg_quarter[0][0] + 1) / 30, 3.8)
        peg_soft = stage_attempt_frame_spans(1, 206, 30, "peg-grid", 100)
        self.assertEqual(peg_soft, ((1, 206),))
        pipe = stage_attempt_frame_spans(1, 206, 30, "pipe-bend", 100)
        self.assertGreater(len(pipe), 1)
        self.assertGreaterEqual(min((end - start + 1) / 30 for start, end in pipe), 3.0)
        self.assertLessEqual(max((end - start + 1) / 30 for start, end in pipe), 3.7)

    def test_same_seed_resolves_to_same_variant(self):
        self.assertEqual(variant_for_seed(424242), variant_for_seed(424242))

    def test_adjacent_batch_seeds_change_all_major_visual_axes(self):
        variants = [variant_for_seed(seed) for seed in range(910100, 910105)]
        self.assertEqual(len({variant.key for variant in variants}), len(variants))
        for previous, current in zip(variants, variants[1:]):
            self.assertNotEqual(previous.shape.key, current.shape.key)
            self.assertNotEqual(previous.ramp.key, current.ramp.key)
            self.assertNotEqual(previous.palette.key, current.palette.key)

    def test_every_variant_keeps_clear_rigid_and_soft_extremes(self):
        for seed in range(1000, 1200):
            stages = variant_for_seed(seed).stages
            self.assertEqual(len(stages), 5)
            self.assertEqual(stages[0], 0)
            self.assertEqual(stages[-1], 100)
            self.assertEqual(tuple(sorted(stages)), stages)

    def test_variant_catalog_has_at_least_2500_discrete_combinations(self):
        keys = {variant_for_seed(seed).key for seed in range(10_000)}
        self.assertGreaterEqual(len(keys), 2_500)

    def test_every_obstacle_family_can_be_forced_and_is_reported(self):
        for obstacle in OBSTACLES:
            variant = variant_for_seed(910104, obstacle.key)
            self.assertEqual(variant.obstacle, obstacle)
            self.assertIn(obstacle.key, variant.key)
            self.assertEqual(variant.receiver.x, obstacle.receiver_x)

    def test_automatic_obstacles_cover_only_reference_matched_scenes(self):
        resolved = {variant_for_seed(seed).obstacle.key for seed in range(10_000, 10_500)}
        self.assertEqual(resolved, set(AUTO_OBSTACLE_KEYS))
        self.assertTrue(
            {"pipe-bend", "twin-gears", "compression-ring"}.isdisjoint(resolved)
        )

    def test_capsule_presets_remain_slender_and_reference_scaled(self):
        for shape in SHAPES:
            total_length = 2.0 * (shape.cylinder_half + shape.radius)
            diameter = 2.0 * shape.radius
            self.assertGreaterEqual(total_length / diameter, 3.75, shape.key)
            self.assertLessEqual(total_length / diameter, 4.35, shape.key)
            self.assertLessEqual(total_length, 1.95, shape.key)

    def test_native_filter_does_not_amplify_render_artifacts(self):
        value = PREMIUM_RENDERER.build_video_filter(15.0, (0, 25, 50, 75, 100))
        self.assertNotIn("unsharp", value)
        self.assertNotIn("scale=", value)

    def test_softness_response_starts_at_25_and_reserves_crumpling_for_high_stages(self):
        responses = [
            deformation_response(level / 100.0)
            for level in (0, 25, 50, 75, 100)
        ]
        for axis in range(3):
            values = [response[axis] for response in responses]
            self.assertEqual(values, sorted(values))
        self.assertEqual(responses[0], (0.0, 0.0, 0.0))
        self.assertGreater(responses[1][2], 0.0)
        self.assertLess(responses[1][2], responses[2][2] * 0.35)
        self.assertGreater(responses[2][2], 0.0)
        self.assertGreater(responses[4][2] - responses[3][2], 0.30)

    def test_peg_grid_releases_two_bodies_and_matches_softness_thresholds(self):
        self.assertEqual(obstacle_specimen_offsets("peg-grid"), (-0.64, 0.64))
        self.assertEqual(obstacle_specimen_offsets("stair-cascade"), (-0.18, 0.0, 0.18))
        self.assertEqual(obstacle_specimen_depth_offsets("stair-cascade"), (-1.15, 0.0, 1.15))
        self.assertEqual(obstacle_specimen_offsets("v-stairs"), (0.0, 5.50))
        for obstacle in OBSTACLES:
            if obstacle.key not in {"peg-grid", "stair-cascade", "v-stairs"}:
                self.assertEqual(obstacle_specimen_offsets(obstacle.key), (0.0,))
            self.assertEqual(
                len(obstacle_specimen_depth_offsets(obstacle.key)),
                len(obstacle_specimen_offsets(obstacle.key)),
            )
        shape = max(SHAPES, key=lambda item: item.radius)
        peg_spacing = 0.64
        peg_radius = 0.115
        opening = peg_spacing - 2.0 * peg_radius
        rigid_diameter = 2.0 * shape.radius * obstacle_collision_radius_scale(0.0, "peg-grid")
        quarter_soft_diameter = 2.0 * shape.radius * obstacle_collision_radius_scale(0.25, "peg-grid")
        half_soft_diameter = 2.0 * shape.radius * obstacle_collision_radius_scale(0.50, "peg-grid")
        self.assertGreater(rigid_diameter, opening)
        self.assertGreater(quarter_soft_diameter, opening)
        self.assertLess(quarter_soft_diameter - opening, rigid_diameter - opening)
        self.assertLess(half_soft_diameter, opening)

    def test_peg_grid_uses_one_complete_take_with_two_bodies(self):
        quarter = stage_attempt_frame_spans(1, 115, 30, "peg-grid", 25)
        half = stage_attempt_frame_spans(1, 216, 30, "peg-grid", 50)
        self.assertEqual(quarter, ((1, 115),))
        self.assertEqual(half, ((1, 216),))
        self.assertEqual(len(obstacle_specimen_offsets("peg-grid")), 2)

    def test_long_middle_levels_repeat_without_incomplete_remainders(self):
        for obstacle in OBSTACLES:
            spans = stage_attempt_frame_spans(1, 216, 30, obstacle.key, 55)
            visible_tests = len(spans) * len(obstacle_specimen_offsets(obstacle.key))
            self.assertGreaterEqual(visible_tests, 2, obstacle.key)
            durations = [(end - start + 1) / 30 for start, end in spans]
            self.assertGreaterEqual(min(durations), 3.0, obstacle.key)
            if len(spans) > 1:
                self.assertLessEqual(max(durations) - min(durations), 1 / 30, obstacle.key)

    def test_peg_grid_friction_holds_25_percent_but_releases_50_percent(self):
        quarter = obstacle_drag_retention_per_second(0.25, "peg-grid")
        self.assertGreater(quarter, 0.0)
        self.assertLess(quarter, 1e-3)
        self.assertEqual(obstacle_drag_retention_per_second(0.50, "peg-grid"), 1.0)
        self.assertEqual(obstacle_drag_retention_per_second(0.25, "moving-slide"), 1.0)

    def test_soft_body_solver_clock_is_render_fps_independent(self):
        expected_internal = 0.70 - 0.18
        expected_supported_horizontal = 0.990 ** 60.0
        expected_supported_vertical = (0.998 - 0.001) ** 60.0
        for fps in (3, 24, 30, 60):
            substeps, dt, internal, air_drag = solver_timing(fps, 1.0)
            supported_horizontal, supported_vertical = supported_body_damping(fps, 1.0)
            steps_per_second = fps * substeps
            self.assertAlmostEqual(dt * steps_per_second, 1.0, places=12)
            self.assertAlmostEqual(internal ** steps_per_second, expected_internal, places=12)
            self.assertAlmostEqual(
                air_drag ** steps_per_second,
                AIR_RETENTION_PER_SECOND,
                places=12,
            )
            self.assertAlmostEqual(
                supported_horizontal ** steps_per_second,
                expected_supported_horizontal,
                places=12,
            )
            self.assertAlmostEqual(
                supported_vertical ** steps_per_second,
                expected_supported_vertical,
                places=12,
            )
            if fps in (3, 30):
                self.assertEqual(steps_per_second, PHYSICS_HZ)

    def test_ramp_sweep_remains_periodic_for_the_complete_trial(self):
        variant = variant_for_seed(910104)
        for stage_index in range(5):
            phase = stage_motion_for(variant, stage_index).ramp_phase_offset
            period = variant.ramp.sweep_period
            for sample in (0.0, 0.37, 1.13, 4.72):
                first = ramp_motion_state(sample, variant, 6.0, phase)
                repeated = ramp_motion_state(sample + period, variant, 6.0, phase)
                self.assertAlmostEqual(first[0], repeated[0], places=10)
                self.assertAlmostEqual(first[1], repeated[1], places=10)

    def test_stage_motion_is_seeded_and_only_a_micro_variation(self):
        variant = variant_for_seed(910104)
        motions = [stage_motion_for(variant, index) for index in range(5)]
        self.assertEqual(motions, [stage_motion_for(variant, index) for index in range(5)])
        self.assertEqual(len(set(motions)), 5)
        for motion in motions:
            self.assertLessEqual(abs(motion.spawn_x_offset), 0.045)
            self.assertLessEqual(abs(motion.rotation_offset), 0.030)
            self.assertLessEqual(abs(motion.linear_velocity_x), 0.028)
            self.assertLessEqual(abs(motion.ramp_phase_offset), 0.012)

    def test_render_level_release_motion_is_neutral_and_nonzero(self):
        for seed in range(910100, 910125):
            variant = variant_for_seed(seed)
            if variant.obstacle.key in {"v-stairs", "pipe-bend", "peg-grid", "twin-gears", "compression-ring"}:
                self.assertGreater(variant.start_rotation, 1.40)
                self.assertLess(variant.start_rotation, 1.75)
            else:
                self.assertGreaterEqual(abs(variant.start_rotation), 0.10)
                self.assertLessEqual(abs(variant.start_rotation), 0.24)
            self.assertGreaterEqual(abs(variant.initial_spin), 0.20)
            self.assertLessEqual(abs(variant.initial_spin), 0.34)
            self.assertEqual(
                math.copysign(1.0, variant.start_rotation),
                math.copysign(1.0, variant.initial_spin),
            )

    def test_soft_body_has_no_receiver_steering_or_hidden_bowl(self):
        source = (Path(__file__).with_name("blender-soft-body-slide.py")).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("receiver.x - points", source)
        self.assertNotIn("receiver.x - point", source)
        self.assertNotIn("Concave receiver interior", source)
        self.assertNotIn("fall_boost", source)
        self.assertNotIn("max_horizontal_step", source)
        self.assertIn('"kind": "receiver-entry"', source)

    def test_soft_body_publication_has_a_real_physics_preflight(self):
        source = (Path(__file__).with_name("blender-soft-body-slide.py")).read_text(
            encoding="utf-8"
        )
        self.assertIn("def simulation_quality(", source)
        self.assertIn('"missed-obstacle"', source)
        self.assertIn('"constraint-tear"', source)
        self.assertIn('"solver-teleport"', source)
        self.assertIn("Soft-body publication preflight failed", source)

    def test_soft_body_foley_timestamps_use_fixed_physics_samples(self):
        # Extract only the pure event reducer: importing the complete renderer
        # outside Blender would require bpy/mathutils. Synthetic 240 Hz samples
        # prove that render-frame sampling cannot move the exported timestamps.
        import ast

        source = Path(__file__).with_name("blender-soft-body-slide.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "contact_events"
        )
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        namespace = {"math": math, "SoftBodyVariant": object}
        exec(compile(module, "<soft-body-contact-events>", "exec"), namespace)
        reduce_events = namespace["contact_events"]

        class PhysicsTrace(list):
            pass

        physics_dt = 1.0 / 240.0
        physics_samples = []
        for step in range(1, 6 * 240 + 1):
            physics_samples.append(
                (
                    step * physics_dt,
                    0.82 if step == 168 else 0.0,
                    0.76 if step == 480 else 0.0,
                    -0.25,
                )
            )

        signatures = []
        for fps in (3, 30):
            simulated = PhysicsTrace([None] * (6 * fps + 1))
            simulated.physics_dt = physics_dt
            simulated.physics_samples = physics_samples
            simulated.receiver_entries = ((4.0, 2.2, -0.20),)
            events = reduce_events(simulated, 100, 1, fps, None)
            signatures.append(
                tuple((event["kind"], event["time"]) for event in events)
            )

        self.assertEqual(signatures[0], signatures[1])
        self.assertEqual(
            signatures[0],
            (
                ("ramp-contact", 0.7),
                ("receiver-contact", 2.0),
                ("receiver-entry", 4.0),
            ),
        )


class SoftBodyAudioTests(unittest.TestCase):
    def test_premium_renderer_exposes_a_decisive_soft_body_outcome(self):
        source = PREMIUM_RENDERER_PATH.read_text(encoding="utf-8")
        self.assertIn('"completed_at": args.duration', source)
        self.assertIn('"outcome": "comparison-complete"', source)

    def test_missing_collision_telemetry_never_invents_foley(self):
        self.assertFalse(hasattr(PREMIUM_RENDERER, "fallback_foley_events"))
        source = PREMIUM_RENDERER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("timeline-fallback", source)
        self.assertIn('event_source = "no-physical-events"', source)

    def test_stage_boundaries_are_replaced_with_clean_visible_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = Path(directory)
            for frame in range(1, 181):
                (frames / f"frame_{frame:04d}.png").write_bytes(str(frame).encode("ascii"))
            repaired = PREMIUM_RENDERER.repair_stage_cut_frames(
                frames, 180, 5, (70, 120)
            )
            self.assertEqual(repaired, (28, 51, 70, 94, 120, 140))
            for boundary in repaired:
                self.assertEqual(
                    (frames / f"frame_{boundary:04d}.png").read_bytes(),
                    str(boundary + 1).encode("ascii"),
                )
            self.assertEqual((frames / "frame_0036.png").read_bytes(), b"36")

    def test_cut_repairs_never_modify_the_immutable_source_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for frame in range(1, 181):
                (source / f"frame_{frame:04d}.png").write_bytes(
                    str(frame).encode("ascii")
                )
            staged = root / "staged"
            FINALIZER.stage_frame_sequence(source, staged, 180)
            repaired = PREMIUM_RENDERER.repair_stage_cut_frames(
                staged, 180, 5, (70, 120)
            )
            self.assertEqual(repaired, (28, 51, 70, 94, 120, 140))
            for boundary in repaired:
                self.assertEqual(
                    (source / f"frame_{boundary:04d}.png").read_bytes(),
                    str(boundary).encode("ascii"),
                )
                self.assertEqual(
                    (staged / f"frame_{boundary:04d}.png").read_bytes(),
                    str(boundary + 1).encode("ascii"),
                )

    def test_generated_bed_is_seeded_stereo_and_platform_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.wav"
            second = Path(directory) / "second.wav"
            PREMIUM_RENDERER.synth_soft_body_bed(0.25, first, 910104)
            PREMIUM_RENDERER.synth_soft_body_bed(0.25, second, 910104)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with wave.open(str(first), "rb") as source:
                self.assertEqual(source.getnchannels(), 2)
                self.assertEqual(source.getframerate(), 48_000)
                self.assertGreater(source.getnframes(), 10_000)
        audio_filter = PREMIUM_RENDERER.build_continuous_audio_filter(0.58)
        self.assertIn("sidechaincompress", audio_filter)
        self.assertIn("loudnorm=I=-20:TP=-1.5:LRA=10", audio_filter)


class GameEngineTests(unittest.TestCase):
    def test_every_engine_renders_and_completes(self):
        for game_id in ENGINE_IDS:
            with self.subTest(game=game_id):
                game = build(game_id)
                frames = []
                for frame_index in range(55):
                    time_sec = frame_index / 12
                    game.update(time_sec)
                    if frame_index in (0, 12, 30, 54):
                        frames.append(game.frame(time_sec))
                for frame in frames:
                    self.assertEqual(frame.size, (270, 480))
                    self.assertEqual(frame.mode, "RGB")
                expected_total = game.total if hasattr(game, "total") else game.ring_count
                if game_id in ("ball-escape", "shape-tunnel", "laser-dodge", "boss-battle"):
                    # Physical runs are allowed to fall short naturally.
                    self.assertGreaterEqual(game.active, 0)
                else:
                    self.assertGreater(game.active, 0)
                self.assertLessEqual(game.active, expected_total)
                if game_id not in ("ball-escape", "shape-tunnel", "laser-dodge", "boss-battle"):
                    self.assertEqual(game.active, expected_total)
                if game_id not in ("ball-escape", "shape-tunnel"):
                    self.assertIsNotNone(game.completed_at)
                self.assertGreater(len(game.events), 0)
                self.assertGreater(len(game.music_hits), 0)
                self.assertGreaterEqual(game.max_speed_ratio, 1.0)

    def test_every_engine_is_deterministic(self):
        for game_id in ENGINE_IDS:
            with self.subTest(game=game_id):
                digests = []
                for _ in range(2):
                    game = build(game_id, seed=987654)
                    for time_sec in (0.0, 0.75, 1.5, 2.25):
                        game.update(time_sec)
                    frame = game.frame(2.25)
                    digests.append(hashlib.sha256(frame.tobytes()).hexdigest())
                self.assertEqual(digests[0], digests[1])

    def test_seeds_produce_visual_variation(self):
        for game_id in ENGINE_IDS:
            with self.subTest(game=game_id):
                digests = []
                for seed in (111111, 222222):
                    game = build(game_id, seed=seed)
                    game.update(2.25)
                    digests.append(hashlib.sha256(game.frame(2.25).tobytes()).hexdigest())
                self.assertNotEqual(digests[0], digests[1])


class ShapeTunnelRegressionTests(unittest.TestCase):
    def test_fixed_timestep_is_independent_from_render_fps(self):
        states = []
        for fps in (12, 15, 24, 30, 60):
            game = run_shape_tunnel(seed=8, fps=fps, duration=5.0, layers=48)
            states.append({
                "active": game.active,
                "completed_at": game.completed_at,
                "position": tuple(game.position),
                "velocity": tuple(game.velocity),
                "events": tuple(game.events),
                "contacts": tuple(game.contact_history),
                "frame": hashlib.sha256(game.frame(5.0).tobytes()).hexdigest(),
            })
        self.assertTrue(all(state == states[0] for state in states[1:]))

    def test_free_flight_contains_only_velocity_and_gravity(self):
        game = GAME_CLASSES["shape-tunnel"](
            270, 480, 30, 5.0, 48, 424242, "neon", "WILL IT ESCAPE?"
        )
        initial_position = tuple(game.position)
        initial_velocity = tuple(game.velocity)
        # Isolate free flight. Shape phase, openings, or future contact points
        # cannot influence this trajectory because no boundary can be reached.
        game.boundary_radius = lambda progress, angle, time_sec=0.0: 10_000.0
        elapsed = 0.5
        game.update(elapsed)
        self.assertAlmostEqual(game.position[0], initial_position[0] + initial_velocity[0] * elapsed, places=8)
        self.assertAlmostEqual(game.velocity[0], initial_velocity[0], places=8)
        self.assertAlmostEqual(game.velocity[1], initial_velocity[1] + game.gravity * elapsed, places=8)
        self.assertEqual(game.active, 0)
        self.assertEqual(game.contact_history, [])

    def test_every_layer_change_is_backed_by_a_geometric_contact(self):
        for seed in (0, 8, 424242):
            with self.subTest(seed=seed):
                game = run_shape_tunnel(seed=seed, fps=30, duration=5.0, layers=48)
                self.assertGreater(len(game.contact_history), 0)
                self.assertEqual(sum(contact[6] for contact in game.contact_history), game.active)
                self.assertFalse(hasattr(game, "hit_times"))
                self.assertFalse(hasattr(game, "hit_angles"))
                self.assertFalse(hasattr(game, "contact_point"))
                for time_sec, x, y, nx, ny, speed, damage, progress in game.contact_history:
                    angle = math.atan2(y - game.cy, x - game.cx)
                    radius = math.hypot(x - game.cx, y - game.cy)
                    boundary = game.boundary_radius(progress, angle, time_sec)
                    self.assertLess(abs(radius - boundary), game.width * 0.012)
                    self.assertAlmostEqual(math.hypot(nx, ny), 1.0, places=10)
                    self.assertGreater(speed, 0.0)
                    self.assertGreaterEqual(damage, 1)

    def test_catalog_physics_produces_natural_success_and_failure(self):
        winner = run_shape_tunnel(seed=8, fps=30)
        failure = run_shape_tunnel(seed=0, fps=30)

        self.assertEqual(winner.active, winner.total)
        self.assertIsNotNone(winner.completed_at)
        self.assertGreaterEqual(winner.completed_at, winner.duration * 0.65)

        self.assertGreater(failure.active, failure.total * 0.75)
        self.assertLess(failure.active, failure.total)
        self.assertIsNone(failure.completed_at)

    def test_timeout_is_irreversible_and_exposes_an_explicit_payoff(self):
        game = GAME_CLASSES["shape-tunnel"](
            270, 480, 30, 15.0, 200, 0, "neon", "WILL IT ESCAPE?"
        )
        game.update(game.gameplay_deadline + 0.1)

        self.assertEqual(game.failed_at, game.gameplay_deadline)
        self.assertIsNone(game.completed_at)
        self.assertEqual(
            game.outcome_lines(),
            ("TIME'S UP!", f"{game.total - game.active} LAYERS LEFT"),
        )
        frozen_state = {
            "active": game.active,
            "position": tuple(game.position),
            "velocity": tuple(game.velocity),
            "contacts": tuple(game.contact_history),
            "events": tuple(game.events),
        }

        game.update(game.duration)

        self.assertEqual(game.failed_at, game.gameplay_deadline)
        self.assertIsNone(game.completed_at)
        self.assertEqual(game.active, frozen_state["active"])
        self.assertEqual(tuple(game.position), frozen_state["position"])
        self.assertEqual(tuple(game.velocity), frozen_state["velocity"])
        self.assertEqual(tuple(game.contact_history), frozen_state["contacts"])
        self.assertEqual(tuple(game.events), frozen_state["events"])


class LaserDodgeRegressionTests(unittest.TestCase):
    def make_game(self, seed: int, fps: int = 30):
        return GAME_CLASSES["laser-dodge"](
            270, 480, fps, 10.0, 24, seed, "neon", "CAN IT DODGE EVERY LASER?"
        )

    def run_game(self, seed: int, fps: int = 30):
        game = self.make_game(seed, fps)
        for frame_index in range(round(game.duration * fps) + 1):
            game.update(min(game.duration, frame_index / fps))
        game.update(game.duration)
        return game

    def test_laser_world_is_identical_for_different_controllers(self):
        engine = GAME_CLASSES["laser-dodge"]

        class PassiveRunner(engine):
            def _choose_acceleration(self, time_sec, position, velocity, previous_acceleration):
                return 0.0, 0.0

        active = self.make_game(33)
        passive = PassiveRunner(
            270, 480, 30, 10.0, 24, 33, "neon", "CAN IT DODGE EVERY LASER?"
        )
        self.assertEqual(active.event_times, passive.event_times)
        self.assertEqual(active.lasers, passive.lasers)
        self.assertNotEqual(active.trajectory, passive.trajectory)
        self.assertFalse(hasattr(active, "waypoints"))
        self.assertFalse(hasattr(active, "failure_index"))
        self.assertEqual(active.total, active.event_count)
        self.assertEqual(active.total, 24)

    def test_fixed_physics_is_independent_from_render_fps(self):
        states = []
        for fps in (8, 12, 30, 60):
            game = self.make_game(33, fps)
            states.append({
                "lasers": game.lasers,
                "trajectory": game.trajectory,
                "velocities": game.velocity_history,
                "accelerations": game.acceleration_history,
                "collision_time": game.simulated_collision_time,
                "collision_index": game.simulated_collision_index,
            })
        self.assertTrue(all(state == states[0] for state in states[1:]))

    def test_runner_respects_position_velocity_and_acceleration_limits(self):
        game = self.make_game(0)
        x_low = game.arena[0] + game.runner_radius
        x_high = game.arena[2] - game.runner_radius
        y_low = game.arena[1] + game.runner_radius
        y_high = game.arena[3] - game.runner_radius
        for position, velocity, acceleration in zip(
            game.trajectory, game.velocity_history, game.acceleration_history
        ):
            self.assertGreaterEqual(position[0], x_low - 1e-9)
            self.assertLessEqual(position[0], x_high + 1e-9)
            self.assertGreaterEqual(position[1], y_low - 1e-9)
            self.assertLessEqual(position[1], y_high + 1e-9)
            self.assertLessEqual(math.hypot(*velocity), game.max_speed + 1e-9)
            self.assertLessEqual(math.hypot(*acceleration), game.max_acceleration + 1e-9)
        self.assertLessEqual(game.reaction_horizon, 0.30)
        measured_ratio = max(
            1.0,
            max(math.hypot(*velocity) for velocity in game.velocity_history)
            / (game.max_speed * 0.25),
        )
        game.update(game.duration)
        self.assertAlmostEqual(game.max_speed_ratio, measured_ratio, places=9)

    def test_real_geometry_produces_natural_success_and_failure(self):
        winner = self.run_game(0)
        failure = self.run_game(58)

        self.assertTrue(winner.will_survive)
        self.assertFalse(winner.crashed)
        self.assertEqual(winner.active, winner.total)
        self.assertTrue(all(clearance > 0.0 for clearance in winner.laser_clearances))

        self.assertFalse(failure.will_survive)
        self.assertTrue(failure.crashed)
        self.assertIsNotNone(failure.completed_at)
        self.assertGreater(failure.active, failure.total * 0.85)
        self.assertEqual(failure.events[-1][3], "impact")
        collision_index = failure.simulated_collision_index
        collision_time = failure.simulated_collision_time
        self.assertIsNotNone(collision_index)
        self.assertIsNotNone(collision_time)
        assert collision_index is not None and collision_time is not None
        laser = failure.lasers[collision_index]
        crash = failure.simulated_crash_position
        assert crash is not None
        self.assertTrue(failure.laser_is_active(laser, collision_time))
        self.assertLessEqual(
            failure.collision_distance(laser, crash, collision_time),
            failure.runner_radius + float(laser["half_width"]) + 1e-9,
        )
        self.assertLessEqual(failure.laser_clearances[collision_index], 0.0)


class BossBattleRegressionTests(unittest.TestCase):
    def make_game(self, seed: int, fps: int = 30):
        return GAME_CLASSES["boss-battle"](
            270, 480, fps, 10.0, 300, seed, "sunset", "WHO WINS THIS BATTLE?"
        )

    def run_game(self, seed: int, fps: int = 30):
        game = self.make_game(seed, fps)
        for frame_index in range(round(game.duration * fps) + 1):
            game.update(min(game.duration, frame_index / fps))
        game.update(game.duration)
        return game

    @staticmethod
    def snapshot(game):
        bodies = (game.player_body, game.boss_body, game.player_mace, game.boss_mace)
        return {
            "positions": tuple(tuple(body["position"]) for body in bodies),
            "velocities": tuple(tuple(body["velocity"]) for body in bodies),
            "hp": (game.player_hp, game.boss_hp),
            "hits": tuple(
                (
                    hit["time"],
                    hit["player"],
                    hit["damage"],
                    hit["energy"],
                    hit["position"],
                )
                for hit in game.hit_history
            ),
            "events": tuple(game.events),
            "winner": game.winner,
            "completed_at": game.completed_at,
        }

    def test_fixed_timestep_is_independent_from_render_fps(self):
        states = [self.snapshot(self.run_game(10, fps)) for fps in (8, 12, 24, 30, 60)]
        self.assertTrue(all(state == states[0] for state in states[1:]))

    def test_damage_and_winner_come_only_from_physical_impacts(self):
        for seed in (0, 10, 25):
            with self.subTest(seed=seed):
                game = self.run_game(seed)
                self.assertGreater(len(game.hit_history), 0)
                player_damage = sum(
                    float(hit["damage"]) for hit in game.hit_history if not bool(hit["player"])
                )
                boss_damage = sum(
                    float(hit["damage"]) for hit in game.hit_history if bool(hit["player"])
                )
                self.assertAlmostEqual(player_damage, game.player_max - game.player_hp, places=9)
                self.assertAlmostEqual(boss_damage, game.boss_max - game.boss_hp, places=9)
                self.assertEqual(game.active, round(game.boss_max - game.boss_hp))
                for hit in game.hit_history:
                    self.assertGreater(float(hit["energy"]), 0.0)
                    self.assertGreater(float(hit["damage"]), 0.0)
                expected = (
                    "draw"
                    if abs(game.player_hp / game.player_max - game.boss_hp / game.boss_max) <= 1e-9
                    else (
                        "player"
                        if game.player_hp / game.player_max > game.boss_hp / game.boss_max
                        else "boss"
                    )
                )
                self.assertEqual(game.winner, expected)
                self.assertFalse(hasattr(game, "player_wins"))
                self.assertFalse(hasattr(game, "attacks"))
                self.assertFalse(hasattr(game, "attack_times"))

    def test_seeded_physics_produces_both_natural_outcomes(self):
        boss_win = self.run_game(0)
        player_win = self.run_game(10)
        self.assertEqual(boss_win.winner, "boss")
        self.assertEqual(player_win.winner, "player")
        self.assertGreater(boss_win.player_hp, 0.0)
        self.assertGreater(player_win.boss_hp, 0.0)
        self.assertEqual(boss_win.completed_at, boss_win.battle_end)
        self.assertEqual(player_win.completed_at, player_win.battle_end)

    def test_verdict_is_one_dedicated_non_collision_event_at_battle_end(self):
        game = self.run_game(10)
        verdicts = [event for event in game.events if event[3] == "victory"]
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0][0], game.battle_end)
        self.assertEqual(game.music_outcome_at, game.battle_end)
        self.assertEqual(len(game.events), len(game.music_hits) + 1)
        self.assertTrue(all(hit["kind"] != "victory" for hit in game.hit_history))

    def test_boss_audio_graph_has_an_outcome_tail_and_quiet_ambient_floor(self):
        game = self.run_game(10)
        audio_graph = RENDERER.build_hit_reveal_filter(
            game.music_hits,
            game.duration,
            0.62,
            game.seed,
            outcome_time=game.music_outcome_at,
            ambient_floor=0.10,
        )
        self.assertIn("[outcome_tail]", audio_graph)
        self.assertIn("duration=1.000", audio_graph)
        self.assertIn("volume=0.100[ambient]", audio_graph)
        self.assertNotIn("victory", tuple(hit["kind"] for hit in game.hit_history))

    def test_boss_hp_changes_real_durability_not_just_displayed_numbers(self):
        games = []
        for boss_hp in (100, 300, 500):
            game = GAME_CLASSES["boss-battle"](
                270, 480, 30, 10.0, boss_hp, 10, "sunset", "WHO WINS THIS BATTLE?"
            )
            game.update(game.duration)
            games.append(game)

        easy, normal, hard = games
        self.assertEqual((easy.boss_max, normal.boss_max, hard.boss_max), (100.0, 300.0, 500.0))
        self.assertLessEqual(easy.boss_hp, normal.boss_hp)
        self.assertLess(normal.boss_hp, hard.boss_hp)
        self.assertNotAlmostEqual(
            easy.boss_hp / easy.boss_max,
            hard.boss_hp / hard.boss_max,
            places=6,
        )
        # The world and measured collision energies are independent of the HP
        # choice until an easier boss is actually defeated.
        normal_energies = [
            float(hit["energy"]) for hit in normal.hit_history if bool(hit["player"])
        ]
        hard_energies = [
            float(hit["energy"]) for hit in hard.hit_history if bool(hit["player"])
        ]
        self.assertEqual(normal_energies, hard_energies)
        self.assertEqual(normal.winner, "player")
        self.assertEqual(hard.winner, "boss")

    def test_chain_constraints_and_arena_collisions_stay_geometric(self):
        game = self.run_game(10)
        left, top, right, bottom = game.arena_bounds()
        for owner, mace in (
            (game.player_body, game.player_mace),
            (game.boss_body, game.boss_mace),
        ):
            distance = math.hypot(
                mace["position"][0] - owner["position"][0],
                mace["position"][1] - owner["position"][1],
            )
            self.assertAlmostEqual(distance, mace["chain_length"], places=9)
        for body in (game.player_body, game.boss_body, game.player_mace, game.boss_mace):
            radius = body["radius"]
            self.assertGreaterEqual(body["position"][0], left + radius - 1e-6)
            self.assertLessEqual(body["position"][0], right - radius + 1e-6)
            self.assertGreaterEqual(body["position"][1], top + radius - 1e-6)
            self.assertLessEqual(body["position"][1], bottom - radius + 1e-6)

    def test_render_positions_are_the_simulated_positions_without_lerp(self):
        game = self.make_game(10)
        game.update(2.0)
        expected = (list(game.player_body["position"]), list(game.boss_body["position"]))
        self.assertEqual(game.fighter_positions(-999.0, None, 999.0), expected)
        self.assertEqual(
            game.fighter_positions(999.0, {"player": True, "time": 0.0}, -999.0),
            expected,
        )


class BallEscapeRegressionTests(unittest.TestCase):
    def test_outcome_is_independent_from_render_resolution(self):
        states = []
        for width in (270, 360, 540, 1080):
            height = round(width * 16 / 9)
            game = BallEscape(width, height, 60, 15.0, 14, 9, "neon", "WILL IT ESCAPE?")
            game.update(15.0)
            states.append({
                "active": game.active,
                "completed_at": game.completed_at,
                "failed_at": game.failed_at,
                "event_kinds": tuple(event[3] for event in game.events),
                "position": tuple(round(value / width, 9) for value in game.position),
                "velocity": tuple(round(value / width, 9) for value in game.velocity),
            })

        self.assertTrue(all(state == states[0] for state in states[1:]))
        self.assertEqual(states[0]["active"], 14)
        self.assertIsNotNone(states[0]["completed_at"])
        self.assertIsNone(states[0]["failed_at"])

    def test_fixed_timestep_is_independent_from_render_fps(self):
        states = []
        for fps in (12, 15, 24, 30, 60):
            game = run_ball_escape(seed=101, fps=fps, until=7.5)
            states.append({
                "active": game.active,
                "completed_at": game.completed_at,
                "position": tuple(game.position),
                "velocity": tuple(game.velocity),
                "events": tuple(game.events),
                "music_hits": tuple(game.music_hits),
                "frame": hashlib.sha256(game.frame(7.5).tobytes()).hexdigest(),
            })
        self.assertTrue(all(state == states[0] for state in states[1:]))

    def test_gap_geometry_never_reads_ball_state(self):
        game = BallEscape(270, 480, 30, 10.0, 8, 27, "neon", "WILL IT ESCAPE?")
        times = (0.0, 0.63, 4.25, 9.8)
        expected_angles = tuple(
            tuple(game.ring_gap(index, time_sec) for index in range(game.ring_count))
            for time_sec in times
        )
        expected_widths = tuple(game.ring_gap_width(index) for index in range(game.ring_count))

        game.position = [game.width * 4.0, -game.height * 3.0]
        game.velocity = [-game.width * 8.0, game.height * 6.0]
        game.active = game.ring_count - 1
        game.failed_at = 1.0

        self.assertEqual(
            tuple(
                tuple(game.ring_gap(index, time_sec) for index in range(game.ring_count))
                for time_sec in times
            ),
            expected_angles,
        )
        self.assertEqual(
            tuple(game.ring_gap_width(index) for index in range(game.ring_count)),
            expected_widths,
        )

    def test_authored_layout_has_no_spiral_corridor_or_instant_clear_geometry(self):
        for rings in (10, 14, 20):
            for seed in range(12):
                with self.subTest(rings=rings, seed=seed):
                    game = BallEscape(360, 640, 30, 15.0, rings, seed, "neon", "WILL IT ESCAPE?")
                    self.assertLessEqual(game.bands_per_ring, 3)
                    self.assertLessEqual(game.band_span, game.radial_step * 0.34 + 1e-9)

                    # Once a whole sphere has left one visible ribbon, its
                    # centre travels more than a full diameter before it can
                    # touch the next visible ribbon.
                    centre_free_flight = (
                        game.radial_step - game.band_span - 2.0 * game.ball_radius
                    )
                    self.assertGreater(centre_free_flight, 2.0 * game.ball_radius)

                    # Adjacent physical openings never overlap at any point in
                    # the clip. There is therefore no static or rotating radial
                    # corridor for the sphere to follow.
                    for sample in range(121):
                        time_sec = game.duration * sample / 120.0
                        for index in range(1, game.ring_count):
                            separation = abs(RENDERER.angle_delta(
                                game.ring_gap(index, time_sec),
                                game.ring_gap(index - 1, time_sec),
                            ))
                            opening_sum = (
                                game.gap_widths[index] + game.gap_widths[index - 1]
                            ) * 0.5
                            self.assertGreaterEqual(separation, opening_sum + 10.0)

    def test_velocity_is_independent_from_gap_layout_before_collision(self):
        first = BallEscape(270, 480, 30, 10.0, 8, 27, "neon", "WILL IT ESCAPE?")
        second = BallEscape(270, 480, 30, 10.0, 8, 27, "neon", "WILL IT ESCAPE?")
        for game in (first, second):
            # Isolate free flight: any divergence can only be hidden steering.
            game.radii = [10_000.0 + index * 100.0 for index in range(game.ring_count)]
        first.base_gaps = [0.0] * first.ring_count
        second.base_gaps = [180.0] * second.ring_count

        first.update(0.75)
        second.update(0.75)

        self.assertEqual(first.position, second.position)
        self.assertEqual(first.velocity, second.velocity)

    def test_real_collisions_produce_both_success_and_failure(self):
        rings = 14
        duration = 15.0
        winner = BallEscape(360, 640, 30, duration, rings, 9, "neon", "WILL IT ESCAPE?")
        failure = BallEscape(360, 640, 30, duration, rings, 0, "neon", "WILL IT ESCAPE?")
        winner.update(duration)
        failure.update(duration)

        self.assertEqual(winner.active, rings)
        self.assertIsNotNone(winner.completed_at)
        self.assertIsNone(winner.failed_at)
        self.assertEqual(sum(event[3] == "clear" for event in winner.events), rings)
        clear_times = [event[0] for event in winner.events if event[3] == "clear"]
        clear_intervals = [
            clear_times[index] - clear_times[index - 1]
            for index in range(1, len(clear_times))
        ]
        self.assertTrue(all(interval > 0.20 for interval in clear_intervals))
        previous_clear = -1.0
        for clear_time in clear_times:
            self.assertTrue(any(
                event_type == "bounce" and previous_clear < event_time < clear_time
                for event_time, _frequency, _volume, event_type in winner.events
            ))
            previous_clear = clear_time

        self.assertLess(failure.active, rings)
        self.assertGreater(failure.active, 0)
        self.assertIsNone(failure.completed_at)
        self.assertIsNotNone(failure.failed_at)
        self.assertEqual(sum(event[3] == "clear" for event in failure.events), failure.active)

    def test_catalog_sample_contains_natural_outcomes(self):
        completed = []
        incomplete = []
        for seed in range(0, 70):
            with self.subTest(seed=seed):
                game = BallEscape(360, 640, 15, 15.0, 14, seed, "neon", "WILL IT ESCAPE?")
                for frame_index in range(15 * 15 + 1):
                    game.update(min(15.0, frame_index / 15))
                self.assertEqual(game.frame(15.0).size, (360, 640))
                self.assertEqual(sum(event[3] == "clear" for event in game.events), game.active)
                if game.completed_at is None:
                    incomplete.append(seed)
                    self.assertLess(game.active, game.ring_count)
                    self.assertIsNotNone(game.failed_at)
                else:
                    completed.append(seed)
                    self.assertEqual(game.active, game.ring_count)
                    self.assertIsNone(game.failed_at)
        self.assertTrue(completed)
        self.assertTrue(incomplete)

    def test_each_clear_advances_exactly_one_ring(self):
        duration = 15.0
        rings = 14
        game = BallEscape(360, 640, 30, duration, rings, 9, "neon", "WILL IT ESCAPE?")
        fixed_dt = 1.0 / 120.0
        for step in range(round(duration / fixed_dt)):
            active_before = game.active
            clears_before = sum(event[3] == "clear" for event in game.events)
            game.update((step + 1) * fixed_dt)
            active_delta = game.active - active_before
            clear_delta = sum(event[3] == "clear" for event in game.events) - clears_before
            self.assertLessEqual(active_delta, 1)
            self.assertEqual(active_delta, clear_delta)
        self.assertEqual(game.active, rings)
        self.assertEqual(sum(event[3] == "clear" for event in game.events), rings)

    def test_timeout_never_unlocks_or_overrides_the_last_ring(self):
        game = BallEscape(360, 640, 30, 15.0, 14, 0, "neon", "WILL IT ESCAPE?")
        game.update(14.4)
        active_at_timeout = game.active
        self.assertIsNotNone(game.failed_at)
        self.assertIsNone(game.completed_at)

        game.update(15.0)

        self.assertEqual(game.active, active_at_timeout)
        self.assertIsNone(game.completed_at)
        for legacy_control in ("will_escape", "final_unlock", "ring_deadline", "last_clear"):
            self.assertFalse(hasattr(game, legacy_control))


if __name__ == "__main__":
    unittest.main()
