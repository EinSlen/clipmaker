"""Two labels can be one account, and only the identity check can say so."""

from __future__ import annotations

import importlib.util
import pickle
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# The script is named for the command line, with hyphens, so it has to be
# loaded by path rather than imported by name.
_SPEC = importlib.util.spec_from_file_location(
    "tiktok_account_status", Path(__file__).with_name("tiktok-account-status.py"),
)
status = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(status)


def cookie_file(directory: Path, username: str, expiry: float | None = None) -> Path:
    path = directory / f"tiktok_session-{username}.cookie"
    with path.open("wb") as handle:
        pickle.dump([
            {"name": "sessionid", "value": f"session-{username}", "expiry": expiry or (time.time() + 86400)},
            {"name": "tt-target-idc", "value": "alisg"},
        ], handle)
    return path


class CookieHealthTests(unittest.TestCase):
    def test_only_session_files_are_read_and_the_label_comes_from_the_name(self):
        self.assertEqual(status.username_from_path(Path("tiktok_session-dvlad.cookie")), "dvlad")
        self.assertEqual(status.username_from_path(Path("tiktok_session-a.b_2.cookie")), "a.b_2")
        self.assertIsNone(status.username_from_path(Path("empty.cookie")))
        self.assertIsNone(status.username_from_path(Path("tiktok_session-.cookie")))

    def test_an_expired_session_is_never_reported_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fresh = status.inspect_account(cookie_file(directory, "live"))
            stale = status.inspect_account(cookie_file(directory, "dead", expiry=time.time() - 10))
            self.assertTrue(fresh["ready"])
            self.assertFalse(fresh["expired"])
            self.assertFalse(stale["ready"])
            self.assertTrue(stale["expired"])

    def test_the_identity_lookup_is_opt_in_so_the_default_never_touches_the_network(self):
        with tempfile.TemporaryDirectory() as raw:
            path = cookie_file(Path(raw), "dvlad")
            with patch.object(status.urllib.request, "urlopen") as opened:
                account = status.inspect_account(path)
            opened.assert_not_called()
            self.assertIsNone(account["accountId"])

    def test_an_unreadable_cookie_is_a_diagnostic_rather_than_a_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tiktok_session-broken.cookie"
            path.write_bytes(b"not a pickle")
            account = status.inspect_account(path)
            self.assertFalse(account["ready"])
            self.assertIn("Unreadable cookie file", account["error"])


class SharedAccountTests(unittest.TestCase):
    def test_two_labels_on_one_account_are_reported_together(self):
        # The real case: softbody-dvlad and story-dvlad published to what the
        # configuration called two accounts and TikTok called one.
        shared = status.shared_accounts([
            {"username": "dvlad", "accountId": "7115772658990875653"},
            {"username": "dvlad2", "accountId": "7115772658990875653"},
            {"username": "other", "accountId": "7000000000000000001"},
        ])
        self.assertEqual(shared, [{
            "accountId": "7115772658990875653",
            "usernames": ["dvlad", "dvlad2"],
        }])

    def test_genuinely_separate_accounts_report_nothing(self):
        self.assertEqual(status.shared_accounts([
            {"username": "softbody", "accountId": "1"},
            {"username": "story", "accountId": "2"},
        ]), [])

    def test_an_unknown_identity_never_invents_a_collision(self):
        # A TikTok outage leaves the id unknown. Two unknowns are not a match.
        self.assertEqual(status.shared_accounts([
            {"username": "softbody", "accountId": None},
            {"username": "story", "accountId": None},
        ]), [])


class IdentityRequestTests(unittest.TestCase):
    def test_the_account_id_is_read_from_either_shape_studio_answers_with(self):
        for payload, expected in (
            (b'{"userId": 7115772658990875653}', "7115772658990875653"),
            (b'{"userBaseInfo": {"UserProfile": {"Id": "42"}}}', "42"),
            (b'{"statusCode": 0}', None),
        ):
            with patch.object(status.urllib.request, "urlopen") as opened:
                opened.return_value.__enter__.return_value.read.return_value = payload
                self.assertEqual(status.account_id_of([{"name": "sessionid", "value": "x"}]), expected)

    def test_a_network_failure_leaves_the_identity_unknown_instead_of_raising(self):
        with patch.object(status.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(status.account_id_of([{"name": "sessionid", "value": "x"}]))
        self.assertIsNone(status.account_id_of([]))


if __name__ == "__main__":
    unittest.main()
