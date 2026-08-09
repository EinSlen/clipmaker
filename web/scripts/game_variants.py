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


def smoothstep(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def smootherstep(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def lerp(start: float, end: float, ratio: float) -> float:
    return start + (end - start) * ratio


def catmull_rom(a: float, b: float, c: float, d: float, ratio: float) -> float:
    """Interpolate through b/c with a continuous first derivative."""
    ratio2 = ratio * ratio
    ratio3 = ratio2 * ratio
    return 0.5 * (
        2.0 * b
        + (-a + c) * ratio
        + (2.0 * a - 5.0 * b + 4.0 * c - d) * ratio2
        + (-a + 3.0 * b - 3.0 * c + d) * ratio3
    )


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
        # A short, continuously fading tail reads as speed without leaving the
        # polygonal scribbles that long trails create on a phone screen.
        self.trail = self.trail[-10:]
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
        # Fifty-eight close contours keep the image visually dense at 1080p,
        # while the widening central void makes every successful impact obvious.
        visible = math.ceil(58 * remaining / self.total)
        spacing = self.width * 0.0145
        impact_pulse = clamp(1.0 - (time_sec - self.last_impact) * 5.8, 0.0, 1.0)
        impact_angle = math.atan2(self.last_contact[1] - self.cy, self.last_contact[0] - self.cx)
        for layer in range(visible - 1, -1, -1):
            radius = self.width * (0.155 + progress * 0.43) + layer * spacing
            index = self.active + round((layer + 1) / 58 * self.total)
            color = color_for(self.theme, index, self.total, time_sec * 0.018)
            points = []
            sides = 128
            for point in range(sides + 1):
                angle = math.tau * point / sides
                wave = 1.0
                wave += 0.084 * math.sin(angle * 7 + self.shape_phase + layer * 0.012)
                wave += 0.032 * math.sin(angle * 3 - self.shape_phase * 0.7)
                wave += 0.013 * math.sin(angle * 13 + self.shape_phase * 1.8 + time_sec * 0.30)
                # A local pressure wave propagates through neighbouring contours
                # after contact. This tiny phase-delayed bulge is what makes the
                # tunnel feel elastic instead of a stack of static SVG paths.
                angular_distance = math.atan2(math.sin(angle - impact_angle), math.cos(angle - impact_angle))
                ripple_width = 0.20 + layer * 0.002
                ripple = math.exp(-((angular_distance / ripple_width) ** 2))
                ripple *= impact_pulse * math.sin((1.0 - impact_pulse) * 9.0 - layer * 0.22)
                wave += ripple * 0.024
                points.append((self.cx + math.cos(angle) * radius * wave, self.cy + math.sin(angle) * radius * wave))
            line_width = max(1, round(self.width * (0.0022 if layer > 1 else 0.0038)))
            # A one-pixel dark under-stroke preserves separation after TikTok's
            # aggressive compression and gives the nested layers real depth.
            cd.line(points, fill=(0, 0, 0, 230), width=line_width + max(1, round(self.width * 0.0022)), joint="curve")
            cd.line(points, fill=(*color, 244), width=line_width, joint="curve")
            if layer % 7 == 0 or layer < 2:
                gd.line(points, fill=(*color, 105), width=max(5, round(self.width * 0.018)), joint="curve")
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(max(4, round(self.width * 0.012)))))
        image = Image.alpha_composite(image, crisp)
        effects = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(effects)
        comet = color_for(self.theme, self.active + 5, self.total, 0.2)
        if len(self.trail) > 1:
            for index in range(1, len(self.trail)):
                age = index / (len(self.trail) - 1)
                width = max(2, round(self.width * (0.004 + age * 0.012)))
                draw.line((*self.trail[index - 1], *self.trail[index]), fill=(*comet, round(155 * age * age)), width=width)
                tx, ty = self.trail[index]
                tail_radius = width * 0.42
                draw.ellipse((tx - tail_radius, ty - tail_radius, tx + tail_radius, ty + tail_radius), fill=(*comet, round(115 * age)))
        x, y = self.position
        ball_radius = self.width * 0.026
        draw.ellipse((x - ball_radius * 2.4, y - ball_radius * 2.4, x + ball_radius * 2.4, y + ball_radius * 2.4), fill=(*comet, 80))
        draw.ellipse((x - ball_radius, y - ball_radius, x + ball_radius, y + ball_radius), fill=(*comet, 255))
        draw.ellipse((x - ball_radius * 0.72, y - ball_radius * 0.72, x + ball_radius * 0.72, y + ball_radius * 0.72), fill=(235, 248, 255, 255))
        draw.ellipse((x - ball_radius * 0.42, y - ball_radius * 0.55, x - ball_radius * 0.06, y - ball_radius * 0.19), fill=(255, 255, 255, 245))
        image = Image.alpha_composite(image, effects.filter(ImageFilter.GaussianBlur(max(4, round(self.width * 0.014)))))
        image = Image.alpha_composite(image, effects)
        center_draw = ImageDraw.Draw(image)
        hook = self.title if self.title else "WILL THE BOUNCING BALL ESCAPE?"
        title_lines = ("WILL THE BOUNCING BALL", "ESCAPE?") if hook == "WILL THE BOUNCING BALL ESCAPE?" else (hook,)
        title_font = fitted_font(max(title_lines, key=len), round(self.width * 0.050), round(self.width * 0.031), round(self.width * 0.89), True)
        title_y = self.height * (0.058 if len(title_lines) == 2 else 0.074)
        for line_index, line in enumerate(title_lines):
            center_draw.text(
                (self.cx, title_y + line_index * self.height * 0.035),
                line,
                font=title_font,
                fill=(3, 5, 11, 255),
                anchor="mm",
                stroke_width=max(2, round(self.width * 0.0045)),
                stroke_fill=(255, 255, 255, 255),
            )
        pulse = clamp(1.0 - (time_sec - self.last_impact) * 6.0, 0.0, 1.0)
        counter_size = 0.040 + pulse * 0.013
        centered(center_draw, self.cx, self.cy, str(remaining), font(round(self.width * counter_size), True), (255, 255, 255, 235), 2)
        if self.completed_at is not None:
            centered(center_draw, self.cx, self.height * 0.82, "ESCAPED!", font(round(self.width * 0.065), True), (255, 255, 255, 255), 3)
        centered(center_draw, self.cx, self.height * 0.955, "ORIGINAL PHYSICS SIMULATION", font(max(8, round(self.width * 0.015)), True), (212, 220, 236, 190), 1)
        return image.convert("RGB")


