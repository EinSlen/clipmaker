#!/usr/bin/env python3
"""Render the Blender-powered premium 3D game and add synchronized audio."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

from soft_body_variants import (
    OBSTACLE_KEYS, obstacle_specimen_offsets, stage_attempt_frame_spans,
    stage_frame_spans, stage_time_spans, variant_for_seed, variant_summary, source_variant_summary,
)
from soft_body_framing import validate_stair_outlet_evidence
from soft_body_stair_geometry import VOLUME_CONTACT
from vocal_playlist import PROFILES, prepare_vocal_soundtrack
from edit_audio import EDIT_PROFILES, prepare_edit_soundtrack

SCRIPT_DIR = Path(__file__).resolve().parent

def softness_stages(seed: int) -> tuple[int, ...]:
    return variant_for_seed(seed).stages


def validate_motion_preflight(payload, variant, frame_count, fps):
    """Require native physics/surface evidence for every body of every take."""
    source_variant_summary(variant, payload)
    if (
        payload.get("preflight_schema") != 3
        or payload.get("obstacle") != variant.obstacle.key
        or payload.get("stages") != list(variant.stages)
        or payload.get("fps") != fps
        or abs(float(payload.get("duration", 0)) - frame_count / fps) > 1e-6
    ):
        raise ValueError("Missing or mismatched native 3D preflight evidence")
    expected = set()
    for stage_index, (softness, (start, end)) in enumerate(zip(
        variant.stages, stage_frame_spans(frame_count, len(variant.stages), variant.obstacle.key, variant.stages),
    ), start=1):
        for attempt, (first, last) in enumerate(stage_attempt_frame_spans(start, end, fps, variant.obstacle.key, softness), start=1):
            for body in range(1, len(obstacle_specimen_offsets(variant.obstacle.key)) + 1):
                expected.add((stage_index, softness, attempt, body, first, last))
    quality = payload.get("attempt_quality")
    if not isinstance(quality, list) or len(quality) != len(expected):
        raise ValueError("Incomplete native 3D preflight: a trial or body is missing")
    actual = set()
    for item in quality:
        if not isinstance(item, dict) or item.get("issues") != []:
            raise ValueError("Native 3D preflight reports a physical defect")
        surface = item.get("surface")
        if not isinstance(surface, dict) or surface.get("inside_contacts") != 0:
            raise ValueError("Native 3D surface contacts were not validated")
        rendered_surface = item.get("rendered_surface")
        if (not isinstance(rendered_surface, dict) or rendered_surface.get("issues") != []
            or rendered_surface.get("frames_checked") != item.get("end_frame", 0) - item.get("start_frame", 0) + 1
            or not isinstance(rendered_surface.get("vertices_checked"), int) or rendered_surface["vertices_checked"] <= 0
            or rendered_surface.get("subdivision") != 3
            or not isinstance(rendered_surface.get("maximum_penetration"), (int, float))
            or not math.isfinite(rendered_surface["maximum_penetration"])
            or not 0 <= rendered_surface["maximum_penetration"] <= 0.003
            or not isinstance(rendered_surface.get("maximum_correction"), (int, float))
            or not math.isfinite(rendered_surface["maximum_correction"])
            or not 0 <= rendered_surface["maximum_correction"] <= 0.08):
            raise ValueError("Native 3D final subdivided surface was not validated")
        framing = item.get("framing")
        if (not isinstance(framing, dict) or framing.get("issues") != []
            or framing.get("frames_checked") != item.get("end_frame", 0) - item.get("start_frame", 0) + 1
            or any(not isinstance(framing.get(key), (int, float))
                   or not math.isfinite(framing[key]) or not 0 <= framing[key] <= limit
                   for key, limit in (("maximum_empty_seconds", 1.0), ("maximum_side_exit_seconds", 0.5)))):
            raise ValueError("Native 3D camera framing was not validated")
        if variant.obstacle.key == "stair-cascade":
            if (rendered_surface.get("contact_model") != VOLUME_CONTACT
                or rendered_surface.get("classification") != "independent-three-ray-parity"
                or type(rendered_surface.get("outside_vertices_moved")) is not int
                or rendered_surface["outside_vertices_moved"] != 0):
                raise ValueError("Native stair closed-volume contact was not validated")
            validate_stair_outlet_evidence(framing.get("outlet"), framing["frames_checked"], fps)
        if len(obstacle_specimen_offsets(variant.obstacle.key)) > 1:
            between = item.get("inter_body_contact")
            if not isinstance(between, dict) or between.get("issues") != [] or between.get("frames_checked") != item.get("end_frame", 0) - item.get("start_frame", 0) + 1:
                raise ValueError("Native 3D contacts between specimens were not validated")
        actual.add(tuple(item.get(key) for key in (
            "stage", "softness", "attempt", "body", "start_frame", "end_frame",
        )))
    if actual != expected:
        raise ValueError("Native 3D preflight does not cover the requested timeline")
    return quality


def repair_stage_cut_frames(
    frames: Path,
    frame_count: int,
    stage_count: int,
    extra_boundaries: tuple[int, ...] = (),
    obstacle_key: str | None = None,
    stage_values: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    """Replace Eevee's hidden-to-visible motion-blur ghost with a clean cut."""
    repaired: list[int] = []
    spans = stage_frame_spans(frame_count, stage_count, obstacle_key, stage_values)
    boundaries = {spans[stage_index][0] for stage_index in range(1, stage_count)}
    boundaries.update(
        boundary for boundary in extra_boundaries if 1 < boundary < frame_count
    )
    for boundary in sorted(boundaries):
        source = frames / f"frame_{boundary + 1:04d}.png"
        target = frames / f"frame_{boundary:04d}.png"
        if source.is_file() and target.is_file():
            temporary = target.with_name(f".{target.name}.repair.tmp")
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            repaired.append(boundary)
    return tuple(repaired)


