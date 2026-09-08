import tempfile
import unittest
import wave
from array import array
from pathlib import Path

import sample_foley as foley


def read(path: Path) -> array:
    with wave.open(str(path), "rb") as source:
        frames = array("h")
        frames.frombytes(source.readframes(source.getnframes()))
        return frames


def energy(frames: array, start: float, end: float) -> float:
    first = int(start * foley.RATE) * 2
    last = int(end * foley.RATE) * 2
    window = frames[first:last]
    return sum(abs(value) for value in window) / max(1, len(window))


class SoundPackTests(unittest.TestCase):
    def test_shipped_pack_is_complete_and_credited(self):
        for name in {value for value in foley.ALIASES.values()}:
            manifest, samples = foley.load_pack(name)
            self.assertGreaterEqual(len(samples), 8)
            self.assertTrue(manifest.get("rights"))
            for entry in manifest["samples"]:
                for key in ("file", "title", "author", "source", "license"):
                    self.assertTrue(str(entry.get(key, "")).strip(), f"{name}/{entry.get('file')} misses {key}")
                self.assertTrue(entry["source"].startswith("https://freesound.org/people/"))
                self.assertEqual(entry["license"], "https://creativecommons.org/publicdomain/zero/1.0/")

    def test_only_the_sampled_requests_resolve(self):
        self.assertEqual(foley.resolve_pack("auto"), "funny")
        self.assertEqual(foley.resolve_pack("funny"), "funny")
        for request in ("meme", "arcade", "impact", "asmr", "unknown"):
            self.assertIsNone(foley.resolve_pack(request))


class SampleFoleyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rendered = 0

    def render(self, events, seed=4242, duration=8.0):
        self.rendered += 1
        output = self.root / f"foley-{self.rendered}.wav"
        report = foley.synth_sample_foley(duration, events, output, seed, "funny")
        return output, report

    def test_track_matches_the_requested_duration_and_format(self):
        output, report = self.render([{"time": 1.0, "kind": "obstacle-contact"}])
        with wave.open(str(output), "rb") as source:
            self.assertEqual((source.getframerate(), source.getnchannels(), source.getsampwidth()), (48_000, 2, 2))
            self.assertAlmostEqual(source.getnframes() / 48_000, 8.0, delta=0.01)
        self.assertEqual(report["sound_pack"], "funny")
        self.assertEqual(report["sound_pack_hits"], 1)
        self.assertTrue(report["sound_pack_credits"])

    def test_every_contact_is_audible_and_the_rest_stays_quiet(self):
        output, _ = self.render([{"time": 2.0, "strength": 0.9}, {"time": 5.0, "strength": 0.9}])
        frames = read(output)
        for moment in (2.0, 5.0):
            self.assertGreater(energy(frames, moment, moment + 0.12), 20 * energy(frames, 3.4, 3.6))

    def test_a_receiver_entry_only_brushes_past(self):
        contact, _ = self.render([{"time": 2.0, "kind": "receiver-contact", "strength": 0.9}])
        entry, _ = self.render([{"time": 2.0, "kind": "receiver-entry", "strength": 0.9}])
        self.assertLess(energy(read(entry), 2.0, 2.4), energy(read(contact), 2.0, 2.4) / 2)

    def test_the_same_seed_replays_the_same_track(self):
        events = [{"time": 1.0}, {"time": 2.5}, {"time": 4.0}]
        first, _ = self.render(events, seed=77)
        second = self.root / "again.wav"
        foley.synth_sample_foley(8.0, events, second, 77, "funny")
        third, _ = self.render(events, seed=78)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertNotEqual(first.read_bytes(), third.read_bytes())

    def test_a_contact_on_the_last_frame_does_not_overflow(self):
        output, report = self.render([{"time": 7.999, "strength": 1.0}], duration=8.0)
        self.assertEqual(report["sound_pack_hits"], 1)
        with wave.open(str(output), "rb") as source:
            self.assertAlmostEqual(source.getnframes() / 48_000, 8.0, delta=0.01)

    def test_a_silent_simulation_still_produces_a_full_track(self):
        output, report = self.render([])
        self.assertEqual(report["sound_pack_hits"], 0)
        with wave.open(str(output), "rb") as source:
            self.assertAlmostEqual(source.getnframes() / 48_000, 8.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
