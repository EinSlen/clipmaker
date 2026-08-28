#!/usr/bin/env python3
"""Assemble native Blender frames into the production Soft Body MP4."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType


SCRIPT_DIR = Path(__file__).resolve().parent


def load_renderer() -> ModuleType:
    renderer_path = SCRIPT_DIR / "render-premium-3d.py"
    spec = importlib.util.spec_from_file_location("clipmaker_premium_renderer", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load renderer helpers from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_motion_events(path: Path) -> tuple[list[dict[str, object]], tuple[int, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_events = payload.get("events", [])
    raw_cuts = payload.get("attempt_cuts", [])
    events = [event for event in raw_events if isinstance(event, dict)] if isinstance(raw_events, list) else []
    cuts = tuple(int(value) for value in raw_cuts if isinstance(value, (int, float))) if isinstance(raw_cuts, list) else ()
    return events, cuts


def require_complete_sequence(frames: Path, frame_count: int) -> None:
    missing = [index for index in range(1, frame_count + 1) if not (frames / f"frame_{index:04d}.png").is_file()]
    if missing:
        preview = ", ".join(str(index) for index in missing[:12])
        suffix = "..." if len(missing) > 12 else ""
        raise RuntimeError(f"Missing {len(missing)} native frame(s): {preview}{suffix}")


def stage_frame_sequence(source: Path, destination: Path, frame_count: int) -> None:
    """Expose an immutable frame sequence through a writable working directory.

    Hard links are preferred on a shared filesystem, then symbolic links across
    Docker bind mounts. Copying is the portable fallback. Cut repairs replace a
    staged directory entry atomically, so the source sequence is never changed.
    """
    destination.mkdir(parents=True, exist_ok=False)
    for index in range(1, frame_count + 1):
        original = source / f"frame_{index:04d}.png"
        staged = destination / original.name
        try:
            os.link(original, staged)
            continue
        except OSError:
            pass
        try:
            staged.symlink_to(original)
            continue
        except OSError:
            shutil.copyfile(original, staged)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--difficulty", type=int, default=100)
    parser.add_argument("--obstacle", required=True)
    parser.add_argument("--music-volume", type=float, default=0.58)
    parser.add_argument("--preset", default="slow")
    parser.add_argument("--crf", default="14")
    args = parser.parse_args()

    renderer = load_renderer()
    frames = Path(args.frames).resolve()
    events_path = Path(args.events).resolve()
    output = Path(args.output).resolve()
    metadata_path = Path(args.metadata).resolve()
    frame_count = round(args.duration * args.fps)
    require_complete_sequence(frames, frame_count)
    if not events_path.is_file():
        raise FileNotFoundError(f"Motion event sidecar not found: {events_path}")

    variant = renderer.variant_for_seed(args.seed, args.obstacle)
    stages = variant.stages
    motion_payload = json.loads(events_path.read_text(encoding="utf-8"))
    attempt_quality = renderer.validate_motion_preflight(motion_payload, variant, frame_count, args.fps)
    events, attempt_cuts = read_motion_events(events_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="clipmaker-finalize-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        staged_frames = root / "frames"
        stage_frame_sequence(frames, staged_frames, frame_count)
        repaired = renderer.repair_stage_cut_frames(
            staged_frames, frame_count, len(stages), attempt_cuts, variant.obstacle.key, stages
        )
        silent = root / "silent.mp4"
        effects = root / "premium-foley.wav"
        music = root / "original-soft-body-bed.wav"
        video_filter = renderer.build_video_filter(args.duration, stages, variant.obstacle.key)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-framerate", str(args.fps), "-i", str(staged_frames / "frame_%04d.png"),
                "-vf", video_filter,
                "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                "-pix_fmt", "yuv420p", "-an", str(silent),
            ],
            check=True,
        )
        renderer.synth_premium_foley(args.duration, events, effects, args.seed)
        renderer.synth_soft_body_bed(args.duration, music, args.seed)
        audio_filter = renderer.build_continuous_audio_filter(args.music_volume)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(silent), "-i", str(effects), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex", audio_filter,
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-ar", "48000", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                str(output),
            ],
            check=True,
        )

    metadata: dict[str, object] = {
        "ok": True,
        "output": output.name,
        "duration": args.duration,
        "seed": args.seed,
        "game": "soft-body-slide",
        "difficulty": args.difficulty,
        "sound_pack": "premium-foley",
        "music": "Original seeded ambient bed",
        "music_generated": True,
        "music_mode": "subtle-bed",
        "music_hits": len(events),
        "events": len(events),
        "event_source": "simulated-collision-peaks" if events else "no-physical-events",
        "physics_preflight": "passed",
        "attempt_quality": attempt_quality,
        "foley_event_times": [round(float(event["time"]), 3) for event in events],
        "foley_event_types": sorted({str(event.get("kind", "contact")) for event in events}),
        "trials": len(stages),
        "units_completed": args.difficulty,
        "units_total": 100,
        "renderer": "Blender Eevee native GitHub matrix",
        "frames": frame_count,
        "render_width": 1080,
        "render_height": 1920,
        "render_fps": args.fps,
        "output_fps": 30,
        "repaired_cut_frames": list(repaired),
        "completed_at": args.duration,
        "outcome": "comparison-complete",
        **renderer.variant_summary(variant),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
