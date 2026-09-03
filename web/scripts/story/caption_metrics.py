#!/usr/bin/env python3
"""Exact word positions for karaoke captions.

drawtext cannot report where a word lands inside a line, so the red highlight
would drift if the positions were estimated from an average glyph width. The
real advances come from the font itself, which is the same file ffmpeg draws
with, so the box sits exactly on the spoken word.
"""

import json
import sys

from PIL import ImageFont


def layout(font_path: str, max_size: int, max_width: int, canvas: int, words: list[str]) -> dict:
    size = max(20, max_size)
    while True:
        font = ImageFont.truetype(font_path, size)
        widths = [font.getlength(word) for word in words]
        space = font.getlength(" ")
        line = sum(widths) + space * max(0, len(words) - 1)
        if line <= max_width or size <= 20:
            break
        size -= 2

    cursor = (canvas - line) / 2
    placed = []
    for word, width in zip(words, widths):
        placed.append({"text": word, "x": round(cursor), "w": round(width)})
        cursor += width + space
    return {"size": size, "lineWidth": round(line), "words": placed}


def main() -> int:
    request = json.load(sys.stdin)
    font_path = request["font"]
    max_size = int(request.get("maxSize", 74))
    max_width = int(request.get("maxWidth", 960))
    canvas = int(request.get("canvas", 1080))
    groups = [
        layout(font_path, max_size, max_width, canvas, [str(word) for word in group])
        for group in request.get("groups", [])
    ]
    json.dump({"groups": groups}, sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
