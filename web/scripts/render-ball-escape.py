#!/usr/bin/env python3
"""Render an original, deterministic vertical Ball Escape game video."""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import random
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from game_variants import GAME_CLASSES, SOCIAL_HOOK_CENTER_Y, create_game
from procedural_variation import game_variation_manifest


THEMES = {
    "neon": ((5, 7, 18), 0.58, 0.92),
    "sunset": ((16, 5, 16), 0.96, 0.90),
    "ice": ((3, 12, 18), 0.52, 0.78),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def angle_delta(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def color_for(theme: str, index: int, total: int, offset: float = 0.0) -> tuple[int, int, int]:
    _, base_hue, saturation = THEMES[theme]
    if theme == "neon":
        hue = (base_hue + index / max(1, total) * 0.82 + offset) % 1.0
    elif theme == "sunset":
        hue = (base_hue + index / max(1, total) * 0.17 + offset) % 1.0
    else:
        hue = (base_hue + index / max(1, total) * 0.20 + offset) % 1.0
    rgb = colorsys.hsv_to_rgb(hue, saturation, 1.0)
    return tuple(round(channel * 255) for channel in rgb)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fitted_font(text: str, preferred_size: int, minimum_size: int, maximum_width: int, bold: bool = False):
    size = preferred_size
    while size > minimum_size:
        candidate = font(size, bold=bold)
        left, _, right, _ = candidate.getbbox(text)
        if right - left <= maximum_width:
            return candidate
        size -= 1
    return font(minimum_size, bold=bold)


def draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, text_font, fill, stroke=0) -> None:
    draw.text(xy, text, font=text_font, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=(0, 0, 0, 220))


def synth_audio(duration: float, events: list[tuple[float, float, float, str]], output: Path, seed: int, sound_pack: str, include_bed: bool = True) -> None:
    rate = 44_100
    samples = array("f", [0.0]) * (math.ceil(duration * rate) + 1)

    def add_tone(start: float, frequency: float, strength: float, tone_length: float, kind: str) -> None:
        length = min(int(rate * tone_length), len(samples) - int(start * rate))
        if length <= 0:
            return
        start_index = int(start * rate)
        for i in range(length):
            elapsed = i / rate
            if kind == "meow":
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = min(1.0, elapsed * 34.0) * max(0.0, 1.0 - progress) ** 1.25
                bent_frequency = frequency * (0.72 + 0.68 * math.sin(math.pi * progress))
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.38 * math.sin(2 * math.pi * bent_frequency * 2.02 * elapsed)
                tone += 0.13 * math.sin(2 * math.pi * bent_frequency * 3.03 * elapsed)
            elif kind == "funny":
                envelope = math.exp(-elapsed * 20.0) * min(1.0, elapsed * 90.0)
                bent_frequency = frequency * (1.0 + 0.22 * math.sin(2 * math.pi * 13 * elapsed)) * (1.0 - elapsed * 0.7)
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.28 * math.sin(2 * math.pi * bent_frequency * 1.5 * elapsed)
            elif kind == "impact":
                # A short click on top of a descending low body reads like a
                # physical impact even under a loud social-media music bed.
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = math.exp(-elapsed * 18.0) * min(1.0, elapsed * 110.0)
                bent_frequency = max(42.0, frequency * 0.62 * (1.0 - progress * 0.58))
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.32 * math.sin(2 * math.pi * bent_frequency * 0.51 * elapsed)
                tone += 0.12 * math.sin(2 * math.pi * 1_850.0 * elapsed) * math.exp(-elapsed * 72.0)
            elif kind == "glass":
                # Inharmonic partials create a clean glass/marble click rather
                # than the recognisable cheap sine beep of an arcade prototype.
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = min(1.0, elapsed * 180.0) * math.exp(-progress * 5.6)
                phase = 2 * math.pi * frequency * (1.0 - progress * 0.012) * elapsed
                tone = 0.72 * math.sin(phase)
                tone += 0.31 * math.sin(phase * 2.756)
                tone += 0.17 * math.sin(phase * 5.404)
                tone += 0.08 * math.sin(phase * 8.933)
            elif kind == "asmr":
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = min(1.0, elapsed * 120.0) * math.exp(-progress * 4.8)
                bent_frequency = frequency * (1.025 - progress * 0.025)
                phase = 2 * math.pi * bent_frequency * elapsed
                tone = 0.78 * math.sin(phase)
                tone += 0.20 * math.sin(phase * 2.01)
                tone += 0.09 * math.sin(phase * 3.97)
                tone += 0.07 * math.sin(2 * math.pi * 2_300.0 * elapsed) * math.exp(-elapsed * 85.0)
            elif kind == "arcade":
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = min(1.0, elapsed * 150.0) * math.exp(-progress * 4.4)
                phase = 2 * math.pi * frequency * (1.0 + progress * 0.035) * elapsed
                tone = 0.82 * math.sin(phase)
                tone += 0.16 * math.sin(phase * 2.005)
                tone += 0.06 * math.sin(phase * 3.01)
            else:
                envelope = math.exp(-elapsed * 27.0) * min(1.0, elapsed * 90.0)
                tone = math.sin(2 * math.pi * frequency * elapsed)
                tone += 0.32 * math.sin(2 * math.pi * frequency * 2.01 * elapsed)
            samples[start_index + i] += tone * envelope * strength

    # A quiet, original 118 BPM loop prevents dead air while leaving room for a
    # licensed background track or an official TikTok sound at upload time.
    audio_rng = random.Random(seed ^ 0xB011CE)
    beat = 60.0 / 118.0
    scale = [220.0, 261.63, 329.63, 392.0, 329.63, 523.25, 392.0, 261.63]
    beat_index = 0
    time_sec = 0.0
    if include_bed:
        # Only the standalone effects-bed mode owns an intro hook. Normal game
        # renders already have music and should open without three synthetic
        # beeps fighting it.
        for hook_time, hook_note in ((0.0, 392.0), (0.14, 523.25), (0.30, 783.99)):
            add_tone(hook_time, hook_note, 0.14, 0.22, "arcade")
        while time_sec < duration:
            note = scale[beat_index % len(scale)] * (1.0 + audio_rng.uniform(-0.002, 0.002))
            add_tone(time_sec, note, 0.055, 0.17, "arcade")
            if beat_index % 2 == 0:
                add_tone(time_sec, 92.0, 0.09, 0.18, "impact")
            time_sec += beat / 2
            beat_index += 1

    for event_index, (start, frequency, strength, event_kind) in enumerate(events):
        event_sound = sound_pack
        event_frequency = frequency
        event_strength = strength
        event_length = 0.18
        if event_kind == "victory":
            # A verdict is not a collision.  Give it a short ascending sting
            # that remains recognisable with the automatic impact sound pack.
            for offset, ratio, level, length in (
                (0.0, 1.0, 1.0, 0.62),
                (0.085, 1.25, 0.70, 0.56),
                (0.170, 1.50, 0.50, 0.50),
            ):
                add_tone(
                    start + offset,
                    event_frequency * ratio,
                    min(0.72, event_strength * level),
                    length,
                    "arcade",
                )
            continue
        if sound_pack == "meme":
            if event_kind == "bounce" and (event_index + seed) % 5 in (0, 3):
                event_sound = "meow"
                event_frequency = 380.0 + ((event_index + seed) % 4) * 42.0
                event_strength = min(0.55, strength * 0.82)
                event_length = 0.31
            elif event_kind == "bounce":
                event_sound = "funny"
                event_frequency = 290.0 + ((event_index + seed) % 5) * 54.0
                event_length = 0.22
            else:
                event_sound = "arcade"
                event_length = 0.18
        elif sound_pack == "funny":
            event_length = 0.24
        elif sound_pack == "asmr":
            event_sound = "asmr"
            event_strength = min(0.34, strength)
            event_length = 0.16
        elif sound_pack == "glass":
            event_sound = "glass"
            if event_kind == "bounce":
                event_frequency = 610.0 + ((event_index + seed) % 7) * 31.0
                event_strength = min(0.42, strength * 1.05)
                event_length = 0.13
            elif event_kind == "clear":
                event_frequency = 880.0 + ((event_index + seed) % 9) * 37.0
                event_strength = min(0.54, strength * 1.02)
                event_length = 0.21
            elif event_kind == "victory":
                event_frequency *= 1.12
                event_strength = min(0.68, strength)
                event_length = 0.44
            else:
                event_sound = "impact"
                event_frequency = max(110.0, frequency)
                event_length = 0.24
        add_tone(start, event_frequency, event_strength, event_length, event_sound)

    peak = max(0.001, max(abs(sample) for sample in samples))
    gain = min(0.88 / peak, 1.0)
    pcm = array("h", (round(clamp(sample * gain, -1.0, 1.0) * 32767) for sample in samples))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


def synth_original_music(output: Path, seed: int, duration: float = 48.0) -> None:
    """Create a copyright-safe electronic song used when no track is supplied."""
    rate = 44_100
    samples = array("f", [0.0]) * (math.ceil(duration * rate) + 1)
    rng = random.Random(seed ^ 0x51A6B17)

    def add_note(start: float, frequency: float, length: float, strength: float, color: str = "lead") -> None:
        start_index = int(start * rate)
        sample_count = min(int(length * rate), len(samples) - start_index)
        if sample_count <= 0:
            return
        for index in range(sample_count):
            elapsed = index / rate
            attack = min(1.0, elapsed / (0.006 if color == "bass" else 0.012))
            release = min(1.0, max(0.0, length - elapsed) / (0.10 if color == "pad" else 0.055))
            envelope = attack * release
            phase = 2 * math.pi * frequency * elapsed
            if color == "bass":
                tone = math.sin(phase) + 0.22 * math.sin(phase * 2.0)
            elif color == "pad":
                tone = math.sin(phase) + 0.20 * math.sin(phase * 1.005) + 0.13 * math.sin(phase * 2.0)
            else:
                tone = math.sin(phase) + 0.30 * math.sin(phase * 2.0) + 0.09 * math.sin(phase * 3.0)
            samples[start_index + index] += tone * envelope * strength

    def add_kick(start: float, strength: float = 0.72) -> None:
        start_index = int(start * rate)
        length = min(int(0.24 * rate), len(samples) - start_index)
        phase = 0.0
        for index in range(max(0, length)):
            elapsed = index / rate
            frequency = 48.0 + 118.0 * math.exp(-elapsed * 19.0)
            phase += 2 * math.pi * frequency / rate
            envelope = math.exp(-elapsed * 13.0) * min(1.0, elapsed * 100.0)
            samples[start_index + index] += math.sin(phase) * envelope * strength

    def add_noise(start: float, length: float, strength: float, salt: int) -> None:
        start_index = int(start * rate)
        sample_count = min(int(length * rate), len(samples) - start_index)
        state = (seed ^ salt ^ 0x9E3779B9) & 0xFFFFFFFF
        previous = 0.0
        for index in range(max(0, sample_count)):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            raw = state / 0xFFFFFFFF * 2.0 - 1.0
            bright = raw - previous * 0.72
            previous = raw
            elapsed = index / rate
            envelope = math.exp(-elapsed * (45.0 if length < 0.10 else 18.0))
            samples[start_index + index] += bright * envelope * strength

    bpm = 148.0 + (seed % 5) * 2.0
    beat = 60.0 / bpm
    step_length = beat / 2.0
    chord_roots = (220.0, 174.61, 130.81, 196.0)  # Am, F, C, G
    melody_steps = (12, 7, 10, 7, 15, 12, 10, 7, 12, 7, 10, 5, 7, 10, 12, 15)
    step_count = math.ceil(duration / step_length)

    for step in range(step_count):
        start = step * step_length
        bar = step // 8
        root = chord_roots[bar % len(chord_roots)]
        if step % 8 == 0:
            for interval in (1.0, 1.189207, 1.498307):
                add_note(start, root * interval, beat * 1.85, 0.055, "pad")
        if step % 2 == 0:
            add_kick(start, 0.68 if step % 8 else 0.82)
            add_note(start, root / 2.0, beat * 0.72, 0.25, "bass")
        if step % 4 == 2:
            add_noise(start, 0.18, 0.11, step * 17)
        add_noise(start, 0.055, 0.036 if step % 2 else 0.026, step * 31)

        melody_offset = melody_steps[(step + seed) % len(melody_steps)]
        melody_frequency = 220.0 * (2.0 ** (melody_offset / 12.0))
        if step % 4 != 3 or rng.random() > 0.32:
            add_note(start, melody_frequency, step_length * 0.82, 0.105, "lead")

    peak = max(0.001, max(abs(sample) for sample in samples))
    gain = min(0.92 / peak, 1.0)
    pcm = array("h", (round(clamp(sample * gain, -1.0, 1.0) * 32767) for sample in samples))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


def synth_peaceful_music(output: Path, seed: int, duration: float = 48.0) -> None:
    """Create a calm, beatless ambient loop for satisfying simulations."""
    rate = 44_100
    samples = array("f", [0.0]) * (math.ceil(duration * rate) + 1)
    rng = random.Random(seed ^ 0x0A5A4F)

    def add_note(start: float, frequency: float, length: float, strength: float, bell: bool = False) -> None:
        start_index = int(start * rate)
        count = min(int(length * rate), len(samples) - start_index)
        for index in range(max(0, count)):
            elapsed = index / rate
            attack = min(1.0, elapsed / (0.018 if bell else 0.45))
            release = min(1.0, max(0.0, length - elapsed) / (0.55 if bell else 1.4))
            envelope = attack * release * (math.exp(-elapsed * 1.5) if bell else 1.0)
            phase = 2 * math.pi * frequency * elapsed
            if bell:
                tone = math.sin(phase) + 0.22 * math.sin(phase * 2.01) + 0.08 * math.sin(phase * 3.98)
            else:
                tone = math.sin(phase) + 0.18 * math.sin(phase * 1.003) + 0.10 * math.sin(phase * 2.0)
            samples[start_index + index] += tone * envelope * strength

    roots = (130.81, 110.0, 146.83, 98.0)  # C, A, D, G
    chord_length = 4.8
    for chord_index in range(math.ceil(duration / chord_length)):
        start = chord_index * chord_length
        root = roots[chord_index % len(roots)]
        for ratio in (1.0, 1.189207, 1.498307):
            add_note(start, root * ratio, chord_length * 1.18, 0.042, False)
    notes = (523.25, 659.25, 783.99, 587.33, 698.46, 523.25, 440.0, 587.33)
    cursor = 0.45
    note_index = seed % len(notes)
    while cursor < duration:
        add_note(cursor, notes[note_index % len(notes)], 1.05, 0.09, True)
        cursor += 0.72 + rng.uniform(-0.06, 0.10)
        note_index += 1 if rng.random() > 0.22 else 2

    peak = max(0.001, max(abs(sample) for sample in samples))
    gain = min(0.82 / peak, 1.0)
    pcm = array("h", (round(clamp(sample * gain, -1.0, 1.0) * 32767) for sample in samples))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


def build_hit_reveal_filter(
    hit_times: list[float],
    duration: float,
    volume: float,
    seed: int,
    outcome_time: float | None = None,
    ambient_floor: float = 0.0,
) -> str:
    """Build a sequential sampler: every collision unlocks the next music slice."""
    selected: list[float] = []
    for hit_time in sorted([0.0, *hit_times]):
        bounded = clamp(hit_time, 0.0, max(0.0, duration - 0.04))
        if not selected or bounded - selected[-1] >= 0.075:
            selected.append(bounded)
    selected = selected[:96]
    if not selected:
        return f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.80[fx];[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]"

    bounded_outcome = (
        clamp(outcome_time, 0.0, max(0.0, duration - 0.04))
        if outcome_time is not None
        else None
    )
    has_ambient = ambient_floor > 0.0
    source_count = len(selected) + int(bounded_outcome is not None) + int(has_ambient)
    split_outputs = "".join(f"[source{index}]" for index in range(source_count))
    filters = [
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.72[fx]",
        f"[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asplit={source_count}{split_outputs}",
    ]
    labels: list[str] = []
    source_cursor = (seed % 900) / 100.0
    for index, hit_time in enumerate(selected):
        next_hit = selected[index + 1] if index + 1 < len(selected) else duration
        fragment = clamp(next_hit - hit_time + 0.025, 0.12, 0.36)
        if index == len(selected) - 1:
            fragment = clamp(duration - hit_time, 0.20, 0.90)
        fade_out_at = max(0.04, fragment - 0.045)
        delay_ms = max(0, round(hit_time * 1000))
        label = f"slice{index}"
        filters.append(
            f"[source{index}]atrim=start={source_cursor:.3f}:duration={fragment:.3f},"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.012,"
            f"afade=t=out:st={fade_out_at:.3f}:d=0.045,adelay={delay_ms}:all=1[{label}]"
        )
        labels.append(f"[{label}]")
        source_cursor += fragment

    source_index = len(selected)
    if bounded_outcome is not None:
        outcome_duration = max(0.12, duration - bounded_outcome)
        outcome_delay = max(0, round(bounded_outcome * 1000))
        filters.append(
            f"[source{source_index}]atrim=start={source_cursor:.3f}:duration={outcome_duration:.3f},"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.018,"
            f"adelay={outcome_delay}:all=1[outcome_tail]"
        )
        labels.append("[outcome_tail]")
        source_cursor += outcome_duration
        source_index += 1
    if has_ambient:
        filters.append(
            f"[source{source_index}]atrim=start=0:duration={duration:.3f},"
            f"asetpts=PTS-STARTPTS,volume={clamp(ambient_floor, 0.0, 0.25):.3f}[ambient]"
        )
        labels.append("[ambient]")

    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
        f"volume={volume:.3f}[reveal]"
    )
    filters.append("[fx][reveal]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]")
    filters.append("[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]")
    return ";".join(filters)


