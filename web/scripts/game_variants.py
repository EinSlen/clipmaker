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
    game_name = "ORGANIC ESCAPE"
    unit_name = "LAYERS"

    def __init__(self, *args):
        super().__init__(*args)
        self.position = [self.cx, self.cy]
        self.trail: list[tuple[float, float]] = []
        self.last_impact = -10.0
        self.last_contact = [self.cx, self.cy]
        hit_count = max(12, min(self.total, round(self.duration * 5.2)))
        start, finish = self.duration * 0.035, self.duration * 0.89
        self.hit_times = [
            start + (finish - start) * (index / max(1, hit_count - 1)) ** 0.86
            for index in range(hit_count)
        ]
        angle = self.rng.uniform(0, math.tau)
        self.hit_angles = []
        for index in range(hit_count):
            angle += math.pi + self.rng.uniform(-0.78, 0.78)
            angle += math.sin(index * 0.73 + self.seed % 17) * 0.08
            self.hit_angles.append(angle)
        self.shape_phase = self.rng.uniform(0, math.tau)

    def boundary_radius(self, progress: float, angle: float) -> float:
        base = self.width * (0.155 + progress * 0.43)
        organic = 1.0
        organic += 0.095 * math.sin(angle * 7 + self.shape_phase)
        organic += 0.038 * math.sin(angle * 3 - self.shape_phase * 0.7)
        organic += 0.020 * math.sin(angle * 13 + self.shape_phase * 1.8)
        return base * organic

    def contact_point(self, hit_index: int) -> tuple[float, float]:
        if hit_index < 0:
            return self.cx, self.cy
        progress = min(1.0, (hit_index + 1) / len(self.hit_times))
        angle = self.hit_angles[min(hit_index, len(self.hit_angles) - 1)]
        radius = max(18.0, self.boundary_radius(progress, angle) - self.width * 0.026)
        return self.cx + math.cos(angle) * radius, self.cy + math.sin(angle) * radius

    def update(self, time_sec: float):
        hit_target = 0
        while hit_target < len(self.hit_times) and self.hit_times[hit_target] <= time_sec:
            hit_target += 1
        while self.last_tick < hit_target - 1:
            self.last_tick += 1
            previous = self.active
            self.active = min(self.total, round((self.last_tick + 1) / len(self.hit_times) * self.total))
            contact = self.contact_point(self.last_tick)
            scale = (0, 2, 4, 7, 9)[self.last_tick % 5]
            frequency = 220.0 * 2 ** (scale / 12)
            self.record_hit(self.hit_times[self.last_tick], frequency, 0.28, "clear")
            self.burst(*contact, color_for(self.theme, previous + self.last_tick, self.total), 10 + min(12, self.active - previous))
            self.last_contact = list(contact)
            self.last_impact = self.hit_times[self.last_tick]

        current_hit = min(hit_target, len(self.hit_times) - 1)
        previous_time = 0.0 if current_hit == 0 else self.hit_times[current_hit - 1]
        next_time = self.hit_times[current_hit]
        phase = clamp((time_sec - previous_time) / max(0.001, next_time - previous_time), 0.0, 1.0)
        eased = phase * phase * (3.0 - 2.0 * phase)
        start = (self.cx, self.cy) if current_hit == 0 else self.contact_point(current_hit - 1)
        end = self.contact_point(current_hit)
        gravity_arc = self.height * (0.018 + 0.032 * self.active / self.total) * 4.0 * phase * (1.0 - phase)
        self.position = [
            start[0] + (end[0] - start[0]) * eased,
            start[1] + (end[1] - start[1]) * eased + gravity_arc,
        ]
        self.trail.append(tuple(self.position))
        self.trail = self.trail[-13:]
        progress = self.active / self.total
        self.max_speed_ratio = 1.0 + progress * 5.4
        self.gravity_g = 1.0 + progress * 1.8
        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(*self.position, (255, 255, 255), 72)
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        progress = self.active / self.total
        remaining = max(0, self.total - self.active)
        visible = math.ceil(44 * remaining / self.total)
        spacing = self.width * 0.0175
        for layer in range(visible - 1, -1, -1):
            radius = self.width * (0.155 + progress * 0.43) + layer * spacing
            index = self.active + round((layer + 1) / 44 * self.total)
            color = color_for(self.theme, index, self.total, time_sec * 0.018)
            points = []
            sides = 88
            for point in range(sides + 1):
                angle = math.tau * point / sides
                wave = 1.0
                wave += 0.095 * math.sin(angle * 7 + self.shape_phase + layer * 0.015)
                wave += 0.038 * math.sin(angle * 3 - self.shape_phase * 0.7)
                wave += 0.020 * math.sin(angle * 13 + self.shape_phase * 1.8 + time_sec * 0.35)
                points.append((self.cx + math.cos(angle) * radius * wave, self.cy + math.sin(angle) * radius * wave))
            line_width = 2 if layer > 1 else 3
            cd.line(points, fill=(*color, 235), width=line_width, joint="curve")
            if layer % 5 == 0 or layer < 2:
                gd.line(points, fill=(*color, 115), width=9, joint="curve")
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(7)))
        image = Image.alpha_composite(image, crisp)
        effects = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(effects)
        comet = color_for(self.theme, self.active + 5, self.total, 0.2)
        if len(self.trail) > 1:
            for index in range(1, len(self.trail)):
                age = index / len(self.trail)
                draw.line((*self.trail[index - 1], *self.trail[index]), fill=(*comet, round(190 * age)), width=max(2, round(2 + age * 6)))
        x, y = self.position
        ball_radius = self.width * 0.026
        draw.ellipse((x - ball_radius, y - ball_radius, x + ball_radius, y + ball_radius), fill=(248, 252, 255, 255), outline=(*comet, 255), width=3)
        image = Image.alpha_composite(image, effects.filter(ImageFilter.GaussianBlur(6)))
        image = Image.alpha_composite(image, effects)
        center_draw = ImageDraw.Draw(image)
        hook = self.title if self.title else "WILL THE BOUNCING BALL ESCAPE?"
        if hook == "WILL THE BOUNCING BALL ESCAPE?":
            hook_font = font(round(self.width * 0.052), True)
            centered(center_draw, self.cx, self.height * 0.057, "WILL THE BOUNCING BALL", hook_font, (255, 255, 255, 255), 2)
            centered(center_draw, self.cx, self.height * 0.094, "ESCAPE?", hook_font, (255, 255, 255, 255), 2)
        else:
            hook_font = fitted_font(hook, round(self.width * 0.052), round(self.width * 0.032), round(self.width * 0.88), True)
            centered(center_draw, self.cx, self.height * 0.075, hook, hook_font, (255, 255, 255, 255), 2)
        centered(center_draw, self.cx, self.height * 0.137, "EVERY HIT BREAKS A LAYER", font(max(9, round(self.width * 0.022)), True), (*comet, 235), 1)
        pulse = clamp(1.0 - (time_sec - self.last_impact) * 6.0, 0.0, 1.0)
        counter_size = 0.039 + pulse * 0.014
        centered(center_draw, self.cx, self.cy, str(remaining), font(round(self.width * counter_size), True), (255, 255, 255, 235), 2)
        if self.completed_at is not None:
            centered(center_draw, self.cx, self.height * 0.82, "ESCAPED!", font(round(self.width * 0.065), True), (255, 255, 255, 255), 2)
        centered(center_draw, self.cx, self.height * 0.955, "ORIGINAL ORGANIC SIMULATION", font(max(8, round(self.width * 0.018)), True), (180, 195, 220, 205), 1)
        return image.convert("RGB")








GAME_CLASSES = {
    "shape-tunnel": ShapeTunnel,
}


def create_game(game_id: str, width: int, height: int, fps: int, duration: float, difficulty: int, seed: int, theme: str, title: str):
    game_class = GAME_CLASSES.get(game_id)
    if game_class is None:
        raise ValueError(f"Unknown game variant: {game_id}")
    return game_class(width, height, fps, duration, difficulty, seed, theme, title)
