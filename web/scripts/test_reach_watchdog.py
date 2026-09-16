"""The watchdog has to name the two failures this account actually had."""

from __future__ import annotations

import unittest

import reach_watchdog

NOW = 1_789_589_661
HOUR = 3600


def post(identifier, age_hours, plays=0, visibility=1, in_review=False):
    return {
        "item_id": str(identifier),
        "create_time": str(int(NOW - (age_hours * HOUR))),
        "play_count": str(plays),
        "visibility": visibility,
        "in_review": in_review,
        "desc": f"post {identifier}",
    }


def capture(items, for_you=0.4, followers=64):
    return {
        "account": "softbody",
        "signedIn": True,
        "capturedAt": "2026-09-16T20:19:08.152Z",
        "responses": [
            {"url": "insight", "payload": {
                "extra": {"now": NOW * 1000},
                "video_page_percent": {"value": [
                    {"key": "For You", "value": for_you},
                    {"key": "Search", "value": round(1 - for_you, 3)},
                ]},
            }},
            {"url": "insight", "payload": {
                "follower_num": {"value": followers},
                "unique_viewer_num": {"value": 56},
                "vv_history": [{"value": 8}, {"value": 15}],
            }},
            {"url": "item_list", "payload": {"item_list": items}},
        ],
    }


class ReadingStudioTests(unittest.TestCase):
    def test_traffic_and_numbers_are_read_from_whichever_response_carries_them(self):
        result = reach_watchdog.verdict(capture([post(1, 48, plays=120)]))
        self.assertEqual(result["trafficSources"]["For You"], 0.4)
        self.assertEqual(result["followers"], 64)
        self.assertEqual(result["uniqueViewers"], 56)
        self.assertEqual(result["viewsPerDay"], [8, 15])
        self.assertEqual(result["posts"], 1)

    def test_posts_are_deduplicated_across_pages_and_sorted_newest_first(self):
        paged = capture([post(1, 48), post(2, 24)])
        paged["responses"].append({"url": "item_list", "payload": {"item_list": [post(2, 24), post(3, 72)]}})
        self.assertEqual([entry["id"] for entry in reach_watchdog.posts(paged)], ["2", "1", "3"])

    def test_an_empty_capture_says_nothing_rather_than_crashing(self):
        result = reach_watchdog.verdict({"account": "softbody", "responses": []})
        self.assertEqual(result["alarms"], [])
        self.assertEqual(result["posts"], 0)
        self.assertFalse(result["signedIn"])


class SilenceTests(unittest.TestCase):
    def test_a_fresh_post_is_not_yet_evidence_of_anything(self):
        entries = reach_watchdog.posts(capture([post(1, 2), post(2, 3), post(3, 4)]))
        self.assertEqual(reach_watchdog.zero_view_streak(entries, NOW), [])

    def test_private_posts_and_reviews_are_skipped_rather_than_counted_as_silence(self):
        items = [post(1, 24, visibility=2), post(2, 48, in_review=True), post(3, 72, plays=90)]
        entries = reach_watchdog.posts(capture(items))
        self.assertEqual(reach_watchdog.zero_view_streak(entries, NOW), [])

    def test_three_settled_public_posts_without_a_single_view_raise_the_alarm(self):
        items = [post(1, 25), post(2, 49), post(3, 73), post(4, 97, plays=40)]
        result = reach_watchdog.verdict(capture(items))
        self.assertEqual(result["zeroViewStreak"], 3)
        self.assertEqual([alarm["code"] for alarm in result["alarms"]], ["zero-view-streak"])

    def test_posting_in_private_is_reported_as_its_own_failure(self):
        # Twenty three days of this went out unnoticed because a private post
        # looks exactly like a published one everywhere except Studio.
        items = [post(index, 24 * (index + 1), visibility=2) for index in range(5)]
        result = reach_watchdog.verdict(capture(items))
        self.assertEqual(result["privateStreak"], 5)
        self.assertIn("published-private", [alarm["code"] for alarm in result["alarms"]])


class ForYouTests(unittest.TestCase):
    def test_a_feed_that_stopped_showing_the_account_is_named(self):
        result = reach_watchdog.verdict(capture([post(1, 48, plays=20)], for_you=0.0))
        self.assertEqual([alarm["code"] for alarm in result["alarms"]], ["for-you-share"])
        self.assertIn("0.0%", result["alarms"][0]["detail"])

    def test_an_account_the_feed_still_carries_raises_nothing(self):
        items = [post(index, 24 * (index + 1), plays=300) for index in range(5)]
        result = reach_watchdog.verdict(capture(items, for_you=0.72))
        self.assertEqual(result["alarms"], [])
        self.assertIn("Aucun seuil franchi", reach_watchdog.report(result))

    def test_the_floor_is_a_floor_and_not_a_rounding_accident(self):
        self.assertEqual(reach_watchdog.verdict(capture([], for_you=0.05))["alarms"], [])
        self.assertEqual(len(reach_watchdog.verdict(capture([], for_you=0.049))["alarms"]), 1)


if __name__ == "__main__":
    unittest.main()
