"""Join TikTok's own analytics export to what the pipeline shipped that day.

Nothing here talks to TikTok. The numbers come from the CSV the creator
exports from TikTok Studio, and everything the pipeline chose for a given day
is recomputed from the date, because it is all deterministic: the obstacle
family follows the rotation, and the caption and tags follow the deck. Only
the scene seed is drawn per render, and it is not a variable worth tuning.

    python reach_report.py analytics.csv [--channel softbody-dvlad]

The report groups the days by what changed between them. It also says how
little a handful of days can tell you, because one video a day against four
obstacle families needs weeks before a difference means anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from soft_body_variants import rotated_auto_obstacle

DATE_HEADERS = ("date", "post time", "posted", "publish time", "published", "time", "create time")
VIEW_HEADERS = ("video views", "views", "play count", "plays", "total views", "vues")
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def find_column(headers, candidates):
    """Match a column by name without demanding TikTok keep one spelling."""
    lowered = {str(header or "").strip().lower(): header for header in headers}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for name, header in lowered.items():
        if any(candidate in name for candidate in candidates):
            return header
    return None


def parse_day(value):
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(text[: len(pattern) + 6], pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_count(value):
    text = str(value or "").strip().replace(",", "").replace(" ", "").replace(" ", "")
    if text.upper().endswith("K"):
        return int(float(text[:-1]) * 1_000)
    if text.upper().endswith("M"):
        return int(float(text[:-1]) * 1_000_000)
    try:
        return int(float(text))
    except ValueError:
        return None


def read_export(path: Path):
    """Return one (day, views) pair per row the export actually carries."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        day_header = find_column(headers, DATE_HEADERS)
        view_header = find_column(headers, VIEW_HEADERS)
        if not day_header or not view_header:
            raise SystemExit(
                "Could not find a date and a views column in the export.\n"
                f"Columns seen: {', '.join(str(header) for header in headers)}"
            )
        rows = []
        for row in reader:
            day, views = parse_day(row.get(day_header)), parse_count(row.get(view_header))
            if day and views is not None:
                rows.append((day, views))
    return rows


def captions_for(days, channel_id):
    """Ask the publisher's own caption module what each day was posted with."""
    script = (
        "import { publicationCopy } from './web/src/automation/edit-captions.mjs';\n"
        "const days = JSON.parse(process.argv[1]);\n"
        "const channelId = process.argv[2];\n"
        "const out = {};\n"
        "for (const date of days) {\n"
        "  const copy = publicationCopy({ channelId, date, raw: { music_profile: 'original' } });\n"
        "  out[date] = { caption: copy.caption, tags: copy.tags.join(' ') };\n"
        "}\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    done = subprocess.run(
        ["node", "--input-type=module", "-e", script,
         json.dumps([day.isoformat() for day in days]), channel_id],
        capture_output=True, text=True, encoding="utf-8", cwd=SCRIPT_DIR.parents[1],
    )
    if done.returncode:
        raise SystemExit(f"Could not read the caption deck:\n{done.stderr[-400:]}")
    return json.loads(done.stdout)


def grouped(rows, key):
    buckets = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(row["views"])
    return sorted(
        ((name, len(views), statistics.median(views), max(views)) for name, views in buckets.items()),
        key=lambda item: item[2], reverse=True,
    )


def report(rows, channel_id):
    days = sorted({day for day, _views in rows})
    copy = captions_for(days, channel_id)
    enriched = [
        {"day": day, "views": views,
         "obstacle": rotated_auto_obstacle(day, channel_id),
         "caption": copy[day.isoformat()]["caption"],
         "tags": copy[day.isoformat()]["tags"]}
        for day, views in rows
    ]
    counts = [row["views"] for row in enriched]
    print(f"{len(enriched)} posts, {days[0]} to {days[-1]}")
    print(f"views: median {statistics.median(counts):,.0f}  best {max(counts):,}  worst {min(counts):,}")
    for label, key in (("obstacle family", lambda row: row["obstacle"]),
                       ("tag footer", lambda row: row["tags"])):
        print(f"\nby {label}")
        for name, count, median, best in grouped(enriched, key):
            print(f"  {str(name)[:46]:<46} {count:>3} posts  median {median:>9,.0f}  best {best:>9,}")
    print("\nbest five days")
    for row in sorted(enriched, key=lambda item: item["views"], reverse=True)[:5]:
        print(f"  {row['day']}  {row['views']:>9,}  {row['obstacle']:<14} {row['caption'][:44]}")
    smallest = min((count for _n, count, _m, _b in grouped(enriched, lambda row: row["obstacle"])), default=0)
    print(
        "\nHow much of this to believe: one post a day across four obstacle families means "
        f"the thinnest group here holds {smallest} post(s). Views on a single video swing by "
        "an order of magnitude for reasons that have nothing to do with the render, so treat "
        "anything under roughly ten posts per group as a direction to test, never as a result."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", help="CSV exported from TikTok Studio analytics")
    parser.add_argument("--channel", default="softbody-dvlad")
    args = parser.parse_args()
    rows = read_export(Path(args.export))
    if not rows:
        raise SystemExit("The export carried no readable row.")
    report(rows, args.channel)


if __name__ == "__main__":
    main()
