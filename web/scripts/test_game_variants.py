"""Fast deterministic tests for every procedural game engine."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

from game_variants import GAME_CLASSES
from soft_body_variants import variant_for_seed
ROOT = Path(__file__).resolve().parents[1]
PREMIUM_IDS = ("soft-body-slide",)
ENGINE_IDS = ("ball-escape", *GAME_CLASSES)
RENDERER_PATH = Path(__file__).with_name("render-ball-escape.py")
RENDERER_SPEC = importlib.util.spec_from_file_location("render_ball_escape", RENDERER_PATH)
assert RENDERER_SPEC and RENDERER_SPEC.loader
RENDERER = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(RENDERER)
BallEscape = RENDERER.BallEscape


def build(game_id: str, seed: int = 424242):
    arguments = (270, 480, 12, 5.0, 48, seed, "neon", "CAN IT FINISH?")
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


class GameCatalogTests(unittest.TestCase):
    def test_frontend_catalog_matches_python_engines(self):
        source = (ROOT / "lib" / "game-catalog.ts").read_text(encoding="utf-8")
        catalog_ids = tuple(re.findall(r"\bid:\s*['\"]([a-z-]+)['\"]", source))
        self.assertEqual(catalog_ids, (*ENGINE_IDS, *PREMIUM_IDS))
        self.assertEqual(len(catalog_ids), len(set(catalog_ids)))


class SoftBodyVariantTests(unittest.TestCase):
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
                self.assertGreater(game.active, 0)
                self.assertLessEqual(game.active, expected_total)
                if game_id != "ball-escape":
                    self.assertEqual(game.active, expected_total)
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


class BallEscapeRegressionTests(unittest.TestCase):
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

    def test_winning_seeds_only_escape_in_the_late_window(self):
        duration = 10.0
        for seed in (101, 102, 103):
            with self.subTest(seed=seed):
                game = run_ball_escape(seed=seed, fps=30, duration=duration)
                self.assertTrue(game.will_escape)
                self.assertIsNotNone(game.completed_at)
                assert game.completed_at is not None
                self.assertGreaterEqual(game.completed_at, duration * 0.85)
                self.assertGreaterEqual(game.completed_at, game.final_unlock)
                self.assertLessEqual(game.completed_at, duration)

    def test_failure_seed_stays_blocked_at_the_final_ring(self):
        rings = 8
        game = run_ball_escape(seed=100, fps=30, rings=rings)
        self.assertFalse(game.will_escape)
        self.assertEqual(game.active, rings - 1)
        self.assertIsNone(game.completed_at)
        self.assertIsNotNone(game.failed_at)
        self.assertEqual(sum(event[3] == "clear" for event in game.events), rings - 1)

    def test_catalog_default_always_reaches_a_decisive_final_gate(self):
        for seed in range(1000, 1020):
            with self.subTest(seed=seed):
                game = BallEscape(360, 640, 15, 15.0, 14, seed, "neon", "WILL IT ESCAPE?")
                for frame_index in range(15 * 15 + 1):
                    game.update(min(15.0, frame_index / 15))
                self.assertEqual(game.frame(15.0).size, (360, 640))
                if seed % 4 == 0:
                    self.assertEqual(game.active, 13)
                    self.assertIsNone(game.completed_at)
                    self.assertIsNotNone(game.failed_at)
                else:
                    self.assertEqual(game.active, 14)
                    self.assertIsNotNone(game.completed_at)
                    assert game.completed_at is not None
                    self.assertGreaterEqual(game.completed_at, game.final_unlock)

    def test_each_clear_advances_exactly_one_ring(self):
        duration = 10.0
        rings = 8
        game = BallEscape(270, 480, 30, duration, rings, 101, "neon", "WILL IT ESCAPE?")
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


if __name__ == "__main__":
    unittest.main()
