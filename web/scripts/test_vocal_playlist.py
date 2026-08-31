import hashlib
import tempfile
import unittest
import wave
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import vocal_playlist as vocal


class VocalPlaylistTests(unittest.TestCase):
    def test_daily_deck_has_no_repetition_in_a_full_cycle(self):
        tracks = vocal.load_catalog()
        for profile in ("auto", "revenge", "sad-english"):
            count = sum(profile == "auto" or track["profile"] == profile for track in tracks)
            for start in (date(2026, 8, 31), date(2026, 12, 28)):
                selected = [vocal.select_track(9000 + day, profile, (start + timedelta(days=day)).isoformat(), "softbody-dvlad")
                            for day in range(count)]
                self.assertEqual(len({track["id"] for track in selected}), count)

    def test_retry_is_stable_and_channels_have_their_own_deck(self):
        first = vocal.select_track(1, daily_date="2026-08-31", channel_id="one")
        self.assertEqual(first, vocal.select_track(99, daily_date="2026-08-31", channel_id="one"))
        decks = [[vocal.select_track(day, channel_id=channel)["id"] for day in range(9)] for channel in ("one", "two")]
        self.assertNotEqual(*decks)
        self.assertEqual(vocal.select_track(123), vocal.select_track(123))

    def test_invalid_profile_date_and_empty_playlist_fail(self):
        for profile in ("original", "random-url", "", None):
            with self.assertRaises(ValueError):
                vocal.select_track(1, profile)
        with self.assertRaises(ValueError):
            vocal.select_track(1, daily_date="not-a-date")
        with self.assertRaises(ValueError):
            vocal.select_track(1, tracks=[])

    def test_only_official_https_sources_are_allowed(self):
        for url in ("http://ncs.io/song", "https://ncs.io.evil.test/x", "https://user@ncs.io/x",
                    "https://127.0.0.1/x", "file:///secret", "https://ncs.io:8080/x"):
            with self.assertRaises(ValueError):
                vocal.checked_url(url)
        self.assertEqual(vocal.checked_url("https://ncs.io/Royalty"), "https://ncs.io/Royalty")

    def page(self):
        return ('<a href="/track/download/abc-def">Download Track</a>'
                '<div data-url="https://ncsmusic.s3.eu-west-1.amazonaws.com/tracks/song.mp3"></div>'
                '<p id="panel-copy2">Song: Test &amp; Artist<br />'
                'Music provided by NoCopyrightSounds<br />Watch: https://example.com</p>')

    def test_exact_official_credit_is_preserved(self):
        audio, credit = vocal.parse_official_page(self.page())
        self.assertTrue(audio.endswith("song.mp3"))
        self.assertEqual(credit, "Song: Test & Artist\nMusic provided by NoCopyrightSounds\nWatch: https://example.com")
        for page in (self.page().replace('href="/track/download/abc-def"', ''),
                     self.page().replace('panel-copy2', 'missing'),
                     self.page().replace('ncsmusic.s3.eu-west-1.amazonaws.com', 'localhost')):
            with self.assertRaises(ValueError):
                vocal.parse_official_page(page)

    def test_preparation_has_a_contiguous_excerpt_and_complete_provenance(self):
        calls = []
        def fake_ffmpeg(command, **kwargs):
            calls.append(command)
            with wave.open(command[-1], "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\0" * (48000 * 2 * 2))
        with tempfile.TemporaryDirectory() as directory, patch.object(vocal, 'fetch_bytes', side_effect=[self.page().encode(), b"audio"]), patch.object(vocal.subprocess, 'run', side_effect=fake_ffmpeg):
            output = Path(directory) / "track.wav"
            result = vocal.prepare_vocal_soundtrack(1, output, 3, "revenge")
            self.assertTrue(output.is_file())
            self.assertFalse(result["music_generated"])
            self.assertTrue(result["music_has_vocals"])
            self.assertEqual(result["music_source_sha256"], hashlib.sha256(b"audio").hexdigest())
            self.assertEqual(result["music_license_url"], vocal.LICENSE_URL)
            self.assertIn("Music provided by NoCopyrightSounds", result["music_credit"])
            self.assertEqual(calls[0][calls[0].index("-t") + 1], "1")
            self.assertNotIn("-stream_loop", calls[0])

    def test_no_network_failure_is_disguised_as_instrumental_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(vocal, 'fetch_bytes', side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                vocal.prepare_vocal_soundtrack(30, Path(directory) / "track.wav", 1)

    def test_transient_download_errors_retry_the_same_source_but_permanent_errors_do_not(self):
        url = 'https://ncs.io/Mortals'
        with patch.object(vocal, '_fetch_bytes_once', side_effect=[URLError('offline'), b'audio']) as fetch, patch.object(vocal.time, 'sleep'):
            self.assertEqual(vocal.fetch_bytes(url, 50), b'audio')
            self.assertEqual(fetch.call_args_list[0], fetch.call_args_list[1])
        with patch.object(vocal, '_fetch_bytes_once', side_effect=HTTPError(url, 403, 'forbidden', {}, None)) as fetch, patch.object(vocal.time, 'sleep'):
            with self.assertRaises(HTTPError):
                vocal.fetch_bytes(url, 50)
            self.assertEqual(fetch.call_count, 1)
        with patch.object(vocal, '_fetch_bytes_once', side_effect=URLError('offline')) as fetch, patch.object(vocal.time, 'sleep'):
            with self.assertRaises(URLError):
                vocal.fetch_bytes(url, 50)
            self.assertEqual(fetch.call_count, 3)

    def test_daily_and_local_renderers_share_the_playlist_and_vocal_mix(self):
        scripts = Path(__file__).parent
        for filename in ("render-premium-3d.py", "finalize-premium-3d.py"):
            source = (scripts / filename).read_text(encoding="utf-8")
            self.assertIn("prepare_vocal_soundtrack", source)
            self.assertIn('"--music-profile"', source)
            self.assertIn('bool(soundtrack.get("music_has_vocals"))', source)
        workflow = (scripts.parents[1] / ".github/workflows/soft-body-artifact.yml").read_text(encoding="utf-8")
        self.assertIn('game.get("musicProfile", "auto")', workflow)
        self.assertIn('--date "$MUSIC_DATE" --channel-id "$MUSIC_CHANNEL"', workflow)
        self.assertIn('metadata["music_credit"]', workflow)


if __name__ == "__main__":
    unittest.main()
