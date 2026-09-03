#!/usr/bin/env python3
"""Speak one line and report where every word lands.

The edge-tts command line only writes sentence level subtitles, but the service
sends a WordBoundary event per word. Reading the stream directly therefore gives
exact word timings for free, with no transcriber and no API key, which is what
places the highlight on the word being pronounced.
"""

import asyncio
import json
import sys

import edge_tts

TICKS_PER_SECOND = 10_000_000


async def run() -> int:
    request = json.load(sys.stdin)
    voice = request.get("voice", "fr-FR-HenriNeural")
    rate = request.get("rate", "+0%")
    try:
        # The service groups by sentence unless word boundaries are requested.
        communicate = edge_tts.Communicate(request["text"], voice, rate=rate, boundary="WordBoundary")
    except TypeError:
        # Older releases have no boundary argument and only report sentences,
        # which still beats spreading the words evenly.
        communicate = edge_tts.Communicate(request["text"], voice, rate=rate)
    words = []
    with open(request["output"], "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append({
                    "text": chunk["text"],
                    "start": round(start, 3),
                    "end": round(start + chunk["duration"] / TICKS_PER_SECOND, 3),
                })
    json.dump({"words": words}, sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
