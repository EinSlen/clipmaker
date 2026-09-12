"""The reach report has to survive whatever spelling the export arrives with."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import reach_report


class ExportReadingTests(unittest.TestCase):
    def test_columns_are_found_whatever_the_export_calls_them(self):
        for headers, expected in (
            (["Date", "Video views"], ("Date", "Video views")),
            (["Post time", "Views", "Likes"], ("Post time", "Views")),
            (["publish time (UTC)", "total views"], ("publish time (UTC)", "total views")),
            (["Titre", "Vues", "Date"], ("Date", "Vues")),
        ):
            self.assertEqual(
                (reach_report.find_column(headers, reach_report.DATE_HEADERS),
                 reach_report.find_column(headers, reach_report.VIEW_HEADERS)),
                expected, headers)
        self.assertIsNone(reach_report.find_column(["likes", "shares"], reach_report.VIEW_HEADERS))

    def test_dates_and_counts_are_read_in_every_shape_tiktok_writes_them(self):
        for text in ("2026-09-12", "2026/09/12", "2026-09-12 08:30:00", "2026-09-12T08:30:00Z"):
            self.assertEqual(reach_report.parse_day(text), date(2026, 9, 12), text)
        self.assertEqual(reach_report.parse_day("12/09/2026"), date(2026, 9, 12))
        self.assertIsNone(reach_report.parse_day(""))
        self.assertIsNone(reach_report.parse_day("not a date"))
        for text, expected in (("1,234", 1234), ("1234", 1234), ("12.5K", 12_500),
                               ("2M", 2_000_000), ("0", 0)):
            self.assertEqual(reach_report.parse_count(text), expected, text)
        self.assertIsNone(reach_report.parse_count("n/a"))

    def test_unreadable_rows_are_skipped_and_a_useless_export_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.csv"
            good.write_text(
                "Post time,Video views,Likes\n"
                "2026-09-10,\"12,000\",30\n"
                "not a date,900,4\n"
                "2026-09-11,n/a,7\n"
                "2026-09-12,8K,11\n",
                encoding="utf-8-sig")
            self.assertEqual(reach_report.read_export(good),
                             [(date(2026, 9, 10), 12_000), (date(2026, 9, 12), 8_000)])
            useless = Path(directory) / "useless.csv"
            useless.write_text("caption,likes\nhello,3\n", encoding="utf-8-sig")
            with self.assertRaisesRegex(SystemExit, "caption"):
                reach_report.read_export(useless)


class GroupingTests(unittest.TestCase):
    def test_groups_are_ordered_by_median_and_keep_their_count(self):
        rows = [
            {"views": 10, "obstacle": "peg-grid"},
            {"views": 30, "obstacle": "peg-grid"},
            {"views": 100, "obstacle": "moving-slide"},
        ]
        self.assertEqual(reach_report.grouped(rows, lambda row: row["obstacle"]),
                         [("moving-slide", 1, 100, 100), ("peg-grid", 2, 20, 30)])


if __name__ == "__main__":
    unittest.main()