class BallEscape:
    def __init__(self, width: int, height: int, fps: int, duration: float, rings: int, seed: int, theme: str, title: str):
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.ring_count = rings
        self.seed = seed
        self.theme = theme
        self.title = title.strip()[:52] or "Will the ball escape?"
        self.rng = random.Random(seed)
        self.cx = width / 2
        self.cy = height * 0.505
        # Physics is authored against a 360 px-wide reference canvas. Every
        # pixel-space impulse and contact offset must scale with the canvas or
        # the same seed changes outcome between a preview and a 1080p export.
        self.physics_scale = width / 360.0
        # The 5.7M-view reference fills the vertical canvas with a dense rainbow
        # vortex. Each logical gate is one thick, collidable rainbow ribbon;
        # the narrow coloured lines below are surface stripes, not extra gates.
        # Physics clears the gate only after the ball crosses its full depth.
        self.inner_radius = width * 0.040
        self.outer_radius = min(width * 0.84, height * 0.47)
        self.radial_step = (self.outer_radius - self.inner_radius) / max(1, rings)
        self.radii = [self.inner_radius + self.radial_step * i for i in range(rings)]
        # The public 10-20 ring range must leave genuine room for a whole ball
        # between two obstacles.  Scaling the physical sphere with the authored
        # radial step keeps that invariant at every supported ring count while
        # still producing a 16-25 px diameter in the final 1080p encode.
        target_ball_radius = max(2.0, width * 0.0125)
        self.ball_radius = max(2.0, min(target_ball_radius, self.radial_step / 5.0))
        # One physical ribbon has a filled body and at most three reflective
        # surface lines. It must never read as seven independent obstacles.
        self.bands_per_ring = 3 if rings <= 72 else 2 if rings <= 120 else 1
        # Body-to-body spacing exceeds four ball radii.  After the sphere has
        # fully left one ribbon and first touches the next, its centre therefore
        # travels more than one complete ball diameter: a clear can never chain
        # on the following simulation tick just because the geometry is dense.
        self.band_span = max(
            0.0,
            min(
                self.radial_step * (0.34 if self.bands_per_ring > 1 else 0.0),
                self.radial_step - self.ball_radius * 4.12,
            ),
        )
        self.gap_widths = [self.rng.uniform(70.0, 86.0) for _ in range(rings)]
        self.base_gaps, self.rotations = self.build_gap_layout()
        self.active = 0
        self.level = 1
        self.completed_at: float | None = None
        self.position = [self.cx + 4 * self.physics_scale, self.cy + 4 * self.physics_scale]
        # Always launch upward first so gravity visibly bends the trajectory
        # into an arc instead of looking like random linear movement.
        launch_sector = (210, 246) if self.rng.random() < 0.5 else (294, 330)
        start_angle = self.rng.uniform(math.radians(launch_sector[0]), math.radians(launch_sector[1]))
        speed = width * 0.54
        self.velocity = [math.cos(start_angle) * speed, math.sin(start_angle) * speed]
        self.trail: list[tuple[float, float]] = []
        self.particles: list[dict[str, float | tuple[int, int, int]]] = []
        self.pulses: list[dict[str, float | tuple[int, int, int]]] = []
        self.flash = 0.0
        self.impact_squash = 0.0
        self.max_speed_ratio = 1.0
        self.gravity_g = 1.0
        self.events: list[tuple[float, float, float, str]] = []
        self.music_hits: list[float] = []
        self.last_collision = -1.0
        self.streak = 0
        self.last_streak_at = 0.0
        self.failed_at: float | None = None
        self.simulation_time = 0.0
        self.camera_zoom = 1.0
        self.stars = [
            (
                self.rng.uniform(0, width),
                self.rng.uniform(0, height),
                self.rng.uniform(0.5, 1.7),
                self.rng.uniform(0, math.tau),
                self.rng.uniform(4, 18),
            )
            for _ in range(34)
        ]
        self.background = self.make_background()

    def build_gap_layout(self) -> tuple[list[float], list[float]]:
        """Author independent openings without constructing an escape corridor.

        This samples only the seed, clip duration and already-authored widths.
        It never reads the ball, progress, collision state or time remaining.
        Neighbouring openings remain physically disjoint for the entire clip.
        The vortex rotates, but the tiny authored speed variations are bounded
        so two adjacent gaps can never sweep across one another. This removes
        both a static spiral corridor and the transient two-ring highways that
        used to create near-simultaneous clears.
        """
        base_gaps: list[float] = []
        rotations: list[float] = []

        direction = self.rng.choice((-1.0, 1.0))
        common_speed = direction * self.rng.uniform(30.8, 47.6)
        # At most four degrees of relative drift per opening over the complete
        # clip. The separation calculation below reserves twice that amount.
        drift_limit = min(0.168, 5.6 / max(0.25, self.duration))

        for index in range(self.ring_count):
            rotation = common_speed + direction * self.rng.uniform(-drift_limit, drift_limit)
            if index == 0:
                base_gap = self.rng.uniform(0.0, 360.0)
            else:
                relative_drift = abs(rotation - rotations[-1]) * self.duration
                safe_separation = (
                    (self.gap_widths[index] + self.gap_widths[index - 1]) * 0.5
                    + relative_drift
                    + 12.0
                )
                # Sampling a side and a broad offset avoids a repeated spiral
                # increment. The next opening is an independent zig-zag choice,
                # never a continuation of the previous arc.
                offset = self.rng.choice((-1.0, 1.0)) * self.rng.uniform(
                    min(178.0, safe_separation),
                    178.0,
                )
                base_gap = (base_gaps[-1] + offset) % 360.0
            base_gaps.append(base_gap)
            rotations.append(rotation)

        return base_gaps, rotations

    def record_music_hit(self, time_sec: float) -> None:
        if not self.music_hits or time_sec - self.music_hits[-1] >= 0.075:
            self.music_hits.append(time_sec)

    def make_background(self) -> Image.Image:
        base = THEMES[self.theme][0]
        background = Image.new("RGB", (self.width, self.height), base)
        draw = ImageDraw.Draw(background)
        for y in range(self.height):
            center_distance = abs(y - self.cy) / max(1, self.height)
            glow = round(max(0.0, 1.0 - center_distance * 2.0) * 4)
            line = tuple(min(255, channel + glow) for channel in base)
            draw.line((0, y, self.width, y), fill=line)
        # A restrained radial pool makes the saturated rings feel emissive but
        # preserves the near-black negative space of the reference.
        pool = Image.new("RGBA", background.size, (0, 0, 0, 0))
        pool_draw = ImageDraw.Draw(pool)
        pool_radius = self.width * 0.58
        pool_draw.ellipse(
            (self.cx - pool_radius, self.cy - pool_radius, self.cx + pool_radius, self.cy + pool_radius),
            fill=(22, 28, 52, 34),
        )
        pool = pool.filter(ImageFilter.GaussianBlur(radius=max(12, round(self.width * 0.12))))
        return Image.alpha_composite(background.convert("RGBA"), pool).convert("RGB")

    def target_camera_scale(self) -> float:
        """Keep the active collision visible while the giant vortex opens up."""
        if self.active >= self.ring_count:
            active_outer = self.outer_radius
        else:
            active_outer = self.radii[self.active] + self.band_span
        return min(1.0, self.width * 0.465 / max(self.width * 0.14, active_outer))

    def camera_scale(self) -> float:
        return self.camera_zoom

    def screen_point(self, x: float, y: float, scale: float) -> tuple[float, float]:
        return self.cx + (x - self.cx) * scale, self.cy + (y - self.cy) * scale

    def ring_gap(self, index: int, time_sec: float) -> float:
        """Return the authored rotation only; gameplay state never moves a gap."""
        return (self.base_gaps[index] + self.rotations[index] * time_sec) % 360

    def ring_gap_width(self, index: int) -> float:
        """Keep the physical opening identical for the full simulation."""
        return self.gap_widths[index]

    def reset_level(self, time_sec: float) -> None:
        self.level += 1
        self.active = 0
        self.completed_at = None
        self.position = [self.cx, self.cy]
        launch_sector = (210, 246) if self.rng.random() < 0.5 else (294, 330)
        angle = self.rng.uniform(math.radians(launch_sector[0]), math.radians(launch_sector[1]))
        speed = self.width * 0.57
        self.velocity = [math.cos(angle) * speed, math.sin(angle) * speed]
        self.base_gaps, self.rotations = self.build_gap_layout()
        self.streak = 0
        self.failed_at = None

    def add_particles(self, angle: float, color: tuple[int, int, int]) -> None:
        for _ in range(24):
            spread = angle + self.rng.uniform(-0.55, 0.55)
            speed = self.rng.uniform(55, 190)
            self.particles.append({
                "x": self.position[0], "y": self.position[1],
                "vx": math.cos(spread) * speed, "vy": math.sin(spread) * speed,
                "life": self.rng.uniform(0.35, 0.85), "max_life": 0.85,
                "color": color,
            })

    def add_victory_particles(self) -> None:
        for index in range(90):
            angle = math.tau * index / 90 + self.rng.uniform(-0.08, 0.08)
            speed = self.rng.uniform(90, 330)
            color = color_for(self.theme, index, 90, self.level * 0.02)
            self.particles.append({
                "x": self.cx, "y": self.cy,
                "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed,
                "life": self.rng.uniform(0.7, 1.45), "max_life": 1.45,
                "color": color,
            })

    def update(self, time_sec: float) -> None:
        fixed_dt = 1.0 / 120.0
        while self.simulation_time + fixed_dt <= time_sec + 1e-9:
            self.simulation_time += fixed_dt
            self._simulate_step(self.simulation_time, fixed_dt)

    def _simulate_step(self, time_sec: float, dt: float) -> None:
        progress = self.active / max(1, self.ring_count)
        time_progress = clamp(time_sec / max(1.0, self.duration), 0.0, 1.0)

        # Real downward gravity creates readable parabolic falls. The ceiling
        # opens progressively, so the first seconds are legible and the final
        # third becomes genuinely frantic instead of merely changing a HUD
        # number.
        self.gravity_g = 0.88 + progress * 0.52 + time_progress * 0.24
        gravity = self.height * self.gravity_g
        self.velocity[1] += gravity * dt
        continuous_boost = 1.0 + dt * (0.016 + progress * 0.055 + time_progress * 0.072)
        self.velocity[0] *= continuous_boost
        self.velocity[1] *= continuous_boost

        speed = math.hypot(*self.velocity)
        min_speed = self.width * (0.54 + progress * 0.90 + time_progress * 0.32)
        max_speed = self.width * (0.90 + progress * 1.30 + time_progress * 0.46)
        if speed < min_speed:
            scale = min_speed / max(speed, 0.001)
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        elif speed > max_speed:
            scale = max_speed / speed
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        self.max_speed_ratio = max(self.max_speed_ratio, math.hypot(*self.velocity) / max(1.0, self.width * 0.50))

        self.position[0] += self.velocity[0] * dt
        self.position[1] += self.velocity[1] * dt
        dx, dy = self.position[0] - self.cx, self.position[1] - self.cy
        distance = max(0.001, math.hypot(dx, dy))

        if self.completed_at is None and self.failed_at is None and self.active < self.ring_count:
            radius = self.radii[self.active]
            nx, ny = dx / distance, dy / distance
            outward_speed = self.velocity[0] * nx + self.velocity[1] * ny
            ball_angle = math.degrees(math.atan2(dy, dx)) % 360
            gap_width = self.ring_gap_width(self.active)
            ball_clearance = self.ball_radius + max(2.0, self.width * 0.006)
            occupied_half_angle = math.degrees(math.asin(min(0.92, ball_clearance / max(radius, ball_clearance + 0.01))))
            center_tolerance = max(0.0, gap_width / 2 - occupied_half_angle)
            in_gap = abs(angle_delta(ball_angle, self.ring_gap(self.active, time_sec))) <= center_tolerance

            if distance + self.ball_radius >= radius and outward_speed > 0:
                if in_gap:
                    ribbon_outer_radius = radius + self.band_span
                    if distance >= ribbon_outer_radius + self.ball_radius:
                        color = color_for(self.theme, self.active, self.ring_count)
                        self.add_particles(math.atan2(dy, dx), color)
                        self.pulses.append({
                            "radius": radius + self.band_span * 0.5,
                            "life": 0.42,
                            "max_life": 0.42,
                            "color": color,
                        })
                        self.flash = max(self.flash, 0.18)
                        self.impact_squash = max(self.impact_squash, 0.45)
                        self.events.append((time_sec, 620 + self.active * 2.2, 0.52, "clear"))
                        self.record_music_hit(time_sec)
                        clear_batch = 1
                        self.active = min(self.ring_count, self.active + 1)
                        if time_sec - self.last_streak_at < 0.34:
                            self.streak += clear_batch
                        else:
                            self.streak = clear_batch
                        self.last_streak_at = time_sec
                        acceleration = min(1.060, 1.018 + self.active / max(1, self.ring_count) * 0.042)
                        self.velocity[0] *= acceleration
                        self.velocity[1] *= acceleration
                        if self.active >= self.ring_count:
                            self.completed_at = time_sec
                            self.failed_at = None
                            self.add_victory_particles()
                            self.flash = 0.72
                            self.events.extend([
                                (time_sec + 0.06, 783.99, 0.58, "victory"),
                                (time_sec + 0.18, 987.77, 0.62, "victory"),
                                (time_sec + 0.32, 1318.51, 0.70, "victory"),
                            ])
                else:
                    contact_inset = self.physics_scale
                    self.position[0] = self.cx + nx * (radius - self.ball_radius - contact_inset)
                    self.position[1] = self.cy + ny * (radius - self.ball_radius - contact_inset)
                    self.velocity[0] -= 2 * outward_speed * nx
                    self.velocity[1] -= 2 * outward_speed * ny
                    bounce_boost = 1.008 + time_progress * 0.008
                    self.velocity[0] *= bounce_boost
                    self.velocity[1] *= bounce_boost
                    tangent_push = self.rng.uniform(-18, 18) * self.physics_scale
                    self.velocity[0] += -ny * tangent_push
                    self.velocity[1] += nx * tangent_push
                    if time_sec - self.last_collision > 0.055:
                        if time_sec - self.last_streak_at > 0.34:
                            self.streak = 0
                        self.events.append((time_sec, 260 + self.active * 16, 0.34, "bounce"))
                        self.record_music_hit(time_sec)
                        color = color_for(self.theme, self.active, self.ring_count)
                        self.pulses.append({"radius": radius, "life": 0.18, "max_life": 0.18, "color": color})
                        self.flash = max(self.flash, 0.07)
                        self.impact_squash = 1.0
                        self.last_collision = time_sec

        if self.completed_at is None and self.failed_at is None and time_sec >= self.duration - 0.62:
            self.failed_at = time_sec
            self.events.extend([
                (time_sec, 196.0, 0.30, "impact"),
                (time_sec + 0.16, 164.81, 0.26, "impact"),
            ])

        self.trail.append((self.position[0], self.position[1]))
        speed_ratio = self.max_speed_ratio
        trail_limit = round(18 + clamp(speed_ratio, 1.0, 5.0) * 9)
        self.trail = self.trail[-trail_limit:]
        next_particles = []
        for particle in self.particles:
            particle["x"] = float(particle["x"]) + float(particle["vx"]) * dt
            particle["y"] = float(particle["y"]) + float(particle["vy"]) * dt
            particle["vx"] = float(particle["vx"]) * 0.985
            particle["vy"] = float(particle["vy"]) * 0.985 + self.height * 0.025 * dt
            particle["life"] = float(particle["life"]) - dt
            if float(particle["life"]) > 0:
                next_particles.append(particle)
        self.particles = next_particles
        next_pulses = []
        for pulse in self.pulses:
            pulse["radius"] = float(pulse["radius"]) + self.width * 0.06 * dt
            pulse["life"] = float(pulse["life"]) - dt
            if float(pulse["life"]) > 0:
                next_pulses.append(pulse)
        self.pulses = next_pulses
        self.flash = max(0.0, self.flash - dt * 1.8)
        self.impact_squash = max(0.0, self.impact_squash - dt * 5.5)
        zoom_blend = 1.0 - math.exp(-dt * 2.8)
        self.camera_zoom += (self.target_camera_scale() - self.camera_zoom) * zoom_blend

    def frame(self, time_sec: float) -> Image.Image:
        """Render the reference-led, full-canvas satisfying composition."""
        scale = self.camera_scale()
        image = self.background.copy().convert("RGBA")

        # Sparse dust only: the vortex and its growing black centre own the shot.
        atmosphere = Image.new("RGBA", image.size, (0, 0, 0, 0))
        atmosphere_draw = ImageDraw.Draw(atmosphere)
        for x, base_y, radius, phase, speed in self.stars:
            y = (base_y + time_sec * speed) % self.height
            alpha = round(18 + 38 * (0.5 + 0.5 * math.sin(time_sec * 1.35 + phase)))
            atmosphere_draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(175, 195, 235, alpha),
            )
        image = Image.alpha_composite(image, atmosphere)

        rings_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rings_draw = ImageDraw.Draw(rings_layer)
        glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        visual_total = max(1, self.ring_count)
        dense = visual_total > 60
        base_width = max(1, round(self.width * (0.0018 if dense else 0.0027)))

        for index in range(self.active, self.ring_count):
            gap = self.ring_gap(index, time_sec)
            gap_width = self.ring_gap_width(index)
            start = gap + gap_width / 2
            end = gap + 360 - gap_width / 2

            # A continuous coloured body makes this read as one thick ribbon.
            # Its radial depth matches the clear test in `_simulate_step`; the
            # following two or three narrow lines are reflections, not gates.
            tube_radius = (self.radii[index] + self.band_span * 0.5) * scale
            # The opaque body is exactly the projected physical depth. Glow and
            # the dark anti-alias outline may extend beyond it, but no coloured
            # collision-looking surface exists outside the simulated ribbon.
            tube_width = max(1, round(self.band_span * scale))
            tube_box = (
                self.cx - tube_radius,
                self.cy - tube_radius,
                self.cx + tube_radius,
                self.cy + tube_radius,
            )
            ribbon_color = color_for(self.theme, index, visual_total, self.level * 0.012)
            active_wave = 0.5 + 0.5 * math.sin(time_sec * 7.5 + index * 0.31)
            body_strength = (0.42 + active_wave * 0.05) if index == self.active else 0.31
            body_color = tuple(
                min(255, round(7 + channel * body_strength))
                for channel in ribbon_color
            )
            tube_alpha = round(118 + active_wave * 38) if index == self.active else 74
            glow_draw.arc(
                tube_box,
                start=start,
                end=end,
                fill=(*ribbon_color, tube_alpha),
                width=tube_width + max(3, base_width * 5),
            )
            rings_draw.arc(
                tube_box,
                start=start,
                end=end,
                fill=(0, 2, 8, 245),
                width=tube_width + max(3, base_width * 2),
            )
            rings_draw.arc(
                tube_box,
                start=start,
                end=end,
                fill=(*body_color, 255),
                width=tube_width,
            )

            # Rounded body caps agree with the angular ball-clearance check and
            # remove the comb-like ends produced by many independent stripes.
            body_cap_radius = max(1.0, tube_width * 0.5)
            outline_cap_radius = body_cap_radius + max(1.0, base_width)
            for angle in (start, end):
                angle_rad = math.radians(angle)
                cap_x = self.cx + math.cos(angle_rad) * tube_radius
                cap_y = self.cy + math.sin(angle_rad) * tube_radius
                rings_draw.ellipse(
                    (
                        cap_x - outline_cap_radius,
                        cap_y - outline_cap_radius,
                        cap_x + outline_cap_radius,
                        cap_y + outline_cap_radius,
                    ),
                    fill=(0, 2, 8, 245),
                )
                rings_draw.ellipse(
                    (
                        cap_x - body_cap_radius,
                        cap_y - body_cap_radius,
                        cap_x + body_cap_radius,
                        cap_y + body_cap_radius,
                    ),
                    fill=(*body_color, 255),
                )

            if self.bands_per_ring == 3:
                reflection_fractions = (0.14, 0.50, 0.86)
            elif self.bands_per_ring == 2:
                reflection_fractions = (0.22, 0.78)
            else:
                reflection_fractions = (0.50,)

            light = tuple(min(255, round(channel * 1.10 + 24)) for channel in ribbon_color)
            for reflection_index, band_fraction in enumerate(reflection_fractions):
                world_radius = self.radii[index] + self.band_span * band_fraction
                radius = world_radius * scale
                if radius < 2:
                    continue
                core_width = base_width + (
                    1
                    if index == self.active and reflection_index == len(reflection_fractions) // 2 and active_wave > 0.56
                    else 0
                )
                glow_alpha = 108 if index == self.active else 48
                bbox = (
                    self.cx - radius,
                    self.cy - radius,
                    self.cx + radius,
                    self.cy + radius,
                )
                reflection_color = light if reflection_index == len(reflection_fractions) // 2 else ribbon_color

                glow_draw.arc(
                    bbox,
                    start=start,
                    end=end,
                    fill=(*reflection_color, glow_alpha),
                    width=max(3, core_width * 4),
                )
                rings_draw.arc(
                    bbox,
                    start=start,
                    end=end,
                    fill=(0, 0, 0, 220),
                    width=core_width + 2,
                )
                rings_draw.arc(
                    bbox,
                    start=start,
                    end=end,
                    fill=(*reflection_color, 255),
                    width=core_width,
                )
                cap_radius = max(1.0, core_width * 0.58)
                for angle in (start, end):
                    angle_rad = math.radians(angle)
                    cap_x = self.cx + math.cos(angle_rad) * radius
                    cap_y = self.cy + math.sin(angle_rad) * radius
                    rings_draw.ellipse(
                        (
                            cap_x - cap_radius,
                            cap_y - cap_radius,
                            cap_x + cap_radius,
                            cap_y + cap_radius,
                        ),
                        fill=(*reflection_color, 255),
                    )

        ring_glow = glow_layer.filter(
            ImageFilter.GaussianBlur(radius=max(2, round(self.width * 0.0065)))
        )
        image = Image.alpha_composite(image, ring_glow)
        image = Image.alpha_composite(image, rings_layer)

        effects = Image.new("RGBA", image.size, (0, 0, 0, 0))
        effects_draw = ImageDraw.Draw(effects)
        ball_color = color_for(
            self.theme,
            min(self.active, self.ring_count - 1),
            visual_total,
            time_sec * 0.018,
        )
        screen_trail = [self.screen_point(x, y, scale) for x, y in self.trail]
        for trail_index in range(1, len(screen_trail)):
            age = trail_index / max(1, len(screen_trail) - 1)
            if trail_index % 2 == 0 or trail_index == len(screen_trail) - 1:
                effects_draw.line(
                    (*screen_trail[trail_index - 1], *screen_trail[trail_index]),
                    fill=(*ball_color, round(18 + 126 * age * age)),
                    width=max(1, round(self.ball_radius * (0.18 + age * 0.48))),
                )
        for particle in self.particles:
            life = clamp(
                float(particle["life"]) / float(particle["max_life"]),
                0.0,
                1.0,
            )
            particle_radius = max(
                1.0,
                (1.5 + self.width * 0.004 * life) * (0.72 + scale * 0.28),
            )
            color = particle["color"]
            particle_x, particle_y = self.screen_point(
                float(particle["x"]),
                float(particle["y"]),
                scale,
            )
            effects_draw.ellipse(
                (
                    particle_x - particle_radius,
                    particle_y - particle_radius,
                    particle_x + particle_radius,
                    particle_y + particle_radius,
                ),
                fill=(*color, round(245 * life)),
            )
        for pulse in self.pulses:
            life = clamp(
                float(pulse["life"]) / float(pulse["max_life"]),
                0.0,
                1.0,
            )
            pulse_radius = float(pulse["radius"]) * scale
            color = pulse["color"]
            effects_draw.ellipse(
                (
                    self.cx - pulse_radius,
                    self.cy - pulse_radius,
                    self.cx + pulse_radius,
                    self.cy + pulse_radius,
                ),
                outline=(*color, round(170 * life)),
                width=max(2, round(self.width * 0.006 * life)),
            )

        bx, by = self.screen_point(self.position[0], self.position[1], scale)
        ball_speed = math.hypot(*self.velocity)
        speed_ratio = ball_speed / max(1.0, self.width * 0.46)
        display_ball_radius = max(5.0, self.ball_radius * (0.98 + scale * 0.12))
        if ball_speed > 0:
            streak_length = display_ball_radius * clamp(speed_ratio * 2.0, 1.8, 9.0)
            ux, uy = self.velocity[0] / ball_speed, self.velocity[1] / ball_speed
            effects_draw.line(
                (bx - ux * streak_length, by - uy * streak_length, bx, by),
                fill=(*ball_color, round(92 + 23 * clamp(speed_ratio, 1.0, 5.0))),
                width=max(2, round(display_ball_radius * 0.72)),
            )
        halo_radius = display_ball_radius * (2.8 + min(1.5, speed_ratio * 0.18))
        effects_draw.ellipse(
            (bx - halo_radius, by - halo_radius, bx + halo_radius, by + halo_radius),
            fill=(*ball_color, 48),
        )
        locator_radius = display_ball_radius * 1.38
        effects_draw.ellipse(
            (
                bx - locator_radius,
                by - locator_radius,
                bx + locator_radius,
                by + locator_radius,
            ),
            outline=(245, 250, 255, 145),
            width=max(1, round(self.width * 0.0015)),
        )
        image = Image.alpha_composite(
            image,
            effects.filter(
                ImageFilter.GaussianBlur(radius=max(2, round(self.width * 0.0055)))
            ),
        )
        image = Image.alpha_composite(image, effects)

        # Layered sphere shading plus real impact squash replaces the flat icon.
        ball_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ball_draw = ImageDraw.Draw(ball_layer)
        ball_rx = display_ball_radius * (1.0 + self.impact_squash * 0.24)
        ball_ry = display_ball_radius * (1.0 - self.impact_squash * 0.18)
        shadow_offset = display_ball_radius * 0.38
        ball_draw.ellipse(
            (
                bx - ball_rx + shadow_offset,
                by - ball_ry + shadow_offset,
                bx + ball_rx + shadow_offset,
                by + ball_ry + shadow_offset,
            ),
            fill=(0, 0, 0, 175),
        )
        gradient_steps = max(4, round(display_ball_radius))
        for gradient_index in range(gradient_steps, 0, -1):
            fraction = gradient_index / gradient_steps
            shade = 0.58 + (1.0 - fraction) * 0.52
            sphere_color = tuple(
                min(255, round(channel * shade + (1.0 - fraction) * 12))
                for channel in ball_color
            )
            ball_draw.ellipse(
                (
                    bx - ball_rx * fraction,
                    by - ball_ry * fraction,
                    bx + ball_rx * fraction,
                    by + ball_ry * fraction,
                ),
                fill=(*sphere_color, 255),
            )
        ball_draw.ellipse(
            (bx - ball_rx, by - ball_ry, bx + ball_rx, by + ball_ry),
            outline=(250, 253, 255, 250),
            width=max(2, round(self.width * 0.0024)),
        )
        highlight_radius = display_ball_radius * 0.29
        highlight_x = bx - ball_rx * 0.30
        highlight_y = by - ball_ry * 0.34
        ball_draw.ellipse(
            (
                highlight_x - highlight_radius,
                highlight_y - highlight_radius,
                highlight_x + highlight_radius,
                highlight_y + highlight_radius,
            ),
            fill=(255, 255, 255, 235),
        )
        image = Image.alpha_composite(image, ball_layer)

        if self.flash > 0:
            flash_alpha = round(clamp(self.flash, 0.0, 1.0) * 34)
            image = Image.alpha_composite(
                image,
                Image.new("RGBA", image.size, (255, 255, 255, flash_alpha)),
            )

        # One hook plus one central count: no cards, timer, streak or CTA.
        draw = ImageDraw.Draw(image)
        remaining = max(0, self.ring_count - self.active)
        title_font = fitted_font(
            self.title,
            max(22, round(self.width * 0.044)),
            max(15, round(self.width * 0.027)),
            round(self.width * 0.88),
            bold=True,
        )
        if self.completed_at is None and self.failed_at is None:
            draw_centered(
                draw,
                (self.cx, self.height * SOCIAL_HOOK_CENTER_Y),
                self.title,
                title_font,
                (255, 255, 255, 245),
                stroke=max(1, round(self.width * 0.0022)),
            )
            counter_pulse = 1.0
            if remaining == 1:
                counter_pulse += 0.07 * (0.5 + 0.5 * math.sin(time_sec * 8.0))
            counter_font = font(
                max(15, round(self.width * 0.031 * counter_pulse)),
                bold=True,
            )
            counter_color = (
                (*ball_color, 248)
                if remaining == 1
                else (245, 248, 255, 225)
            )
            # The reference keeps the count central, but it must never disappear
            # under the ball. A small continuous repulsion moves it only during
            # a centre crossing and returns it smoothly afterwards.
            counter_x, counter_y = self.cx, self.cy
            counter_dx, counter_dy = bx - self.cx, by - self.cy
            counter_distance = math.hypot(counter_dx, counter_dy)
            # Include both the ball halo and the glyph footprint. The previous
            # small radius technically avoided the centre point but still let
            # the sphere visually merge with the number on a phone display.
            counter_safe_radius = self.width * 0.082 + display_ball_radius
            if counter_distance < counter_safe_radius:
                if counter_distance < 0.001:
                    velocity_length = max(0.001, ball_speed)
                    counter_dx = self.velocity[0] / velocity_length
                    counter_dy = self.velocity[1] / velocity_length
                    counter_distance = 1.0
                push = counter_safe_radius - counter_distance
                counter_x -= counter_dx / counter_distance * push
                counter_y -= counter_dy / counter_distance * push
            draw_centered(
                draw,
                (counter_x, counter_y),
                str(remaining),
                counter_font,
                counter_color,
                stroke=max(1, round(self.width * 0.0015)),
            )
        else:
            outcome = "ESCAPED" if self.completed_at is not None else "SO CLOSE"
            outcome_font = fitted_font(
                outcome,
                max(34, round(self.width * 0.070)),
                max(22, round(self.width * 0.045)),
                round(self.width * 0.82),
                bold=True,
            )
            outcome_time = self.completed_at if self.completed_at is not None else self.failed_at
            outcome_age = time_sec - (outcome_time if outcome_time is not None else time_sec)
            outcome_y = self.cy + math.sin(
                clamp(outcome_age / 0.28, 0.0, 1.0) * math.pi
            ) * self.height * 0.009
            draw_centered(
                draw,
                (self.cx, outcome_y),
                outcome,
                outcome_font,
                (255, 255, 255, 255),
                stroke=max(2, round(self.width * 0.003)),
            )
        return image.convert("RGB")