def synth_premium_foley(
    duration: float,
    events: list[dict[str, object]],
    output: Path,
    seed: int,
) -> None:
    """Create layered ASMR Foley at the collisions exported by Blender."""
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

    for event in sorted(events, key=lambda item: float(item["time"])):
        timestamp = max(0.0, min(duration - 0.005, float(event["time"])))
        softness = max(0.0, min(1.0, float(event.get("softness", 50)) / 100.0))
        strength = max(0.16, min(1.0, float(event.get("strength", 0.55))))
        pan = max(-0.82, min(0.82, float(event.get("pan", 0.0))))
        kind = str(event.get("kind", "ramp-contact"))

        if kind == "receiver-contact":
            # Marble rim/wall: a low body transient, soft metallic ring and a
            # short gel squash.  All layers share the exact collision frame.
            add_tone(timestamp, 114.0 - softness * 30.0, 0.30 + softness * 0.10, 0.34 * strength, pan, 0.58)
            add_tone(timestamp, 520.0 - softness * 260.0, 0.18 + softness * 0.12, 0.24 * strength, pan, 0.43)
            add_texture(timestamp, 0.15 + softness * 0.24, 0.11 * strength, pan, softness, fade=False)
            add_tone(timestamp + 0.075, 310.0 - softness * 130.0, 0.12, 0.10 * strength, -pan * 0.35, 0.24)
        elif kind == "receiver-entry":
            # A clean geometric crossing has no rim strike. Give it a restrained
            # air/sink cue instead of inventing a collision that never happened.
            add_texture(timestamp - 0.045, 0.20 + softness * 0.12, 0.055 * strength, pan, 0.82, fade=False)
            add_tone(timestamp, 178.0 - softness * 46.0, 0.20, 0.10 * strength, pan, 0.50)
            add_tone(timestamp + 0.055, 292.0 - softness * 90.0, 0.12, 0.055 * strength, -pan * 0.25, 0.32)
        else:
            # Ramp impacts remain crisp at 0% and progressively become broad,
            # damped rubs at 100%, just like the reference waveform.
            add_texture(
                timestamp - (0.055 + softness * 0.055),
                0.17 + softness * 0.27,
                (0.040 + softness * 0.050) * strength,
                pan,
                0.24 + softness * 0.66,
            )
            add_tone(
                timestamp,
                690.0 - softness * 410.0,
                0.09 + softness * 0.12,
                (0.16 + softness * 0.055) * strength,
                pan,
                0.18 + softness * 0.33,
            )
            add_tone(
                timestamp,
                205.0 - softness * 72.0,
                0.13 + softness * 0.09,
                0.105 * strength,
                pan * 0.7,
                0.38,
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


def synth_soft_body_bed(duration: float, output: Path, seed: int) -> None:
    """Create a different, calm stereo music bed for every seeded simulation."""
    rate = 48_000
    sample_count = math.ceil(duration * rate) + 1
    left = array("f", [0.0]) * sample_count
    right = array("f", [0.0]) * sample_count
    rng = random.Random(seed ^ 0x5AF7B0D7)
    bpm = rng.choice((72.0, 76.0, 80.0, 84.0))
    beat = 60.0 / bpm
    key = rng.choice((130.81, 146.83, 164.81, 174.61, 196.0))
    progressions = (
        (0, 5, 3, 7),
        (0, 3, 7, 5),
        (0, 7, 5, 3),
        (0, 5, 7, 3),
    )
    progression = rng.choice(progressions)
    ratios = (1.0, 1.189207, 1.498307)

    # Slowly cross-faded triads create an elegant studio bed without drawing
    # attention away from the collision Foley.
    for index in range(sample_count):
        time_sec = index / rate
        chord_position = time_sec / (beat * 4.0)
        chord_index = math.floor(chord_position)
        phase = chord_position - chord_index
        degree = progression[chord_index % len(progression)]
        next_degree = progression[(chord_index + 1) % len(progression)]
        fade = 0.5 - 0.5 * math.cos(math.pi * min(1.0, phase * 1.7))
        value_left = 0.0
        value_right = 0.0
        for voice, ratio in enumerate(ratios):
            frequency = key * (2.0 ** (degree / 12.0)) * ratio
            next_frequency = key * (2.0 ** (next_degree / 12.0)) * ratio
            detune = 1.0 + (voice - 1) * 0.0018
            current_left = math.sin(math.tau * frequency * detune * time_sec + voice * 0.72)
            current_right = math.sin(math.tau * frequency / detune * time_sec + voice * 0.72 + 0.24)
            next_left = math.sin(math.tau * next_frequency * detune * time_sec + voice * 0.72)
            next_right = math.sin(math.tau * next_frequency / detune * time_sec + voice * 0.72 + 0.24)
            harmonic = 0.56 / (voice + 1)
            value_left += ((1.0 - fade) * current_left + fade * next_left) * harmonic
            value_right += ((1.0 - fade) * current_right + fade * next_right) * harmonic
        breathing = 0.72 + 0.18 * math.sin(math.tau * time_sec / (beat * 8.0) - math.pi / 2)
        left[index] += value_left * breathing * 0.19
        right[index] += value_right * breathing * 0.19

    # Seeded glassy notes supply a memorable motif, while leaving deliberate
    # gaps so every ramp hit remains the foreground event.
    scale = (0, 2, 3, 5, 7, 10, 12)
    note_time = beat * 0.5
    note_index = 0
    while note_time < duration:
        if note_index % 4 != 2 or rng.random() > 0.36:
            degree = scale[(note_index * 3 + rng.randrange(len(scale))) % len(scale)]
            frequency = key * 2.0 ** (degree / 12.0) * rng.choice((1.0, 2.0))
            length = min(beat * 1.35, duration - note_time)
            start = round(note_time * rate)
            count = max(0, min(round(length * rate), sample_count - start))
            pan = rng.uniform(-0.48, 0.48)
            gain_left = math.cos((pan + 1.0) * math.pi / 4.0)
            gain_right = math.sin((pan + 1.0) * math.pi / 4.0)
            for offset in range(count):
                elapsed = offset / rate
                envelope = min(1.0, elapsed * 80.0) * math.exp(-elapsed * 4.6 / max(length, 0.001))
                shimmer = math.sin(math.tau * frequency * elapsed)
                shimmer += 0.28 * math.sin(math.tau * frequency * 2.01 * elapsed + 0.4)
                shimmer += 0.10 * math.sin(math.tau * frequency * 3.98 * elapsed + 1.1)
                value = shimmer * envelope * 0.12
                left[start + offset] += value * gain_left
                right[start + offset] += value * gain_right
        note_time += beat * rng.choice((0.5, 1.0, 1.5))
        note_index += 1

    peak = max(0.001, max(max(abs(value) for value in left), max(abs(value) for value in right)))
    gain = 0.82 / peak
    pcm = array("h")
    for left_value, right_value in zip(left, right):
        pcm.append(round(max(-1.0, min(1.0, left_value * gain)) * 32767))
        pcm.append(round(max(-1.0, min(1.0, right_value * gain)) * 32767))
    with wave.open(str(output), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(rate)
        destination.writeframes(pcm.tobytes())


def build_continuous_audio_filter(music_volume: float, vocals: bool = False, spoken: bool = False) -> str:
    """Mix readable vocals or a quiet instrumental bed with collision Foley."""
    bounded_volume = max(0.0, min(1.5, music_volume))
    if vocals:
        # Keep the actual recording's character and stereo image. No pitch,
        # reverb, synthetic voice or impact-triggered chopping of the lyrics.
        return (
            f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={0.16 if spoken else 0.75}[fx];"
            "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={bounded_volume:.4f}[music];"
            "[music][fx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=8[a]"
        )
    ambient_volume = bounded_volume * 0.55
    return (
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=1.35,asplit=2[fxmix][fxkey];"
        "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"highpass=f=90,lowpass=f=4800,haas=side_gain=0.18,volume={ambient_volume:.4f}[music];"
        "[music][fxkey]sidechaincompress=threshold=0.020:ratio=2.8:attack=8:release=190:makeup=1[ducked];"
        "[ducked][fxmix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
        "[mix]alimiter=limit=0.891:attack=5:release=70:level=false[limited];"
        "[limited]loudnorm=I=-20:TP=-1.5:LRA=10[a]"
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


def build_video_filter(
    duration: float,
    stages: tuple[int, ...],
    obstacle_key: str | None = None,
) -> str:
    """Keep native pixels and reproduce the reference's stage-only typography."""
    font_file = premium_font_file()
    filters = [
        "fps=30:round=up",
    ]
    for index, (softness, (start, stop)) in enumerate(
        zip(stages, stage_time_spans(duration, len(stages), obstacle_key, stages))
    ):
        end = duration if index == len(stages) - 1 else stop - 0.001
        filters.append(
            f"drawtext=fontfile='{font_file}':text='{softness}% SOFT':expansion=none:"
            "fontcolor=white:fontsize=78:x=(w-text_w)/2:y=112:"
            "shadowcolor=black@0.46:shadowx=4:shadowy=4:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'"
        )
    return ",".join(filters)


def render(args: argparse.Namespace) -> dict[str, object]:
    if args.music_profile in EDIT_PROFILES and (args.music or args.music_volume <= 0):
        raise ValueError("Spoken edits cannot be replaced by external music or muted")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blender = os.environ.get("BLENDER_BIN", "blender")
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
    width = int(os.environ.get("PREMIUM_RENDER_WIDTH", "1080"))
    height = int(os.environ.get("PREMIUM_RENDER_HEIGHT", "1920"))
    fps = int(os.environ.get("PREMIUM_RENDER_FPS", "30"))
    samples = int(os.environ.get("PREMIUM_RENDER_SAMPLES", "128"))
    video_preset = os.environ.get("PREMIUM_VIDEO_PRESET", "slow")
    video_crf = os.environ.get("PREMIUM_VIDEO_CRF", "14")
    frame_count = round(args.duration * fps)
    variant = variant_for_seed(args.seed, args.obstacle)
    stages = variant.stages
    events: list[dict[str, object]] = []
    attempt_quality: list[dict[str, object]] = []
    event_source = "simulated-collision-peaks"

    with tempfile.TemporaryDirectory(prefix="clipmaker-premium-", dir=str(output.parent)) as temporary:
        root = Path(temporary)
        frames = root / "frames"
        frames.mkdir()
        silent = root / "silent.mp4"
        effects = root / "premium-foley.wav"
        generated_bed = root / "original-soft-body-bed.wav"
        external_music = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None
        soundtrack = {"music": external_music.name if external_music else "Original seeded ambient bed",
                      "music_generated": external_music is None, "music_profile": "external" if external_music else "original"}
        if external_music is None:
            if args.music_profile == "original":
                synth_soft_body_bed(args.duration, generated_bed, args.seed)
            elif args.music_profile in EDIT_PROFILES:
                soundtrack = prepare_edit_soundtrack(args.duration, generated_bed, args.seed, args.music_profile, synth_bed=synth_soft_body_bed)
            else:
                soundtrack = prepare_vocal_soundtrack(args.duration, generated_bed, args.seed, args.music_profile)
        motion_events = root / "motion-events.json"
        blender_command = [
            blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(SCRIPT_DIR / "blender-soft-body-slide.py"), "--",
            "--frames", str(frames), "--duration", str(args.duration), "--fps", str(fps),
            "--width", str(width), "--height", str(height), "--samples", str(samples), "--seed", str(args.seed),
            "--softness", str(args.difficulty), "--theme", args.theme, "--title", args.title,
            "--obstacle", args.obstacle,
            "--events", str(motion_events),
        ]
        subprocess.run(blender_command, check=True)
        expected_last_frame = frames / f"frame_{frame_count:04d}.png"
        if not expected_last_frame.is_file():
            raise RuntimeError(
                f"Blender did not produce the expected final frame: {expected_last_frame.name}"
            )
        attempt_cuts: tuple[int, ...] = ()
        if motion_events.is_file():
            payload = json.loads(motion_events.read_text(encoding="utf-8"))
            attempt_quality = validate_motion_preflight(payload, variant, frame_count, fps)
            exported_cuts = payload.get("attempt_cuts", [])
            if isinstance(exported_cuts, list):
                attempt_cuts = tuple(
                    int(boundary)
                    for boundary in exported_cuts
                    if isinstance(boundary, (int, float))
                )
            exported_events = payload.get("events", [])
            if isinstance(exported_events, list):
                events = [event for event in exported_events if isinstance(event, dict)]
        else:
            raise RuntimeError("Blender produced no native 3D preflight evidence")
        repair_stage_cut_frames(
            frames,
            frame_count,
            len(stages),
            attempt_cuts,
            variant.obstacle.key,
            stages,
        )
        if not events:
            # Silence is truthful here: Foley must correspond to a measured
            # collision or a clean geometric receiver entry exported by
            # Blender.  The ambient bed still keeps the mix alive.
            event_source = "no-physical-events"
        video_filter = build_video_filter(args.duration, stages, variant.obstacle.key)
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
            "-i", str(frames / "frame_%04d.png"),
            "-vf", video_filter,
            "-c:v", "libx264", "-preset", video_preset, "-crf", video_crf,
            "-pix_fmt", "yuv420p", "-an", str(silent),
        ], check=True)
        synth_premium_foley(args.duration, events, effects, args.seed)
        music_source = external_music or generated_bed
        audio_filter = build_continuous_audio_filter(args.music_volume, bool(soundtrack.get("music_has_vocals")), soundtrack.get("music_content_kind") == "spoken")
        audio_command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(effects),
            *([] if soundtrack.get("music_content_kind") == "spoken" else ["-stream_loop", "-1"]), "-i", str(music_source), "-filter_complex", audio_filter,
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
        **soundtrack,
        "music_mode": soundtrack.get("music_mode", "vocal-playlist" if soundtrack.get("music_has_vocals") else "subtle-bed"),
        "requested_music_mode": args.music_mode,
        "music_hits": len(events),
        "events": len(events),
        "trials": len(stages),
        "trial_duration": args.duration / len(stages),
        "events_per_trial": round(len(events) / max(1, len(stages)), 2),
        "event_ratios": None,
        "event_source": event_source,
        "physics_preflight": "passed",
        "attempt_quality": attempt_quality,
        "foley_event_times": [round(float(event["time"]), 3) for event in events],
        "foley_event_types": sorted({str(event.get("kind", "contact")) for event in events}),
        "units_completed": args.difficulty,
        "units_total": 100,
        "renderer": "Blender Eevee cinematic rod",
        "frames": frame_count,
        "render_width": width,
        "render_height": height,
        "render_fps": fps,
        "output_fps": 30,
        "completed_at": args.duration,
        "outcome": "comparison-complete",
        **variant_summary(variant),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--game", default="soft-body-slide")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--difficulty", type=int, default=100)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--obstacle", choices=("auto",) + OBSTACLE_KEYS, default="auto")
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), default="sunset")
    parser.add_argument("--sound-pack", choices=("auto", "meme", "funny", "arcade", "impact", "asmr"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-mode", choices=("hit-reveal", "continuous"), default="continuous")
    parser.add_argument("--music-profile", choices=PROFILES, default="original")
    parser.add_argument("--music-volume", type=float, default=0.58)
    parser.add_argument("--title", default="0% VS 100% SOFTNESS")
    args = parser.parse_args()
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
