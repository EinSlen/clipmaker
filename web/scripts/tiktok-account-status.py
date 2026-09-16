#!/usr/bin/env python3
"""Return TikTok cookie health without exposing cookie values."""

import json
import math
import pickle
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Two cookie files can be two logins of one account, and nothing in the file
# says so: the name is a label somebody typed at login time. This pipeline
# ran two channels against what looked like two accounts for weeks, posting
# twice a day to the same one. Studio answers with the numeric account id for
# the price of one request, and that id is what tells them apart.
IDENTITY_URL = "https://www.tiktok.com/tiktokstudio/api/web/user"
IDENTITY_TIMEOUT_SECONDS = 20
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


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


def account_id_of(cookies: list) -> str | None:
    """Ask Studio which account this session belongs to, never printing it back."""
    header = "; ".join(
        f"{item['name']}={item['value']}"
        for item in cookies
        if item.get("name") and item.get("value")
    )
    if not header:
        return None
    request = urllib.request.Request(
        IDENTITY_URL,
        headers={
            "Cookie": header,
            "User-Agent": BROWSER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.tiktok.com/tiktokstudio",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=IDENTITY_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # A missing identity is reported as unknown. It must never turn a
        # healthy cookie into a failed publication.
        return None
    identity = payload.get("userId") or (payload.get("userBaseInfo") or {}).get("UserProfile", {}).get("Id")
    return str(identity) if identity else None


def inspect_account(cookie_path: Path, identity: bool = False) -> dict | None:
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
            "accountId": account_id_of(cookies) if identity and ready else None,
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
            "accountId": None,
            "error": f"Unreadable cookie file: {type(error).__name__}",
        }


def shared_accounts(accounts: list) -> list:
    """Group the labels that turned out to be the same TikTok account."""
    owners: dict[str, list] = {}
    for account in accounts:
        identity = account.get("accountId")
        if identity:
            owners.setdefault(identity, []).append(account["username"])
    return [
        {"accountId": identity, "usernames": sorted(names)}
        for identity, names in sorted(owners.items())
        if len(names) > 1
    ]


def main() -> int:
    arguments = [value for value in sys.argv[1:] if not value.startswith("--")]
    identity = "--identity" in sys.argv[1:]
    cookie_dir = Path(arguments[0]).resolve() if arguments else Path("CookiesDir").resolve()
    accounts = [
        account
        for cookie_path in sorted(cookie_dir.glob("tiktok_session-*.cookie"))
        if (account := inspect_account(cookie_path, identity)) is not None
    ]
    report = {"accounts": accounts}
    if identity:
        report["shared"] = shared_accounts(accounts)
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
