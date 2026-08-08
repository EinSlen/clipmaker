#!/usr/bin/env python3
"""Render the Blender-powered premium 3D game and add synchronized audio."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER_SPEC = importlib.util.spec_from_file_location("clipmaker_audio", SCRIPT_DIR / "render-ball-escape.py")
assert RENDERER_SPEC and RENDERER_SPEC.loader
AUDIO = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(AUDIO)

SOFTNESS_RATIOS = (0.0, 0.25, 0.50, 0.75, 1.0)


def softness_stages(max_softness: int) -> tuple[int, ...]:
    bounded = max(0, min(100, max_softness))
    return tuple(round(bounded * ratio) for ratio in SOFTNESS_RATIOS)


def stage_impact_times(duration: float) -> list[float]:
    """Return receiver contacts at the rendered 0.82 keyframes (frame 1 is t=0)."""
    segment = duration / len(SOFTNESS_RATIOS)
    return [min(duration - 0.01, (index + 0.80) * segment) for index in range(len(SOFTNESS_RATIOS))]


def synth_premium_foley(duration: float, impact_times: list[float], stages: tuple[int, ...], output: Path, seed: int) -> None:
    """Create a stereo slide, squash and receiver-impact layer for the five trials."""
    rate = 48_000
    sample_count = math.ceil(duration * rate) + 1
    left = array("f", [0.0]) * sample_count
    right = array("f", [0.0]) * sample_count
    rng = random.Random(seed ^ 0x50F7B0D7)

    def stereo_gains(pan: float) -> tuple[float, float]:
        angle = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
        return math.cos(angle), math.sin(angle)

    def add_tone(start: float, frequency: float, length: float, strength: float, pan: float, pitch_drop: float) -> None:
        start_index = max(0, round(start * rate))
        count = min(round(length * rate), sample_count - start_index)
        gain_left, gain_right = stereo_gains(pan)
        phase = 0.0
        for index in range(max(0, count)):
            elapsed = index / rate
            progress = elapsed / max(length, 0.001)
            envelope = min(1.0, elapsed * 110.0) * math.exp(-progress * 5.8)
            current_frequency = max(42.0, frequency * (1.0 - pitch_drop * progress))
            phase += math.tau * current_frequency / rate
            tone = math.sin(phase) + 0.24 * math.sin(phase * 2.01) + 0.07 * math.sin(phase * 3.97)
            value = tone * envelope * strength
            left[start_index + index] += value * gain_left
            right[start_index + index] += value * gain_right

    def add_texture(start: float, length: float, strength: float, pan: float, softness: float, fade: bool = True) -> None:
        start_index = max(0, round(start * rate))
        count = min(round(length * rate), sample_count - start_index)
        gain_left, gain_right = stereo_gains(pan)
        smoothed = 0.0
        previous = 0.0
        for index in range(max(0, count)):
            progress = index / max(1, count - 1)
            raw = rng.random() * 2.0 - 1.0
            smoothed += (raw - smoothed) * (0.055 + softness * 0.065)
            bright = raw - previous * 0.72
            previous = raw
            color = bright * (1.0 - softness) + smoothed * (0.65 + softness * 1.25)
            if fade:
                envelope = math.sin(math.pi * progress) ** 0.72
            else:
                envelope = min(1.0, progress * 45.0) * math.exp(-progress * 5.2)
            value = color * envelope * strength
            left[start_index + index] += value * gain_left
            right[start_index + index] += value * gain_right

    segment = duration / len(stages)
    for index, (softness_percent, impact_time) in enumerate(zip(stages, impact_times)):
        softness = softness_percent / 100.0
        pan = -0.20 + index * 0.10
        slide_start = index * segment + segment * 0.18
        slide_length = max(0.12, impact_time - slide_start - 0.08)
        add_texture(slide_start, slide_length, 0.012 + softness * 0.010, pan, 0.18 + softness * 0.45)

        # Rigid trials ring; softer trials trade that ring for a lower, wetter squash.
        add_tone(
            impact_time,
            520.0 - softness * 330.0,
            0.16 + softness * 0.13,
            0.22 + softness * 0.08,
            pan,
            0.18 + softness * 0.46,
        )
        add_tone(impact_time, 92.0 - softness * 24.0, 0.24, 0.26 + softness * 0.10, pan, 0.54)
        add_texture(impact_time, 0.12 + softness * 0.18, 0.035 + softness * 0.075, pan, softness, fade=False)
        add_tone(
            impact_time + segment * 0.07,
            330.0 - softness * 170.0,
            0.10 + softness * 0.07,
            0.09 + (1.0 - softness) * 0.07,
            -pan,
            0.28,
        )

    peak = max(0.001, max(max(abs(value) for value in left), max(abs(value) for value in right)))
    gain = min(0.86 / peak, 1.0)
    pcm = array("h")
    for left_value, right_value in zip(left, right):
        pcm.append(round(max(-1.0, min(1.0, left_value * gain)) * 32767))
        pcm.append(round(max(-1.0, min(1.0, right_value * gain)) * 32767))
    with wave.open(str(output), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(rate)
        destination.writeframes(pcm.tobytes())


def build_continuous_audio_filter(music_volume: float) -> str:
    """Keep the stereo music bed audible and duck it briefly under the foley."""
    bounded_volume = max(0.0, min(1.5, music_volume))
    return (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=0.92,asplit=2[fxmix][fxkey];"
        "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"haas=side_gain=0.32,volume={bounded_volume:.3f}[music];"
        "[music][fxkey]sidechaincompress=threshold=0.020:ratio=2.8:attack=8:release=190:makeup=1[ducked];"
        "[ducked][fxmix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
        "[mix]loudnorm=I=-16:TP=-1.0:LRA=8[a]"
    )


def ffmpeg_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def premium_font_file() -> str:
    configured = os.environ.get("PREMIUM_FONT_FILE")
    candidates = (
        configured,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    )
    selected = next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)
    if selected is None:
        raise FileNotFoundError("No bold font found; set PREMIUM_FONT_FILE for the FFmpeg title overlay")
    return ffmpeg_filter_path(Path(selected))


def build_video_filter(duration: float, stages: tuple[int, ...], title_file: Path, title_length: int) -> str:
    """Upscale cleanly and add crisp post-render labels outside Blender."""
    font_file = premium_font_file()
    title_path = ffmpeg_filter_path(title_file)
    title_size = max(34, min(60, round(950 / (max(16, title_length) * 0.62))))
    filters = [
        "fps=30:round=up",
        "scale=1080:1920:flags=lanczos",
        "unsharp=5:5:0.28:3:3:0.0",
        (
            f"drawtext=fontfile='{font_file}':textfile='{title_path}':expansion=none:"
            f"fontcolor=0x182135:fontsize={title_size}:x=(w-text_w)/2:y=150:"
            "box=1:boxcolor=white@0.52:boxborderw=18"
        ),
    ]
    segment = duration / len(stages)
    for index, softness in enumerate(stages):
        start = index * segment
        end = duration if index == len(stages) - 1 else (index + 1) * segment - 0.001
        filters.append(
            f"drawtext=fontfile='{font_file}':text='{softness}% SOFT':expansion=none:"
            "fontcolor=0xB87618:fontsize=48:x=(w-text_w)/2:y=250:"
            "box=1:boxcolor=white@0.46:boxborderw=14:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'"
        )
    return ",".join(filters)


def render(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blender = os.environ.get("BLENDER_BIN", "blender")
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
    width = int(os.environ.get("PREMIUM_RENDER_WIDTH", "360"))
    height = int(os.environ.get("PREMIUM_RENDER_HEIGHT", "640"))
    fps = int(os.environ.get("PREMIUM_RENDER_FPS", "15"))
    samples = int(os.environ.get("PREMIUM_RENDER_SAMPLES", "5"))
    frame_count = round(args.duration * fps)
    stages = softness_stages(args.difficulty)
    impact_times = stage_impact_times(args.duration)

    with tempfile.TemporaryDirectory(prefix="clipmaker-premium-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        frames = root / "frames"
        frames.mkdir()
        silent = root / "silent.mp4"
        effects = root / "premium-foley.wav"
        music = root / "peaceful-generated-track.wav"
        title_file = root / "title.txt"
        display_title = (args.title.strip() or "SOFT BODY LANDING TEST").upper()[:52]
        title_file.write_text(display_title, encoding="utf-8")
        blender_command = [
            blender, "--background", "--factory-startup", "--python", str(SCRIPT_DIR / "blender-soft-body-slide.py"), "--",
            "--frames", str(frames), "--duration", str(args.duration), "--fps", str(fps),
            "--width", str(width), "--height", str(height), "--samples", str(samples), "--seed", str(args.seed),
            "--softness", str(args.difficulty), "--theme", args.theme, "--title", args.title,
        ]
        subprocess.run(blender_command, check=True)
        video_filter = build_video_filter(args.duration, stages, title_file, len(display_title))
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
            "-i", str(frames / "frame_%04d.png"),
            "-vf", video_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-an", str(silent),
        ], check=True)
        synth_premium_foley(args.duration, impact_times, stages, effects, args.seed)
        external_music = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None
        if external_music is None:
            AUDIO.synth_peaceful_music(music, args.seed, duration=max(16.0, args.duration + 1.0))
        music_source = external_music or music
        audio_filter = build_continuous_audio_filter(args.music_volume)
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
        "sound_pack": "premium-foley",
        "requested_sound_pack": args.sound_pack,
        "music": external_music.name if external_music else "Original peaceful stereo bed",
        "music_generated": external_music is None,
        "music_mode": "continuous",
        "requested_music_mode": args.music_mode,
        "music_hits": len(impact_times),
        "events": len(impact_times),
        "softness_stages": list(stages),
        "units_completed": args.difficulty,
        "units_total": 100,
        "renderer": "Blender Eevee",
        "frames": frame_count,
        "render_width": width,
        "render_height": height,
        "render_fps": fps,
        "output_fps": 30,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--game", default="soft-body-slide")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--difficulty", type=int, default=100)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), default="sunset")
    parser.add_argument("--sound-pack", choices=("auto", "meme", "funny", "arcade", "impact", "asmr"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-mode", choices=("hit-reveal", "continuous"), default="continuous")
    parser.add_argument("--music-volume", type=float, default=0.58)
    parser.add_argument("--title", default="0% VS 100% SOFTNESS")
    args = parser.parse_args()
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
