#!/usr/bin/env python3
"""Render the Blender-powered premium 3D game and add synchronized audio."""

from __future__ import annotations

import argparse
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

SOFTNESS_RATIOS = (0.0, 0.25, 0.50, 0.75, 1.0)
FOLEY_EVENT_RATIOS = (0.23, 0.39, 0.96)
FOLEY_EVENT_TYPES = ("ramp-contact-1", "ramp-contact-2", "receiver-outcome")


def softness_stages(max_softness: int) -> tuple[int, ...]:
    # The recognizable comparison always uses the same five canonical levels.
    # The difficulty argument is retained for API compatibility and metadata.
    del max_softness
    return (0, 25, 50, 75, 100)


def stage_event_times(duration: float) -> list[tuple[float, float, float]]:
    """Return the two ramp contacts and receiver outcome for each trial."""
    segment = duration / len(SOFTNESS_RATIOS)
    return [
        tuple(min(duration - 0.01, (index + ratio) * segment) for ratio in FOLEY_EVENT_RATIOS)
        for index in range(len(SOFTNESS_RATIOS))
    ]


def synth_premium_foley(
    duration: float,
    event_times: list[tuple[float, float, float]],
    stages: tuple[int, ...],
    output: Path,
    seed: int,
) -> None:
    """Create three distinct, synchronized stereo foley cues for each trial."""
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

    # A near-silent stereo room tone prevents hard digital silence between actions.
    ambience_left = 0.0
    ambience_right = 0.0
    for sample_index in range(sample_count):
        ambience_left += ((rng.random() * 2.0 - 1.0) - ambience_left) * 0.006
        ambience_right += ((rng.random() * 2.0 - 1.0) - ambience_right) * 0.005
        left[sample_index] += ambience_left * 0.0014
        right[sample_index] += ambience_right * 0.0014

    for index, (softness_percent, trial_events) in enumerate(zip(stages, event_times)):
        softness = softness_percent / 100.0
        contact_one, contact_two, outcome = trial_events
        trial_pan = -0.12 + index * 0.06

        # First ramp contact: a quick whoosh into a bright clink.
        add_texture(contact_one - 0.16, 0.18, 0.028 + softness * 0.010, -0.34 + trial_pan, 0.20 + softness * 0.25)
        add_tone(
            contact_one,
            760.0 - softness * 250.0,
            0.085 + softness * 0.035,
            0.13 + softness * 0.025,
            -0.34 + trial_pan,
            0.14 + softness * 0.16,
        )

        # Second ramp contact: a lower friction burst with a separate knock.
        add_texture(contact_two - 0.12, 0.25, 0.045 + softness * 0.022, trial_pan, 0.30 + softness * 0.42)
        add_tone(
            contact_two,
            420.0 - softness * 195.0,
            0.13 + softness * 0.07,
            0.18 + softness * 0.05,
            trial_pan,
            0.25 + softness * 0.30,
        )

        # Receptacle/outcome: a compact plop whose body follows the softness.
        add_tone(outcome, 500.0 - softness * 315.0, 0.17 + softness * 0.14, 0.24 + softness * 0.09, 0.30 + trial_pan, 0.46)
        add_tone(outcome, 94.0 - softness * 26.0, 0.25, 0.28 + softness * 0.11, 0.30 + trial_pan, 0.56)
        add_texture(outcome, 0.13 + softness * 0.19, 0.042 + softness * 0.084, 0.30 + trial_pan, softness, fade=False)
        add_tone(
            outcome + 0.10,
            330.0 - softness * 170.0,
            0.10 + softness * 0.07,
            0.09 + (1.0 - softness) * 0.07,
            0.12 - trial_pan,
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
    """Keep only a very low stereo bed beneath the dynamic foley bursts."""
    bounded_volume = max(0.0, min(1.5, music_volume))
    ambient_volume = bounded_volume * 0.055
    return (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=1.35,asplit=2[fxmix][fxkey];"
        "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"highpass=f=90,lowpass=f=4800,haas=side_gain=0.18,volume={ambient_volume:.4f}[music];"
        "[music][fxkey]sidechaincompress=threshold=0.020:ratio=2.8:attack=8:release=190:makeup=1[ducked];"
        "[ducked][fxmix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
        "[mix]alimiter=limit=0.891:attack=5:release=70:level=false[a]"
    )


def build_foley_only_audio_filter() -> str:
    """Preserve the reference's large contrast between impacts and quiet air."""
    return (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "highpass=f=28,volume=1.55,alimiter=limit=0.891:attack=5:release=70:level=false[a]"
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
    """Upscale cleanly and add only restrained, high-positioned labels."""
    font_file = premium_font_file()
    title_path = ffmpeg_filter_path(title_file)
    title_size = max(22, min(30, round(650 / (max(16, title_length) * 0.62))))
    filters = [
        "fps=30:round=up",
        "scale=1080:1920:flags=lanczos",
        "unsharp=5:5:0.28:3:3:0.0",
        (
            f"drawtext=fontfile='{font_file}':textfile='{title_path}':expansion=none:"
            f"fontcolor=white@0.68:fontsize={title_size}:x=(w-text_w)/2:y=224:"
            "shadowcolor=black@0.40:shadowx=2:shadowy=2:"
            "enable='between(t\\,0\\,0.800)'"
        ),
    ]
    segment = duration / len(stages)
    for index, softness in enumerate(stages):
        start = index * segment
        end = duration if index == len(stages) - 1 else (index + 1) * segment - 0.001
        filters.append(
            f"drawtext=fontfile='{font_file}':text='{softness}% SOFT':expansion=none:"
            "fontcolor=white:fontsize=78:x=(w-text_w)/2:y=112:"
            "shadowcolor=black@0.46:shadowx=4:shadowy=4:"
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
    event_times = stage_event_times(args.duration)

    with tempfile.TemporaryDirectory(prefix="clipmaker-premium-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        frames = root / "frames"
        frames.mkdir()
        silent = root / "silent.mp4"
        effects = root / "premium-foley.wav"
        title_file = root / "title.txt"
        display_title = (args.title.strip() or "Soft Body Landing Test")[:52]
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
        synth_premium_foley(args.duration, event_times, stages, effects, args.seed)
        external_music = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None
        if external_music is None:
            audio_filter = build_foley_only_audio_filter()
            audio_command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(effects),
                "-filter_complex", audio_filter,
            ]
        else:
            audio_filter = build_continuous_audio_filter(args.music_volume)
            audio_command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(effects),
                "-stream_loop", "-1", "-i", str(external_music), "-filter_complex", audio_filter,
            ]
        subprocess.run(audio_command + [
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
        "music": external_music.name if external_music else "Foley-only ASMR mix",
        "music_generated": False,
        "music_mode": "subtle-bed" if external_music else "foley-only",
        "requested_music_mode": args.music_mode,
        "music_hits": len(event_times) * len(FOLEY_EVENT_RATIOS),
        "events": len(event_times) * len(FOLEY_EVENT_RATIOS),
        "trials": len(stages),
        "trial_duration": args.duration / len(stages),
        "events_per_trial": len(FOLEY_EVENT_RATIOS),
        "event_ratios": list(FOLEY_EVENT_RATIOS),
        "foley_event_types": list(FOLEY_EVENT_TYPES),
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
