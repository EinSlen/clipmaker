"""Diversity checks use real geometry/initial conditions, never seed labels."""

import math
import unittest

from procedural_variation import (
    game_variation_manifest, organic_contour_for_seed, scoped_random, variation_manifest,
)
from soft_body_variants import OBSTACLES, SHAPES, source_variant_summary, variant_for_seed, variant_summary
from test_game_variants import ENGINE_IDS, build


class ProceduralVariationTests(unittest.TestCase):
    def test_scoped_streams_are_repeatable_and_independent(self):
        first, replay = scoped_random(10, "shape"), scoped_random(10, "shape")
        unrelated = scoped_random(10, "decoration")
        expected = [first.random() for _ in range(20)]
        for _ in range(500):
            unrelated.random()
        self.assertEqual(expected, [replay.random() for _ in range(20)])
        self.assertNotEqual(expected[0], scoped_random(11, "shape").random())

    def test_fingerprint_is_a_snapshot_of_parameters_not_a_seed_label(self):
        parameters = {"speed": 1.2, "gaps": [40, 90]}
        manifest = variation_manifest("ball-escape", parameters)
        self.assertEqual(manifest, variation_manifest("ball-escape", {"gaps": [40, 90], "speed": 1.2}))
        parameters["gaps"][0] = 50
        self.assertEqual(manifest["variation_parameters"]["gaps"][0], 40)
        self.assertNotEqual(manifest["variation_fingerprint"],
                            variation_manifest("ball-escape", parameters)["variation_fingerprint"])
        with self.assertRaises(ValueError):
            variation_manifest("ball-escape", {"speed": float("nan")})

    def test_each_2d_game_has_distinct_worlds_and_replayable_manifests(self):
        for game_id in ENGINE_IDS:
            with self.subTest(game=game_id):
                manifests = []
                for seed in range(40):
                    game = build(game_id, seed)
                    manifest = game_variation_manifest(game_id, game)
                    manifests.append(manifest["variation_fingerprint"])
                    if seed == 0:
                        snapshot = manifest["variation_parameters"]
                        game.update(3.0)
                        self.assertEqual(manifest, game_variation_manifest(game_id, build(game_id, seed)))
                        self.assertEqual(manifest["variation_parameters"], snapshot)
                self.assertEqual(len(set(manifests)), len(manifests))

    def test_organic_contours_are_not_a_small_preset_cycle(self):
        contours = [organic_contour_for_seed(seed) for seed in range(10_000)]
        self.assertEqual(len(set(contours)), len(contours))
        self.assertEqual({c.lobes for c in contours}, {5, 6, 7, 8, 9})
        self.assertEqual(contours[123], organic_contour_for_seed(123))

    def test_organic_display_collision_normals_and_velocity_share_one_curve(self):
        eps = 1e-5
        for seed in range(150):
            contour = organic_contour_for_seed(seed)
            for index in range(16):
                angle, time = index * math.tau / 16, .9
                radius, gradient, speed = contour.sample(angle, .3, time=time)
                self.assertGreaterEqual(radius, 1 - .129 - 1e-12)
                self.assertLessEqual(radius, 1 + .129 + 1e-12)
                self.assertLessEqual(abs(gradient), .853 + 1e-12)
                derivative = (contour.sample(angle + eps, .3, time=time)[0]
                              - contour.sample(angle - eps, .3, time=time)[0]) / (2 * eps)
                velocity = (contour.sample(angle, .3, time=time + eps)[0]
                            - contour.sample(angle, .3, time=time - eps)[0]) / (2 * eps)
                self.assertAlmostEqual(gradient, derivative, places=7)
                self.assertAlmostEqual(speed, velocity, places=8)

    def test_10000_3d_profiles_are_distinct_within_calibrated_dimensions(self):
        profiles, fingerprints = set(), set()
        for seed in range(10_000):
            variant = variant_for_seed(seed)
            shape, baseline = variant.shape, SHAPES[seed % len(SHAPES)]
            self.assertEqual((shape.radius, shape.cylinder_half), (baseline.radius, baseline.cylinder_half))
            self.assertTrue(.045 <= shape.groove <= .13)
            self.assertTrue(-.025 <= shape.bulge <= .055)
            profiles.add((shape.groove, shape.bulge))
            fingerprints.add(variant_summary(variant)["variation_fingerprint"])
        self.assertEqual(len(profiles), 10_000)
        self.assertEqual(len(fingerprints), 10_000)

    def test_generated_organic_shapes_keep_real_contacts_and_finite_trajectories(self):
        for seed in range(60):
            game = build("shape-tunnel", seed)
            for index in range(1, 61):
                game.update(index / 12)
                self.assertTrue(all(math.isfinite(v) for v in (*game.position, *game.velocity)))
            self.assertEqual(sum(contact[6] for contact in game.contact_history), game.active)
            self.assertGreater(len(game.contact_history), 0)
            for time, x, y, nx, ny, speed, damage, progress in game.contact_history:
                angle = math.atan2(y - game.cy, x - game.cx)
                distance = math.hypot(x - game.cx, y - game.cy)
                self.assertLess(abs(distance - game.boundary_radius(progress, angle, time)), game.width * .012)
                self.assertAlmostEqual(math.hypot(nx, ny), 1.0, places=10)

    def test_each_3d_family_keeps_its_own_geometry_and_no_retry_reroll(self):
        for obstacle in OBSTACLES:
            fingerprints = set()
            for seed in range(50):
                variant = variant_for_seed(seed, obstacle.key)
                self.assertEqual(variant.obstacle, obstacle)
                summary = variant_summary(variant)
                self.assertEqual(summary, variant_summary(variant_for_seed(seed, obstacle.key)))
                self.assertEqual(summary["variation_parameters"]["shape"]["groove"], variant.shape.groove)
                fingerprints.add(summary["variation_fingerprint"])
            self.assertEqual(len(fingerprints), 50)

    def test_recovered_frames_cannot_claim_a_new_procedural_profile(self):
        variant = variant_for_seed(910104)
        summary = variant_summary(variant)
        self.assertEqual(source_variant_summary(variant, summary), summary)
        self.assertNotIn("variation_fingerprint", source_variant_summary(variant, {}))
        for bad in ({"variation_version": 2}, {"variation_fingerprint": "bad"},
                    {"variation_parameters": {"invented": True}}):
            with self.assertRaisesRegex(ValueError, "different procedural variant"):
                source_variant_summary(variant, {**summary, **bad})


if __name__ == "__main__":
    unittest.main()
