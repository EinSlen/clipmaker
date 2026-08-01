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


def synth_audio(duration: float, events: list[tuple[float, float, float]], output: Path, seed: int, sound_pack: str) -> None:
    rate = 44_100
    samples = array("f", [0.0]) * (math.ceil(duration * rate) + 1)

    def add_tone(start: float, frequency: float, strength: float, tone_length: float, kind: str) -> None:
        length = min(int(rate * tone_length), len(samples) - int(start * rate))
        if length <= 0:
            return
        start_index = int(start * rate)
        for i in range(length):
            elapsed = i / rate
            envelope = math.exp(-elapsed * (20.0 if kind == "funny" else 27.0)) * min(1.0, elapsed * 90.0)
            if kind == "funny":
                bent_frequency = frequency * (1.0 + 0.22 * math.sin(2 * math.pi * 13 * elapsed)) * (1.0 - elapsed * 0.7)
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.28 * math.sin(2 * math.pi * bent_frequency * 1.5 * elapsed)
            elif kind == "impact":
                bent_frequency = max(45.0, frequency * 0.42 * (1.0 - elapsed * 2.4))
                tone = math.sin(2 * math.pi * bent_frequency * elapsed)
                tone += 0.18 * math.sin(2 * math.pi * bent_frequency * 0.51 * elapsed)
            else:
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
    while time_sec < duration:
        note = scale[beat_index % len(scale)] * (1.0 + audio_rng.uniform(-0.002, 0.002))
        add_tone(time_sec, note, 0.055, 0.17, "arcade")
        if beat_index % 2 == 0:
            add_tone(time_sec, 92.0, 0.09, 0.18, "impact")
        time_sec += beat / 2
        beat_index += 1

    for start, frequency, strength in events:
        add_tone(start, frequency, strength, 0.24 if sound_pack == "funny" else 0.18, sound_pack)

    peak = max(0.001, max(abs(sample) for sample in samples))
    gain = min(0.88 / peak, 1.0)
    pcm = array("h", (round(clamp(sample * gain, -1.0, 1.0) * 32767) for sample in samples))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


