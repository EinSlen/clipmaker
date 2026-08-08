"""Deterministic game variants used by the vertical short renderer."""

from __future__ import annotations

import colorsys
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


THEMES = {
    "neon": ((5, 7, 18), 0.58, 0.92),
    "sunset": ((16, 5, 16), 0.96, 0.90),
    "ice": ((3, 12, 18), 0.52, 0.78),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def color_for(theme: str, index: int, total: int, offset: float = 0.0) -> tuple[int, int, int]:
    _, base_hue, saturation = THEMES[theme]
    spread = 0.82 if theme == "neon" else 0.18
    hue = (base_hue + index / max(1, total) * spread + offset) % 1.0
    return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, 1.0))


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fitted_font(text: str, preferred: int, minimum: int, width: int, bold: bool = False):
    for size in range(preferred, minimum - 1, -1):
        candidate = font(size, bold)
        left, _, right, _ = candidate.getbbox(text)
        if right - left <= width:
            return candidate
    return font(minimum, bold)


def centered(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, text_font, fill, stroke: int = 0):
    draw.text((x, y), text, font=text_font, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=(0, 0, 0, 220))


class BaseGame:
    game_name = "PROCEDURAL GAME"
    unit_name = "POINTS"

    def __init__(self, width: int, height: int, fps: int, duration: float, difficulty: int, seed: int, theme: str, title: str):
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.total = max(1, difficulty)
        self.seed = seed
        self.theme = theme
        self.title = title.upper()
        self.rng = random.Random(seed)
        self.cx = width / 2
        self.cy = height * 0.53
        self.active = 0
        self.level = 1
        self.completed_at: float | None = None
        self.events: list[tuple[float, float, float, str]] = []
        self.music_hits: list[float] = []
        self.max_speed_ratio = 1.0
        self.gravity_g = 1.0
        self.particles: list[dict[str, float | tuple[int, int, int]]] = []
        self.last_tick = -1
        self.stars = [
            (self.rng.uniform(0, width), self.rng.uniform(0, height), self.rng.uniform(0.6, 2.0), self.rng.uniform(0, math.tau))
            for _ in range(54)
        ]
        self.background = self._background()

    def _background(self) -> Image.Image:
        base = THEMES[self.theme][0]
        image = Image.new("RGB", (self.width, self.height), base)
        draw = ImageDraw.Draw(image)
        for y in range(self.height):
            glow = round(max(0.0, 1.0 - abs(y - self.cy) / self.height * 2.0) * 9)
            draw.line((0, y, self.width, y), fill=tuple(min(255, channel + glow) for channel in base))
        return image

    def record_hit(self, time_sec: float, frequency: float, strength: float = 0.42, kind: str = "bounce"):
        if not self.music_hits or time_sec - self.music_hits[-1] >= 0.065:
            self.music_hits.append(time_sec)
            self.events.append((time_sec, frequency, strength, kind))

    def burst(self, x: float, y: float, color: tuple[int, int, int], count: int = 12):
        for index in range(count):
            angle = math.tau * index / max(1, count) + self.rng.uniform(-0.2, 0.2)
            speed = self.rng.uniform(55, 190)
            self.particles.append({
                "x": x, "y": y, "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed,
                "life": self.rng.uniform(0.35, 0.85), "max_life": 0.85, "color": color,
            })

    def update_particles(self):
        dt = 1.0 / self.fps
        alive = []
        for particle in self.particles:
            particle["x"] = float(particle["x"]) + float(particle["vx"]) * dt
            particle["y"] = float(particle["y"]) + float(particle["vy"]) * dt
            particle["vx"] = float(particle["vx"]) * 0.982
            particle["vy"] = float(particle["vy"]) * 0.982 + self.height * 0.06 * dt
            particle["life"] = float(particle["life"]) - dt
            if float(particle["life"]) > 0:
                alive.append(particle)
        self.particles = alive

    def canvas(self, time_sec: float) -> Image.Image:
        image = self.background.copy().convert("RGBA")
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for x, y, radius, phase in self.stars:
            alpha = round(35 + 65 * (0.5 + 0.5 * math.sin(time_sec * 1.8 + phase)))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(180, 210, 255, alpha))
        for particle in self.particles:
            life = clamp(float(particle["life"]) / float(particle["max_life"]), 0, 1)
            radius = 2 + life * 4
            color = particle["color"]
            x, y = float(particle["x"]), float(particle["y"])
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, round(255 * life)))
        return Image.alpha_composite(image, layer)

    def hud(self, image: Image.Image, time_sec: float, left_label: str, left_value: str, right_label: str, right_value: str, status: str):
        draw = ImageDraw.Draw(image)
        accent = color_for(self.theme, self.active + 3, self.total, time_sec * 0.02)
        title_font = fitted_font(self.title, max(20, round(self.width * 0.052)), 15, round(self.width * 0.88), True)
        label_font = font(max(10, round(self.width * 0.018)), True)
        value_font = font(max(16, round(self.width * 0.031)), True)
        draw.line((self.width * 0.08, self.height * 0.052, self.width * 0.29, self.height * 0.052), fill=(*accent, 160), width=2)
        draw.line((self.width * 0.71, self.height * 0.052, self.width * 0.92, self.height * 0.052), fill=(*accent, 160), width=2)
        centered(draw, self.cx, self.height * 0.052, self.game_name, label_font, (*accent, 255))
        centered(draw, self.cx, self.height * 0.095, self.title, title_font, (255, 255, 255, 255), 2)
        panel_y1, panel_y2 = self.height * 0.135, self.height * 0.184
        panels = ((self.width * 0.08, panel_y1, self.width * 0.46, panel_y2), (self.width * 0.54, panel_y1, self.width * 0.92, panel_y2))
        for panel, label, value in zip(panels, (left_label, right_label), (left_value, right_value)):
            draw.rounded_rectangle(panel, radius=9, fill=(3, 6, 12, 225), outline=(*accent, 115), width=2)
            draw.text((panel[0] + 18, (panel_y1 + panel_y2) / 2), label, font=label_font, fill=(140, 155, 185, 255), anchor="lm")
            draw.text((panel[2] - 18, (panel_y1 + panel_y2) / 2), value, font=value_font, fill=(*accent, 255), anchor="rm")
        centered(draw, self.cx, self.height * 0.205, status, label_font, (*accent, 255))
        footer = (self.width * 0.08, self.height * 0.885, self.width * 0.92, self.height * 0.935)
        draw.rounded_rectangle(footer, radius=9, fill=(3, 6, 12, 225), outline=(255, 255, 255, 42), width=2)
        seconds = max(0, math.ceil(self.duration - time_sec))
        draw.text((footer[0] + 18, (footer[1] + footer[3]) / 2), "TIME LEFT", font=label_font, fill=(140, 155, 185, 255), anchor="lm")
        draw.text((self.cx, (footer[1] + footer[3]) / 2), f"{seconds // 60:02d}:{seconds % 60:02d}", font=value_font, fill=(255, 255, 255, 255), anchor="mm")
        draw.text((footer[2] - 18, (footer[1] + footer[3]) / 2), f"{self.active}/{self.total}", font=value_font, fill=(*accent, 255), anchor="rm")
        centered(draw, self.cx, self.height * 0.965, "FOLLOW FOR THE NEXT RUN", label_font, (215, 225, 245, 255), 1)


