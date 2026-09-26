"""The published edit keeps the action and drops the frames nobody watches."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from PIL import Image, ImageDraw

import sample_foley
import soft_body_edit
from soft_body_edit import (
    accent_times, active_span, frame_motion, opening_span, published_edit,
    published_events, stage_published_frames,
)

FPS = 30
RENDERER_PATH = Path(__file__).with_name("render-premium-3d.py")
RENDERER_SPEC = importlib.util.spec_from_file_location("edit_test_renderer", RENDERER_PATH)
RENDERER = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(RENDERER)


def take(moving: int, still: int, level: float = 0.012) -> list[float]:
    """Motion of a take that moves for ``moving`` frames, then stops."""
    return [level] * moving + [0.0] * still


# Measured on the 26 September daily (pipe-bend, frames 1 to 138): the rigid
# capsule lands on the ring after 1.5 s and then only rocks.
RIGID_TAKE = (
    0.0, 0.0027, 0.0033, 0.0039, 0.005, 0.0058, 0.0064, 0.0068, 0.0073, 0.0078, 0.0082, 0.0086,
    0.009, 0.0093, 0.0097, 0.01, 0.0104, 0.0108, 0.0111, 0.0113, 0.0118, 0.0123, 0.0142, 0.0141,
    0.0134, 0.0125, 0.0145, 0.0112, 0.0103, 0.0095, 0.0082, 0.0066, 0.0121, 0.0129, 0.0133, 0.0129,
    0.0123, 0.0137, 0.0108, 0.0071, 0.0073, 0.0084, 0.0048, 0.0049, 0.0061, 0.0057, 0.006, 0.0032,
    0.0032, 0.0038, 0.0037, 0.0039, 0.0039, 0.0037, 0.0034, 0.0033, 0.0031, 0.0033, 0.0037, 0.0038,
    0.004, 0.0032, 0.0032, 0.003, 0.0032, 0.0032, 0.0033, 0.0035, 0.0033, 0.003, 0.0025, 0.0025,
    0.0023, 0.002, 0.0018, 0.0014, 0.0011, 0.0014, 0.0017, 0.0008, 0.0009, 0.0014, 0.0018, 0.0021,
    0.0022, 0.0024, 0.0023, 0.0021, 0.0023, 0.0031, 0.0033, 0.0033, 0.0027, 0.0023, 0.0021, 0.002,
    0.002, 0.0021, 0.002, 0.0019, 0.0012, 0.0008, 0.0007, 0.0001, 0.0003, 0.0008, 0.0011, 0.0006,
    0.0009, 0.0013, 0.0014, 0.0013, 0.0013, 0.0014, 0.0016, 0.0018, 0.0018, 0.002, 0.002, 0.0022,
    0.0023, 0.0025, 0.0026, 0.0026, 0.0027, 0.0022, 0.0016, 0.0011, 0.0006, 0.0002, 0.0001, 0.0002,
    0.0002, 0.0004, 0.0009, 0.0012, 0.0015, 0.0018,
)


class ActiveSpanTests(unittest.TestCase):
    def test_the_rigid_take_ends_a_beat_after_it_lands(self):
        motion = tuple(RIGID_TAKE)
        self.assertEqual(len(motion), 138)
        start, end = active_span(motion, 1, 138, FPS)
        self.assertEqual(start, 1)
        # The capsule has stopped by 1.9 s; the three seconds after it go.
        self.assertLess(end, 70)
        self.assertGreater(end, 45)

    def test_an_empty_studio_after_the_body_left_is_cut(self):
        motion = tuple([0.0] + take(79, 40))
        start, end = active_span(motion, 1, 120, FPS)
        self.assertEqual(start, 1)
        # The last moving frame is 80, the smoothing reads one frame past it,
        # then the 0.3 s beat.
        self.assertEqual(end, 81 + 9)

    def test_a_hold_before_the_release_keeps_only_its_lead(self):
        motion = tuple([0.0] * 30 + take(90, 0))
        start, end = active_span(motion, 1, 120, FPS)
        # Movement starts on frame 31, the smoothing one frame before it, and
        # the 0.2 s lead before that.
        self.assertEqual((start, end), (30 - 6, 120))

    def test_a_take_that_moves_to_its_last_frame_is_kept_whole(self):
        motion = tuple([0.0] + take(119, 0))
        self.assertEqual(active_span(motion, 1, 120, FPS), (1, 120))

    def test_a_take_with_no_motion_is_kept_rather_than_judged(self):
        motion = tuple([0.0] * 120)
        self.assertEqual(active_span(motion, 1, 120, FPS), (1, 120))

    def test_the_cut_into_a_take_is_not_read_as_its_motion(self):
        # Frame 121 differs from 120 because it is a new take. That jump must
        # not make a take that never moves look busy.
        motion = tuple([0.0] + take(119, 0) + [0.4] + [0.0] * 119)
        self.assertEqual(active_span(motion, 121, 240, FPS), (121, 240))


def events_for(*items):
    return [{"time": (frame - 1) / FPS + 0.01, "frame": frame, "kind": kind, "strength": strength}
            for frame, kind, strength in items]


class OpeningTests(unittest.TestCase):
    attempts = ((1, 100), (101, 200), (201, 300))
    counts = (1, 2)

    def test_the_opening_is_the_last_level_arriving_in_its_receiver(self):
        events = events_for((50, "obstacle-contact", 0.9), (160, "obstacle-contact", 1.0), (180, "receiver-entry", 0.4))
        self.assertEqual(opening_span(events, self.attempts, self.counts, FPS), (180 - 24, 180 + 12, 180))

    def test_without_a_receiver_the_hardest_contact_is_the_payoff(self):
        events = events_for((150, "obstacle-contact", 0.5), (170, "ramp-contact", 0.9))
        self.assertEqual(opening_span(events, self.attempts, self.counts, FPS), (146, 182, 170))

    def test_the_opening_never_leaves_its_take(self):
        events = events_for((105, "receiver-contact", 0.7), (195, "obstacle-contact", 0.2))
        start, end, anchor = opening_span(events, self.attempts, self.counts, FPS)
        self.assertEqual((start, anchor), (102, 105))
        self.assertLessEqual(end, 200)

    def test_a_last_level_without_events_has_no_opening(self):
        events = events_for((50, "obstacle-contact", 0.9))
        self.assertIsNone(opening_span(events, self.attempts, self.counts, FPS))


class PublishedEditTests(unittest.TestCase):
    attempts = ((1, 120), (121, 240), (241, 360))
    counts = (1, 1, 1)

    def motion(self):
        return tuple([0.0] + take(59, 60) + [0.3] + take(119, 0) + [0.3] + take(89, 30))

    def test_levels_follow_the_published_frames_after_the_opening(self):
        events = events_for((300, "receiver-entry", 0.4))
        edit = published_edit(self.motion(), self.attempts, self.counts, events, FPS)
        self.assertEqual(edit.opening, (276, 312))
        self.assertEqual(edit.takes, ((1, 70), (121, 240), (241, 340)))
        self.assertEqual(edit.frames[:37], tuple(range(276, 313)))
        self.assertEqual(len(edit.frames), 37 + 70 + 120 + 100)
        self.assertEqual(edit.opening_seconds, (0.0, 37 / FPS))
        self.assertEqual(edit.level_seconds[0], (37 / FPS, 107 / FPS))
        self.assertEqual(edit.level_seconds[-1], (227 / FPS, len(edit.frames) / FPS))
        self.assertAlmostEqual(edit.duration, len(edit.frames) / FPS)

    def test_the_native_timeline_is_kept_when_the_edit_must_not_cut(self):
        events = events_for((300, "receiver-entry", 0.4))
        edit = published_edit((), self.attempts, self.counts, events, FPS, cut=False)
        self.assertEqual(edit.frames, tuple(range(1, 361)))
        self.assertIsNone(edit.opening)
        self.assertEqual(edit.level_seconds, ((0.0, 4.0), (4.0, 8.0), (8.0, 12.0)))
        self.assertEqual(accent_times(edit, events), ())

    def test_every_level_must_own_a_take(self):
        with self.assertRaises(ValueError):
            published_edit(self.motion(), self.attempts, (1, 2, 1), [], FPS)

    def test_a_contact_is_heard_where_its_frame_is_seen(self):
        events = events_for((30, "obstacle-contact", 0.5), (100, "obstacle-contact", 0.5), (300, "receiver-entry", 0.4))
        edit = published_edit(self.motion(), self.attempts, self.counts, events, FPS)
        heard = published_events(edit, events)
        times = [round(event["time"], 4) for event in heard]
        # Frame 300 is in the opening and in the last take, so it plays twice;
        # frame 100 was in the cut tail of the first take, so it is silent.
        self.assertEqual(times, [round(24 / FPS + 0.01, 4), round(37 / FPS + 29 / FPS + 0.01, 4),
                                 round((37 + 70 + 120 + 59) / FPS + 0.01, 4)])
        (accent,) = accent_times(edit, events)
        self.assertAlmostEqual(accent, 24 / FPS + 0.01)

    def test_the_summary_records_what_was_published(self):
        events = events_for((300, "receiver-entry", 0.4))
        summary = published_edit(self.motion(), self.attempts, self.counts, events, FPS).summary()
        self.assertEqual(summary["opening"], [276, 312])
        self.assertEqual(summary["takes"][0], [1, 70])
        self.assertEqual(summary["frames"], 327)


class FrameTests(unittest.TestCase):
    def test_motion_counts_pixels_that_change_and_ignores_noise(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (shade, box) in enumerate(((120, None), (123, None), (123, (0, 0, 40, 40))), start=1):
                image = Image.new("L", (160, 160), shade)
                if box:
                    ImageDraw.Draw(image).rectangle(box, fill=255)
                image.save(root / f"frame_{index:04d}.png")
            motion = frame_motion(root, 3)
            self.assertEqual(motion[0], 0.0)
            self.assertEqual(motion[1], 0.0)
            self.assertAlmostEqual(motion[2], (41 * 41) / (160 * 160), delta=0.01)

    def test_published_frames_are_numbered_from_one_in_edit_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for index in range(1, 7):
                (source / f"frame_{index:04d}.png").write_bytes(bytes([index]))
            edit = soft_body_edit.PublishedEdit(FPS, (5, 6, 1, 2), ((1, 2),), (5, 6), 5, (0.0, 2 / FPS), ((2 / FPS, 4 / FPS),))
            stage_published_frames(source, root / "published", edit)
            self.assertEqual([(root / "published" / f"frame_{n:04d}.png").read_bytes() for n in range(1, 5)],
                             [b"\x05", b"\x06", b"\x01", b"\x02"])


class AccentTests(unittest.TestCase):
    def render(self, accents):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fx.wav"
            events = [{"time": time, "kind": "obstacle-contact", "strength": 0.9, "softness": 100}
                      for time in (0.5, 0.8, 3.0)]
            report = sample_foley.synth_sample_foley(4.0, events, output, 7, "meme", accents)
            with wave.open(str(output), "rb") as source:
                samples = array("h")
                samples.frombytes(source.readframes(source.getnframes()))
        return report, samples

    def test_the_meow_plays_once_without_turning_the_contacts_down(self):
        plain_report, plain = self.render(())
        report, accented = self.render((0.79,))
        self.assertEqual(report["sound_pack_accent"], "Cat meow")
        self.assertEqual(report["sound_pack_accent_times"], [0.79])
        self.assertIn("Cat meow by philsapphire (https://freesound.org/people/philsapphire/sounds/256452/)",
                      report["sound_pack_credits"])
        self.assertNotIn("sound_pack_accent", plain_report)
        # Outside the meow the contact track is the same, sample for sample.
        after = round((0.79 + 1.3) * 48_000) * 2
        self.assertEqual(accented[after:], plain[after:])
        self.assertEqual(accented[:round(0.79 * 48_000) * 2], plain[:round(0.79 * 48_000) * 2])
        self.assertLessEqual(max(abs(value) for value in accented), 32767)
        window = accented[round(0.79 * 48_000) * 2:after]
        self.assertGreater(max(abs(value) for value in window), max(abs(value) for value in plain))

    def test_a_pack_without_accent_ignores_the_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = sample_foley.synth_sample_foley(1.0, [], Path(temporary) / "fx.wav", 7, "funny", (0.2,))
        self.assertNotIn("sound_pack_accent", report)


class LoudnessTests(unittest.TestCase):
    measured = {"input_i": "-16.1", "input_tp": "-1.0", "input_lra": "6.2",
                "input_thresh": "-26.5", "target_offset": "0.1"}

    def test_the_instrumental_mix_applies_one_measured_gain(self):
        riding = RENDERER.build_continuous_audio_filter(0.58)
        linear = RENDERER.build_continuous_audio_filter(0.58, measured=self.measured)
        self.assertTrue(riding.endswith("[limited]loudnorm=I=-18:TP=-2.5:LRA=10[a]"))
        self.assertTrue(linear.endswith(
            "[limited]loudnorm=I=-18:TP=-2.5:LRA=10:measured_I=-16.1:measured_TP=-1.0"
            ":measured_LRA=6.2:measured_thresh=-26.5:offset=0.1:linear=true[a]"))

    def test_vocal_mixes_are_not_measured(self):
        vocal = RENDERER.build_continuous_audio_filter(0.58, True)
        self.assertIsNone(RENDERER.measure_mix_loudness("ffmpeg", [], vocal, 1.0))
        self.assertEqual(vocal, RENDERER.build_continuous_audio_filter(0.58, True, measured=self.measured))

    def test_the_labels_open_on_the_last_level(self):
        value = RENDERER.build_video_filter(20.0, (0, 50, 100), "pipe-bend", ((1.2, 8.0), (8.0, 14.0), (14.0, 20.0)), (0.0, 1.2))
        self.assertIn("text='100%'", value.split("text='0%'")[0])
        self.assertIn("between(t\\,0.000\\,1.199)", value)
        self.assertIn("between(t\\,14.000\\,20.000)", value)


if __name__ == "__main__":
    unittest.main()
