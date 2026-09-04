import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from discover_edit_audio import assess_speech, candidate, collect, safe_url, transcript_hash, verify_page


def segments(text="I really miss him, and I know that my heart will never forget him."):
    return [{"text": text, "avg_logprob": -.1, "no_speech_prob": .01,
             "words": [{"start": .2 + i * .35, "end": .48 + i * .35, "word": word, "probability": .95}
                       for i, word in enumerate(text.split())]}]


class DiscoveryTests(unittest.TestCase):
    def test_search_timeout_is_reported_without_failing_the_optional_refresh(self):
        with tempfile.TemporaryDirectory() as root, \
                patch("discover_edit_audio.download", side_effect=TimeoutError), \
                patch("discover_edit_audio.time.sleep"):
            report = collect(Path(root), publish=False)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["searched"], 0)
        self.assertEqual(report["errors"], ["search-unavailable"] * 3)

    def test_source_urls_are_strictly_allowlisted(self):
        good = "https://cdn.freesound.org/previews/123/123456_1-hq.mp3"
        self.assertEqual(safe_url(good, "audio"), good)
        for value in ("http://cdn.freesound.org/previews/123/123456_1-hq.mp3",
                      "https://cdn.freesound.org@127.0.0.1/anything",
                      "https://cdn.freesound.org/previews/123/not-matching.mp3"):
            with self.assertRaises(ValueError): safe_url(value, "audio")

    def test_index_license_and_identity_are_bound(self):
        item = {"source": "freesound", "provider": "freesound", "mature": False, "unstable__sensitivity": [],
                "license": "by", "license_version": "4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "title": "I miss you", "duration": 19000, "creator": "actor_one",
                "foreign_landing_url": "https://freesound.org/people/actor_one/sounds/123456",
                "url": "https://cdn.freesound.org/previews/123/123456_1-hq.mp3",
                "id": "59299898-6d14-49dd-82bd-7a6380c39668", "tags": [{"name": "speech"}, {"name": "sad"}]}
        self.assertEqual(candidate(item)["sourceId"], "123456")
        with self.assertRaises(ValueError): candidate({**item, "license": "by-nc"})
        with self.assertRaises(ValueError): candidate({**item, "title": "movie dialogue"})

    def test_page_must_claim_original_voice_and_match_license(self):
        source = {"license": "https://creativecommons.org/licenses/by/4.0/"}
        page = b'<div id="soundDescriptionSection">Me saying an original sad sentence.</div><a href="https://creativecommons.org/licenses/by/4.0/">license</a>'
        self.assertTrue(verify_page(source, page)["originalClaim"])
        with self.assertRaises(ValueError): verify_page(source, page.replace(b"Me saying", b"A movie line"))

    def test_speech_is_english_complete_emotional_and_not_repeated(self):
        checked = assess_speech(segments(), "en", .97, 10)
        self.assertEqual(checked["mood"], "sad")
        self.assertEqual(checked["transcriptSha256"], transcript_hash(checked["transcript"]))
        with self.assertRaises(ValueError):
            assess_speech(segments("I miss you and I love you. I miss you and I love you."), "en", .98, 10)
        with self.assertRaises(ValueError): assess_speech(segments(), "fr", .98, 10)


if __name__ == "__main__":
    unittest.main()