class ShapeTunnel(BaseGame):
    game_name = "SHAPE TUNNEL"
    unit_name = "LAYERS"

    def __init__(self, *args):
        super().__init__(*args)
        self.position = [self.cx, self.cy]
        self.trail: list[tuple[float, float]] = []

    def update(self, time_sec: float):
        target = min(self.total, int(time_sec / max(0.1, self.duration * 0.88) * self.total))
        while self.active < target:
            self.active += 1
            frequency = 260 * 2 ** ((self.active % 12) / 12)
            self.record_hit(time_sec, frequency, 0.38, "clear")
            if self.active % max(1, self.total // 18) == 0:
                self.burst(*self.position, color_for(self.theme, self.active, self.total), 14)
        progress = self.active / self.total
        self.max_speed_ratio = 1.0 + progress * 4.2
        self.gravity_g = 1.0 + progress * 1.4
        self.position = [
            self.cx + math.sin(time_sec * (2.4 + progress * 1.8)) * self.width * (0.10 + progress * 0.06),
            self.cy + math.cos(time_sec * 3.1) * self.height * 0.055,
        ]
        self.trail.append(tuple(self.position))
        self.trail = self.trail[-42:]
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(self.cx, self.cy, color_for(self.theme, self.total, self.total), 60)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        progress = self.active / self.total
        visible = 30
        for layer in range(visible, 0, -1):
            radius = self.width * (0.065 + layer / visible * 0.43)
            index = self.active + layer * max(1, self.total // visible)
            color = color_for(self.theme, index, self.total, time_sec * 0.018)
            points = []
            sides = 44
            for point in range(sides + 1):
                angle = math.tau * point / sides + time_sec * (0.08 + layer * 0.002)
                wobble = 1 + 0.055 * math.sin(angle * 5 + time_sec * 2.8 + layer * 0.7)
                squeeze = 1 - progress * 0.16 * math.sin(angle * 2 + time_sec)
                points.append((self.cx + math.cos(angle) * radius * wobble * squeeze, self.cy + math.sin(angle) * radius * wobble))
            width = 2 if layer > 2 else 4
            cd.line(points, fill=(*color, 210), width=width, joint="curve")
            if layer % 4 == 0 or layer < 3:
                gd.line(points, fill=(*color, 110), width=10, joint="curve")
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(10)))
        image = Image.alpha_composite(image, crisp)
        effects = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(effects)
        comet = color_for(self.theme, self.active + 5, self.total, 0.2)
        for index, (x, y) in enumerate(self.trail):
            age = (index + 1) / max(1, len(self.trail))
            radius = 3 + age * 8
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*comet, round(145 * age)))
        x, y = self.position
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(250, 253, 255, 255), outline=(*comet, 255), width=4)
        image = Image.alpha_composite(image, effects.filter(ImageFilter.GaussianBlur(5)))
        image = Image.alpha_composite(image, effects)
        center_draw = ImageDraw.Draw(image)
        if self.completed_at is not None:
            centered(center_draw, self.cx, self.cy, "CENTER REACHED!", font(round(self.width * 0.052), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "SPEED", f"{self.max_speed_ratio:.1f}X", "LAYERS", str(max(0, self.total - self.active)), "TUNNEL IS COLLAPSING")
        return image.convert("RGB")


class BossBattle(BaseGame):
    game_name = "BOSS BATTLE"
    unit_name = "BOSS HP"

    def __init__(self, *args):
        super().__init__(*args)
        self.boss_hp = float(self.total)
        self.player_max = max(100.0, self.total * 0.72)
        self.player_hp = self.player_max
        self.player_wins = self.seed % 10 < 7
        self.attack_count = max(24, min(64, self.total // 6))
        self.last_attacker = "player"
        self.last_impact = 0.0

    def update(self, time_sec: float):
        target_tick = min(self.attack_count, int(time_sec / max(0.1, self.duration * 0.86) * self.attack_count))
        while self.last_tick < target_tick - 1:
            self.last_tick += 1
            player_attacks = self.last_tick % 2 == 0
            if player_attacks:
                factor = 1.10 if self.player_wins else 0.62
                damage = self.total / math.ceil(self.attack_count / 2) * factor * self.rng.uniform(0.82, 1.18)
                self.boss_hp = max(0.0, self.boss_hp - damage)
                self.last_attacker = "player"
                frequency = 520 + (self.last_tick % 5) * 80
            else:
                factor = 0.55 if self.player_wins else 1.16
                damage = self.player_max / math.floor(self.attack_count / 2) * factor * self.rng.uniform(0.82, 1.18)
                self.player_hp = max(0.0, self.player_hp - damage)
                self.last_attacker = "boss"
                frequency = 140 + (self.last_tick % 4) * 28
            self.active = min(self.total, round(self.total - self.boss_hp))
            self.last_impact = time_sec
            self.record_hit(time_sec, frequency, 0.50, "impact")
            impact_x = self.width * (0.73 if player_attacks else 0.27)
            self.burst(impact_x, self.cy, color_for(self.theme, self.last_tick, self.attack_count), 18)
        finished = self.boss_hp <= 0 or self.player_hp <= 0 or target_tick >= self.attack_count
        if finished and self.completed_at is None:
            if self.player_wins:
                self.boss_hp = 0
                self.active = self.total
            else:
                self.player_hp = 0
            self.completed_at = time_sec
            self.burst(self.cx, self.cy, (255, 215, 90), 70)
        progress = target_tick / self.attack_count
        self.max_speed_ratio = 1.0 + progress * 3.6
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        arena = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(arena)
        pulse = clamp(1.0 - (time_sec - self.last_impact) * 5, 0, 1)
        for ring in range(6):
            radius = self.width * (0.10 + ring * 0.065) * (1 + 0.015 * math.sin(time_sec * 3 + ring))
            color = color_for(self.theme, ring * 8, 48, time_sec * 0.01)
            draw.ellipse((self.cx - radius, self.cy - radius, self.cx + radius, self.cy + radius), outline=(*color, 38 + ring * 9), width=2)
        player = (self.width * 0.27, self.cy + math.sin(time_sec * 2.8) * 24)
        boss = (self.width * 0.73, self.cy + math.cos(time_sec * 2.2) * 28)
        beam_from, beam_to = (player, boss) if self.last_attacker == "player" else (boss, player)
        beam_color = (90, 230, 255) if self.last_attacker == "player" else (255, 85, 120)
        if pulse > 0:
            draw.line((*beam_from, *beam_to), fill=(*beam_color, round(210 * pulse)), width=round(4 + 8 * pulse))
        for (x, y), radius, color, label in ((player, 38, (70, 225, 255), "YOU"), (boss, 54, (255, 75, 115), "BOSS")):
            draw.ellipse((x - radius * 1.7, y - radius * 1.7, x + radius * 1.7, y + radius * 1.7), fill=(*color, 38))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(9, 13, 25, 255), outline=(*color, 255), width=6)
            centered(draw, x, y, label, font(17, True), (255, 255, 255, 255), 1)
        image = Image.alpha_composite(image, arena.filter(ImageFilter.GaussianBlur(4)))
        image = Image.alpha_composite(image, arena)
        draw = ImageDraw.Draw(image)
        bar_y = self.height * 0.73
        for x1, x2, ratio, color, label in (
            (self.width * 0.10, self.width * 0.47, self.player_hp / self.player_max, (70, 225, 255), "PLAYER"),
            (self.width * 0.53, self.width * 0.90, self.boss_hp / self.total, (255, 75, 115), "WARDEN"),
        ):
            draw.rounded_rectangle((x1, bar_y, x2, bar_y + 28), radius=14, fill=(2, 4, 10, 230), outline=(255, 255, 255, 50), width=2)
            if ratio > 0:
                draw.rounded_rectangle((x1 + 3, bar_y + 3, x1 + 3 + (x2 - x1 - 6) * ratio, bar_y + 25), radius=11, fill=(*color, 245))
            centered(draw, (x1 + x2) / 2, bar_y + 50, label, font(13, True), (*color, 255))
        if self.completed_at is not None:
            result = "PLAYER WINS!" if self.player_wins else "BOSS WINS!"
            centered(draw, self.cx, self.cy - self.height * 0.13, result, font(round(self.width * 0.055), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "PLAYER", str(round(self.player_hp)), "BOSS", str(round(self.boss_hp)), "CRITICAL HITS ENABLED")
        return image.convert("RGB")


class MelodyDrop(BaseGame):
    game_name = "MELODY DROP"
    unit_name = "NOTES"

    def __init__(self, *args):
        super().__init__(*args)
        self.key_count = 8
        self.key_index = 0
        self.ball = [self.cx, self.height * 0.35]
        self.trail: list[tuple[float, float]] = []
        self.scale = (261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25)

    def update(self, time_sec: float):
        note_span = max(0.075, self.duration * 0.88 / self.total)
        target = min(self.total, int(time_sec / note_span))
        while self.active < target:
            self.active += 1
            self.key_index = (self.active * 5 + self.seed) % self.key_count
            self.record_hit(time_sec, self.scale[self.key_index], 0.48, "bounce")
            key_width = self.width * 0.78 / self.key_count
            x = self.width * 0.11 + key_width * (self.key_index + 0.5)
            self.burst(x, self.height * 0.72, color_for(self.theme, self.key_index, self.key_count), 12)
        phase = (time_sec % note_span) / note_span
        key_width = self.width * 0.78 / self.key_count
        target_x = self.width * 0.11 + key_width * (self.key_index + 0.5)
        previous_key = ((max(0, self.active - 1) * 5 + self.seed) % self.key_count)
        previous_x = self.width * 0.11 + key_width * (previous_key + 0.5)
        x = previous_x + (target_x - previous_x) * (phase * phase * (3 - 2 * phase))
        y_top, y_bottom = self.height * 0.34, self.height * 0.705
        y = y_top + (y_bottom - y_top) * phase * phase
        self.ball = [x, y]
        self.trail.append(tuple(self.ball))
        self.trail = self.trail[-32:]
        progress = self.active / self.total
        self.gravity_g = 1.0 + progress * 1.2
        self.max_speed_ratio = 1.0 + progress * 3.8
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(x, y_bottom, (255, 255, 255), 60)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        keyboard_x1, keyboard_x2 = self.width * 0.11, self.width * 0.89
        keyboard_y1, keyboard_y2 = self.height * 0.72, self.height * 0.82
        key_width = (keyboard_x2 - keyboard_x1) / self.key_count
        for index in range(self.key_count):
            x1 = keyboard_x1 + index * key_width
            x2 = x1 + key_width - 3
            color = color_for(self.theme, index, self.key_count, time_sec * 0.01)
            active = index == self.key_index and self.completed_at is None
            draw.rounded_rectangle((x1, keyboard_y1 + (9 if active else 0), x2, keyboard_y2), radius=8, fill=(*color, 245 if active else 135), outline=(255, 255, 255, 160), width=2)
            centered(draw, (x1 + x2) / 2, keyboard_y2 - 22, str(index + 1), font(12, True), (255, 255, 255, 220))
        for lane in range(self.key_count):
            x = keyboard_x1 + key_width * (lane + 0.5)
            amplitude = 25 + 80 * (0.5 + 0.5 * math.sin(time_sec * 4 + lane))
            draw.rounded_rectangle((x - 7, keyboard_y1 - amplitude - 35, x + 7, keyboard_y1 - 35), radius=7, fill=(*color_for(self.theme, lane, self.key_count), 75))
        comet = color_for(self.theme, self.key_index, self.key_count)
        for index, (x, y) in enumerate(self.trail):
            age = (index + 1) / max(1, len(self.trail))
            radius = 2 + 10 * age
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*comet, round(135 * age)))
        x, y = self.ball
        draw.ellipse((x - 17, y - 17, x + 17, y + 17), fill=(255, 255, 255, 255), outline=(*comet, 255), width=4)
        image = Image.alpha_composite(image, layer.filter(ImageFilter.GaussianBlur(5)))
        image = Image.alpha_composite(image, layer)
        if self.completed_at is not None:
            centered(ImageDraw.Draw(image), self.cx, self.cy, "MELODY COMPLETE!", font(round(self.width * 0.052), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "GRAVITY", f"{self.gravity_g:.1f}G", "NOTES", str(max(0, self.total - self.active)), "EVERY BOUNCE PLAYS A NOTE")
        return image.convert("RGB")


class ColorSwitch(BaseGame):
    game_name = "COLOR SWITCH"
    unit_name = "GATES"

    def __init__(self, *args):
        super().__init__(*args)
        self.palette = [color_for(self.theme, index, 4) for index in range(4)]
        self.ball_color = self.seed % 4
        self.gate_flash = 0.0

    def update(self, time_sec: float):
        target = min(self.total, int(time_sec / max(0.1, self.duration * 0.88) * self.total))
        while self.active < target:
            self.active += 1
            self.ball_color = (self.ball_color + 1 + (self.active % 3 == 0)) % 4
            self.gate_flash = time_sec
            self.record_hit(time_sec, 330 * 2 ** (self.ball_color / 6), 0.44, "clear")
            angle = time_sec * 2.8 + self.active
            self.burst(
                self.cx + math.cos(angle) * self.width * 0.18,
                self.cy + math.sin(angle) * self.width * 0.18,
                self.palette[self.ball_color],
                11,
            )
        progress = self.active / self.total
        self.max_speed_ratio = 1.0 + progress * 4.8
        self.gravity_g = 1.0 + progress * 1.7
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(self.cx, self.cy, (255, 255, 255), 64)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        progress = self.active / self.total
        flash = clamp(1.0 - (time_sec - self.gate_flash) * 7.5, 0.0, 1.0)
        for gate in range(8, 0, -1):
            radius = self.width * (0.075 + gate * 0.047)
            phase = time_sec * (44 + progress * 125) * (-1 if gate % 2 else 1) + gate * 27
            box = (self.cx - radius, self.cy - radius, self.cx + radius, self.cy + radius)
            for segment, color in enumerate(self.palette):
                start = phase + segment * 90 + 3
                draw.arc(box, start=start, end=start + 82, fill=(*color, 235), width=max(4, round(self.width * 0.012)))
                gd.arc(box, start=start, end=start + 82, fill=(*color, 100), width=max(12, round(self.width * 0.034)))
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(10)))
        image = Image.alpha_composite(image, crisp)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        orbit = time_sec * (3.4 + progress * 4.0)
        bx = self.cx + math.sin(orbit) * self.width * 0.055
        by = self.cy + math.cos(orbit * 1.35) * self.height * 0.035
        radius = 18 + 5 * flash
        color = self.palette[self.ball_color]
        draw.ellipse((bx - radius * 2.0, by - radius * 2.0, bx + radius * 2.0, by + radius * 2.0), fill=(*color, 75))
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius), fill=(255, 255, 255, 255), outline=(*color, 255), width=5)
        image = Image.alpha_composite(image, layer.filter(ImageFilter.GaussianBlur(7)))
        image = Image.alpha_composite(image, layer)
        if self.completed_at is not None:
            centered(ImageDraw.Draw(image), self.cx, self.cy, "PERFECT MATCH!", font(round(self.width * 0.050), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "SPEED", f"{self.max_speed_ratio:.1f}X", "GATES", str(max(0, self.total - self.active)), "MATCH THE NEXT COLOR")
        return image.convert("RGB")


class OrbitMerge(BaseGame):
    game_name = "ORBIT MERGE"
    unit_name = "MERGES"

    def __init__(self, *args):
        super().__init__(*args)
        self.last_merge = 0.0
        self.orbiters = 14

    def update(self, time_sec: float):
        target = min(self.total, int(time_sec / max(0.1, self.duration * 0.88) * self.total))
        while self.active < target:
            self.active += 1
            self.last_merge = time_sec
            frequency = 180 * 2 ** ((self.active % 10) / 12)
            self.record_hit(time_sec, frequency, 0.45, "impact")
            angle = self.active * 2.399963
            radius = self.width * (0.16 + 0.14 * ((self.active % 7) / 7))
            self.burst(self.cx + math.cos(angle) * radius, self.cy + math.sin(angle) * radius, color_for(self.theme, self.active, self.total), 10)
        progress = self.active / self.total
        self.max_speed_ratio = 1.0 + progress * 3.9
        self.gravity_g = 1.0 + progress * 7.0
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(self.cx, self.cy, (255, 245, 180), 72)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        progress = self.active / self.total
        pulse = clamp(1.0 - (time_sec - self.last_merge) * 5.5, 0.0, 1.0)
        planet_radius = self.width * (0.070 + progress * 0.115) + pulse * 8
        for ring in range(4):
            rx = self.width * (0.16 + ring * 0.064)
            ry = rx * (0.42 + ring * 0.035)
            color = color_for(self.theme, ring * 19 + self.active, self.total)
            box = (self.cx - rx, self.cy - ry, self.cx + rx, self.cy + ry)
            draw.ellipse(box, outline=(*color, 100), width=2)
            gd.ellipse(box, outline=(*color, 50), width=9)
        for index in range(self.orbiters):
            lane = index % 4
            angle = time_sec * (1.15 + progress * 2.6) * (1 if lane % 2 else -1) + index * 1.73
            rx = self.width * (0.16 + lane * 0.064)
            ry = rx * (0.42 + lane * 0.035)
            x = self.cx + math.cos(angle) * rx
            y = self.cy + math.sin(angle) * ry
            size = 5 + (index % 4) * 2
            color = color_for(self.theme, index * 11 + self.active, self.total)
            gd.ellipse((x - size * 2, y - size * 2, x + size * 2, y + size * 2), fill=(*color, 100))
            draw.ellipse((x - size, y - size, x + size, y + size), fill=(*color, 245))
        planet = color_for(self.theme, self.active + 12, self.total, 0.08)
        gd.ellipse((self.cx - planet_radius * 1.45, self.cy - planet_radius * 1.45, self.cx + planet_radius * 1.45, self.cy + planet_radius * 1.45), fill=(*planet, 120))
        draw.ellipse((self.cx - planet_radius, self.cy - planet_radius, self.cx + planet_radius, self.cy + planet_radius), fill=(*planet, 245), outline=(255, 255, 255, 210), width=4)
        for band in (-0.46, -0.12, 0.24, 0.52):
            band_y = self.cy + planet_radius * band
            band_width = planet_radius * math.sqrt(max(0.0, 1.0 - band * band))
            draw.arc(
                (self.cx - band_width, band_y - planet_radius * 0.18, self.cx + band_width, band_y + planet_radius * 0.18),
                start=8,
                end=172,
                fill=(5, 12, 30, 90),
                width=max(2, round(planet_radius * 0.055)),
            )
        for spot in range(5):
            angle = self.seed * 0.001 + spot * 2.399963 + time_sec * 0.03
            distance = planet_radius * (0.22 + (spot % 3) * 0.16)
            sx = self.cx + math.cos(angle) * distance
            sy = self.cy + math.sin(angle) * distance * 0.72
            size = planet_radius * (0.07 + (spot % 2) * 0.035)
            draw.ellipse((sx - size, sy - size * 0.7, sx + size, sy + size * 0.7), fill=(5, 12, 30, 70))
        highlight = planet_radius * 0.34
        draw.ellipse((self.cx - planet_radius * 0.48, self.cy - planet_radius * 0.50, self.cx - planet_radius * 0.48 + highlight, self.cy - planet_radius * 0.50 + highlight), fill=(255, 255, 255, 115))
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(9)))
        image = Image.alpha_composite(image, crisp)
        if self.completed_at is not None:
            centered(ImageDraw.Draw(image), self.cx, self.cy - self.height * 0.19, "MAXIMUM MASS!", font(round(self.width * 0.050), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "GRAVITY", f"{self.gravity_g:.1f}G", "MERGES", str(max(0, self.total - self.active)), "EVERY COLLISION ADDS MASS")
        return image.convert("RGB")


class LaserDodge(BaseGame):
    game_name = "LASER DODGE"
    unit_name = "LASERS"

    def __init__(self, *args):
        super().__init__(*args)
        self.last_dodge = 0.0
        self.runner = [self.cx, self.cy]
        self.trail: list[tuple[float, float]] = []

    def update(self, time_sec: float):
        target = min(self.total, int(time_sec / max(0.1, self.duration * 0.88) * self.total))
        while self.active < target:
            self.active += 1
            self.last_dodge = time_sec
            self.record_hit(time_sec, 610 + (self.active % 7) * 55, 0.38, "clear")
            self.burst(*self.runner, color_for(self.theme, self.active, self.total), 8)
        progress = self.active / self.total
        speed = 2.4 + progress * 5.3
        self.runner = [
            self.cx + math.sin(time_sec * speed) * self.width * (0.18 + 0.04 * math.sin(time_sec * 0.7)),
            self.cy + math.sin(time_sec * speed * 0.63 + 1.2) * self.height * 0.16,
        ]
        self.trail.append(tuple(self.runner))
        self.trail = self.trail[-38:]
        self.max_speed_ratio = 1.0 + progress * 5.4
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(*self.runner, (255, 255, 255), 68)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        progress = self.active / self.total
        arena = (self.width * 0.08, self.height * 0.25, self.width * 0.92, self.height * 0.82)
        draw.rounded_rectangle(arena, radius=18, fill=(2, 4, 12, 125), outline=(255, 255, 255, 35), width=2)
        for index in range(11):
            angle = time_sec * (0.34 + progress * 0.85) * (-1 if index % 2 else 1) + index * math.pi / 11
            anchor_x = self.cx + math.sin(index * 2.1) * self.width * 0.15
            anchor_y = self.cy + math.cos(index * 1.7) * self.height * 0.13
            length = self.width * 0.46
            dx, dy = math.cos(angle) * length, math.sin(angle) * length
            color = (255, 48 + (index % 3) * 35, 80 + (index % 4) * 30)
            gd.line((anchor_x - dx, anchor_y - dy, anchor_x + dx, anchor_y + dy), fill=(*color, 95), width=15)
            draw.line((anchor_x - dx, anchor_y - dy, anchor_x + dx, anchor_y + dy), fill=(*color, 210), width=3)
        comet = color_for(self.theme, self.active + 8, self.total)
        for index, (x, y) in enumerate(self.trail):
            age = (index + 1) / max(1, len(self.trail))
            radius = 2 + age * 7
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*comet, round(120 * age)))
        x, y = self.runner
        dodge_pulse = clamp(1.0 - (time_sec - self.last_dodge) * 7.0, 0.0, 1.0)
        radius = 14 + dodge_pulse * 5
        gd.ellipse((x - radius * 2.2, y - radius * 2.2, x + radius * 2.2, y + radius * 2.2), fill=(*comet, 150))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 255), outline=(*comet, 255), width=4)
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(8)))
        image = Image.alpha_composite(image, crisp)
        if self.completed_at is not None:
            centered(ImageDraw.Draw(image), self.cx, self.height * 0.74, "FLAWLESS RUN!", font(round(self.width * 0.052), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "SPEED", f"{self.max_speed_ratio:.1f}X", "DODGED", str(self.active), "ZERO CONTACT ALLOWED")
        return image.convert("RGB")


class BrickCascade(BaseGame):
    game_name = "BRICK CASCADE"
    unit_name = "BRICKS"

    def __init__(self, *args):
        super().__init__(*args)
        self.columns = 10
        self.rows = 14
        self.last_fall = 0.0

    def update(self, time_sec: float):
        target = min(self.total, int(time_sec / max(0.1, self.duration * 0.88) * self.total))
        while self.active < target:
            self.active += 1
            self.last_fall = time_sec
            self.record_hit(time_sec, 210 + (self.active % 12) * 30, 0.40, "bounce")
            if self.active % max(1, self.total // 28) == 0:
                visible_index = self.active % (self.columns * self.rows)
                row, column = divmod(visible_index, self.columns)
                x = self.width * 0.10 + (column + 0.5) * self.width * 0.80 / self.columns
                y = self.height * 0.29 + (row + 0.5) * self.height * 0.50 / self.rows
                self.burst(x, y, color_for(self.theme, self.active, self.total), 8)
        progress = self.active / self.total
        self.max_speed_ratio = 1.0 + progress * 6.0
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(self.cx, self.height * 0.76, (255, 255, 255), 76)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        grid_total = self.columns * self.rows
        visible_fallen = round(self.active / self.total * grid_total)
        x1, x2 = self.width * 0.10, self.width * 0.90
        y1, y2 = self.height * 0.28, self.height * 0.80
        cell_w = (x2 - x1) / self.columns
        cell_h = (y2 - y1) / self.rows
        for order in range(grid_total):
            row, path_column = divmod(order, self.columns)
            column = path_column if row % 2 == 0 else self.columns - 1 - path_column
            fallen = order < visible_fallen
            progress = clamp(visible_fallen - order, 0.0, 1.0)
            cx = x1 + (column + 0.5) * cell_w
            cy = y1 + (row + 0.5) * cell_h + (cell_h * 0.28 * progress if fallen else 0)
            color = color_for(self.theme, order + self.active, grid_total)
            brick_w = cell_w * (0.76 if fallen else 0.58)
            brick_h = cell_h * (0.28 if fallen else 0.76)
            alpha = 100 if fallen else 235
            draw.rounded_rectangle((cx - brick_w / 2, cy - brick_h / 2, cx + brick_w / 2, cy + brick_h / 2), radius=4, fill=(*color, alpha), outline=(255, 255, 255, 80), width=1)
        wave_order = min(grid_total - 1, visible_fallen)
        wave_row, wave_path_column = divmod(wave_order, self.columns)
        wave_column = wave_path_column if wave_row % 2 == 0 else self.columns - 1 - wave_path_column
        wx = x1 + (wave_column + 0.5) * cell_w
        wy = y1 + (wave_row + 0.5) * cell_h
        pulse = clamp(1.0 - (time_sec - self.last_fall) * 6.0, 0.0, 1.0)
        radius = 10 + pulse * 8
        draw.ellipse((wx - radius, wy - radius, wx + radius, wy + radius), fill=(255, 255, 255, 235), outline=(*color_for(self.theme, self.active, self.total), 255), width=4)
        image = Image.alpha_composite(image, layer.filter(ImageFilter.GaussianBlur(4)))
        image = Image.alpha_composite(image, layer)
        if self.completed_at is not None:
            centered(ImageDraw.Draw(image), self.cx, self.cy, "CHAIN COMPLETE!", font(round(self.width * 0.052), True), (255, 255, 255, 255), 2)
        self.hud(image, time_sec, "CHAIN", f"{self.active}X", "LEFT", str(max(0, self.total - self.active)), "ONE HIT STARTS EVERYTHING")
        return image.convert("RGB")


GAME_CLASSES = {
    "shape-tunnel": ShapeTunnel,
    "boss-battle": BossBattle,
    "melody-drop": MelodyDrop,
    "color-switch": ColorSwitch,
    "orbit-merge": OrbitMerge,
    "laser-dodge": LaserDodge,
    "brick-cascade": BrickCascade,
}


def create_game(game_id: str, width: int, height: int, fps: int, duration: float, difficulty: int, seed: int, theme: str, title: str):
    game_class = GAME_CLASSES.get(game_id)
    if game_class is None:
        raise ValueError(f"Unknown game variant: {game_id}")
    return game_class(width, height, fps, duration, difficulty, seed, theme, title)
