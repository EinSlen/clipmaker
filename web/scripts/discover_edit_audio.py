"""Bounded Internet discovery of original CC0/CC-BY spoken recordings.

Search is live, not a fixed playlist. Keep whole short recordings: ASR is an
automatic filter, never a claim of human review or a guarantee of legal title.
No TikTok/YouTube ripping, voice cloning, model training or paid API required.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import html
import io
import json
import math
import os
import re
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from edit_audio import BASE, MAX_BYTES, NoRedirect, USER_AGENT, cloud

SEARCH = "https://api.openverse.org/v1/audio/"
VERSION = "freesound-whisper-v1"
WHISPER_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
QUERIES = ("sad speech", "heartbreak spoken", "lonely speech", "emotional dialogue",
           "sad saying", "revenge speech", "regret voice", "missing someone voice",
           "breakup speech", "determined voice", "melancholy spoken", "lost love speech")
LICENSES = {"https://creativecommons.org/licenses/by/" + v + "/" for v in ("2.0", "2.5", "3.0", "4.0")}
LICENSES.add("https://creativecommons.org/publicdomain/zero/1.0/")
SPOKEN = {"speech", "spoken", "speaking", "saying", "sentence", "dialogue", "acting", "voiceover", "voice-over"}
EXCLUDED = re.compile(r"\b(singing|song|lyrics|scream\w*|gibberish|horror|synthesizer|movie.lines|movie|television|tv|anime|cover|remix|tts|ai.generated|text.to.speech|impression|impersonation)\b", re.I)
OWN = re.compile(r"\b(me saying|my (?:own )?voice|i recorded|recorded (?:by me|myself)|my (?:original )?(?:recording|samples)|original (?:dialogue|monologue)|voice acting by me)\b", re.I)
SAD = re.compile(r"\b(miss|alone|lonely|sorry|love|loved|lost|hurt|pain|cry|crying|tears|heart|leave|left|goodbye|forget|forgot|remember|nothing|regret|broken|sad)\b", re.I)
REVENGE = re.compile(r"\b(revenge|betray\w*|stronger|fight|payback|prove|rise|enemy|enemies|win|revenge|never give up)\b", re.I)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower().replace("’", "'"))


def transcript_hash(text: str) -> str:
    return sha(" ".join(normalized_words(text)).encode())


def safe_url(url: str, kind: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
        raise ValueError("unsafe-url")
    valid = (kind == "search" and parsed.netloc == "api.openverse.org" and parsed.path == "/v1/audio/")
    valid |= (kind == "page" and parsed.netloc == "freesound.org" and re.fullmatch(r"/people/[A-Za-z0-9_.-]+/sounds/[0-9]+/", parsed.path) is not None and not parsed.query)
    valid |= (kind == "audio" and parsed.netloc == "cdn.freesound.org" and re.fullmatch(r"/previews/[0-9]+/[0-9]+_[0-9]+-hq\.mp3", parsed.path) is not None and not parsed.query)
    if not valid:
        raise ValueError("unapproved-source-url")
    return url


def download(url: str, kind: str, maximum: int) -> bytes:
    request = Request(safe_url(url, kind), headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    # No credentials on public requests; refuse redirects rather than follow
    # an index entry to localhost, a login page or an unapproved media server.
    with build_opener(NoRedirect()).open(request, timeout=25) as response:
        if int(response.headers.get("Content-Length", 0)) > maximum:
            raise ValueError("source-too-large")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("source-too-large")
    return data


def candidate(item: dict) -> dict:
    if item.get("source") != "freesound" or item.get("provider") != "freesound" or item.get("mature") is not False or item.get("unstable__sensitivity"):
        raise ValueError("source-or-sensitivity")
    license_url = item.get("license_url", "")
    expected = ("https://creativecommons.org/publicdomain/zero/1.0/" if item.get("license") == "cc0"
                else f"https://creativecommons.org/licenses/by/{item.get('license_version')}/" if item.get("license") == "by" else "")
    if license_url not in LICENSES or license_url != expected:
        raise ValueError("license-not-commercial-remix")
    tags = {str(tag.get("name", "")).lower() for tag in item.get("tags", [])}
    title = item.get("title", "")
    if not isinstance(title, str) or not title.strip() or len(title) > 80 or not (tags & SPOKEN) or EXCLUDED.search(title + " " + " ".join(tags)):
        raise ValueError("not-original-spoken-style")
    duration = item.get("duration", 0) / 1000
    if not 10 <= duration <= 29.5:
        raise ValueError("whole-recording-duration")
    source = safe_url(item.get("foreign_landing_url", "").rstrip("/") + "/", "page")
    media = safe_url(item.get("url", ""), "audio")
    sound_id = source.rstrip("/").split("/")[-1]
    creator = source.split("/")[4]
    if item.get("creator") != creator or media.split("/")[-1].split("_")[0] != sound_id or not re.fullmatch(r"[a-f0-9-]{36}", item.get("id", "")):
        raise ValueError("source-identity-mismatch")
    return {"sourceId": sound_id, "source": source, "media": media, "creator": creator,
            "title": title, "license": license_url, "duration": duration, "openverseId": item["id"],
            "tags": sorted(tags), "indexSha256": sha(json.dumps(item, sort_keys=True).encode())}


def verify_page(clip: dict, data: bytes) -> dict:
    text = data.decode("utf-8")
    match = re.search(r'<div id="soundDescriptionSection">(.*?)</div>', text, re.S)
    if not match:
        raise ValueError("source-description-missing")
    description = html.unescape(re.sub(r"<[^>]+>", " ", match[1]))
    description = " ".join(description.split())
    links = set(re.findall(r'href=[\"\'](https://creativecommons.org/[^\"\']+)[\"\']', text))
    if clip["license"] not in links or len(links & LICENSES) != 1:
        raise ValueError("source-license-mismatch")
    if not OWN.search(description) or EXCLUDED.search(description) or re.search(r"follow.on|previous sentence|part of a sentence|from (?:a|the) (?:film|show|game)|not (?:my|original)", description, re.I):
        raise ValueError("original-recording-not-established")
    if len(description) > 4000:
        raise ValueError("source-description-too-long")
    return {"pageSha256": sha(data), "description": description, "license": clip["license"], "originalClaim": True}


def decode_audio(data: bytes, output: Path) -> dict:
    source = output.with_suffix(".mp3")
    source.write_bytes(data)
    # Local file input only; ffmpeg cannot fetch embedded protocols. Decode no
    # more than 31s: oversized/mislabelled sources are rejected, never cropped.
    subprocess.run([os.environ.get("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-y", "-protocol_whitelist", "file,pipe",
                    "-i", str(source), "-t", "31", "-vn", "-ar", "48000", "-ac", "2", "-f", "s16le", str(output.with_suffix(".pcm"))], check=True, timeout=45)
    pcm = output.with_suffix(".pcm").read_bytes()
    samples = array.array("h", pcm)
    if not 10 <= len(pcm) / 192000 <= 29.5:
        raise ValueError("decoded-duration")
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
    clipped = sum(abs(x) >= 32760 for x in samples) / len(samples)
    if rms < .002 or clipped > .002:
        raise ValueError("silence-or-clipping")
    # wave emits canonical 44-byte PCM accepted by the private import API.
    with wave.open(str(output), "wb") as wav:
        wav.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return {"duration": len(pcm) / 192000, "rms": rms, "clippedFraction": clipped}


def assess_speech(segments: list[dict], language: str, language_probability: float, duration: float) -> dict:
    if language != "en" or language_probability < .9 or not segments:
        raise ValueError("not-confident-english")
    words = [word for segment in segments for word in segment["words"]]
    text = " ".join(segment["text"].strip() for segment in segments).strip()
    tokens = normalized_words(text)
    if not 12 <= len(tokens) <= 90 or len(set(tokens)) < 9 or not words:
        raise ValueError("not-enough-meaningful-speech")
    # Detect looped/repeated takes, not just byte-identical files.
    grams = [tuple(tokens[i:i + 4]) for i in range(len(tokens) - 3)]
    if len(set(grams)) / len(grams) < .9:
        raise ValueError("repeated-takes")
    if words[0]["start"] < .10 or duration - words[-1]["end"] < .12 or tokens[-1] in {"a", "an", "the", "to", "of", "and", "but", "or", "with", "for"}:
        raise ValueError("sentence-boundary-uncertain")
    confidence = sum(w["probability"] for w in words) / len(words)
    if confidence < .82 or min(w["probability"] for w in words) < .15 or any(s["avg_logprob"] < -.65 or s["no_speech_prob"] > .35 for s in segments):
        raise ValueError("speech-confidence")
    spoken_span = words[-1]["end"] - words[0]["start"]
    if spoken_span / duration < .35 or max((b["start"] - a["end"] for a, b in zip(words, words[1:])), default=0) > 4:
        raise ValueError("sparse-speech")
    if re.search(r"\b(subscribe|copyright|all rights reserved|thank you for watching|kill yourself)\b", text, re.I):
        raise ValueError("unsuitable-script")
    mood = "revenge" if REVENGE.search(text) else "sad" if SAD.search(text) else None
    if mood is None:
        raise ValueError("not-emotional-dialogue")
    return {"transcript": text, "transcriptSha256": transcript_hash(text), "language": language,
            "languageProbability": language_probability, "wordConfidence": confidence, "wordCount": len(tokens),
            "start": words[0]["start"], "end": words[-1]["end"], "mood": mood,
            "wholeRecording": True, "repeatedTakes": False, "model": "faster-whisper-small"}


def transcribe(path: Path, model) -> dict:
    result, info = model.transcribe(str(path), beam_size=5, word_timestamps=True, vad_filter=True,
                                    condition_on_previous_text=False, temperature=0)
    segments = [{"text": s.text, "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
                 "words": [{"start": w.start, "end": w.end, "word": w.word, "probability": w.probability} for w in s.words or []]}
                for s in result]
    return {"segments": segments, "language": info.language, "language_probability": info.language_probability}


def import_clip(path: Path, metadata: dict, audit: dict) -> dict:
    boundary = "clipmaker-" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (("metadata", json.dumps(metadata).encode()), ("audit", json.dumps(audit).encode()), ("audio", path.read_bytes())):
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'.encode())
        if name == "audio":
            body.extend(b'; filename="clip.wav"\r\nContent-Type: audio/wav')
        body.extend(b"\r\n\r\n" + value + b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    token = os.environ.get("CLIPMAKER_UPLOAD_TOKEN", "")
    if not token:
        raise ValueError("Missing private collection credential")
    request = Request(BASE + "/import", data=body, headers={"Authorization": f"Bearer {token}",
                      "User-Agent": USER_AGENT, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    # Import endpoint is idempotent by source/transcript/audio hashes. Do not
    # log bodies, tokens or raw upstream exceptions in public Actions logs.
    with build_opener(NoRedirect()).open(request, timeout=45) as response:
        return json.loads(response.read(12000))["clip"]


def collect(output: Path, *, publish=False, max_imports=2, scan_limit=12) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    previous = json.loads(cloud("/collection", maximum=100000)) if publish else (
        json.loads((output / "collection.json").read_text()) if (output / "collection.json").exists() else {})
    if previous.get("enabled") is False:
        return {"status": "disabled", "imported": 0}
    cursor = int(previous.get("cursor", 0))
    seen = set(previous.get("seen", []))
    report = {"version": VERSION, "startedAt": datetime.now(timezone.utc).isoformat(), "cursor": cursor,
              "status": "ok", "searched": 0, "examined": 0, "imported": 0, "duplicates": 0,
              "rejected": {}, "errors": [], "clips": [], "seen": [], "queries": []}
    if publish:
        existing = json.loads(cloud("", maximum=300000))["clips"]
        seen.update(c.get("sourceId") for c in existing if c.get("sourceId"))
        if len(existing) >= 190:
            report["status"] = "capacity"
    model = None
    local_clips = json.loads((output / "catalog.json").read_text()).get("clips", []) if (output / "catalog.json").exists() else []
    try:
        for offset in range(3):
            if report["imported"] >= max_imports or report["status"] == "capacity":
                break
            slot = cursor + offset
            query = QUERIES[slot % len(QUERIES)]
            page = 1 + (slot // len(QUERIES)) % 10
            params = {"q": query, "source": "freesound", "license": "by,cc0", "page_size": 20, "page": page}
            report["queries"].append({"q": query, "page": page})
            try:
                result = json.loads(download(SEARCH + "?" + urlencode(params), "search", 500000))
                report["searched"] += 1
            except HTTPError as error:
                if error.code == 400 and page > 1:
                    continue  # Search pages vary in count; next cycle revisits page 1.
                report["errors"].append(f"search-http-{error.code}")
                if error.code == 429:
                    break
                continue
            for item in result.get("results", []):
                if report["imported"] >= max_imports or report["examined"] >= scan_limit:
                    break
                source_id = str(item.get("foreign_landing_url", "")).rstrip("/").split("/")[-1]
                if source_id in seen:
                    report["duplicates"] += 1
                    continue
                try:
                    clip = candidate(item)
                    report["examined"] += 1
                    page_data = download(clip["source"], "page", 500000)
                    license_evidence = verify_page(clip, page_data)
                    data = download(clip["media"], "audio", 4_000_000)
                    path = output / (clip["sourceId"] + ".wav")
                    levels = decode_audio(data, path)
                    if abs(levels["duration"] - clip["duration"]) > .15:
                        raise ValueError("source-duration-mismatch")
                    if model is None:
                        from faster_whisper import WhisperModel
                        model = WhisperModel("small", revision=WHISPER_REVISION, device="cpu", compute_type="int8", cpu_threads=2)
                    raw = transcribe(path, model)
                    (output / (clip["sourceId"] + ".asr.json")).write_text(json.dumps(raw, indent=2), encoding="utf-8")
                    speech = assess_speech(**raw, duration=levels["duration"])
                    digest = sha(path.read_bytes())
                    audit = {"version": VERSION, "sourceId": clip["sourceId"], "source": clip["source"],
                             "media": clip["media"], "openverseId": clip["openverseId"], "indexSha256": clip["indexSha256"],
                             "sourceSha256": sha(data), "audioSha256": digest, "licenseEvidence": license_evidence,
                             "speech": speech, "levels": levels, "checkedAt": datetime.now(timezone.utc).isoformat()}
                    label = "CC0 1.0" if "/zero/" in clip["license"] else "CC BY " + clip["license"].rstrip("/").split("/")[-1]
                    credit = f'{clip["title"]} — {clip["creator"]} ({label}); normalized + background added.'
                    if len(credit) > 160:
                        raise ValueError("attribution-too-long")
                    metadata = {"title": clip["title"], "mood": speech["mood"], "mix": "voice-only", "rights": "licensed",
                                "source": clip["source"], "sourceId": clip["sourceId"], "credit": credit,
                                "rightsEvidence": clip["license"], "speechReviewed": False, "rightsConfirmed": False,
                                "reviewMode": VERSION}
                    if publish:
                        try:
                            imported = import_clip(path, metadata, audit)
                        except HTTPError as error:
                            if error.code == 409:
                                report["duplicates"] += 1
                                raise ValueError("duplicate-source-or-transcript") from None
                            raise
                    else:
                        if any(c.get("sourceId") == clip["sourceId"] or c.get("transcriptSha256") == speech["transcriptSha256"] for c in local_clips):
                            raise ValueError("duplicate-source-or-transcript")
                        imported = {**metadata, "id": digest, "duration": levels["duration"], "active": True,
                                    "kind": "spoken", "language": "en", "auditSha256": sha(json.dumps(audit, separators=(",", ":"), ensure_ascii=False).encode()),
                                    "transcriptSha256": speech["transcriptSha256"]}
                        (output / (digest + ".wav")).write_bytes(path.read_bytes())
                        local_clips.append(imported)
                    (output / (digest + ".audit.json")).write_text(json.dumps(audit, indent=2), encoding="utf-8")
                    report["clips"].append({"id": imported["id"], "title": imported["title"]})
                    report["imported"] += 1
                except ValueError as error:
                    reason = str(error) if re.fullmatch(r"[a-z-]+", str(error)) else "invalid-source"
                    report["rejected"][reason] = report["rejected"].get(reason, 0) + 1
                except (HTTPError, URLError, TimeoutError, subprocess.SubprocessError, OSError) as error:
                    report["errors"].append(f"candidate-{source_id}-" + (f"http-{error.code}" if isinstance(error, HTTPError) else "unavailable"))
                    continue  # Network/transient failures remain retryable.
                seen.add(source_id)
                report["seen"].append(source_id)
            time.sleep(2)  # Respect the unauthenticated public search service.
    finally:
        report["cursor"] = cursor + len(report["queries"])
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        if report["errors"]:
            report["status"] = "degraded"
        if report["status"] == "ok" and not report["imported"]:
            report["status"] = "no-new-clips"
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if publish:
            cloud("/collection", report, maximum=100000)
        else:
            (output / "collection.json").write_text(json.dumps({**report, "seen": sorted(seen)[-2000:]}), encoding="utf-8")
            (output / "catalog.json").write_text(json.dumps({"clips": local_clips}, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true", help="Import approved candidates into the existing private cloud library")
    parser.add_argument("--max-imports", type=int, default=2, choices=range(1, 4))
    parser.add_argument("--scan-limit", type=int, default=12, choices=range(1, 21))
    args = parser.parse_args()
    try:
        summary = collect(args.output.resolve(), publish=args.publish, max_imports=args.max_imports, scan_limit=args.scan_limit)
        print(json.dumps({k: summary[k] for k in ("status", "imported", "searched", "examined", "rejected", "errors") if k in summary}))
        if summary["status"] == "degraded":
            raise SystemExit(1)
    except (ValueError, HTTPError, URLError, OSError) as error:
        print(json.dumps({"status": "error", "error": f"http-{error.code}" if isinstance(error, HTTPError) else type(error).__name__}))
        raise SystemExit(1) from None