def render(args: argparse.Namespace) -> dict[str, object]:
    width = int(os.environ.get("GAME_RENDER_WIDTH", args.width))
    height = int(os.environ.get("GAME_RENDER_HEIGHT", args.height))
    fps = int(os.environ.get("GAME_RENDER_FPS", args.fps))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    difficulty = args.difficulty if args.difficulty is not None else args.rings
    if args.game == "ball-escape":
        game = BallEscape(width, height, fps, args.duration, difficulty, args.seed, args.theme, args.title)
    else:
        game = create_game(args.game, width, height, fps, args.duration, difficulty, args.seed, args.theme, args.title)
    variation = game_variation_manifest(args.game, game)
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
    external_music_file = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None

    with tempfile.TemporaryDirectory(prefix="clipmaker-game-", dir=str(output.parent)) as temp_dir:
        silent = Path(temp_dir) / "silent.mp4"
        audio = Path(temp_dir) / "effects.wav"
        generated_music = Path(temp_dir) / "original-generated-track.wav"
        video_crf = os.environ.get("GAME_VIDEO_CRF", "15")
        video_preset = os.environ.get("GAME_VIDEO_PRESET", "slow")
        encode = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-vf", "scale=1080:1920:flags=lanczos",
            "-c:v", "libx264", "-preset", video_preset, "-tune", "animation", "-crf", video_crf,
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-an", str(silent),
        ]
        process = subprocess.Popen(encode, stdin=subprocess.PIPE)
        assert process.stdin is not None
        try:
            frame_count = round(args.duration * fps)
            rendered_frames = frame_count
            for frame_index in range(frame_count):
                time_sec = frame_index / fps
                game.update(time_sec)
                process.stdin.write(game.frame(time_sec).tobytes())
                if game.completed_at is not None and time_sec - game.completed_at >= 1.6:
                    rendered_frames = frame_index + 1
                    break
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("ffmpeg n'a pas pu encoder les images du jeu")

        if args.sound_pack == "auto":
            if args.game == "shape-tunnel":
                selected_sound_pack = "asmr"
            elif args.game == "laser-dodge":
                selected_sound_pack = "arcade"
            elif args.game == "boss-battle":
                selected_sound_pack = "impact"
            else:
                selected_sound_pack = "glass"
        else:
            selected_sound_pack = args.sound_pack
        actual_duration = rendered_frames / fps
        synth_audio(actual_duration, game.events, audio, args.seed, selected_sound_pack, include_bed=False)
        if external_music_file:
            music_source = external_music_file
        else:
            if args.game == "shape-tunnel":
                synth_peaceful_music(generated_music, args.seed)
            else:
                synth_original_music(generated_music, args.seed)
            music_source = generated_music

        effective_music_mode = "continuous" if args.game == "shape-tunnel" else args.music_mode
        if effective_music_mode == "hit-reveal":
            audio_filter = build_hit_reveal_filter(
                game.music_hits,
                actual_duration,
                args.music_volume,
                args.seed,
                outcome_time=getattr(game, "music_outcome_at", None),
                ambient_floor=0.10 if args.game == "boss-battle" else 0.0,
            )
        else:
            audio_filter = f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.80[fx];[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={args.music_volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
        mux = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
            "-stream_loop", "-1", "-i", str(music_source),
            "-filter_complex", audio_filter,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output),
        ]
        subprocess.run(mux, check=True)

    completed_at = round(game.completed_at, 3) if game.completed_at is not None else None
    reported_difficulty = game.total if args.game == "laser-dodge" else difficulty
    if args.game == "ball-escape":
        outcome = "escaped" if game.completed_at is not None else "failed"
    elif args.game == "shape-tunnel":
        outcome = "escaped" if game.completed_at is not None else "incomplete"
    elif args.game == "laser-dodge":
        outcome = "collision" if game.crashed else "survived"
    else:
        outcome = game.winner if game.winner in {"player", "boss", "draw"} else "draw"

    return {
        "ok": True,
        **variation,
        "output": output.name,
        "duration": round(actual_duration, 3),
        "seed": args.seed,
        "game": args.game,
        "difficulty": reported_difficulty,
        "rings": difficulty if args.game == "ball-escape" else None,
        "theme": args.theme,
        "sound_pack": selected_sound_pack,
        "sound_mode": args.sound_pack,
        "music": external_music_file.name if external_music_file else ("Peaceful generated ambient track" if args.game == "shape-tunnel" else "Original generated track"),
        "music_generated": external_music_file is None,
        "music_mode": effective_music_mode,
        "music_hits": len(game.music_hits),
        "events": len(game.events),
        "completed_at": completed_at,
        "outcome": outcome,
        "levels_completed": game.level - 1,
        "units_completed": game.active,
        "units_total": getattr(game, "total", getattr(game, "ring_count", difficulty)),
        "max_speed_x": round(game.max_speed_ratio, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--game", choices=("ball-escape", *GAME_CLASSES), default="ball-escape")
    parser.add_argument("--difficulty", type=int)
    parser.add_argument("--rings", type=int, default=14)
    parser.add_argument("--theme", choices=sorted(THEMES), default="neon")
    parser.add_argument("--sound-pack", choices=("auto", "meme", "funny", "arcade", "impact", "asmr", "glass"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-mode", choices=("hit-reveal", "continuous"), default="hit-reveal")
    parser.add_argument("--music-volume", type=float, default=0.62)
    parser.add_argument("--title", default="WILL THE BALL ESCAPE?")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()
    args.duration = clamp(args.duration, 5.0, 60.0)
    args.rings = round(clamp(args.rings, 40, 300))
    args.music_volume = clamp(args.music_volume, 0.0, 1.0)
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
