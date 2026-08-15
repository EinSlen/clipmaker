"""Render a few native frames and report their real Blender render time.

This script runs inside Blender.  It intentionally benchmarks production
resolution and sampling instead of upscaling a tiny smoke render and calling
that representative of the final video.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--samples", type=int, default=128)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def main() -> None:
    args = arguments()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    frames = tuple(int(value) for value in args.frames.split(",") if value.strip())
    if not frames:
        raise ValueError("At least one benchmark frame is required")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    scene.render.use_file_extension = True
    scene.eevee.taa_render_samples = args.samples

    timings = []
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(output / f"soft-body-native-{frame:04d}")
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed = time.perf_counter() - started
        rendered = output / f"soft-body-native-{frame:04d}.png"
        if not rendered.is_file():
            raise RuntimeError(f"Blender did not write {rendered.name}")
        timings.append({"frame": frame, "seconds": elapsed, "file": rendered.name})

    average = sum(item["seconds"] for item in timings) / len(timings)
    payload = {
        "ok": True,
        "width": args.width,
        "height": args.height,
        "samples": args.samples,
        "frames": timings,
        "average_frame_seconds": average,
    }
    (output / "native-frame-timings.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    main()
