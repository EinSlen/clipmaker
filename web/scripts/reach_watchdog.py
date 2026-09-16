#!/usr/bin/env python3
"""Say out loud when the account has stopped reaching anybody.

This reads a capture written by `tiktok-analytics-agent.cjs`, which is the
account's own TikTok Studio data, and answers the one question nobody was
asking while the daily kept going out: is the feed still showing this?

    node web/scripts/tiktok-analytics-agent.cjs --user dvlad --out capture.json
    python web/scripts/reach_watchdog.py capture.json

It exists because of what those numbers eventually said. Twenty three posts
went out private, so they could not be seen at all, and once that was fixed
the four public ones sat at zero views for three days with For You at exactly
zero percent of traffic. Every single signal was already in Studio the whole
time. Nothing read it, so nothing said anything, for six weeks.

The verdict is printed as markdown for the daily status issue and repeated on
one CLIPMAKER_REACH line so a workflow can pick it up without parsing prose.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# A healthy account is carried by the feed, not by its own back catalogue.
# Anything under this share means the recommendation system is not handing
# the posts to anybody who does not already know the profile.
FOR_YOU_FLOOR = 0.05
# Three in a row, because one zero is an unlucky post and two is a bad week.
ZERO_VIEW_STREAK = 3
# A post needs a night before its view count means anything.
MIN_POST_AGE_HOURS = 24
PRIVATE_VISIBILITY = 2
MARKER = "CLIPMAKER_REACH:"


def captured_at(capture: dict) -> float:
    for response in capture.get("responses", []):
        now = (response.get("payload") or {}).get("extra", {}).get("now")
        if isinstance(now, (int, float)) and now > 0:
            return float(now) / 1000
    return time.time()


def traffic_sources(capture: dict) -> dict:
    """The share of views each surface sent, as TikTok Studio reports it."""
    for response in capture.get("responses", []):
        percent = (response.get("payload") or {}).get("video_page_percent")
        if not percent:
            continue
        return {
            str(entry.get("key")): float(entry.get("value") or 0)
            for entry in percent.get("value", [])
            if entry.get("key")
        }
    return {}


def account_numbers(capture: dict) -> dict:
    numbers = {}
    for response in capture.get("responses", []):
        payload = response.get("payload") or {}
        for field, name in (("follower_num", "followers"), ("unique_viewer_num", "uniqueViewers")):
            value = payload.get(field)
            if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
                numbers[name] = int(value["value"])
        history = payload.get("vv_history")
        if isinstance(history, list) and history:
            numbers["viewsPerDay"] = [int(entry.get("value") or 0) for entry in history]
    return numbers


def posts(capture: dict) -> list:
    """Every post Studio listed, newest first, deduplicated across pages."""
    collected = {}
    for response in capture.get("responses", []):
        payload = response.get("payload") or {}
        for item in payload.get("item_list") or []:
            identifier = str(item.get("item_id") or "")
            if not identifier:
                continue
            collected[identifier] = {
                "id": identifier,
                "createdAt": int(item.get("create_time") or 0),
                "visibility": int(item.get("visibility") or 0),
                "plays": int(item.get("play_count") or 0),
                "inReview": bool(item.get("in_review")),
                "caption": str(item.get("desc") or ""),
            }
    return sorted(collected.values(), key=lambda entry: entry["createdAt"], reverse=True)


def zero_view_streak(entries: list, now: float) -> list:
    """The run of settled public posts that nobody has watched."""
    streak = []
    for entry in entries:
        if entry["visibility"] == PRIVATE_VISIBILITY or entry["inReview"]:
            continue
        if now - entry["createdAt"] < MIN_POST_AGE_HOURS * 3600:
            continue
        if entry["plays"]:
            break
        streak.append(entry)
    return streak


def private_streak(entries: list, now: float) -> list:
    """Posts that went out invisible, which is the failure nobody can see."""
    streak = []
    for entry in entries:
        if now - entry["createdAt"] < MIN_POST_AGE_HOURS * 3600:
            continue
        if entry["visibility"] != PRIVATE_VISIBILITY:
            break
        streak.append(entry)
    return streak


def verdict(capture: dict) -> dict:
    now = captured_at(capture)
    entries = posts(capture)
    sources = traffic_sources(capture)
    for_you = sources.get("For You")
    silent = zero_view_streak(entries, now)
    invisible = private_streak(entries, now)
    alarms = []
    if for_you is not None and for_you < FOR_YOU_FLOOR:
        alarms.append({
            "code": "for-you-share",
            "detail": f"For You sent {for_you * 100:.1f}% of the views over the last 7 days.",
        })
    if len(silent) >= ZERO_VIEW_STREAK:
        alarms.append({
            "code": "zero-view-streak",
            "detail": f"The last {len(silent)} settled public posts have no views at all.",
        })
    if len(invisible) >= ZERO_VIEW_STREAK:
        alarms.append({
            "code": "published-private",
            "detail": f"The last {len(invisible)} posts went out private, so nobody could see them.",
        })
    return {
        "account": capture.get("account"),
        "capturedAt": capture.get("capturedAt"),
        "signedIn": bool(capture.get("signedIn")),
        "trafficSources": sources,
        "posts": len(entries),
        "zeroViewStreak": len(silent),
        "privateStreak": len(invisible),
        "alarms": alarms,
        **account_numbers(capture),
    }


def report(result: dict) -> str:
    lines = [f"## Portée TikTok · {result.get('account') or 'compte inconnu'}"]
    if not result["signedIn"]:
        lines.append("- La session n'a pas ouvert Studio, donc ces chiffres ne veulent rien dire.")
    sources = result.get("trafficSources") or {}
    if sources:
        shares = ", ".join(f"{name} {share * 100:.1f}%" for name, share in sources.items())
        lines.append(f"- Sources de trafic sur 7 jours : {shares}")
    if "followers" in result:
        lines.append(f"- {result['followers']} abonnés, {result.get('uniqueViewers', 0)} spectateurs uniques")
    lines.append(f"- {result['posts']} posts lus dans Studio")
    for alarm in result["alarms"]:
        lines.append(f"- ALERTE {alarm['code']} : {alarm['detail']}")
    if not result["alarms"]:
        lines.append("- Aucun seuil franchi.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="JSON written by tiktok-analytics-agent.cjs")
    parser.add_argument("--fail-on-alarm", action="store_true",
                        help="Exit non-zero when a threshold is crossed, for a gate rather than a note")
    arguments = parser.parse_args(argv)
    capture = json.loads(arguments.capture.read_text(encoding="utf-8"))
    result = verdict(capture)
    print(report(result))
    print(MARKER + json.dumps(result, separators=(",", ":")))
    return 1 if arguments.fail_on_alarm and result["alarms"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