class BallEscape:
    def __init__(self, width: int, height: int, fps: int, duration: float, rings: int, seed: int, theme: str, title: str):
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.ring_count = rings
        self.seed = seed
        self.theme = theme
        self.title = title.strip().upper()[:52] or "LA BALLE VA-T-ELLE S'ÉCHAPPER ?"
        self.rng = random.Random(seed)
        self.cx = width / 2
        self.cy = height * 0.55
        self.ball_radius = max(9, round(width * 0.017))
        inner = width * 0.125
        outer = width * 0.455
        self.radii = [inner + (outer - inner) * i / max(1, rings - 1) for i in range(rings)]
        self.base_gaps = [self.rng.uniform(0, 360) for _ in range(rings)]
        self.rotations = [self.rng.choice((-1, 1)) * self.rng.uniform(22, 52) for _ in range(rings)]
        self.gap_widths = [self.rng.uniform(30, 42) for _ in range(rings)]
        self.active = 0
        self.level = 1
        self.last_clear = 0.0
        self.completed_at: float | None = None
        self.position = [self.cx + 4, self.cy + 4]
        start_angle = self.rng.uniform(0, math.tau)
        speed = width * 0.38
        self.velocity = [math.cos(start_angle) * speed, math.sin(start_angle) * speed]
        self.trail: list[tuple[float, float]] = []
        self.particles: list[dict[str, float | tuple[int, int, int]]] = []
        self.events: list[tuple[float, float, float]] = []
        self.last_collision = -1.0

    def ring_gap(self, index: int, time_sec: float) -> float:
        natural = (self.base_gaps[index] + self.rotations[index] * time_sec) % 360
        if index == self.active and self.completed_at is None:
            stalled = time_sec - self.last_clear
            if stalled > 1.0:
                dx, dy = self.position[0] - self.cx, self.position[1] - self.cy
                ball_angle = math.degrees(math.atan2(dy, dx)) % 360
                follow = clamp((stalled - 1.0) / 0.8, 0.0, 1.0)
                return (natural + angle_delta(ball_angle, natural) * follow) % 360
        return natural

    def reset_level(self, time_sec: float) -> None:
        self.level += 1
        self.active = 0
        self.last_clear = time_sec
        self.completed_at = None
        self.position = [self.cx, self.cy]
        angle = self.rng.uniform(0, math.tau)
        speed = self.width * 0.40
        self.velocity = [math.cos(angle) * speed, math.sin(angle) * speed]
        self.base_gaps = [(gap + self.rng.uniform(70, 210)) % 360 for gap in self.base_gaps]

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

    def update(self, time_sec: float) -> None:
        dt = 1.0 / self.fps
        if self.completed_at is not None and time_sec - self.completed_at > 1.8:
            self.reset_level(time_sec)

        self.velocity[1] += self.height * 0.052 * dt
        speed = math.hypot(*self.velocity)
        min_speed, max_speed = self.width * 0.31, self.width * 0.62
        if speed < min_speed:
            scale = min_speed / max(speed, 0.001)
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        elif speed > max_speed:
            scale = max_speed / speed
            self.velocity[0] *= scale
            self.velocity[1] *= scale

        if self.active < self.ring_count:
            stalled = time_sec - self.last_clear
            if stalled > 1.1:
                gap_angle = math.radians(self.ring_gap(self.active, time_sec))
                target_x = self.cx + math.cos(gap_angle) * self.radii[self.active]
                target_y = self.cy + math.sin(gap_angle) * self.radii[self.active]
                target_angle = math.atan2(target_y - self.position[1], target_x - self.position[0])
                current_speed = math.hypot(*self.velocity)
                blend = clamp((stalled - 1.1) * 0.045, 0.0, 0.09)
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
            widened_gap = min(165.0, self.gap_widths[self.active] + max(0.0, stalled - 1.1) * 58.0)
            in_gap = abs(angle_delta(ball_angle, self.ring_gap(self.active, time_sec))) <= widened_gap / 2

            if distance + self.ball_radius >= radius and outward_speed > 0:
                if in_gap:
                    if distance >= radius + self.ball_radius * 0.75:
                        color = color_for(self.theme, self.active, self.ring_count)
                        self.add_particles(math.atan2(dy, dx), color)
                        self.events.append((time_sec, 620 + self.active * 18, 0.52))
                        self.active += 1
                        self.last_clear = time_sec
                        if self.active >= self.ring_count:
                            self.completed_at = time_sec
                            self.events.extend([
                                (time_sec + 0.06, 783.99, 0.58),
                                (time_sec + 0.18, 987.77, 0.62),
                                (time_sec + 0.32, 1318.51, 0.70),
                            ])
                else:
                    self.position[0] = self.cx + nx * (radius - self.ball_radius - 1)
                    self.position[1] = self.cy + ny * (radius - self.ball_radius - 1)
                    self.velocity[0] -= 2 * outward_speed * nx
                    self.velocity[1] -= 2 * outward_speed * ny
                    tangent_push = self.rng.uniform(-18, 18)
                    self.velocity[0] += -ny * tangent_push
                    self.velocity[1] += nx * tangent_push
                    if time_sec - self.last_collision > 0.055:
                        self.events.append((time_sec, 260 + self.active * 16, 0.34))
                        self.last_collision = time_sec

        self.trail.append((self.position[0], self.position[1]))
        self.trail = self.trail[-24:]
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

    def frame(self, time_sec: float) -> Image.Image:
        background = THEMES[self.theme][0]
        image = Image.new("RGB", (self.width, self.height), background)
        rings_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rings_draw = ImageDraw.Draw(rings_layer)
        glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        for index in range(self.active, self.ring_count):
            radius = self.radii[index]
            gap = self.ring_gap(index, time_sec)
            gap_width = self.gap_widths[index]
            start = gap + gap_width / 2
            end = gap + 360 - gap_width / 2
            color = color_for(self.theme, index, self.ring_count, self.level * 0.015)
            for offset, alpha in ((-3, 125), (0, 255), (3, 125)):
                current = radius + offset
                bbox = (self.cx - current, self.cy - current, self.cx + current, self.cy + current)
                rings_draw.arc(bbox, start=start, end=end, fill=(*color, alpha), width=2 if offset else 4)
            bbox = (self.cx - radius, self.cy - radius, self.cx + radius, self.cy + radius)
            glow_draw.arc(bbox, start=start, end=end, fill=(*color, 145), width=12)

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
        bx, by = self.position
        effects_draw.ellipse((bx - self.ball_radius * 2.1, by - self.ball_radius * 2.1, bx + self.ball_radius * 2.1, by + self.ball_radius * 2.1), fill=(*ball_color, 100))
        image = Image.alpha_composite(image, effects.filter(ImageFilter.GaussianBlur(radius=5)))
        image = Image.alpha_composite(image, effects)
        draw = ImageDraw.Draw(image)
        draw.ellipse((bx - self.ball_radius, by - self.ball_radius, bx + self.ball_radius, by + self.ball_radius), fill=(245, 250, 255, 255), outline=(*ball_color, 255), width=3)
        draw.ellipse((bx - self.ball_radius * 0.45, by - self.ball_radius * 0.55, bx - self.ball_radius * 0.05, by - self.ball_radius * 0.15), fill=(255, 255, 255, 220))

        title_font = fitted_font(
            self.title,
            preferred_size=max(18, round(self.width * 0.048)),
            minimum_size=max(12, round(self.width * 0.027)),
            maximum_width=round(self.width * 0.90),
            bold=True,
        )
        small_font = font(max(12, round(self.width * 0.023)), bold=True)
        meta_text = f"NIVEAU {self.level:02d}  •  GRAINE {self.seed}"
        meta_font = fitted_font(meta_text, max(12, round(self.width * 0.023)), max(9, round(self.width * 0.018)), round(self.width * 0.88), bold=True)
        cta_text = "ABONNE-TOI POUR LE PROCHAIN NIVEAU"
        cta_font = fitted_font(cta_text, max(12, round(self.width * 0.023)), max(9, round(self.width * 0.017)), round(self.width * 0.88), bold=True)
        counter_font = font(max(34, round(self.width * 0.075)), bold=True)
        draw_centered(draw, (self.cx, self.height * 0.095), self.title, title_font, (255, 255, 255, 255), stroke=2)
        draw_centered(draw, (self.cx, self.height * 0.138), meta_text, meta_font, (165, 180, 215, 255))

        remaining = max(0, self.ring_count - self.active)
        center_text = "LIBRE !" if self.completed_at is not None else str(remaining)
        center_color = (255, 255, 255, 255) if remaining else (*ball_color, 255)
        draw_centered(draw, (self.cx, self.cy), center_text, counter_font, center_color, stroke=2)
        if remaining:
            draw_centered(draw, (self.cx, self.cy + self.height * 0.043), "ANNEAUX", small_font, (150, 165, 195, 230))

        progress_left, progress_right = self.width * 0.12, self.width * 0.88
        progress_y = self.height * 0.925
        draw.rounded_rectangle((progress_left, progress_y, progress_right, progress_y + 8), radius=4, fill=(255, 255, 255, 35))
        progress = self.active / max(1, self.ring_count)
        if progress > 0:
            draw.rounded_rectangle((progress_left, progress_y, progress_left + (progress_right - progress_left) * progress, progress_y + 8), radius=4, fill=(*ball_color, 255))
        draw_centered(draw, (self.cx, self.height * 0.962), cta_text, cta_font, (205, 215, 240, 255), stroke=1)
        return image.convert("RGB")


