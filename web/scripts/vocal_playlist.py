"""Rotate real English vocal recordings cleared for independent creator UGC.

Only official NCS pages and their explicitly advertised audio files are used.
No YouTube/TikTok ripping, scraped lyrics, TTS, or instrumental substitution.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import subprocess
import tempfile
import time
import wave
from datetime import date as Date
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROFILES = ("auto", "revenge", "sad-english", "original")
CATALOG = Path(__file__).resolve().parent.parent / "data" / "vocal-playlists.json"
ALLOWED_HOSTS = frozenset(("ncs.io", "www.ncs.io", "ncsmusic.s3.eu-west-1.amazonaws.com"))
LICENSE_URL = "https://ncs.io/usage-policy/terms"
MAX_AUDIO_BYTES = 48 * 1024 * 1024


def checked_url(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Soundtrack URL is not an approved official HTTPS source")
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_bytes_once(url: str, limit: int) -> bytes:
    request = Request(checked_url(url), headers={"User-Agent": "ClipMaker/1.0 vocal-playlist"})
    with build_opener(SafeRedirect()).open(request, timeout=30) as response:
        checked_url(response.geturl())
        declared = int(response.headers.get("Content-Length", "0"))
        if declared > limit:
            raise ValueError("Soundtrack response exceeds the size limit")
        chunks = []
        total = 0
        while True:
            chunk = response.read(min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise ValueError("Soundtrack response exceeds the size limit")
        if not total:
            raise ValueError("Empty soundtrack response")
        return b"".join(chunks)


def fetch_bytes(url: str, limit: int) -> bytes:
    # A transient provider/network outage must not change the selected song.
    for attempt in range(3):
        try:
            return _fetch_bytes_once(url, limit)
        except HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)
    raise RuntimeError("Soundtrack download retries exhausted")


def load_catalog(path: Path = CATALOG) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tracks = payload.get("tracks")
    if payload.get("version") != 1 or payload.get("licenseUrl") != LICENSE_URL or not isinstance(tracks, list) or not tracks:
        raise ValueError("Invalid vocal playlist catalog")
    ids = set()
    for track in tracks:
        if (not isinstance(track, dict) or not re.fullmatch(r"[a-z0-9-]+", str(track.get("id", "")))
                or track["id"] in ids or not re.fullmatch(r"[A-Za-z0-9_-]+", str(track.get("slug", "")))
                or track.get("profile") not in ("revenge", "sad-english")
                or not isinstance(track.get("start"), (float, int))
                or not math.isfinite(track["start"]) or not 0 <= track["start"] <= 300
                or not track.get("title") or not track.get("artist")):
            raise ValueError("Invalid or duplicate vocal playlist track")
        ids.add(track["id"])
    return tracks


def select_track(seed: int, profile: str = "auto", daily_date: str | None = None,
                 channel_id: str = "preview", tracks: list[dict] | None = None) -> dict:
    if profile not in PROFILES or profile == "original":
        raise ValueError("A vocal playlist must be auto, revenge or sad-english")
    pool = [track for track in (tracks if tracks is not None else load_catalog())
            if profile == "auto" or track["profile"] == profile]
    if not pool:
        raise ValueError("The selected vocal playlist is empty")
    # A channel-specific shuffled deck guarantees no track repetition until
    # the whole selected pool has played. It also works on stateless runners.
    pool.sort(key=lambda track: hashlib.sha256(f"vocal-v1:{channel_id}:{profile}:{track['id']}".encode()).digest())
    index = Date.fromisoformat(daily_date).toordinal() if daily_date else seed
    return dict(pool[index % len(pool)])


def parse_official_page(page: str) -> tuple[str, str]:
    # Require an official download button too; a random data-url is not proof.
    if not re.search(r'href="/track/download/[a-f0-9-]+"', page):
        raise ValueError("The official page no longer offers this recording")
    audio = re.search(r'data-url="([^"]+)"', page)
    if not audio:
        raise ValueError("The official page contains no audio file")
    audio_url = checked_url(html.unescape(audio.group(1)))
    if urlparse(audio_url).hostname != "ncsmusic.s3.eu-west-1.amazonaws.com":
        raise ValueError("Unexpected NCS media host")
    # Preserve the exact publisher-supplied attribution, not guessed credits.
    credit_match = re.search(r'<p[^>]+id="panel-copy2"[^>]*>(.*?)</p>', page, re.S | re.I)
    if not credit_match:
        raise ValueError("The official attribution block is missing")
    credit = re.sub(r'<br\s*/?>', '\n', credit_match.group(1), flags=re.I)
    credit = html.unescape(re.sub(r'<[^>]+>', '', credit)).strip()
    credit = '\n'.join(line.strip() for line in credit.splitlines() if line.strip())
    if "Music provided by NoCopyrightSounds" not in credit:
        raise ValueError("The official NCS credit could not be verified")
    return audio_url, credit


def prepare_vocal_soundtrack(duration: float, output: Path, seed: int,
                            profile: str = "auto", daily_date: str | None = None,
                            channel_id: str = "preview") -> dict:
    if not math.isfinite(duration) or not 1 <= duration <= 60:
        raise ValueError("Soundtrack duration must be between 1 and 60 seconds")
    track = select_track(seed, profile, daily_date, channel_id)
    source_url = f"https://ncs.io/{track['slug']}"
    page_bytes = fetch_bytes(source_url, 2 * 1024 * 1024)
    audio_url, credit = parse_official_page(page_bytes.decode("utf-8"))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipmaker-vocal-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        audio = root / "source.mp3"
        audio_bytes = fetch_bytes(audio_url, MAX_AUDIO_BYTES)
        audio.write_bytes(audio_bytes)
        staged = root / "excerpt.wav"
        # A contiguous vocal verse, never random micro-cuts or pitch changes.
        subprocess.run([
            os.environ.get("FFMPEG_BIN", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(track["start"]), "-i", str(audio), "-t", str(duration), "-vn",
            "-af", f"afade=t=in:d=0.08,afade=t=out:st={max(0, duration - 0.35):.3f}:d=0.35",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(staged),
        ], check=True, timeout=90)
        with wave.open(str(staged), "rb") as wav:
            if wav.getnchannels() != 2 or wav.getframerate() != 48000 or abs(wav.getnframes() / 48000 - duration) > 0.04:
                raise ValueError("Vocal excerpt is incomplete or has an invalid format")
        os.replace(staged, output)
    return {
        "music": f"{track['title']} — {track['artist']}",
        "music_profile": track["profile"], "requested_music_profile": profile,
        "music_generated": False, "music_provider": "ncs", "music_has_vocals": True,
        "music_track_id": track["id"], "music_excerpt_start": track["start"],
        "music_source_url": source_url, "music_license_url": LICENSE_URL,
        "music_clearance": "ncs-independent-creator-ugc", "music_credit": credit,
        "music_source_sha256": hashlib.sha256(audio_bytes).hexdigest(),
        "music_page_sha256": hashlib.sha256(page_bytes).hexdigest(),
        "music_selection_key": f"{channel_id}:{daily_date or seed}:{profile}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--profile", choices=PROFILES[:-1], default="auto")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--date")
    parser.add_argument("--channel-id", default="preview")
    args = parser.parse_args()
    metadata = prepare_vocal_soundtrack(args.duration, Path(args.output), args.seed, args.profile, args.date, args.channel_id)
    Path(args.output).with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
