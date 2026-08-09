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


class LaserDodge(BaseGame):
    """A deterministic near-miss course with geometric collision checks."""

    game_name = "LASER DODGE"
    unit_name = "LASERS"

    def __init__(self, *args):
        super().__init__(*args)
        self.arena = (
            self.width * 0.075,
            self.height * 0.205,
            self.width * 0.925,
            self.height * 0.855,
        )
        self.runner_radius = max(7.0, self.width * 0.021)
        self.event_count = max(18, min(72, round(self.duration * 4.2)))
        start, finish = self.duration * 0.055, self.duration * 0.88
        self.event_times = [
            start + (finish - start) * (index / max(1, self.event_count - 1)) ** 0.96
            for index in range(self.event_count)
        ]
        self.key_times = [0.0, *self.event_times, self.duration]
        margin_x, margin_y = self.width * 0.17, self.height * 0.29
        self.waypoints = [(self.cx, self.height * 0.53)]
        lane = self.seed % 5
        for index in range(self.event_count):
            lane = (lane + self.rng.choice((-2, -1, 1, 2))) % 5
            lane_x = margin_x + lane / 4 * (self.width - margin_x * 2)
            wave_y = self.cy + math.sin(index * 1.37 + self.seed * 0.003) * self.height * 0.205
            wave_y += self.rng.uniform(-self.height * 0.025, self.height * 0.025)
            self.waypoints.append((lane_x, clamp(wave_y, margin_y, self.height * 0.79)))
        self.waypoints.append(self.waypoints[-1])
        self.will_survive = self.seed % 5 != 0
        self.failure_index = self.event_count - 2
        self.lasers = []
        for index, (event_time, waypoint) in enumerate(zip(self.event_times, self.waypoints[1:-1])):
            angle = self.rng.uniform(-1.25, 1.25) + (math.pi / 2 if index % 3 == 0 else 0.0)
            normal = (-math.sin(angle), math.cos(angle))
            safe_gap = self.runner_radius + self.width * self.rng.uniform(0.020, 0.052)
            if not self.will_survive and index == self.failure_index:
                safe_gap = self.runner_radius * 0.20
            side = -1 if (index + self.seed) % 2 else 1
            center = (waypoint[0] + normal[0] * safe_gap * side, waypoint[1] + normal[1] * safe_gap * side)
            self.lasers.append({
                "time": event_time,
                "angle": angle,
                "center": center,
                "speed": self.width * self.rng.uniform(0.48, 0.82),
                "direction": self.rng.choice((-1.0, 1.0)),
                "hue": index + self.seed % 19,
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
        eased = ratio * ratio * (3.0 - 2.0 * ratio)
        start, end = self.waypoints[segment], self.waypoints[segment + 1]
        arc = math.sin(math.pi * ratio) * self.height * 0.012 * (-1 if segment % 2 else 1)
        return (
            start[0] + (end[0] - start[0]) * eased,
            start[1] + (end[1] - start[1]) * eased + arc,
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
        self.trail = self.trail[-30:]
        self.max_speed_ratio = 1.0 + min(1.0, target / self.event_count) * 6.2
        self.update_particles()

    def frame(self, time_sec: float) -> Image.Image:
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


class BossBattle(BaseGame):
    """A seeded combat timeline with telegraphs, damage and decisive outcomes."""

    game_name = "BOSS BATTLE"
    unit_name = "BOSS HP"
    PLAYER_CLASSES = ("VOID BLADE", "ARC RANGER", "NEON MONK")
    BOSS_CLASSES = ("IRON WARDEN", "EMBER TITAN", "ABYSS GOLEM")

    def __init__(self, *args):
        super().__init__(*args)
        self.boss_max = float(self.total)
        self.boss_hp = self.boss_max
        self.player_max = max(120.0, self.total * 0.72)
        self.player_hp = self.player_max
        self.player_class = self.PLAYER_CLASSES[self.seed % len(self.PLAYER_CLASSES)]
        self.boss_class = self.BOSS_CLASSES[(self.seed // 3) % len(self.BOSS_CLASSES)]
        self.player_wins = self.seed % 4 != 0
        base_count = max(13, min(35, round(self.duration * 2.0)))
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
        kinds = ("SLASH", "PLASMA", "SLAM", "CRITICAL")
        self.attacks = []
        for index, event_time in enumerate(self.attack_times):
            player_attacks = index % 2 == 0
            if player_attacks:
                damage = raw_player[player_cursor] * player_scale
                player_cursor += 1
            else:
                damage = raw_boss[boss_cursor] * boss_scale
                boss_cursor += 1
            self.attacks.append({
                "time": event_time,
                "player": player_attacks,
                "damage": damage,
                "kind": kinds[(index + self.seed) % len(kinds)],
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

    def frame(self, time_sec: float) -> Image.Image:
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
