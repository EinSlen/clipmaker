#!/usr/bin/env python3
"""Render the Blender-powered premium 3D game and add synchronized audio."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER_SPEC = importlib.util.spec_from_file_location("clipmaker_audio", SCRIPT_DIR / "render-ball-escape.py")
assert RENDERER_SPEC and RENDERER_SPEC.loader
AUDIO = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(AUDIO)


def render(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blender = os.environ.get("BLENDER_BIN", "blender")
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
    width = int(os.environ.get("PREMIUM_RENDER_WIDTH", "270"))
    height = int(os.environ.get("PREMIUM_RENDER_HEIGHT", "480"))
    fps = int(os.environ.get("PREMIUM_RENDER_FPS", "12"))
    samples = int(os.environ.get("PREMIUM_RENDER_SAMPLES", "8"))
    frame_count = round(args.duration * fps)
    impact_times = [args.duration * ratio for ratio in (0.08, 0.24, 0.48, 0.62, 0.72, 0.81, 0.88, 0.96)]
    events = [(time, 190 + index * 72, 0.50, "impact" if index >= 5 else "clear") for index, time in enumerate(impact_times)]

    with tempfile.TemporaryDirectory(prefix="clipmaker-premium-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        frames = root / "frames"
        frames.mkdir()
        silent = root / "silent.mp4"
        effects = root / "effects.wav"
        music = root / "original-generated-track.wav"
        blender_command = [
            blender, "--background", "--factory-startup", "--python", str(SCRIPT_DIR / "blender-soft-body-slide.py"), "--",
            "--frames", str(frames), "--duration", str(args.duration), "--fps", str(fps),
            "--width", str(width), "--height", str(height), "--samples", str(samples), "--seed", str(args.seed),
            "--softness", str(args.difficulty), "--theme", args.theme, "--title", args.title,
        ]
        subprocess.run(blender_command, check=True)
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
            "-i", str(frames / "frame_%04d.jpg"), "-vf", "minterpolate=fps=30:mi_mode=blend,scale=1080:1920:flags=lanczos",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-an", str(silent),
        ], check=True)
        AUDIO.synth_audio(args.duration, events, effects, args.seed, args.sound_pack if args.sound_pack != "auto" else "impact", include_bed=False)
        external_music = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None
        if external_music is None:
            AUDIO.synth_original_music(music, args.seed)
        music_source = external_music or music
        audio_filter = AUDIO.build_hit_reveal_filter(impact_times, args.duration, args.music_volume, args.seed) if args.music_mode == "hit-reveal" else f"[1:a]volume=0.82[fx];[2:a]volume={args.music_volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(effects),
            "-stream_loop", "-1", "-i", str(music_source), "-filter_complex", audio_filter,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000",
            "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output),
        ], check=True)

    return {
        "ok": True,
        "output": output.name,
        "duration": args.duration,
        "seed": args.seed,
        "game": "soft-body-slide",
        "difficulty": args.difficulty,
        "sound_pack": "impact" if args.sound_pack == "auto" else args.sound_pack,
        "music": external_music.name if external_music else "Original generated track",
        "music_generated": external_music is None,
        "music_mode": args.music_mode,
        "music_hits": len(impact_times),
        "events": len(events),
        "units_completed": args.difficulty,
        "units_total": 100,
        "renderer": "Blender Eevee",
        "frames": frame_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--game", default="soft-body-slide")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--difficulty", type=int, default=100)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), default="sunset")
    parser.add_argument("--sound-pack", choices=("auto", "meme", "funny", "arcade", "impact"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-mode", choices=("hit-reveal", "continuous"), default="hit-reveal")
    parser.add_argument("--music-volume", type=float, default=0.58)
    parser.add_argument("--title", default="0% VS 100% SOFTNESS")
    args = parser.parse_args()
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
