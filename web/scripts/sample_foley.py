"""Fire real CC0 one-shots at the collisions Blender exported.

A pack is a directory of mono 48 kHz PCM samples plus the pack.json that
records every title, author, source page and licence. Selection, pitch and
pan are seeded, so replaying a render reproduces the same soundtrack.
"""
from __future__ import annotations

import json
import math
import random
import wave
from array import array
from pathlib import Path

RATE = 48_000
PACKS = Path(__file__).resolve().parent.parent / "data" / "sound-packs"
# Soft Body request values that resolve to a sampled pack. Anything else keeps
# the synthesised premium Foley.
ALIASES = {"auto": "funny", "funny": "funny", "meme": "meme"}


def resolve_pack(requested: str) -> str | None:
    name = ALIASES.get(requested)
    if name and (PACKS / name / "pack.json").is_file():
        return name
    return None


def load_pack(name: str) -> tuple[dict, list[array]]:
    root = PACKS / name
    manifest = json.loads((root / "pack.json").read_text(encoding="utf-8"))
    entries = manifest.get("samples", [])
    if not entries:
        raise ValueError(f"Sound pack {name} declares no sample")
    samples: list[array] = []
    for entry in entries:
        with wave.open(str(root / entry["file"]), "rb") as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (RATE, 1, 2):
                raise ValueError(f"{entry['file']} is not mono 48 kHz PCM")
            frames = array("h")
            frames.frombytes(source.readframes(source.getnframes()))
        if not len(frames):
            raise ValueError(f"{entry['file']} is empty")
        samples.append(frames)
    return manifest, samples


def synth_sample_foley(
    duration: float,
    events: list[dict[str, object]],
    output: Path,
    seed: int,
    pack: str,
) -> dict[str, object]:
    """Write the stereo one-shot track and report what it used."""
    manifest, samples = load_pack(pack)
    sample_count = math.ceil(duration * RATE) + 1
    left = array("f", [0.0]) * sample_count
    right = array("f", [0.0]) * sample_count
    rng = random.Random(seed ^ 0x5A11B0D7)

    # The same near-silent room tone as the synthesised pack, so a quiet
    # passage never falls into hard digital silence.
    ambience_left = 0.0
    ambience_right = 0.0
    for index in range(sample_count):
        ambience_left += ((rng.random() * 2.0 - 1.0) - ambience_left) * 0.006
        ambience_right += ((rng.random() * 2.0 - 1.0) - ambience_right) * 0.005
        left[index] += ambience_left * 0.0014
        right[index] += ambience_right * 0.0014

    for event in sorted(events, key=lambda item: float(item["time"])):
        timestamp = max(0.0, min(duration - 0.005, float(event["time"])))
        softness = max(0.0, min(1.0, float(event.get("softness", 50)) / 100.0))
        strength = max(0.16, min(1.0, float(event.get("strength", 0.55))))
        pan = max(-0.82, min(0.82, float(event.get("pan", 0.0))))
        kind = str(event.get("kind", "obstacle-contact"))
        source = samples[rng.randrange(len(samples))]
        # A stiff body pops high and short, a soft one squelches lower and
        # longer. A clean receiver entry only brushes past, so it stays quiet.
        ratio = (1.34 - softness * 0.52) * rng.uniform(0.94, 1.08)
        level = (0.34 if kind == "receiver-entry" else 1.0) * strength * rng.uniform(0.68, 1.0) * 0.62
        gain_left = math.cos((pan + 1.0) * math.pi / 4.0) * level
        gain_right = math.sin((pan + 1.0) * math.pi / 4.0) * level
        start = round(timestamp * RATE)
        length = min(int(len(source) / ratio), sample_count - start)
        for index in range(max(0, length)):
            position = index * ratio
            floor = int(position)
            fraction = position - floor
            first = source[floor]
            second = source[min(floor + 1, len(source) - 1)]
            value = (first + (second - first) * fraction) / 32768.0
            left[start + index] += value * gain_left
            right[start + index] += value * gain_right

    # Overlapping contacts are the only thing that can pile up past the
    # ceiling: the per-hit level already sets the balance with the bed.
    peak = max(0.001, max(max(abs(value) for value in left), max(abs(value) for value in right)))
    scale = min(0.86 / peak, 1.0)
    pcm = array("h")
    for left_value, right_value in zip(left, right):
        pcm.append(round(max(-1.0, min(1.0, left_value * scale)) * 32767))
        pcm.append(round(max(-1.0, min(1.0, right_value * scale)) * 32767))
    with wave.open(str(output), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(RATE)
        destination.writeframes(pcm.tobytes())

    return {
        "sound_pack": pack,
        "sound_pack_kind": "sampled-one-shots",
        "sound_pack_label": manifest.get("label", pack),
        "sound_pack_size": len(samples),
        "sound_pack_rights": manifest.get("rights", ""),
        "sound_pack_credits": [
            f"{entry['title']} by {entry['author']} ({entry['source']})"
            for entry in manifest["samples"]
        ],
        "sound_pack_hits": len(events),
    }
