#!/usr/bin/env python3
"""Return TikTok cookie health without exposing cookie values."""

import json
import math
import pickle
import re
import sys
import time
from pathlib import Path


def username_from_path(cookie_path: Path) -> str | None:
    match = re.fullmatch(r"tiktok_session-([A-Za-z0-9._]{2,32})\.cookie", cookie_path.name)
    return match.group(1) if match else None


def expiry_of(cookie: dict) -> float:
    raw = cookie.get("expiry", cookie.get("expires", 0)) or 0
    try:
        value = float(raw)
        return value if math.isfinite(value) else 0
    except (TypeError, ValueError):
        return 0


def inspect_account(cookie_path: Path) -> dict | None:
    username = username_from_path(cookie_path)
    if not username:
        return None
    try:
        with cookie_path.open("rb") as handle:
            cookies = pickle.load(handle)
        session = next((item for item in cookies if item.get("name") == "sessionid"), {})
        datacenter = next((item for item in cookies if item.get("name") == "tt-target-idc"), {})
        expiry = expiry_of(session)
        expired = bool(expiry and expiry <= time.time() + 60)
        ready = bool(session.get("value") and datacenter.get("value") and not expired)
        return {
            "username": username,
            "cookieFile": cookie_path.name,
            "ready": ready,
            "expired": expired,
            "sessionPresent": bool(session.get("value")),
            "datacenterPresent": bool(datacenter.get("value")),
            "expiresAt": int(expiry) if expiry else None,
        }
    except Exception as error:  # The API needs a safe diagnostic, not a traceback.
        return {
            "username": username,
            "cookieFile": cookie_path.name,
            "ready": False,
            "expired": False,
            "sessionPresent": False,
            "datacenterPresent": False,
            "expiresAt": None,
            "error": f"Unreadable cookie file: {type(error).__name__}",
        }


def main() -> int:
    cookie_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("CookiesDir").resolve()
    accounts = [
        account
        for cookie_path in sorted(cookie_dir.glob("tiktok_session-*.cookie"))
        if (account := inspect_account(cookie_path)) is not None
    ]
    print(json.dumps({"accounts": accounts}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
