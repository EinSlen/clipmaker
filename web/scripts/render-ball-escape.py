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

from game_variants import GAME_CLASSES, create_game


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
                envelope = math.exp(-elapsed * 27.0) * min(1.0, elapsed * 90.0)
                bent_frequency = max(45.0, frequency * 0.42 * (1.0 - elapsed * 2.4))
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.18 * math.sin(2 * math.pi * bent_frequency * 0.51 * elapsed)
            elif kind == "asmr":
                progress = clamp(elapsed / max(0.001, tone_length), 0.0, 1.0)
                envelope = min(1.0, elapsed * 120.0) * math.exp(-progress * 4.8)
                bent_frequency = frequency * (1.025 - progress * 0.025)
                phase = 2 * math.pi * bent_frequency * elapsed
                tone = math.sin(phase)
                tone += 0.22 * math.sin(phase * 2.0)
                tone += 0.08 * math.sin(phase * 3.01)
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
    # Three-note hook in the first half-second: useful before viewers can swipe.
    for hook_time, hook_note in ((0.0, 392.0), (0.14, 523.25), (0.30, 783.99)):
        add_tone(hook_time, hook_note, 0.14, 0.22, "arcade")
    if include_bed:
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


def build_hit_reveal_filter(hit_times: list[float], duration: float, volume: float, seed: int) -> str:
    """Build a sequential sampler: every collision unlocks the next music slice."""
    selected: list[float] = []
    for hit_time in sorted([0.0, *hit_times]):
        bounded = clamp(hit_time, 0.0, max(0.0, duration - 0.04))
        if not selected or bounded - selected[-1] >= 0.075:
            selected.append(bounded)
    selected = selected[:96]
    if not selected:
        return f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.80[fx];[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]"

    split_outputs = "".join(f"[source{index}]" for index in range(len(selected)))
    filters = [
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.72[fx]",
        f"[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asplit={len(selected)}{split_outputs}",
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
        self.title = title.strip().upper()[:52] or "WILL THE BALL ESCAPE?"
        self.rng = random.Random(seed)
        self.cx = width / 2
        self.cy = height * 0.55
        self.ball_radius = max(7, round(width * 0.015))
        inner = width * 0.140
        outer = width * 0.455
        self.radii = [inner + (outer - inner) * i / max(1, rings - 1) for i in range(rings)]
        spiral_start = self.rng.uniform(0, 360)
        spiral_step = self.rng.choice((-1, 1)) * self.rng.uniform(9.0, 19.0)
        self.base_gaps = [(spiral_start + index * spiral_step + self.rng.uniform(-11.0, 11.0)) % 360 for index in range(rings)]
        self.rotations = [self.rng.choice((-1, 1)) * self.rng.uniform(18.0, 46.0) for _ in range(rings)]
        self.gap_widths = [self.rng.uniform(62.0, 74.0) for _ in range(rings)]
        self.active = 0
        self.level = 1
        self.last_clear = 0.0
        self.completed_at: float | None = None
        self.position = [self.cx + 4, self.cy + 4]
        # Always launch upward first so gravity visibly bends the trajectory
        # into an arc instead of looking like random linear movement.
        launch_sector = (210, 246) if self.rng.random() < 0.5 else (294, 330)
        start_angle = self.rng.uniform(math.radians(launch_sector[0]), math.radians(launch_sector[1]))
        speed = width * 0.50
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
        self.will_escape = seed % 4 != 0
        self.final_unlock = duration * (0.850 + (seed % 5) * 0.006)
        self.failed_at: float | None = None
        self.simulation_time = 0.0
        self.level_started_at = 0.0
        self.min_clear_interval = max(0.22, duration * 0.033)
        self.stars = [
            (
                self.rng.uniform(0, width),
                self.rng.uniform(0, height),
                self.rng.uniform(0.7, 2.2),
                self.rng.uniform(0, math.tau),
                self.rng.uniform(4, 18),
            )
            for _ in range(64)
        ]
        self.background = self.make_background()

    def record_music_hit(self, time_sec: float) -> None:
        if not self.music_hits or time_sec - self.music_hits[-1] >= 0.075:
            self.music_hits.append(time_sec)

    def make_background(self) -> Image.Image:
        base = THEMES[self.theme][0]
        background = Image.new("RGB", (self.width, self.height), base)
        draw = ImageDraw.Draw(background)
        for y in range(self.height):
            center_distance = abs(y - self.cy) / max(1, self.height)
            glow = round(max(0.0, 1.0 - center_distance * 2.1) * 7)
            line = tuple(min(255, channel + glow) for channel in base)
            draw.line((0, y, self.width, y), fill=line)
        return background

    def ring_gap(self, index: int, time_sec: float) -> float:
        natural = (self.base_gaps[index] + self.rotations[index] * time_sec) % 360
        if index == self.active and self.completed_at is None:
            stalled = time_sec - self.last_clear
            final_ring = index == self.ring_count - 1
            late_chase = clamp((time_sec - self.duration * 0.58) / max(0.25, self.duration * 0.14), 0.0, 1.0)
            schedule_pressure = 0.0 if final_ring else clamp(
                (time_sec - self.ring_deadline(index)) / max(0.20, self.duration * 0.035), 0.0, 1.0
            )
            help_after = 0.25 if final_ring and time_sec >= self.final_unlock else 0.58 - late_chase * 0.48
            if stalled > help_after or schedule_pressure > 0.0:
                dx, dy = self.position[0] - self.cx, self.position[1] - self.cy
                ball_angle = math.degrees(math.atan2(dy, dx)) % 360
                maximum_follow = 0.98 if final_ring and time_sec >= self.final_unlock and self.will_escape else 0.62 + late_chase * 0.38
                follow = clamp((stalled - help_after) / 1.25, 0.0, maximum_follow)
                follow = max(follow, schedule_pressure * 0.985)
                return (natural + angle_delta(ball_angle, natural) * follow) % 360
        return natural

    def ring_deadline(self, index: int) -> float:
        if index >= self.ring_count - 1:
            return self.final_unlock
        pre_final_rings = max(1, self.ring_count - 1)
        paced_progress = 0.04 + 0.70 * (index + 1) / pre_final_rings
        return self.level_started_at + self.duration * paced_progress

    def reset_level(self, time_sec: float) -> None:
        self.level += 1
        self.level_started_at = time_sec
        self.active = 0
        self.last_clear = time_sec
        self.completed_at = None
        self.position = [self.cx, self.cy]
        launch_sector = (210, 246) if self.rng.random() < 0.5 else (294, 330)
        angle = self.rng.uniform(math.radians(launch_sector[0]), math.radians(launch_sector[1]))
        speed = self.width * 0.54
        self.velocity = [math.cos(angle) * speed, math.sin(angle) * speed]
        self.base_gaps = [(gap + self.rng.uniform(70, 210)) % 360 for gap in self.base_gaps]
        self.streak = 0
        self.will_escape = (self.seed + self.level * 3) % 4 != 0
        self.final_unlock = time_sec + self.duration * (0.850 + ((self.seed + self.level) % 5) * 0.006)
        self.failed_at = None

    def add_particles(self, angle: float, color: tuple[int, int, int]) -> None:
        for _ in range(18):
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

        # Real downward gravity creates visible parabolic falls. A small,
        # continuous energy gain plus the progress floor makes every run speed
        # up from roughly 1x to 3x-5x instead of staying mechanically constant.
        self.gravity_g = 1.0 + progress * 0.42 + time_progress * 0.22
        gravity = self.height * self.gravity_g
        self.velocity[1] += gravity * dt
        continuous_boost = 1.0 + dt * (0.018 + progress * 0.026 + time_progress * 0.040)
        self.velocity[0] *= continuous_boost
        self.velocity[1] *= continuous_boost

        speed = math.hypot(*self.velocity)
        min_speed = self.width * (0.43 + progress * 0.36 + time_progress * 0.14)
        max_speed = self.width * (0.64 + progress * 0.56 + time_progress * 0.18)
        if speed < min_speed:
            scale = min_speed / max(speed, 0.001)
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        elif speed > max_speed:
            scale = max_speed / speed
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        self.max_speed_ratio = max(self.max_speed_ratio, math.hypot(*self.velocity) / max(1.0, self.width * 0.50))

        if self.active < self.ring_count:
            stalled = time_sec - self.last_clear
            final_ring = self.active == self.ring_count - 1
            late_chase = clamp((time_sec - self.duration * 0.58) / max(0.25, self.duration * 0.14), 0.0, 1.0)
            schedule_pressure = 0.0 if final_ring else clamp(
                (time_sec - self.ring_deadline(self.active)) / max(0.20, self.duration * 0.035), 0.0, 1.0
            )
            help_after = 0.25 if final_ring and time_sec >= self.final_unlock else 0.54 - late_chase * 0.44
            if stalled > help_after or schedule_pressure > 0.0:
                gap_angle = math.radians(self.ring_gap(self.active, time_sec))
                # Aim beyond the line. Targeting the ring itself pulls the ball
                # back inward just before its full diameter has cleared it.
                target_radius = self.radii[self.active] + self.ball_radius * 2.35
                target_x = self.cx + math.cos(gap_angle) * target_radius
                target_y = self.cy + math.sin(gap_angle) * target_radius
                target_angle = math.atan2(target_y - self.position[1], target_x - self.position[0])
                current_speed = math.hypot(*self.velocity)
                max_blend = 0.18 if final_ring and time_sec >= self.final_unlock and self.will_escape else 0.075 + late_chase * 0.145
                blend = clamp((stalled - help_after) * 0.055, 0.0, max_blend)
                if schedule_pressure > 0.0:
                    blend = max(blend, 0.035 + schedule_pressure * 0.115)
                self.velocity[0] = self.velocity[0] * (1 - blend) + math.cos(target_angle) * current_speed * blend
                self.velocity[1] = self.velocity[1] * (1 - blend) + math.sin(target_angle) * current_speed * blend

        self.position[0] += self.velocity[0] * dt
        self.position[1] += self.velocity[1] * dt
        dx, dy = self.position[0] - self.cx, self.position[1] - self.cy
        distance = max(0.001, math.hypot(dx, dy))

        if self.active < self.ring_count:
            radius = self.radii[self.active]
            nx, ny = dx / distance, dy / distance
            outward_speed = self.velocity[0] * nx + self.velocity[1] * ny
            ball_angle = math.degrees(math.atan2(dy, dx)) % 360
            stalled = time_sec - self.last_clear
            final_ring = self.active == self.ring_count - 1
            gate_closed = final_ring and (time_sec < self.final_unlock or not self.will_escape)
            if gate_closed:
                widened_gap = 0.0
            elif final_ring:
                unlock_progress = clamp((time_sec - self.final_unlock) / max(0.25, self.duration * 0.08), 0.0, 1.0)
                widened_gap = self.gap_widths[self.active] + unlock_progress * 70.0
            else:
                late_bonus = clamp((time_sec - self.duration * 0.58) / max(0.25, self.duration * 0.14), 0.0, 1.0) * 70.0
                widened_gap = min(self.gap_widths[self.active] + 36.0 + late_bonus, self.gap_widths[self.active] + max(0.0, stalled - 0.58) * 22.0 + late_bonus)
                schedule_pressure = clamp(
                    (time_sec - self.ring_deadline(self.active)) / max(0.20, self.duration * 0.035), 0.0, 1.0
                )
                widened_gap = max(widened_gap, self.gap_widths[self.active] + schedule_pressure * 105.0)
            ball_clearance = self.ball_radius + max(2.0, self.width * 0.006)
            occupied_half_angle = math.degrees(math.asin(min(0.92, ball_clearance / max(radius, ball_clearance + 0.01))))
            center_tolerance = max(0.0, widened_gap / 2 - occupied_half_angle)
            in_gap = not gate_closed and abs(angle_delta(ball_angle, self.ring_gap(self.active, time_sec))) <= center_tolerance

            if distance + self.ball_radius >= radius and outward_speed > 0:
                can_clear = stalled >= self.min_clear_interval
                if in_gap and can_clear:
                    if distance >= radius + self.ball_radius * 0.75:
                        color = color_for(self.theme, self.active, self.ring_count)
                        self.add_particles(math.atan2(dy, dx), color)
                        self.pulses.append({"radius": radius, "life": 0.42, "max_life": 0.42, "color": color})
                        self.flash = max(self.flash, 0.18)
                        self.impact_squash = max(self.impact_squash, 0.45)
                        self.events.append((time_sec, 620 + self.active * 2.2, 0.52, "clear"))
                        self.record_music_hit(time_sec)
                        clear_batch = 1
                        next_active = min(self.ring_count, self.active + 1)
                        if next_active >= self.ring_count and (time_sec < self.final_unlock or not self.will_escape):
                            next_active = self.ring_count - 1
                        self.active = next_active
                        if time_sec - self.last_streak_at < 0.34:
                            self.streak += clear_batch
                        else:
                            self.streak = clear_batch
                        self.last_streak_at = time_sec
                        acceleration = min(1.045, 1.015 + self.active / max(1, self.ring_count) * 0.030)
                        self.velocity[0] *= acceleration
                        self.velocity[1] *= acceleration
                        self.last_clear = time_sec
                        if self.active >= self.ring_count:
                            self.completed_at = time_sec
                            self.add_victory_particles()
                            self.flash = 0.72
                            self.events.extend([
                                (time_sec + 0.06, 783.99, 0.58, "victory"),
                                (time_sec + 0.18, 987.77, 0.62, "victory"),
                                (time_sec + 0.32, 1318.51, 0.70, "victory"),
                            ])
                else:
                    self.position[0] = self.cx + nx * (radius - self.ball_radius - 1)
                    self.position[1] = self.cy + ny * (radius - self.ball_radius - 1)
                    self.velocity[0] -= 2 * outward_speed * nx
                    self.velocity[1] -= 2 * outward_speed * ny
                    bounce_boost = 1.008 + time_progress * 0.008
                    self.velocity[0] *= bounce_boost
                    self.velocity[1] *= bounce_boost
                    tangent_push = self.rng.uniform(-18, 18)
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

        if self.completed_at is None and not self.will_escape and self.failed_at is None and time_sec >= self.duration - 0.62:
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

    def frame(self, time_sec: float) -> Image.Image:
        image = self.background.copy()
        atmosphere = Image.new("RGBA", image.size, (0, 0, 0, 0))
        atmosphere_draw = ImageDraw.Draw(atmosphere)
        for x, base_y, radius, phase, speed in self.stars:
            y = (base_y + time_sec * speed) % self.height
            alpha = round(45 + 65 * (0.5 + 0.5 * math.sin(time_sec * 1.7 + phase)))
            atmosphere_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(170, 200, 255, alpha))
        image = Image.alpha_composite(image.convert("RGBA"), atmosphere)
        rings_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rings_draw = ImageDraw.Draw(rings_layer)
        glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        for index in range(self.active, self.ring_count):
            radius = self.radii[index]
            gap = self.ring_gap(index, time_sec)
            gap_width = self.gap_widths[index]
            if index == self.active == self.ring_count - 1:
                if time_sec < self.final_unlock or not self.will_escape:
                    gap_width = 0.25
                else:
                    unlock_progress = clamp((time_sec - self.final_unlock) / max(0.25, self.duration * 0.08), 0.0, 1.0)
                    gap_width += unlock_progress * 70.0
            start = gap + gap_width / 2
            end = gap + 360 - gap_width / 2
            color = color_for(self.theme, index, self.ring_count, self.level * 0.015)
            active_pulse = 1.0 + (0.22 * (0.5 + 0.5 * math.sin(time_sec * 6.5)) if index == self.active else 0.0)
            dense = self.ring_count > 80
            strokes = ((0, 255),) if dense else ((-3, 125), (0, 255), (3, 125))
            for offset, alpha in strokes:
                current = radius + offset
                bbox = (self.cx - current, self.cy - current, self.cx + current, self.cy + current)
                base_width = 1 if self.ring_count > 180 else 2 if dense else 4
                rings_draw.arc(bbox, start=start, end=end, fill=(*color, alpha), width=max(1, round(base_width * active_pulse)) if not offset else 2)
            bbox = (self.cx - radius, self.cy - radius, self.cx + radius, self.cy + radius)
            if not dense or index == self.active or index % 12 == 0:
                glow_draw.arc(bbox, start=start, end=end, fill=(*color, 145 if index == self.active else 55), width=10 if index == self.active else 5)

        blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=9))
        image = Image.alpha_composite(image.convert("RGBA"), blurred)
        image = Image.alpha_composite(image, rings_layer)

        effects = Image.new("RGBA", image.size, (0, 0, 0, 0))
        effects_draw = ImageDraw.Draw(effects)
        ball_color = color_for(self.theme, self.active + 2, self.ring_count, time_sec * 0.025)
        for index, (x, y) in enumerate(self.trail):
            age = (index + 1) / max(1, len(self.trail))
            radius = max(2, round(self.ball_radius * age * 0.75))
            effects_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*ball_color, round(120 * age)))
        for particle in self.particles:
            life = clamp(float(particle["life"]) / float(particle["max_life"]), 0.0, 1.0)
            radius = 2 + 4 * life
            color = particle["color"]
            x, y = float(particle["x"]), float(particle["y"])
            effects_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, round(255 * life)))
        for pulse in self.pulses:
            life = clamp(float(pulse["life"]) / float(pulse["max_life"]), 0.0, 1.0)
            radius = float(pulse["radius"])
            color = pulse["color"]
            effects_draw.ellipse(
                (self.cx - radius, self.cy - radius, self.cx + radius, self.cy + radius),
                outline=(*color, round(190 * life)),
                width=max(2, round(7 * life)),
            )
        bx, by = self.position
        ball_speed = math.hypot(*self.velocity)
        speed_ratio = ball_speed / max(1.0, self.width * 0.50)
        if ball_speed > 0:
            streak_length = self.ball_radius * clamp(speed_ratio * 1.65, 1.4, 6.0)
            ux, uy = self.velocity[0] / ball_speed, self.velocity[1] / ball_speed
            effects_draw.line(
                (bx - ux * streak_length, by - uy * streak_length, bx, by),
                fill=(*ball_color, round(80 + 22 * clamp(speed_ratio, 1.0, 5.0))),
                width=max(3, round(self.ball_radius * 0.95)),
            )
        effects_draw.ellipse((bx - self.ball_radius * 2.1, by - self.ball_radius * 2.1, bx + self.ball_radius * 2.1, by + self.ball_radius * 2.1), fill=(*ball_color, 100))
        image = Image.alpha_composite(image, effects.filter(ImageFilter.GaussianBlur(radius=5)))
        image = Image.alpha_composite(image, effects)
        draw = ImageDraw.Draw(image)
        ball_rx = self.ball_radius * (1.0 + self.impact_squash * 0.22)
        ball_ry = self.ball_radius * (1.0 - self.impact_squash * 0.16)
        draw.ellipse((bx - ball_rx, by - ball_ry, bx + ball_rx, by + ball_ry), fill=(245, 250, 255, 255), outline=(*ball_color, 255), width=3)
        draw.ellipse((bx - ball_rx * 0.45, by - ball_ry * 0.55, bx - ball_rx * 0.05, by - ball_ry * 0.15), fill=(255, 255, 255, 220))

        if self.flash > 0:
            flash_alpha = round(clamp(self.flash, 0.0, 1.0) * 45)
            flash_layer = Image.new("RGBA", image.size, (255, 255, 255, flash_alpha))
            image = Image.alpha_composite(image, flash_layer)
            draw = ImageDraw.Draw(image)

        title_font = fitted_font(self.title, max(20, round(self.width * 0.052)), max(13, round(self.width * 0.029)), round(self.width * 0.90), bold=True)
        label_font = font(max(10, round(self.width * 0.018)), bold=True)
        value_font = font(max(16, round(self.width * 0.032)), bold=True)
        small_font = font(max(11, round(self.width * 0.022)), bold=True)
        cta_text = "FOLLOW FOR THE NEXT RUN"
        cta_font = fitted_font(cta_text, max(13, round(self.width * 0.024)), max(10, round(self.width * 0.018)), round(self.width * 0.80), bold=True)
        accent = (*ball_color, 255)

        # Purpose-built mobile-game HUD: no development metadata is rendered.
        header_y = self.height * 0.052
        draw.line((self.width * 0.08, header_y, self.width * 0.31, header_y), fill=(*ball_color, 150), width=2)
        draw.line((self.width * 0.69, header_y, self.width * 0.92, header_y), fill=(*ball_color, 150), width=2)
        draw_centered(draw, (self.cx, header_y), "BALL ESCAPE", label_font, accent)
        draw_centered(draw, (self.cx, self.height * 0.095), self.title, title_font, (255, 255, 255, 255), stroke=2)

        panel_y1, panel_y2 = self.height * 0.135, self.height * 0.184
        left_panel = (self.width * 0.08, panel_y1, self.width * 0.46, panel_y2)
        right_panel = (self.width * 0.54, panel_y1, self.width * 0.92, panel_y2)
        for panel in (left_panel, right_panel):
            draw.rounded_rectangle(panel, radius=max(6, round(self.width * 0.012)), fill=(3, 6, 12, 220), outline=(*ball_color, 120), width=2)
        speed_ratio = self.max_speed_ratio
        remaining = max(0, self.ring_count - self.active)
        draw.text((left_panel[0] + self.width * 0.025, (panel_y1 + panel_y2) / 2), "SPEED", font=label_font, fill=(135, 150, 180, 255), anchor="lm")
        draw.text((left_panel[2] - self.width * 0.025, (panel_y1 + panel_y2) / 2), f"{speed_ratio:.1f}X", font=value_font, fill=accent, anchor="rm")
        draw.text((right_panel[0] + self.width * 0.025, (panel_y1 + panel_y2) / 2), "RINGS", font=label_font, fill=(135, 150, 180, 255), anchor="lm")
        draw.text((right_panel[2] - self.width * 0.025, (panel_y1 + panel_y2) / 2), str(remaining), font=value_font, fill=(255, 255, 255, 255), anchor="rm")
        final_ring = self.active == self.ring_count - 1 and self.completed_at is None
        if final_ring and (time_sec < self.final_unlock or not self.will_escape):
            status_text = "FINAL GATE LOCKED"
        elif final_ring:
            status_text = "FINAL GATE OPEN — LAST CHANCE"
        else:
            status_text = f"GRAVITY {self.gravity_g:.1f}G  •  ACCELERATING"
        draw_centered(draw, (self.cx, self.height * 0.205), status_text, label_font, accent)

        victory_pulse = 1.0 + (0.11 * math.sin(time_sec * 12.0) if self.completed_at is not None else 0.0)
        counter_font = font(max(32, round(self.width * 0.072 * victory_pulse)), bold=True)
        center_text = "ESCAPED!" if self.completed_at is not None else "SO CLOSE!" if self.failed_at is not None else str(remaining)
        center_color = (255, 255, 255, 255) if remaining else accent
        draw_centered(draw, (self.cx, self.cy), center_text, counter_font, center_color, stroke=2)
        if remaining:
            draw_centered(draw, (self.cx, self.cy + self.height * 0.040), "RINGS LEFT", label_font, (150, 165, 195, 230))

        footer_y1, footer_y2 = self.height * 0.885, self.height * 0.935
        footer = (self.width * 0.08, footer_y1, self.width * 0.92, footer_y2)
        draw.rounded_rectangle(footer, radius=max(6, round(self.width * 0.012)), fill=(3, 6, 12, 225), outline=(255, 255, 255, 40), width=2)
        time_left = max(0, math.ceil(self.duration - time_sec))
        clock = f"{time_left // 60:02d}:{time_left % 60:02d}"
        draw.text((footer[0] + self.width * 0.025, (footer_y1 + footer_y2) / 2), "TIME LEFT", font=label_font, fill=(135, 150, 180, 255), anchor="lm")
        draw.text((self.width * 0.38, (footer_y1 + footer_y2) / 2), clock, font=value_font, fill=(255, 255, 255, 255), anchor="mm")
        streak_text = f"STREAK ×{self.streak}" if self.streak >= 2 else "NO MISSES"
        draw.text((footer[2] - self.width * 0.025, (footer_y1 + footer_y2) / 2), streak_text, font=small_font, fill=accent, anchor="rm")
        draw_centered(draw, (self.cx, self.height * 0.965), cta_text, cta_font, (210, 220, 245, 255), stroke=1)
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
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
    external_music_file = Path(args.music).resolve() if args.music and Path(args.music).is_file() else None

    with tempfile.TemporaryDirectory(prefix="clipmaker-game-", dir=str(output.parent)) as temp_dir:
        silent = Path(temp_dir) / "silent.mp4"
        audio = Path(temp_dir) / "effects.wav"
        generated_music = Path(temp_dir) / "original-generated-track.wav"
        video_crf = "22" if args.game == "shape-tunnel" else "19"
        encode = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-vf", "scale=1080:1920:flags=lanczos",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", video_crf, "-pix_fmt", "yuv420p", "-an", str(silent),
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
            else:
                selector = args.seed % 10
                selected_sound_pack = "meme" if selector < 6 else "funny" if selector < 8 else "arcade" if selector < 9 else "impact"
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
            audio_filter = build_hit_reveal_filter(game.music_hits, actual_duration, args.music_volume, args.seed)
        else:
            audio_filter = f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.80[fx];[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={args.music_volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
        mux = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
            "-stream_loop", "-1", "-i", str(music_source),
            "-filter_complex", audio_filter,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output),
        ]
        subprocess.run(mux, check=True)

    return {
        "ok": True,
        "output": output.name,
        "duration": round(actual_duration, 3),
        "seed": args.seed,
        "game": args.game,
        "difficulty": difficulty,
        "rings": difficulty if args.game == "ball-escape" else None,
        "theme": args.theme,
        "sound_pack": selected_sound_pack,
        "sound_mode": args.sound_pack,
        "music": external_music_file.name if external_music_file else ("Peaceful generated ambient track" if args.game == "shape-tunnel" else "Original generated track"),
        "music_generated": external_music_file is None,
        "music_mode": effective_music_mode,
        "music_hits": len(game.music_hits),
        "events": len(game.events),
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
    parser.add_argument("--rings", type=int, default=240)
    parser.add_argument("--theme", choices=sorted(THEMES), default="neon")
    parser.add_argument("--sound-pack", choices=("auto", "meme", "funny", "arcade", "impact", "asmr"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-mode", choices=("hit-reveal", "continuous"), default="continuous")
    parser.add_argument("--music-volume", type=float, default=0.62)
    parser.add_argument("--title", default="WILL THE BALL ESCAPE?")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    args.duration = clamp(args.duration, 5.0, 60.0)
    args.rings = round(clamp(args.rings, 40, 300))
    args.music_volume = clamp(args.music_volume, 0.0, 1.0)
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
