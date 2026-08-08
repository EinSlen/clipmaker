"""Fast deterministic tests for every procedural game engine."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

from game_variants import GAME_CLASSES
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


class GameCatalogTests(unittest.TestCase):
    def test_frontend_catalog_matches_python_engines(self):
        source = (ROOT / "lib" / "game-catalog.ts").read_text(encoding="utf-8")
        catalog_ids = tuple(re.findall(r"\bid: '([a-z-]+)'", source))
        self.assertEqual(catalog_ids, (*ENGINE_IDS, *PREMIUM_IDS))
        self.assertEqual(len(catalog_ids), len(set(catalog_ids)))


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


if __name__ == "__main__":
    unittest.main()