class LaserDodge(BaseGame):
    """A deterministic near-miss course with geometric collision checks."""

    game_name = "LASER DODGE"
    unit_name = "LASERS"

    def __init__(self, *args):
        super().__init__(*args)
        self.arena = (
            self.width * 0.075,
            self.height * 0.190,
            self.width * 0.925,
            self.height * 0.865,
        )
        self.runner_radius = max(7.0, self.width * 0.022)
        # Fewer, carefully staged beams are much easier to read than a screen
        # full of crossings. The nonlinear timing still accelerates the run.
        self.event_count = max(18, min(44, round(self.duration * 2.7)))
        start, finish = self.duration * 0.055, self.duration * 0.90
        self.event_times = [
            start + (finish - start) * (index / max(1, self.event_count - 1)) ** 0.90
            for index in range(self.event_count)
        ]
        self.key_times = [0.0, *self.event_times, self.duration]
        margin_x, margin_y = self.width * 0.17, self.height * 0.275
        self.waypoints = [(self.cx, self.height * 0.53)]
        phase = self.rng.uniform(0.0, math.tau)
        for index in range(self.event_count):
            angle = phase + index * (0.76 + (self.seed % 7) * 0.018)
            target_x = self.cx + math.sin(angle) * self.width * 0.285
            target_x += math.sin(angle * 2.17 + phase) * self.width * 0.035
            target_y = self.cy + math.sin(angle * 0.73 + phase * 0.41) * self.height * 0.205
            target_y += math.cos(angle * 1.61) * self.height * 0.020
            previous_x, previous_y = self.waypoints[-1]
            # Bound every manoeuvre so Catmull-Rom interpolation produces a
            # flowing ribbon even when adjacent seeded targets diverge.
            step_x = clamp(target_x - previous_x, -self.width * 0.255, self.width * 0.255)
            step_y = clamp(target_y - previous_y, -self.height * 0.145, self.height * 0.145)
            self.waypoints.append((
                clamp(previous_x + step_x, margin_x, self.width - margin_x),
                clamp(previous_y + step_y, margin_y, self.height * 0.795),
            ))
        self.waypoints.append(self.waypoints[-1])
        self.will_survive = self.seed % 5 != 0
        self.failure_index = self.event_count - 2
        self.lasers = []
        for index, (event_time, waypoint) in enumerate(zip(self.event_times, self.waypoints[1:-1])):
            before = self.waypoints[max(0, index)]
            after = self.waypoints[min(len(self.waypoints) - 1, index + 2)]
            path_angle = math.atan2(after[1] - before[1], after[0] - before[0])
            angle = path_angle + math.pi * 0.5 + self.rng.uniform(-0.46, 0.46)
            normal = (-math.sin(angle), math.cos(angle))
            safe_gap = self.runner_radius + self.width * self.rng.uniform(0.014, 0.036)
            if not self.will_survive and index == self.failure_index:
                safe_gap = self.runner_radius * 0.20
            side = -1 if (index + self.seed) % 2 else 1
            center = (waypoint[0] + normal[0] * safe_gap * side, waypoint[1] + normal[1] * safe_gap * side)
            self.lasers.append({
                "time": event_time,
                "angle": angle,
                "center": center,
                "speed": self.width * self.rng.uniform(0.30, 0.52),
                "direction": self.rng.choice((-1.0, 1.0)),
                "hue": index + self.seed % 19,
                "phase": self.rng.uniform(0.0, math.tau),
            })
        self.position = list(self.waypoints[0])
        self.trail: list[tuple[float, float]] = []
        self.last_dodge = -10.0
        self.last_distance = self.width
        self.crashed = False
        self.crash_position: tuple[float, float] | None = None

    def position_at(self, time_sec: float) -> tuple[float, float]:
        if self.crashed and self.crash_position is not None:
            return self.crash_position
        segment = 0
        while segment + 1 < len(self.key_times) and self.key_times[segment + 1] < time_sec:
            segment += 1
        segment = min(segment, len(self.waypoints) - 2)
        start_time, end_time = self.key_times[segment], self.key_times[segment + 1]
        ratio = clamp((time_sec - start_time) / max(0.001, end_time - start_time), 0.0, 1.0)
        ratio = smootherstep(ratio)
        previous = self.waypoints[max(0, segment - 1)]
        start = self.waypoints[segment]
        end = self.waypoints[segment + 1]
        following = self.waypoints[min(len(self.waypoints) - 1, segment + 2)]
        x = catmull_rom(previous[0], start[0], end[0], following[0], ratio)
        y = catmull_rom(previous[1], start[1], end[1], following[1], ratio)
        return (
            clamp(x, self.arena[0] + self.runner_radius * 1.5, self.arena[2] - self.runner_radius * 1.5),
            clamp(y, self.arena[1] + self.runner_radius * 1.5, self.arena[3] - self.runner_radius * 1.5),
        )

    def laser_line(self, laser, time_sec: float):
        tangent = (math.cos(float(laser["angle"])), math.sin(float(laser["angle"])))
        normal = (-tangent[1], tangent[0])
        travel = (time_sec - float(laser["time"])) * float(laser["speed"]) * float(laser["direction"])
        center = (float(laser["center"][0]) + normal[0] * travel, float(laser["center"][1]) + normal[1] * travel)
        return center, tangent, normal

    def collision_distance(self, laser, point: tuple[float, float], time_sec: float) -> float:
        center, _, normal = self.laser_line(laser, time_sec)
        return abs((point[0] - center[0]) * normal[0] + (point[1] - center[1]) * normal[1])

    def update(self, time_sec: float):
        target = sum(event_time <= time_sec for event_time in self.event_times)
        while not self.crashed and self.last_tick < target - 1:
            self.last_tick += 1
            event_time = self.event_times[self.last_tick]
            contact = self.position_at(event_time)
            distance = self.collision_distance(self.lasers[self.last_tick], contact, event_time)
            self.last_distance = distance
            self.last_dodge = event_time
            if distance <= self.runner_radius + self.width * 0.006:
                self.crashed = True
                self.crash_position = contact
                self.completed_at = event_time
                self.record_hit(event_time, 92.0, 0.72, "impact")
                self.burst(*contact, (255, 58, 92), 76)
                break
            previous = self.active
            self.active = min(self.total, round((self.last_tick + 1) / self.event_count * self.total))
            clearance = distance - self.runner_radius
            frequency = 620.0 + (self.last_tick % 8) * 58.0
            self.record_hit(event_time, frequency, 0.32 if clearance > self.width * 0.03 else 0.46, "clear")
            self.burst(*contact, color_for(self.theme, previous + self.last_tick, self.total, 0.42), 7)
        if not self.crashed:
            self.position = list(self.position_at(time_sec))
            if target >= self.event_count and self.completed_at is None:
                self.active = self.total
                self.completed_at = self.event_times[-1]
                self.burst(*self.position, (255, 255, 255), 62)
        self.trail.append(tuple(self.position))
        self.trail = self.trail[-13:]
        self.max_speed_ratio = 1.0 + min(1.0, target / self.event_count) * 6.2
        self.update_particles()

    def _legacy_frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        x1, y1, x2, y2 = self.arena
        draw.rounded_rectangle(self.arena, radius=round(self.width * 0.035), fill=(1, 4, 13, 195), outline=(115, 160, 220, 58), width=2)
        for row in range(11):
            ratio = row / 10
            y = y1 + (y2 - y1) * ratio ** 1.48
            draw.line((x1, y, x2, y), fill=(65, 110, 170, round(18 + ratio * 20)), width=1)
        for column in range(9):
            x = x1 + (x2 - x1) * column / 8
            draw.line((self.cx + (x - self.cx) * 0.28, y1, x, y2), fill=(65, 110, 170, 24), width=1)

        for index, laser in enumerate(self.lasers):
            delta = time_sec - float(laser["time"])
            if delta < -0.62 or delta > 0.48:
                continue
            center, tangent, _ = self.laser_line(laser, time_sec)
            length = math.hypot(self.width, self.height)
            start = (center[0] - tangent[0] * length, center[1] - tangent[1] * length)
            end = (center[0] + tangent[0] * length, center[1] + tangent[1] * length)
            warning = delta < -0.18
            color = (255, 62 + index % 3 * 24, 82) if not warning else (255, 178, 72)
            alpha = round(65 + 190 * clamp(1.0 - abs(delta) / 0.62, 0.0, 1.0))
            if warning:
                alpha = 72
            gd.line((*start, *end), fill=(*color, min(155, alpha)), width=max(9, round(self.width * 0.042)))
            draw.line((*start, *end), fill=(*color, alpha), width=max(2, round(self.width * 0.007)))
            draw.line((*start, *end), fill=(255, 238, 230, min(255, alpha + 30)), width=max(1, round(self.width * 0.0025)))

        if len(self.trail) > 1:
            trail_color = color_for(self.theme, self.active + 9, self.total, 0.37)
            for index in range(1, len(self.trail)):
                age = index / len(self.trail)
                draw.line((*self.trail[index - 1], *self.trail[index]), fill=(*trail_color, round(175 * age)), width=max(1, round(1 + age * self.width * 0.012)))
        x, y = self.position
        pulse = clamp(1.0 - (time_sec - self.last_dodge) * 7.0, 0.0, 1.0)
        radius = self.runner_radius * (1.0 + pulse * 0.20)
        runner_color = (75, 235, 255) if not self.crashed else (255, 58, 92)
        gd.ellipse((x - radius * 2.4, y - radius * 2.4, x + radius * 2.4, y + radius * 2.4), fill=(*runner_color, 160))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(245, 253, 255, 255), outline=(*runner_color, 255), width=max(2, round(self.width * 0.008)))
        arrow = radius * 0.48
        draw.polygon(((x + arrow, y), (x - arrow * 0.55, y - arrow), (x - arrow * 0.55, y + arrow)), fill=(3, 12, 25, 255))
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(max(4, round(self.width * 0.018)))))
        image = Image.alpha_composite(image, crisp)
        overlay = ImageDraw.Draw(image)
        hook = self.title or "CAN IT DODGE EVERY LASER?"
        centered(overlay, self.cx, self.height * 0.064, hook, fitted_font(hook, round(self.width * 0.052), round(self.width * 0.030), round(self.width * 0.90), True), (255, 255, 255, 255), 2)
        centered(overlay, self.cx, self.height * 0.118, f"{self.active} / {self.total} DODGED  •  {self.max_speed_ratio:.1f}× SPEED", font(max(10, round(self.width * 0.021)), True), (91, 226, 255, 235), 1)
        if pulse > 0.0 and not self.crashed and self.last_distance - self.runner_radius < self.width * 0.045:
            centered(overlay, self.cx, self.height * 0.175, "NEAR MISS!", font(round(self.width * 0.029), True), (255, 208, 78, round(255 * pulse)), 1)
        if self.completed_at is not None:
            result = "LASER HIT!" if self.crashed else "FLAWLESS RUN!"
            color = (255, 76, 104, 255) if self.crashed else (105, 255, 211, 255)
            centered(overlay, self.cx, self.height * 0.905, result, font(round(self.width * 0.055), True), color, 2)
        centered(overlay, self.cx, self.height * 0.962, "EVERY BEAM HAS REAL COLLISION", font(max(8, round(self.width * 0.018)), True), (180, 198, 225, 210), 1)
        return image.convert("RGB")

    def frame(self, time_sec: float) -> Image.Image:
        """Render a clean, clipped laser course with a short cinematic trail."""
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        x1, y1, x2, y2 = self.arena
        arena_radius = round(self.width * 0.035)
        draw.rounded_rectangle(
            self.arena,
            radius=arena_radius,
            fill=(1, 5, 15, 232),
            outline=(115, 180, 230, 74),
            width=max(2, round(self.width * 0.003)),
        )
        for row in range(13):
            ratio = row / 12
            y = y1 + (y2 - y1) * ratio ** 1.55
            draw.line((x1 + 2, y, x2 - 2, y), fill=(68, 126, 185, round(12 + ratio * 17)), width=1)
        for column in range(11):
            x = x1 + (x2 - x1) * column / 10
            draw.line((self.cx + (x - self.cx) * 0.18, y1, x, y2), fill=(68, 126, 185, 20), width=1)

        # Render beams through a rounded mask. Energy never spills outside the
        # arena, so even two overlapping warnings remain instantly readable.
        beam_glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        beam_crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        bgd, bcd = ImageDraw.Draw(beam_glow), ImageDraw.Draw(beam_crisp)
        for index, laser in enumerate(self.lasers):
            delta = time_sec - float(laser["time"])
            if delta < -0.46 or delta > 0.28:
                continue
            center, tangent, _ = self.laser_line(laser, time_sec)
            length = math.hypot(self.width, self.height)
            start = (center[0] - tangent[0] * length, center[1] - tangent[1] * length)
            end = (center[0] + tangent[0] * length, center[1] + tangent[1] * length)
            warning = delta < -0.105
            color = (255, 48 + index % 3 * 17, 91) if not warning else (255, 177, 67)
            alpha = round(70 + 185 * clamp(1.0 - abs(delta) / 0.46, 0.0, 1.0))
            if warning:
                alpha = round(35 + 55 * clamp((delta + 0.46) / 0.355, 0.0, 1.0))
            bgd.line(
                (*start, *end),
                fill=(*color, min(150, alpha)),
                width=max(8, round(self.width * (0.029 if warning else 0.047))),
            )
            bcd.line(
                (*start, *end),
                fill=(*color, alpha),
                width=max(2, round(self.width * (0.004 if warning else 0.008))),
            )
            if not warning:
                bcd.line(
                    (*start, *end),
                    fill=(255, 244, 238, min(255, alpha + 40)),
                    width=max(1, round(self.width * 0.0025)),
                )

        arena_mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(arena_mask).rounded_rectangle(self.arena, radius=arena_radius, fill=255)
        empty_alpha = Image.new("L", image.size, 0)
        beam_glow.putalpha(Image.composite(beam_glow.getchannel("A"), empty_alpha, arena_mask))
        beam_crisp.putalpha(Image.composite(beam_crisp.getchannel("A"), empty_alpha, arena_mask))
        glow = Image.alpha_composite(glow, beam_glow)
        crisp = Image.alpha_composite(crisp, beam_crisp)
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)

        if len(self.trail) > 1:
            trail_color = color_for(self.theme, self.active + 9, self.total, 0.37)
            for index in range(1, len(self.trail)):
                age = index / (len(self.trail) - 1)
                draw.line(
                    (*self.trail[index - 1], *self.trail[index]),
                    fill=(*trail_color, round(110 * age * age)),
                    width=max(1, round(self.width * (0.002 + age * 0.006))),
                )

        x, y = self.position
        pulse = clamp(1.0 - (time_sec - self.last_dodge) * 7.0, 0.0, 1.0)
        radius = self.runner_radius * (1.0 + pulse * 0.20)
        runner_color = (75, 235, 255) if not self.crashed else (255, 58, 92)
        for future_index, future_delta in enumerate((0.07, 0.14, 0.21), 1):
            fx, fy = self.position_at(min(self.duration, time_sec + future_delta))
            ghost_radius = radius * (0.34 - future_index * 0.055)
            draw.ellipse(
                (fx - ghost_radius, fy - ghost_radius, fx + ghost_radius, fy + ghost_radius),
                fill=(*runner_color, 75 - future_index * 14),
            )
        gd.ellipse(
            (x - radius * 2.6, y - radius * 2.6, x + radius * 2.6, y + radius * 2.6),
            fill=(*runner_color, 155),
        )
        if pulse > 0:
            ring_radius = radius * (1.45 + (1.0 - pulse) * 1.4)
            draw.ellipse(
                (x - ring_radius, y - ring_radius, x + ring_radius, y + ring_radius),
                outline=(*runner_color, round(170 * pulse)),
                width=max(1, round(self.width * 0.004)),
            )
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(*runner_color, 255),
            outline=(225, 253, 255, 255),
            width=max(2, round(self.width * 0.005)),
        )
        draw.ellipse(
            (x - radius * 0.58, y - radius * 0.63, x + radius * 0.10, y + radius * 0.05),
            fill=(245, 255, 255, 245),
        )

        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(max(4, round(self.width * 0.018)))))
        image = Image.alpha_composite(image, crisp)
        overlay = ImageDraw.Draw(image)
        hook = self.title or "CAN IT DODGE EVERY LASER?"
        centered(
            overlay,
            self.cx,
            self.height * 0.060,
            hook,
            fitted_font(hook, round(self.width * 0.051), round(self.width * 0.030), round(self.width * 0.90), True),
            (255, 255, 255, 255),
            2,
        )
        centered(
            overlay,
            self.cx,
            self.height * 0.112,
            f"{self.active:03d} DODGED   |   {self.max_speed_ratio:.1f}X",
            font(max(10, round(self.width * 0.021)), True),
            (91, 226, 255, 235),
            1,
        )
        if pulse > 0.0 and not self.crashed and self.last_distance - self.runner_radius < self.width * 0.045:
            centered(
                overlay,
                self.cx,
                self.height * 0.151,
                "NEAR MISS +1",
                font(round(self.width * 0.027), True),
                (255, 208, 78, round(255 * pulse)),
                1,
            )
        if self.completed_at is not None:
            result = "LASER HIT!" if self.crashed else "FLAWLESS RUN!"
            color = (255, 76, 104, 255) if self.crashed else (105, 255, 211, 255)
            centered(overlay, self.cx, self.height * 0.915, result, font(round(self.width * 0.055), True), color, 2)
        centered(
            overlay,
            self.cx,
            self.height * 0.963,
            "ONE TOUCH ENDS THE RUN",
            font(max(8, round(self.width * 0.017)), True),
            (180, 198, 225, 205),
            1,
        )
        return image.convert("RGB")