def render(args: argparse.Namespace) -> dict[str, object]:
    width = int(os.environ.get("GAME_RENDER_WIDTH", args.width))
    height = int(os.environ.get("GAME_RENDER_HEIGHT", args.height))
    fps = int(os.environ.get("GAME_RENDER_FPS", args.fps))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    game = BallEscape(width, height, fps, args.duration, args.rings, args.seed, args.theme, args.title)
    ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")

    with tempfile.TemporaryDirectory(prefix="clipmaker-game-", dir=str(output.parent)) as temp_dir:
        silent = Path(temp_dir) / "silent.mp4"
        audio = Path(temp_dir) / "effects.wav"
        encode = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-vf", "scale=1080:1920:flags=lanczos",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-an", str(silent),
        ]
        process = subprocess.Popen(encode, stdin=subprocess.PIPE)
        assert process.stdin is not None
        try:
            frame_count = round(args.duration * fps)
            for frame_index in range(frame_count):
                time_sec = frame_index / fps
                game.update(time_sec)
                process.stdin.write(game.frame(time_sec).tobytes())
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("ffmpeg n'a pas pu encoder les images du jeu")

        if args.sound_pack == "auto":
            selector = args.seed % 10
            selected_sound_pack = "funny" if selector < 5 else "arcade" if selector < 8 else "impact"
        else:
            selected_sound_pack = args.sound_pack
        synth_audio(args.duration, game.events, audio, args.seed, selected_sound_pack)
        if args.music and Path(args.music).is_file():
            mux = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
                "-stream_loop", "-1", "-i", str(Path(args.music).resolve()),
                "-filter_complex", f"[1:a]volume=0.95[fx];[2:a]volume={args.music_volume:.3f}[music];[fx][music]amix=inputs=2:duration=first:dropout_transition=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=9[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output),
            ]
        else:
            mux = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
                "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=9", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(output),
            ]
        subprocess.run(mux, check=True)

    return {
        "ok": True,
        "output": output.name,
        "duration": args.duration,
        "seed": args.seed,
        "rings": args.rings,
        "theme": args.theme,
        "sound_pack": selected_sound_pack,
        "sound_mode": args.sound_pack,
        "music": Path(args.music).name if args.music else None,
        "events": len(game.events),
        "levels_completed": game.level - 1,
        "rings_cleared_current_level": game.active,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--rings", type=int, default=18)
    parser.add_argument("--theme", choices=sorted(THEMES), default="neon")
    parser.add_argument("--sound-pack", choices=("auto", "funny", "arcade", "impact"), default="auto")
    parser.add_argument("--music")
    parser.add_argument("--music-volume", type=float, default=0.24)
    parser.add_argument("--title", default="LA BALLE VA-T-ELLE S'ÉCHAPPER ?")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    args.duration = clamp(args.duration, 5.0, 60.0)
    args.rings = round(clamp(args.rings, 8, 32))
    args.music_volume = clamp(args.music_volume, 0.0, 1.0)
    print(json.dumps(render(args), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
