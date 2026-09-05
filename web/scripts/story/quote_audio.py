"""Soundtrack for the quote format.

The spoken edit library already carries the sad talking clips the channel
publishes, and `prepare_edit_soundtrack` returns the rights metadata that
`assertEditAudioQuality` checks before anything is uploaded. This module only
adds the ambient bed a voice-only clip needs, so the quote format reuses the
cleared catalogue rather than introducing a second, unreviewed music source.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edit_audio import EDIT_PROFILES, prepare_edit_soundtrack  # noqa: E402

RATE = 48000


def synth_quote_bed(duration: float, output: Path, seed: int) -> None:
    """A slow minor drone, quiet enough to sit under a voice.

    Two detuned sines a fifth apart with a long fade at both ends. It is
    deliberately plain: the bed exists so a voice-only clip has something under
    it, not to be noticed.
    """
    root = 110.0 * (2 ** ((seed % 5) / 12.0))
    frames = int(duration * RATE)
    fade = int(min(2.0, duration / 4) * RATE)
    samples = bytearray()
    for index in range(frames):
        t = index / RATE
        value = (
            math.sin(2 * math.pi * root * t)
            + 0.6 * math.sin(2 * math.pi * root * 1.5 * t)
            + 0.3 * math.sin(2 * math.pi * root * 0.5 * t)
        ) / 1.9
        envelope = 1.0
        if index < fade:
            envelope = index / fade
        elif index > frames - fade:
            envelope = max(0.0, (frames - index) / fade)
        # Well under the voice so the words stay the subject.
        sample = int(max(-1.0, min(1.0, value * envelope * 0.08)) * 32767)
        samples += struct.pack("<hh", sample, sample)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(bytes(samples))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--profile", choices=EDIT_PROFILES, default="edit-sad")
    parser.add_argument("--date")
    parser.add_argument("--channel-id", default="quote")
    args = parser.parse_args()
    try:
        metadata = prepare_edit_soundtrack(
            args.duration, Path(args.output), args.seed, args.profile,
            args.date, args.channel_id, synth_bed=synth_quote_bed,
        )
        print("CLIPMAKER_QUOTE_AUDIO:" + json.dumps({"ok": True, "metadata": metadata}))
    except Exception as error:  # noqa: BLE001
        print("CLIPMAKER_QUOTE_AUDIO:" + json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(1)