class BossBattle(BaseGame):
    """A seeded combat timeline with telegraphs, damage and decisive outcomes."""

    game_name = "BOSS BATTLE"
    unit_name = "BOSS HP"
    PLAYER_CLASSES = ("THUNDER MACE", "PLASMA FLAIL", "VOID HAMMER")
    BOSS_CLASSES = ("WARDEN", "ION SENTINEL", "ABYSS CORE")

    def __init__(self, *args):
        super().__init__(*args)
        self.boss_max = float(self.total)
        self.boss_hp = self.boss_max
        self.player_max = 100.0
        self.player_hp = self.player_max
        self.player_class = self.PLAYER_CLASSES[self.seed % len(self.PLAYER_CLASSES)]
        self.boss_class = self.BOSS_CLASSES[(self.seed // 3) % len(self.BOSS_CLASSES)]
        self.player_wins = self.seed % 4 != 0
        # Deliberate, weighty clashes leave enough anticipation for viewers to
        # understand who is about to connect. The final blow keeps its suspense.
        base_count = max(11, min(25, round(self.duration * 1.45)))
        self.attack_count = base_count if (base_count % 2 == (1 if self.player_wins else 0)) else base_count + 1
        start, finish = self.duration * 0.07, self.duration * 0.90
        self.attack_times = [
            start + (finish - start) * (index / max(1, self.attack_count - 1)) ** 0.92
            for index in range(self.attack_count)
        ]
        raw_player = [self.rng.uniform(0.75, 1.28) for index in range(self.attack_count) if index % 2 == 0]
        raw_boss = [self.rng.uniform(0.75, 1.28) for index in range(self.attack_count) if index % 2 == 1]
        player_target = self.boss_max * (1.08 if self.player_wins else 0.73)
        boss_target = self.player_max * (0.76 if self.player_wins else 1.08)
        player_scale = player_target / max(0.001, sum(raw_player))
        boss_scale = boss_target / max(0.001, sum(raw_boss))
        player_cursor = boss_cursor = 0
        kinds = ("ARC", "PLASMA", "SLAM", "CRITICAL")
        self.attacks = []
        for index, event_time in enumerate(self.attack_times):
            player_attacks = index % 2 == 0
            if player_attacks:
                damage = raw_player[player_cursor] * player_scale
                player_cursor += 1
            else:
                damage = raw_boss[boss_cursor] * boss_scale
                boss_cursor += 1
            kind = "CRITICAL" if index == self.attack_count - 1 else kinds[(index + self.seed) % len(kinds)]
            self.attacks.append({
                "time": event_time,
                "player": player_attacks,
                "damage": damage,
                "kind": kind,
            })
        self.last_impact = -10.0
        self.last_damage = 0
        self.last_kind = "READY"
        self.last_attacker_player = True

    def update(self, time_sec: float):
        target = sum(float(attack["time"]) <= time_sec for attack in self.attacks)
        while self.last_tick < target - 1 and self.completed_at is None:
            self.last_tick += 1
            attack = self.attacks[self.last_tick]
            damage = float(attack["damage"])
            player_attacks = bool(attack["player"])
            if player_attacks:
                before = self.boss_hp
                self.boss_hp = max(0.0, self.boss_hp - damage)
                dealt = before - self.boss_hp
                frequency = 510.0 + (self.last_tick % 5) * 72.0
                impact_x = self.width * 0.72
                color = (255, 92, 105)
            else:
                before = self.player_hp
                self.player_hp = max(0.0, self.player_hp - damage)
                dealt = before - self.player_hp
                frequency = 115.0 + (self.last_tick % 4) * 24.0
                impact_x = self.width * 0.28
                color = (75, 220, 255)
            self.active = min(self.total, round(self.boss_max - self.boss_hp))
            self.last_damage = max(1, round(dealt))
            self.last_kind = str(attack["kind"])
            self.last_attacker_player = player_attacks
            self.last_impact = float(attack["time"])
            self.record_hit(self.last_impact, frequency, 0.55, "impact")
            self.burst(impact_x, self.height * 0.61, color, 22 if self.last_kind == "CRITICAL" else 13)
            if self.boss_hp <= 0.0 or self.player_hp <= 0.0:
                self.completed_at = self.last_impact
                self.burst(self.cx, self.height * 0.53, (255, 223, 120), 78)
        self.max_speed_ratio = 1.0 + min(1.0, target / self.attack_count) * 3.8
        self.update_particles()

    def attack_phase(self, time_sec: float):
        if not self.attacks:
            return None, 0.0
        attack = min(self.attacks, key=lambda item: abs(float(item["time"]) - time_sec))
        delta = time_sec - float(attack["time"])
        return attack, delta

    def draw_fighter(self, draw, glow_draw, x: float, y: float, scale: float, color, facing: int, boss: bool = False):
        body_top = y - scale * 0.38
        head = scale * (0.17 if boss else 0.15)
        shoulder = scale * (0.32 if boss else 0.27)
        waist = scale * (0.17 if boss else 0.145)
        armor = tuple(max(18, round(channel * 0.32)) for channel in color)
        armor_light = tuple(min(255, round(channel * 0.78 + 48)) for channel in color)
        outline = max(2, round(scale * 0.032))
        glow_draw.ellipse((x - shoulder * 1.35, body_top - head * 1.8, x + shoulder * 1.35, y + scale * 0.48), fill=(*color, 72))

        # Heavy boots and segmented legs make the silhouettes read as fighters
        # rather than line-art stick figures at phone size.
        for side in (-1, 1):
            hip_x = x + side * waist * 0.62
            knee_x = x + side * scale * (0.16 if boss else 0.14)
            foot_x = x + side * scale * (0.25 if boss else 0.22)
            draw.polygon(
                (
                    (hip_x - scale * 0.065, y + scale * 0.14),
                    (hip_x + scale * 0.065, y + scale * 0.14),
                    (knee_x + scale * 0.070, y + scale * 0.34),
                    (foot_x + scale * 0.085, y + scale * 0.49),
                    (foot_x - scale * 0.105, y + scale * 0.49),
                    (knee_x - scale * 0.070, y + scale * 0.34),
                ),
                fill=(*armor, 255),
                outline=(*color, 255),
            )
            draw.line((hip_x, y + scale * 0.18, knee_x, y + scale * 0.34, foot_x, y + scale * 0.47), fill=(*armor_light, 210), width=max(2, round(scale * 0.025)), joint="curve")
            draw.rounded_rectangle((foot_x - scale * 0.13, y + scale * 0.44, foot_x + scale * 0.13, y + scale * 0.53), radius=max(2, round(scale * 0.025)), fill=(5, 9, 19, 255), outline=(*color, 255), width=outline)

        # Torso, shoulder plates and luminous reactor.
        torso = (
            (x - shoulder, body_top + head * 0.70),
            (x - waist, y + scale * 0.22),
            (x + waist, y + scale * 0.22),
            (x + shoulder, body_top + head * 0.70),
            (x + scale * 0.18, body_top - scale * 0.02),
            (x - scale * 0.18, body_top - scale * 0.02),
        )
        draw.polygon(torso, fill=(*armor, 255), outline=(*color, 255))
        for side in (-1, 1):
            sx = x + side * shoulder * 0.82
            draw.ellipse((sx - scale * 0.105, body_top - scale * 0.01, sx + scale * 0.105, body_top + scale * 0.18), fill=(*armor_light, 255), outline=(*color, 255), width=outline)
        core_radius = scale * (0.075 if boss else 0.065)
        glow_draw.ellipse((x - core_radius * 2.2, body_top + scale * 0.10 - core_radius * 2.2, x + core_radius * 2.2, body_top + scale * 0.10 + core_radius * 2.2), fill=(*color, 140))
        draw.ellipse((x - core_radius, body_top + scale * 0.10 - core_radius, x + core_radius, body_top + scale * 0.10 + core_radius), fill=(238, 252, 255, 255), outline=(*color, 255), width=outline)

        # Helmet with visor and class-specific profile.
        if boss:
            draw.polygon(((x - head * 0.8, body_top - head * 0.9), (x - head * 1.55, body_top - head * 1.55), (x - head * 0.45, body_top - head * 1.20)), fill=(*color, 255))
            draw.polygon(((x + head * 0.8, body_top - head * 0.9), (x + head * 1.55, body_top - head * 1.55), (x + head * 0.45, body_top - head * 1.20)), fill=(*color, 255))
        else:
            draw.polygon(((x - head * 0.25, body_top - head * 1.35), (x + facing * head * 0.95, body_top - head * 1.85), (x + facing * head * 0.58, body_top - head * 0.65)), fill=(*color, 235))
        draw.rounded_rectangle((x - head, body_top - head * 1.05, x + head, body_top + head * 0.78), radius=max(3, round(head * 0.35)), fill=(5, 9, 19, 255), outline=(*color, 255), width=outline)
        visor_y = body_top - head * 0.13
        draw.line((x - head * 0.70, visor_y, x + head * 0.70, visor_y), fill=(*armor_light, 255), width=max(2, round(scale * 0.035)))

        # Forearms and energy weapon.
        arm_width = max(5, round(scale * (0.105 if boss else 0.085)))
        hand_x = x + facing * scale * (0.42 if boss else 0.40)
        hand_y = y - scale * 0.01
        elbow = (x + facing * shoulder * 0.90, body_top + scale * 0.17)
        draw.line((elbow[0], elbow[1], hand_x, hand_y), fill=(*armor, 255), width=arm_width)
        draw.line((elbow[0], elbow[1], hand_x, hand_y), fill=(*color, 245), width=max(2, round(arm_width * 0.30)))
        off_elbow = (x - facing * shoulder * 0.82, body_top + scale * 0.17)
        off_hand = (x - facing * scale * 0.25, y + scale * 0.10)
        draw.line((*off_elbow, *off_hand), fill=(*armor, 255), width=arm_width)
        draw.ellipse((hand_x - scale * 0.055, hand_y - scale * 0.055, hand_x + scale * 0.055, hand_y + scale * 0.055), fill=(*armor_light, 255))
        weapon_end = (hand_x + facing * scale * (0.32 if boss else 0.40), hand_y - scale * (0.29 if boss else 0.25))
        glow_draw.line((hand_x, hand_y, *weapon_end), fill=(*color, 150), width=max(12, round(scale * 0.19)))
        draw.line((hand_x, hand_y, *weapon_end), fill=(245, 252, 255, 255), width=max(3, round(scale * 0.052)))

    def _legacy_frame(self, time_sec: float) -> Image.Image:
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        floor_y = self.height * 0.69
        for ring in range(7, 0, -1):
            rx = self.width * (0.12 + ring * 0.065)
            ry = rx * 0.28
            color = color_for(self.theme, ring * 9 + self.seed, 72)
            draw.ellipse((self.cx - rx, floor_y - ry, self.cx + rx, floor_y + ry), outline=(*color, 28 + ring * 6), width=2)
        draw.ellipse((self.width * 0.07, floor_y - self.height * 0.045, self.width * 0.93, floor_y + self.height * 0.070), fill=(2, 5, 14, 215), outline=(155, 175, 225, 55), width=2)
        for x in (self.width * 0.11, self.width * 0.89):
            draw.polygon(((x - self.width * 0.035, floor_y), (x + self.width * 0.035, floor_y), (x + self.width * 0.018, self.height * 0.27), (x - self.width * 0.018, self.height * 0.27)), fill=(10, 15, 31, 220), outline=(130, 155, 205, 55))

        attack, delta = self.attack_phase(time_sec)
        player_x, boss_x = self.width * 0.285, self.width * 0.715
        impact_pulse = clamp(1.0 - (time_sec - self.last_impact) * 6.0, 0.0, 1.0)
        if attack is not None and -0.28 <= delta <= 0.30:
            telegraph = clamp((delta + 0.28) / 0.28, 0.0, 1.0)
            recovery = clamp(1.0 - delta / 0.30, 0.0, 1.0)
            lunge = telegraph if delta < 0 else recovery
            if bool(attack["player"]):
                player_x += self.width * 0.20 * lunge
            else:
                boss_x -= self.width * 0.20 * lunge
        knock = impact_pulse * self.width * 0.025
        if self.last_attacker_player:
            boss_x += knock
        else:
            player_x -= knock

        player_color = color_for(self.theme, self.seed % 17, 24, 0.35)
        boss_color = (255, 72 + self.seed % 35, 92)
        self.draw_fighter(draw, gd, player_x, floor_y - self.height * 0.018, self.width * 0.30, player_color, 1, False)
        self.draw_fighter(draw, gd, boss_x, floor_y - self.height * 0.015, self.width * 0.36, boss_color, -1, True)
        if attack is not None and -0.24 <= delta <= 0.12:
            attacker_x = player_x if bool(attack["player"]) else boss_x
            defender_x = boss_x if bool(attack["player"]) else player_x
            attack_color = player_color if bool(attack["player"]) else boss_color
            phase = clamp((delta + 0.24) / 0.32, 0.0, 1.0)
            arc_y = self.height * 0.53 - math.sin(math.pi * phase) * self.height * 0.08
            gd.line((attacker_x, self.height * 0.54, (attacker_x + defender_x) / 2, arc_y, defender_x, self.height * 0.55), fill=(*attack_color, 145), width=max(14, round(self.width * 0.055)), joint="curve")
            draw.line((attacker_x, self.height * 0.54, (attacker_x + defender_x) / 2, arc_y, defender_x, self.height * 0.55), fill=(*attack_color, 235), width=max(3, round(self.width * 0.010)), joint="curve")
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(max(5, round(self.width * 0.020)))))
        image = Image.alpha_composite(image, crisp)
        overlay = ImageDraw.Draw(image)
        hook = self.title or "WHO WINS THIS BATTLE?"
        centered(overlay, self.cx, self.height * 0.057, hook, fitted_font(hook, round(self.width * 0.052), round(self.width * 0.030), round(self.width * 0.90), True), (255, 255, 255, 255), 2)
        bar_y = self.height * 0.122
        for left, right, ratio, color, label in (
            (self.width * 0.07, self.width * 0.47, self.player_hp / self.player_max, player_color, self.player_class),
            (self.width * 0.53, self.width * 0.93, self.boss_hp / self.boss_max, boss_color, self.boss_class),
        ):
            overlay.rounded_rectangle((left, bar_y, right, bar_y + self.height * 0.025), radius=8, fill=(2, 5, 13, 235), outline=(*color, 120), width=2)
            if ratio > 0:
                overlay.rounded_rectangle((left + 3, bar_y + 3, left + 3 + (right - left - 6) * ratio, bar_y + self.height * 0.025 - 3), radius=6, fill=(*color, 245))
            centered(overlay, (left + right) / 2, bar_y - self.height * 0.015, label, font(max(8, round(self.width * 0.016)), True), (*color, 245), 1)
        if impact_pulse > 0.0:
            defender_x = self.width * (0.72 if self.last_attacker_player else 0.28)
            centered(overlay, defender_x, self.height * 0.43 - impact_pulse * self.height * 0.035, f"-{self.last_damage}  {self.last_kind}", font(round(self.width * 0.028), True), (255, 232, 165, round(255 * impact_pulse)), 1)
        if self.completed_at is not None:
            result = "PLAYER WINS!" if self.boss_hp <= 0 else "BOSS WINS!"
            color = (115, 255, 215, 255) if self.boss_hp <= 0 else (255, 92, 115, 255)
            centered(overlay, self.cx, self.height * 0.825, result, font(round(self.width * 0.061), True), color, 2)
        centered(overlay, self.cx, self.height * 0.935, f"PLAYER {round(self.player_hp)} HP  •  BOSS {round(self.boss_hp)} HP", font(max(9, round(self.width * 0.020)), True), (224, 232, 250, 235), 1)
        centered(overlay, self.cx, self.height * 0.967, "SEEDED COMBAT • DIFFERENT OUTCOME EVERY RUN", font(max(8, round(self.width * 0.016)), True), (170, 188, 220, 205), 1)
        return image.convert("RGB")

    def arena_bounds(self) -> tuple[float, float, float, float]:
        side = self.width * 0.92
        left = self.cx - side * 0.5
        top = self.height * 0.205
        return left, top, left + side, top + side

    def fighter_positions(self, time_sec: float, attack, delta: float) -> tuple[list[float], list[float]]:
        """Physics-inspired deterministic orbits, pulled together for impact."""
        left, top, right, bottom = self.arena_bounds()
        side = right - left
        phase = (self.seed % 997) * 0.0137
        player = [
            left + side * (0.28 + 0.105 * math.sin(time_sec * 0.83 + phase)),
            top + side * (0.48 + 0.245 * math.sin(time_sec * 1.11 + phase * 0.61)),
        ]
        boss = [
            left + side * (0.72 + 0.105 * math.sin(time_sec * 0.71 + phase + 2.4)),
            top + side * (0.50 + 0.235 * math.sin(time_sec * 0.97 + phase * 0.43 + 2.0)),
        ]
        if attack is None or delta < -0.34 or delta > 0.42:
            return player, boss

        if delta <= 0.0:
            collision_energy = smootherstep((delta + 0.34) / 0.34)
        else:
            collision_energy = 1.0 - smoothstep(delta / 0.42)
        attacker = player if bool(attack["player"]) else boss
        defender = boss if bool(attack["player"]) else player
        start_attacker = tuple(attacker)
        attacker[0] = lerp(attacker[0], defender[0], collision_energy * 0.62)
        attacker[1] = lerp(attacker[1], defender[1], collision_energy * 0.62)
        if delta >= 0.0:
            knock = (1.0 - smoothstep(delta / 0.30)) * side * 0.075
            dx = defender[0] - start_attacker[0]
            dy = defender[1] - start_attacker[1]
            length = max(1.0, math.hypot(dx, dy))
            defender[0] += dx / length * knock
            defender[1] += dy / length * knock

        margin = self.width * 0.095
        for position in (player, boss):
            position[0] = clamp(position[0], left + margin, right - margin)
            position[1] = clamp(position[1], top + margin, bottom - margin)
        return player, boss

    def draw_energy_orb(
        self,
        draw,
        glow_draw,
        x: float,
        y: float,
        radius: float,
        color: tuple[int, int, int],
        hp: float,
        rotation: float,
        armored: bool,
    ):
        outline = max(2, round(self.width * 0.0045))
        glow_draw.ellipse(
            (x - radius * 1.65, y - radius * 1.65, x + radius * 1.65, y + radius * 1.65),
            fill=(*color, 92),
        )
        draw.ellipse(
            (x - radius * 1.07, y - radius * 1.07, x + radius * 1.07, y + radius * 1.07),
            fill=(2, 8, 12, 255),
            outline=(*color, 245),
            width=outline,
        )

        # Offset concentric shells approximate a metallic radial gradient while
        # remaining deterministic and sharp at both preview and final sizes.
        for layer in range(18):
            ratio = layer / 17
            layer_radius = radius * (0.96 - ratio * 0.70)
            light = 0.23 + ratio * 0.78
            fill = tuple(min(255, round(channel * light + 12 * ratio)) for channel in color)
            offset = radius * ratio * 0.16
            draw.ellipse(
                (
                    x - layer_radius - offset,
                    y - layer_radius - offset,
                    x + layer_radius - offset,
                    y + layer_radius - offset,
                ),
                fill=(*fill, 255),
            )

        panel_box = (x - radius * 0.87, y - radius * 0.87, x + radius * 0.87, y + radius * 0.87)
        for segment in range(6 if armored else 4):
            start = math.degrees(rotation) + segment * (60 if armored else 90) + 8
            draw.arc(
                panel_box,
                start=start,
                end=start + (38 if armored else 55),
                fill=(218, 255, 250, 210),
                width=max(1, round(radius * 0.095)),
            )
        if armored:
            for fin in range(4):
                angle = rotation + fin * math.pi * 0.5
                tangent = (-math.sin(angle), math.cos(angle))
                direction = (math.cos(angle), math.sin(angle))
                root = (x + direction[0] * radius * 0.82, y + direction[1] * radius * 0.82)
                tip = (x + direction[0] * radius * 1.30, y + direction[1] * radius * 1.30)
                spread = radius * 0.25
                draw.polygon(
                    (
                        (root[0] + tangent[0] * spread, root[1] + tangent[1] * spread),
                        tip,
                        (root[0] - tangent[0] * spread, root[1] - tangent[1] * spread),
                    ),
                    fill=(*tuple(max(10, round(channel * 0.34)) for channel in color), 255),
                    outline=(*color, 230),
                )

        hp_text = str(max(0, round(hp)))
        centered(
            draw,
            x,
            y + radius * 0.04,
            hp_text,
            fitted_font(hp_text, max(10, round(radius * 0.62)), 8, round(radius * 1.25), True),
            (244, 255, 252, 255),
            max(1, round(radius * 0.055)),
        )
        draw.ellipse(
            (x - radius * 0.50, y - radius * 0.57, x - radius * 0.16, y - radius * 0.23),
            fill=(255, 255, 255, 150),
        )

    def draw_mace(
        self,
        draw,
        glow_draw,
        origin: tuple[float, float],
        core_radius: float,
        angle: float,
        color: tuple[int, int, int],
    ) -> tuple[float, float]:
        distance = core_radius * 2.72
        mace_x = origin[0] + math.cos(angle) * distance
        mace_y = origin[1] + math.sin(angle) * distance
        mace_radius = core_radius * 0.76
        glow_draw.line((*origin, mace_x, mace_y), fill=(*color, 135), width=max(9, round(core_radius * 0.58)))
        draw.line((*origin, mace_x, mace_y), fill=(1, 7, 9, 255), width=max(4, round(core_radius * 0.28)))
        draw.line((*origin, mace_x, mace_y), fill=(*color, 245), width=max(2, round(core_radius * 0.095)))
        chain_count = 5
        for chain_index in range(1, chain_count + 1):
            ratio = chain_index / (chain_count + 1)
            chain_x = lerp(origin[0], mace_x, ratio)
            chain_y = lerp(origin[1], mace_y, ratio)
            link_radius = max(1.8, core_radius * 0.125)
            draw.ellipse(
                (chain_x - link_radius, chain_y - link_radius, chain_x + link_radius, chain_y + link_radius),
                fill=(239, 255, 251, 255),
                outline=(*color, 255),
                width=max(1, round(core_radius * 0.055)),
            )
        for spike in range(10):
            spike_angle = angle * 0.38 + spike * math.tau / 10
            inner = (mace_x + math.cos(spike_angle) * mace_radius * 0.76, mace_y + math.sin(spike_angle) * mace_radius * 0.76)
            tangent = (-math.sin(spike_angle), math.cos(spike_angle))
            tip = (mace_x + math.cos(spike_angle) * mace_radius * 1.38, mace_y + math.sin(spike_angle) * mace_radius * 1.38)
            draw.polygon(
                (
                    (inner[0] + tangent[0] * mace_radius * 0.19, inner[1] + tangent[1] * mace_radius * 0.19),
                    tip,
                    (inner[0] - tangent[0] * mace_radius * 0.19, inner[1] - tangent[1] * mace_radius * 0.19),
                ),
                fill=(198, 225, 221, 255),
                outline=(*color, 220),
            )
        glow_draw.ellipse(
            (mace_x - mace_radius * 1.55, mace_y - mace_radius * 1.55, mace_x + mace_radius * 1.55, mace_y + mace_radius * 1.55),
            fill=(*color, 88),
        )
        draw.ellipse(
            (mace_x - mace_radius, mace_y - mace_radius, mace_x + mace_radius, mace_y + mace_radius),
            fill=(15, 35, 37, 255),
            outline=(*color, 255),
            width=max(2, round(core_radius * 0.12)),
        )
        draw.ellipse(
            (mace_x - mace_radius * 0.55, mace_y - mace_radius * 0.58, mace_x + mace_radius * 0.15, mace_y + mace_radius * 0.12),
            fill=(206, 236, 232, 210),
        )
        return mace_x, mace_y

    def frame(self, time_sec: float) -> Image.Image:
        """Render an object-based physics duel inspired by viral simulations."""
        image = self.canvas(time_sec)
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        crisp = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd, draw = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        left, top, right, bottom = self.arena_bounds()
        side = right - left
        player_color = (66, 255, 103)
        boss_color = (47, 225, 219)

        draw.rectangle((left, top, right, bottom), fill=(0, 4, 6, 246), outline=(215, 255, 247, 185), width=max(2, round(self.width * 0.004)))
        # Angular shadow wedges and sparse dust give the square dimensionality
        # without competing with the two combatants.
        wedge_shift = math.sin(time_sec * 0.34 + self.seed) * side * 0.05
        draw.polygon(
            ((left, top + side * 0.18), (left + side * 0.50 + wedge_shift, bottom), (left, bottom)),
            fill=(3, 34, 34, 125),
        )
        draw.polygon(
            ((right, top), (right, top + side * 0.47), (left + side * 0.45 + wedge_shift, top)),
            fill=(5, 22, 27, 118),
        )
        for star_index in range(30):
            star_x = left + side * ((math.sin(star_index * 91.73 + self.seed * 0.011) + 1.0) * 0.5)
            star_y = top + side * ((math.sin(star_index * 47.19 + self.seed * 0.019) + 1.0) * 0.5)
            star_radius = max(1, round(self.width * (0.0014 + (star_index % 3) * 0.0007)))
            draw.ellipse(
                (star_x - star_radius, star_y - star_radius, star_x + star_radius, star_y + star_radius),
                fill=(221, 255, 248, 75 + (star_index % 4) * 22),
            )

        # Two jagged energy rails make impacts against the walls feel physical.
        for rail_side, rail_color in ((-1, player_color), (1, boss_color)):
            rail_points = []
            for rail_index in range(13):
                ratio = rail_index / 12
                base_x = left if rail_side < 0 else right
                inward = rail_side * -1 * side * (0.012 + 0.040 * (0.5 + 0.5 * math.sin(rail_index * 2.31 + self.seed)))
                rail_points.append((base_x + inward, top + ratio * side))
            gd.line(rail_points, fill=(*rail_color, 100), width=max(8, round(self.width * 0.022)), joint="curve")
            draw.line(rail_points, fill=(*rail_color, 205), width=max(1, round(self.width * 0.004)), joint="curve")

        attack, delta = self.attack_phase(time_sec)
        player_position, boss_position = self.fighter_positions(time_sec, attack, delta)
        impact_pulse = clamp(1.0 - (time_sec - self.last_impact) * 5.2, 0.0, 1.0)
        shake = impact_pulse * self.width * (0.012 if self.last_kind == "CRITICAL" else 0.007)
        shake_x = math.sin(time_sec * 97.0 + self.seed) * shake
        shake_y = math.cos(time_sec * 83.0 + self.seed) * shake
        player_position[0] += shake_x
        player_position[1] += shake_y
        boss_position[0] += shake_x
        boss_position[1] += shake_y

        player_radius = self.width * 0.058
        boss_radius = self.width * 0.086
        spin = time_sec * (4.2 + min(2.4, self.max_speed_ratio * 0.28)) + self.seed * 0.013
        mace_angle = spin
        if attack is not None and bool(attack["player"]) and -0.34 <= delta <= 0.25:
            target_angle = math.atan2(boss_position[1] - player_position[1], boss_position[0] - player_position[0])
            aim = smootherstep((delta + 0.34) / 0.34) if delta < 0 else 1.0 - smoothstep(delta / 0.25)
            angular_error = math.atan2(math.sin(target_angle - mace_angle), math.cos(target_angle - mace_angle))
            mace_angle += angular_error * aim

        sweep_radius = player_radius * 2.72
        sweep_box = (
            player_position[0] - sweep_radius,
            player_position[1] - sweep_radius,
            player_position[0] + sweep_radius,
            player_position[1] + sweep_radius,
        )
        sweep_end = math.degrees(mace_angle)
        gd.arc(
            sweep_box,
            start=sweep_end - 54,
            end=sweep_end,
            fill=(*player_color, 82),
            width=max(7, round(self.width * 0.020)),
        )
        draw.arc(
            sweep_box,
            start=sweep_end - 40,
            end=sweep_end,
            fill=(*player_color, 125),
            width=max(1, round(self.width * 0.0035)),
        )
        self.draw_mace(draw, gd, tuple(player_position), player_radius, mace_angle, player_color)

        # Telegraphs appear before contact, then collapse into a shockwave. The
        # timing is tied to the same attack event that changes HP and audio.
        if attack is not None and -0.34 <= delta < 0.0:
            telegraph = smootherstep((delta + 0.34) / 0.34)
            defender = boss_position if bool(attack["player"]) else player_position
            warning_radius = self.width * (0.078 - telegraph * 0.025)
            draw.ellipse(
                (
                    defender[0] - warning_radius,
                    defender[1] - warning_radius,
                    defender[0] + warning_radius,
                    defender[1] + warning_radius,
                ),
                outline=(255, 218, 83, round(80 + 160 * telegraph)),
                width=max(1, round(self.width * 0.004)),
            )
            for marker in range(4):
                marker_angle = time_sec * 4.0 + marker * math.pi * 0.5
                mx = defender[0] + math.cos(marker_angle) * warning_radius
                my = defender[1] + math.sin(marker_angle) * warning_radius
                draw.ellipse((mx - 2, my - 2, mx + 2, my + 2), fill=(255, 232, 128, 230))

        # Mechanical sphere and energy core replace the old humanoid sprites.
        self.draw_energy_orb(
            draw,
            gd,
            player_position[0],
            player_position[1],
            player_radius,
            player_color,
            self.player_hp,
            spin * 0.43,
            False,
        )
        self.draw_energy_orb(
            draw,
            gd,
            boss_position[0],
            boss_position[1],
            boss_radius,
            boss_color,
            self.boss_hp,
            -spin * 0.31,
            True,
        )

        if impact_pulse > 0.0:
            defender = boss_position if self.last_attacker_player else player_position
            shock_color = player_color if self.last_attacker_player else boss_color
            for ring_index in range(3):
                ring_progress = clamp(1.0 - impact_pulse + ring_index * 0.15, 0.0, 1.0)
                ring_radius = self.width * (0.025 + ring_progress * 0.16)
                draw.ellipse(
                    (
                        defender[0] - ring_radius,
                        defender[1] - ring_radius,
                        defender[0] + ring_radius,
                        defender[1] + ring_radius,
                    ),
                    outline=(*shock_color, round(205 * impact_pulse * (1.0 - ring_index * 0.22))),
                    width=max(1, round(self.width * (0.008 - ring_index * 0.0015))),
                )
            for debris_index in range(18 if self.last_kind == "CRITICAL" else 11):
                debris_angle = debris_index * 2.399 + self.last_tick * 0.71
                debris_distance = self.width * (0.025 + (1.0 - impact_pulse) * (0.11 + (debris_index % 4) * 0.018))
                debris_x = defender[0] + math.cos(debris_angle) * debris_distance
                debris_y = defender[1] + math.sin(debris_angle) * debris_distance
                debris_radius = max(1, round(self.width * 0.004 * impact_pulse))
                draw.ellipse(
                    (debris_x - debris_radius, debris_y - debris_radius, debris_x + debris_radius, debris_y + debris_radius),
                    fill=(244, 255, 250, round(230 * impact_pulse)),
                )

        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(max(5, round(self.width * 0.020)))))
        image = Image.alpha_composite(image, crisp)
        if impact_pulse > 0.0:
            flash_strength = 62 if self.last_kind == "CRITICAL" else 28
            flash = Image.new("RGBA", image.size, (225, 255, 249, round(flash_strength * impact_pulse * impact_pulse)))
            image = Image.alpha_composite(image, flash)

        overlay = ImageDraw.Draw(image)
        hook = self.title or "WHO WINS THIS PHYSICS BATTLE?"
        centered(
            overlay,
            self.cx,
            self.height * 0.052,
            hook,
            fitted_font(hook, round(self.width * 0.047), round(self.width * 0.027), round(self.width * 0.91), True),
            (246, 255, 252, 255),
            2,
        )
        bar_y = self.height * 0.112
        for left_bar, right_bar, ratio, color, label, hp in (
            (self.width * 0.065, self.width * 0.475, self.player_hp / self.player_max, player_color, self.player_class, self.player_hp),
            (self.width * 0.525, self.width * 0.935, self.boss_hp / self.boss_max, boss_color, self.boss_class, self.boss_hp),
        ):
            centered(
                overlay,
                (left_bar + right_bar) * 0.5,
                bar_y - self.height * 0.019,
                label,
                fitted_font(label, max(9, round(self.width * 0.018)), 8, round(right_bar - left_bar), True),
                (*color, 255),
                1,
            )
            overlay.rounded_rectangle(
                (left_bar, bar_y, right_bar, bar_y + self.height * 0.025),
                radius=max(3, round(self.width * 0.011)),
                fill=(1, 7, 9, 245),
                outline=(*color, 180),
                width=max(1, round(self.width * 0.003)),
            )
            if ratio > 0.0:
                fill_radius = max(2, round(self.width * 0.008))
                fill_right = max(
                    left_bar + 3 + fill_radius * 2,
                    left_bar + 3 + (right_bar - left_bar - 6) * ratio,
                )
                overlay.rounded_rectangle(
                    (
                        round(left_bar + 3),
                        round(bar_y + 3),
                        round(fill_right),
                        round(bar_y + self.height * 0.025 - 3),
                    ),
                    radius=fill_radius,
                    fill=(*color, 250),
                )
            overlay.text(
                (right_bar - 5, bar_y + self.height * 0.0125),
                str(max(0, round(hp))),
                font=font(max(8, round(self.width * 0.015)), True),
                fill=(243, 255, 252, 245),
                anchor="rm",
            )

        if impact_pulse > 0.0:
            defender = boss_position if self.last_attacker_player else player_position
            centered(
                overlay,
                defender[0],
                defender[1] - self.width * (0.10 + (1.0 - impact_pulse) * 0.08),
                f"-{self.last_damage} {self.last_kind}",
                font(round(self.width * 0.027), True),
                (255, 240, 174, round(255 * impact_pulse)),
                1,
            )
        if self.completed_at is not None:
            result = f"{self.player_class} WINS!" if self.boss_hp <= 0 else f"{self.boss_class} WINS!"
            result_color = player_color if self.boss_hp <= 0 else boss_color
            centered(
                overlay,
                self.cx,
                self.height * 0.790,
                result,
                fitted_font(result, round(self.width * 0.054), round(self.width * 0.032), round(self.width * 0.88), True),
                (*result_color, 255),
                3,
            )
        centered(
            overlay,
            self.cx,
            self.height * 0.944,
            "REAL IMPACTS  |  DIFFERENT OUTCOME EVERY RUN",
            fitted_font(
                "REAL IMPACTS  |  DIFFERENT OUTCOME EVERY RUN",
                max(8, round(self.width * 0.015)),
                7,
                round(self.width * 0.92),
                True,
            ),
            (176, 208, 208, 205),
            1,
        )
        return image.convert("RGB")








GAME_CLASSES = {
    "shape-tunnel": ShapeTunnel,
    "laser-dodge": LaserDodge,
    "boss-battle": BossBattle,
}


def create_game(game_id: str, width: int, height: int, fps: int, duration: float, difficulty: int, seed: int, theme: str, title: str):
    game_class = GAME_CLASSES.get(game_id)
    if game_class is None:
        raise ValueError(f"Unknown game variant: {game_id}")
    return game_class(width, height, fps, duration, difficulty, seed, theme, title)
