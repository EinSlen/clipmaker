"""Private, reviewed spoken edit audio. Never a song/TTS fallback.

Cloud runners use the existing private control API. Offline tests/studios may
use CLIPMAKER_EDIT_AUDIO_DIR containing catalog.json and <sha256>.wav files.
An excerpt is a complete reviewed recording: no loop, random seek or time-stretch.
"""
from __future__ import annotations

import argparse
import hashlib
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
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

EDIT_PROFILES = ("edit-auto", "edit-sad", "edit-revenge")
BASE = "https://clipmaker-cloud-control.einslen.workers.dev/api/workflow/edit-audio"
MAX_BYTES = 5_700_000
USER_AGENT = "ClipMaker/1.0 (+https://github.com/EinSlen/clipmaker)"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Private audio redirects are forbidden")


def cloud(path: str, payload: dict | None = None, maximum: int = MAX_BYTES) -> bytes:
    token = os.environ.get("CLIPMAKER_UPLOAD_TOKEN", "")
    if not token:
        raise ValueError("Voix d’edit : CLIPMAKER_UPLOAD_TOKEN manque pour accéder à la bibliothèque privée.")
    for attempt in range(3):
        request = Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                   "User-Agent": USER_AGENT})
        try:
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                data = response.read(maximum + 1)
                if len(data) > maximum:
                    raise ValueError("Private audio response exceeds limit")
                return data
        except HTTPError as error:
            if error.code in (400, 401, 403, 404, 409):
                # Server-supplied user messages only, no credentials/URLs.
                try:
                    message = json.loads(error.read(4096)).get("error", f"Bibliothèque indisponible (HTTP {error.code})")
                except (ValueError, AttributeError):
                    message = f"Bibliothèque indisponible (HTTP {error.code})"
                raise ValueError(f"Voix d’edit : {message}") from None
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ValueError("Le service audio est indisponible ; aucun remplacement par une chanson.") from None
        except (URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise ValueError("Le service audio est injoignable ; aucun remplacement par une chanson.") from None
        time.sleep(attempt + 1)
    raise RuntimeError("Audio download retries exhausted")


def validate_clip(clip: dict, profile: str, duration: float = 30) -> dict:
    automatic = isinstance(clip, dict) and clip.get("reviewMode") == "freesound-whisper-v1"
    reviewed = isinstance(clip, dict) and clip.get("speechReviewed") is True and clip.get("rightsConfirmed") is True
    if automatic:
        reviewed = (clip.get("speechReviewed") is False and clip.get("rightsConfirmed") is False
                    and clip.get("rights") == "licensed" and clip.get("mix") == "voice-only"
                    and bool(re.fullmatch(r"[a-f0-9]{64}", clip.get("auditSha256", "")))
                    and bool(re.fullmatch(r"https://freesound\.org/people/[A-Za-z0-9_.-]+/sounds/[0-9]+/", clip.get("source", "")))
                    and bool(re.fullmatch(r"https://creativecommons\.org/(?:licenses/by/(?:2\.0|2\.5|3\.0|4\.0)|publicdomain/zero/1\.0)/", clip.get("rightsEvidence", ""))))
    if (profile not in EDIT_PROFILES or not isinstance(clip, dict)
            or clip.get("kind") != "spoken" or clip.get("language") != "en"
            or not reviewed
            or clip.get("active") is not True or clip.get("rights") not in ("original", "licensed")
            or clip.get("mood") not in ("sad", "revenge") or clip.get("mix") not in ("voice-only", "premixed")
            or (profile != "edit-auto" and profile != "edit-" + clip.get("mood", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", str(clip.get("id", "")))
            or clip.get("sha256", clip.get("id")) != clip.get("id")
            or any(not isinstance(clip.get(key), str) or not clip[key].strip() for key in ("title", "credit", "source", "rightsEvidence"))
            or not isinstance(clip.get("duration"), (int, float))
            or not math.isfinite(clip["duration"]) or not 10 <= clip["duration"] <= min(29.5, duration - .3)):
        raise ValueError("Extrait parlé absent, incomplet, désactivé ou non autorisé. Aucun substitut musical.")
    return clip


def select_clip(seed: int, profile: str, daily_date: str | None = None, channel_id: str = "preview", duration: float = 30) -> dict:
    if profile not in EDIT_PROFILES:
        raise ValueError("Unknown spoken edit profile")
    selected_date = daily_date or Date.today().isoformat()
    Date.fromisoformat(selected_date)
    # The GitHub manual renderer also supplies a date, but multiple manual
    # videos on that date are different previews, not retries of a daily job.
    # Real account/day jobs deliberately ignore seed changes on retry.
    daily_selection = bool(daily_date) and channel_id != "manual-3d"
    if not daily_selection:
        # A preview is identified by its seed, not the wall clock. Encoding
        # after midnight must fetch the same clip as the initial preflight.
        selected_date = "1970-01-01"
    offline = os.environ.get("CLIPMAKER_EDIT_AUDIO_DIR")
    if offline:
        root = Path(offline).resolve()
        data = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        pool = [validate_clip(clip, profile, duration) for clip in data["clips"]
                if clip.get("active") and (profile == "edit-auto" or profile == "edit-" + clip.get("mood", ""))]
        if not pool:
            raise ValueError("Aucune voix d’edit disponible. Importe des extraits parlés autorisés.")
        pool.sort(key=lambda clip: hashlib.sha256(f"{channel_id}:{profile}:{clip['id']}".encode()).hexdigest())
        key = f"edit-selection-v1:{channel_id}:{selected_date}:{profile}"
        index = (Date.fromisoformat(selected_date) - Date(1970, 1, 1)).days if daily_selection else seed
        # Persist a snapshot, so editing the library never changes a retry.
        pin = root / ("selection-" + hashlib.sha256(f"{key}:{'' if daily_selection else seed}".encode()).hexdigest() + ".json")
        if pin.exists():
            clip = json.loads(pin.read_text(encoding="utf-8"))
            if not any(item["id"] == clip["id"] for item in pool):
                raise ValueError("L’extrait prévu a été désactivé ; aucun remplacement automatique.")
        else:
            clip = {**pool[index % len(pool)], "sha256": pool[index % len(pool)]["id"],
                    "selectionKey": key if daily_selection else f"{key}:{seed}", "poolSize": len(pool)}
            try:
                with pin.open("x", encoding="utf-8") as handle:
                    json.dump(clip, handle)
            except FileExistsError:
                clip = json.loads(pin.read_text(encoding="utf-8"))
        return validate_clip(clip, profile, duration)
    # A preview seed gets its own key. Daily reruns ignore seed changes.
    channel = channel_id if daily_selection else f"preview-{seed}"
    result = json.loads(cloud("/select", {"profile": profile, "channel": channel, "date": selected_date,
                                          "seed": seed, "duration": duration}, maximum=12_000))
    return validate_clip(result["clip"], profile, duration)


def fetch_clip(clip: dict) -> bytes:
    root = os.environ.get("CLIPMAKER_EDIT_AUDIO_DIR")
    if root:
        path = Path(root).resolve() / (clip["id"] + ".wav")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Oversized spoken recording")
        data = path.read_bytes()
    else:
        data = cloud("/" + clip["id"])
    if hashlib.sha256(data).hexdigest() != clip["id"]:
        raise ValueError("Spoken recording integrity check failed")
    return data


def mix_filter(duration: float, premixed: bool) -> str:
    frames = round(duration * 48000)
    voice = (f"[0:a]loudnorm=I=-16:TP=-2:LRA=9,aresample=48000,"
             f"asetpts=N/SR/TB,aformat=channel_layouts=stereo,adelay=150:all=1,"
             f"apad=whole_len={frames},atrim=end_sample={frames},asetpts=N/SR/TB")
    if premixed:
        return voice + "[a]"
    return (voice + ",asplit=2[voice][key];"
            "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.12[bed];"
            "[bed][key]sidechaincompress=threshold=0.015:ratio=8:attack=10:release=450[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000,apad=whole_len={frames},atrim=end_sample={frames},asetpts=N/SR/TB[a]")


def prepare_edit_soundtrack(duration: float, output: Path, seed: int, profile: str,
                           daily_date: str | None = None, channel_id: str = "preview", *, synth_bed) -> dict:
    clip = select_clip(seed, profile, daily_date, channel_id, duration)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipmaker-edit-", dir=output.parent) as temporary:
        root = Path(temporary)
        voice = root / "spoken.wav"
        voice.write_bytes(fetch_clip(clip))
        with wave.open(str(voice), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (48000, 2, 2) or abs(wav.getnframes() / 48000 - clip["duration"]) > .002:
                raise ValueError("Spoken recording does not match its reviewed duration")
        command = [os.environ.get("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-y", "-i", str(voice)]
        if clip["mix"] == "voice-only":
            bed = root / "bed.wav"
            synth_bed(duration, bed, seed)
            command += ["-i", str(bed)]
        staged = root / "soundtrack.wav"
        command += ["-filter_complex", mix_filter(duration, clip["mix"] == "premixed"), "-map", "[a]",
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(staged)]
        subprocess.run(command, check=True, timeout=90)
        with wave.open(str(staged), "rb") as wav:
            if abs(wav.getnframes() / wav.getframerate() - duration) > .01:
                raise ValueError("Incomplete spoken edit mix")
        os.replace(staged, output)
    return {
        "music": clip["title"], "music_profile": "edit-" + clip["mood"], "requested_music_profile": profile,
        "music_mode": "spoken-edit", "music_generated": False, "music_provider": "private-edit-library",
        "music_has_vocals": True, "music_content_kind": "spoken", "music_language": "en",
        "music_track_id": clip["id"], "music_source_sha256": clip["id"], "music_source_url": clip["source"],
        "music_clearance": "verified-source-cc" if clip.get("reviewMode") == "freesound-whisper-v1" else "user-attested-cross-platform", "music_rights_evidence": clip["rightsEvidence"],
        "music_review_mode": clip.get("reviewMode", "owner-attested"), "music_audit_sha256": clip.get("auditSha256"),
        "music_credit": clip["credit"], "music_selection_key": clip["selectionKey"],
        "music_excerpt_start": 0, "music_excerpt_duration": clip["duration"], "music_voice_start": .15,
        "music_looped": False, "music_sentence_reviewed": clip["speechReviewed"], "music_preserves_original_mix": clip["mix"] == "premixed",
        "music_added_bed": clip["mix"] == "voice-only", "music_pool_size": clip.get("poolSize", 1),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=EDIT_PROFILES, required=True)
    parser.add_argument("--date")
    parser.add_argument("--channel-id", default="preview")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    clip = select_clip(args.seed, args.profile, args.date, args.channel_id)
    fetch_clip(clip)  # Fail before expensive Blender work if the audio is missing/corrupted.
    print(json.dumps({"ok": True, "id": clip["id"], "profile": args.profile, "duration": clip["duration"], "poolSize": clip.get("poolSize")}))
