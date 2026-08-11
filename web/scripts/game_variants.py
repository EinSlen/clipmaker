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

# Shared vertical layout contract for TikTok and YouTube Shorts.  The hook
# centre leaves the top of the largest 2D title below the upper 8% overlay
# region; primary outcomes stay above the caption area and non-essential
# footers never sit below 88%.
SOCIAL_HOOK_CENTER_Y = 0.105
SOCIAL_RESULT_CENTER_Y = 0.805
SOCIAL_FOOTER_CENTER_Y = 0.880


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
        draw.line((self.width * 0.08, self.height * 0.082, self.width * 0.29, self.height * 0.082), fill=(*accent, 160), width=2)
        draw.line((self.width * 0.71, self.height * 0.082, self.width * 0.92, self.height * 0.082), fill=(*accent, 160), width=2)
        centered(draw, self.cx, self.height * 0.082, self.game_name, label_font, (*accent, 255))
        centered(draw, self.cx, self.height * SOCIAL_HOOK_CENTER_Y, self.title, title_font, (255, 255, 255, 255), 2)
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

    # Rendering can happen at any frame rate, but the game always advances on
    # this clock.  Four pixels is the largest displacement at the launch speed
    # on the 270 px test canvas, which keeps the thin wavy boundary robust.
    PHYSICS_HZ = 240

    def __init__(self, *args):
        super().__init__(*args)
        self.position = [self.cx, self.cy]
        launch_angle = self.rng.uniform(-math.pi, math.pi)
        launch_speed = self.width * self.rng.uniform(3.15, 3.75)
        self.velocity = [
            math.cos(launch_angle) * launch_speed,
            math.sin(launch_angle) * launch_speed,
        ]
        self.initial_speed = launch_speed
        self.ball_radius = self.width * 0.026
        self.gravity = self.height * self.rng.uniform(0.58, 0.82)
        self.restitution = self.rng.uniform(0.955, 0.985)
        self.tangent_retention = self.rng.uniform(0.985, 0.997)
        self.physics_step = 0
        self.physics_dt = 1.0 / self.PHYSICS_HZ
        self.contact_history: list[tuple[float, float, float, float, float, float, int, float]] = []
        self.trail: list[tuple[float, float]] = []
        self.last_impact = -10.0
        self.last_contact = [self.cx, self.cy]
        self.shape_phase = self.rng.uniform(0, math.tau)
        # Difficulty is a visual layer count (normally 30..300), not a demand
        # for hundreds of fake collisions.  A harder physical impact can crack
        # several adjacent layers, but every layer change still originates at
        # the measured contact below.
        expected_contacts = max(20.0, self.duration * 2.45)
        self.damage_scale = max(1.0, self.total / expected_contacts)
        # Reserve the final 0.8 s for an honest result hold.  Once this physical
        # deadline is reached, the simulation is frozen: the comet cannot break
        # another layer after "TIME'S UP!" has appeared on screen.
        self.gameplay_deadline = max(0.0, self.duration - 0.8)
        self.failed_at: float | None = None

    def contour_radius(self, progress: float, angle: float, layer: int = 0, time_sec: float = 0.0) -> float:
        """Radius of the exact contour used by both collision and drawing."""
        base = self.width * (0.155 + progress * 0.43) + layer * self.width * 0.0145
        wave = 1.0
        wave += 0.084 * math.sin(angle * 7 + self.shape_phase + layer * 0.012)
        wave += 0.032 * math.sin(angle * 3 - self.shape_phase * 0.7)
        wave += 0.013 * math.sin(angle * 13 + self.shape_phase * 1.8 + time_sec * 0.30)
        return base * wave

    def boundary_radius(self, progress: float, angle: float, time_sec: float = 0.0) -> float:
        return self.contour_radius(progress, angle, 0, time_sec)

    def boundary_gradient(self, progress: float, angle: float, radius: float, time_sec: float) -> tuple[float, float, float]:
        """Return the normalized outward gradient and its magnitude.

        The boundary is the implicit curve ``rho - R(theta) = 0``.  Its
        gradient is geometric rather than radial, so angled lobes genuinely
        redirect the comet instead of merely reversing its heading.
        """
        base = self.width * (0.155 + progress * 0.43)
        derivative = base * (
            0.084 * 7.0 * math.cos(angle * 7 + self.shape_phase)
            + 0.032 * 3.0 * math.cos(angle * 3 - self.shape_phase * 0.7)
            + 0.013 * 13.0 * math.cos(angle * 13 + self.shape_phase * 1.8 + time_sec * 0.30)
        )
        radial_x, radial_y = math.cos(angle), math.sin(angle)
        tangent_x, tangent_y = -radial_y, radial_x
        scale = derivative / max(1.0, radius)
        gradient_x = radial_x - scale * tangent_x
        gradient_y = radial_y - scale * tangent_y
        magnitude = max(1e-9, math.hypot(gradient_x, gradient_y))
        return gradient_x / magnitude, gradient_y / magnitude, magnitude

    def boundary_radial_speed(self, progress: float, angle: float, time_sec: float) -> float:
        base = self.width * (0.155 + progress * 0.43)
        return base * 0.013 * 0.30 * math.cos(
            angle * 13 + self.shape_phase * 1.8 + time_sec * 0.30
        )

    def _update_particles_fixed(self, dt: float):
        alive = []
        # Match the old 60 fps damping, now independent of output frame rate.
        damping = 0.982 ** (dt * 60.0)
        for particle in self.particles:
            particle["x"] = float(particle["x"]) + float(particle["vx"]) * dt
            particle["y"] = float(particle["y"]) + float(particle["vy"]) * dt
            particle["vx"] = float(particle["vx"]) * damping
            particle["vy"] = float(particle["vy"]) * damping + self.height * 0.06 * dt
            particle["life"] = float(particle["life"]) - dt
            if float(particle["life"]) > 0.0:
                alive.append(particle)
        self.particles = alive

    def _impact_damage(self, normal_speed: float) -> int:
        energy_ratio = clamp(normal_speed / max(1.0, self.width * 3.0), 0.45, 1.55)
        return max(1, round(self.damage_scale * energy_ratio))

    def _resolve_boundary_contact(self, time_sec: float):
        if self.active >= self.total:
            return
        progress_before = self.active / self.total
        offset_x = self.position[0] - self.cx
        offset_y = self.position[1] - self.cy
        radius = max(1e-9, math.hypot(offset_x, offset_y))
        angle = math.atan2(offset_y, offset_x)
        boundary = self.boundary_radius(progress_before, angle, time_sec)
        penetration = radius + self.ball_radius - boundary
        if penetration < 0.0:
            return

        normal_x, normal_y, gradient_magnitude = self.boundary_gradient(
            progress_before, angle, radius, time_sec
        )
        # Project back to the interior along the true implicit-curve normal.
        correction = penetration / gradient_magnitude + self.width * 0.00008
        self.position[0] -= normal_x * correction
        self.position[1] -= normal_y * correction

        radial_x, radial_y = math.cos(angle), math.sin(angle)
        wall_speed = self.boundary_radial_speed(progress_before, angle, time_sec)
        wall_velocity_x = radial_x * wall_speed
        wall_velocity_y = radial_y * wall_speed
        relative_x = self.velocity[0] - wall_velocity_x
        relative_y = self.velocity[1] - wall_velocity_y
        incoming_normal_speed = relative_x * normal_x + relative_y * normal_y
        if incoming_normal_speed <= self.width * 0.10:
            return

        tangent_x, tangent_y = -normal_y, normal_x
        tangent_speed = relative_x * tangent_x + relative_y * tangent_y
        outgoing_normal_speed = -incoming_normal_speed * self.restitution
        tangent_speed *= self.tangent_retention
        self.velocity[0] = (
            wall_velocity_x
            + normal_x * outgoing_normal_speed
            + tangent_x * tangent_speed
        )
        self.velocity[1] = (
            wall_velocity_y
            + normal_y * outgoing_normal_speed
            + tangent_y * tangent_speed
        )

        damage = min(self.total - self.active, self._impact_damage(incoming_normal_speed))
        self.active += damage
        contact_x = self.position[0] + normal_x * self.ball_radius
        contact_y = self.position[1] + normal_y * self.ball_radius
        self.last_contact = [contact_x, contact_y]
        self.last_impact = time_sec
        scale = (0, 2, 4, 7, 9)[len(self.contact_history) % 5]
        frequency = 220.0 * 2 ** (scale / 12)
        strength = clamp(0.20 + incoming_normal_speed / (self.width * 7.5), 0.24, 0.52)
        self.record_hit(time_sec, frequency, strength, "clear")
        impact_color = color_for(self.theme, self.active, self.total)
        self.burst(contact_x, contact_y, impact_color, 10 + min(14, damage))
        self.contact_history.append((
            time_sec,
            contact_x,
            contact_y,
            normal_x,
            normal_y,
            incoming_normal_speed,
            damage,
            progress_before,
        ))

        if self.active >= self.total and self.completed_at is None:
            self.completed_at = time_sec
            self.burst(*self.position, (255, 255, 255), 72)

    def _physics_tick(self, time_sec: float):
        dt = self.physics_dt
        self.velocity[1] += self.gravity * dt
        self.position[0] += self.velocity[0] * dt
        self.position[1] += self.velocity[1] * dt
        self._resolve_boundary_contact(time_sec)
        speed = math.hypot(*self.velocity)
        self.max_speed_ratio = max(self.max_speed_ratio, speed / max(1.0, self.initial_speed))
        self.gravity_g = self.gravity / max(1.0, self.height * 0.70)
        self._update_particles_fixed(dt)

        # Sample motion on its own 60 Hz clock; render FPS cannot reshape the
        # comet tail or influence any subsequent physics state.
        if self.physics_step % (self.PHYSICS_HZ // 60) == 0:
            self.trail.append(tuple(self.position))
            self.trail = self.trail[-12:]

    def update(self, time_sec: float):
        requested_time = max(0.0, time_sec)
        simulation_time = (
            requested_time
            if self.completed_at is not None
            else min(requested_time, self.gameplay_deadline)
        )
        target_step = max(0, math.floor(simulation_time * self.PHYSICS_HZ + 1e-9))
        while self.physics_step < target_step:
            self.physics_step += 1
            self._physics_tick(self.physics_step * self.physics_dt)
        if (
            self.completed_at is None
            and requested_time + 1e-9 >= self.gameplay_deadline
        ):
            self.failed_at = self.gameplay_deadline

    def outcome_lines(self) -> tuple[str, ...]:
        """Return the explicit, immutable result rendered into the video."""
        if self.completed_at is not None:
            return ("ESCAPED!",)
        if self.failed_at is not None:
            remaining = max(0, self.total - self.active)
            return ("TIME'S UP!", f"{remaining} LAYERS LEFT")
        return ()

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
        impact_pulse = clamp(1.0 - (time_sec - self.last_impact) * 5.8, 0.0, 1.0)
        impact_angle = math.atan2(self.last_contact[1] - self.cy, self.last_contact[0] - self.cx)
        for layer in range(visible - 1, -1, -1):
            index = self.active + round((layer + 1) / 58 * self.total)
            color = color_for(self.theme, index, self.total, time_sec * 0.018)
            points = []
            sides = 128
            for point in range(sides + 1):
                angle = math.tau * point / sides
                # A local pressure wave propagates through neighbouring contours
                # after contact. This tiny phase-delayed bulge is what makes the
                # tunnel feel elastic instead of a stack of static SVG paths.
                angular_distance = math.atan2(math.sin(angle - impact_angle), math.cos(angle - impact_angle))
                ripple_width = 0.20 + layer * 0.002
                ripple = math.exp(-((angular_distance / ripple_width) ** 2))
                ripple *= impact_pulse * math.sin((1.0 - impact_pulse) * 9.0 - layer * 0.22)
                radius = self.contour_radius(progress, angle, layer, time_sec)
                radius *= 1.0 + ripple * 0.024
                points.append((self.cx + math.cos(angle) * radius, self.cy + math.sin(angle) * radius))
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
        ball_radius = self.ball_radius
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
        title_y = self.height * SOCIAL_HOOK_CENTER_Y
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
        outcome_lines = self.outcome_lines()
        if outcome_lines:
            result_color = (
                (255, 255, 255, 255)
                if self.completed_at is not None
                else (255, 225, 142, 255)
            )
            centered(
                center_draw,
                self.cx,
                self.height * SOCIAL_RESULT_CENTER_Y,
                outcome_lines[0],
                font(round(self.width * 0.065), True),
                result_color,
                3,
            )
            if len(outcome_lines) > 1:
                centered(
                    center_draw,
                    self.cx,
                    self.height * 0.855,
                    outcome_lines[1],
                    font(round(self.width * 0.030), True),
                    (255, 255, 255, 235),
                    2,
                )
        if not outcome_lines:
            centered(
                center_draw,
                self.cx,
                self.height * SOCIAL_FOOTER_CENTER_Y,
                "ORIGINAL PHYSICS SIMULATION",
                font(max(8, round(self.width * 0.015)), True),
                (212, 220, 236, 190),
                1,
            )
        return image.convert("RGB")


class LaserDodge(BaseGame):
    """A reactive runner facing a laser field authored without knowledge of it.

    Laser geometry is generated first.  A fixed-step simulation then gives the
    runner only a short prediction horizon and bounded acceleration; no
    waypoint or requested outcome is ever fed back into the laser layout.
    """

    game_name = "LASER DODGE"
    unit_name = "LASERS"
    PHYSICS_HZ = 120
    CONTROL_HZ = 30

    def __init__(self, *args):
        super().__init__(*args)
        self.arena = (
            self.width * 0.075,
            self.height * 0.190,
            self.width * 0.925,
            self.height * 0.865,
        )
        self.runner_radius = max(7.0, self.width * 0.022)

        # World generation deliberately finishes before runner state exists.
        # Anchors favour the readable central arena, but never reference a
        # future position, controller decision, or desired success/failure.
        # One requested unit is one real, collidable beam.  Earlier versions
        # rendered roughly two dozen beams while scaling the HUD up to 240,
        # which made the score look impressive but semantically false.
        self.event_count = max(16, min(38, self.total))
        self.total = self.event_count
        start, finish = self.duration * 0.075, self.duration * 0.84
        nominal_gap = (finish - start) / max(1, self.event_count - 1)
        generated_times = []
        for index in range(self.event_count):
            progress = index / max(1, self.event_count - 1)
            authored = start + (finish - start) * progress ** 0.93
            if 0 < index < self.event_count - 1:
                authored += self.rng.uniform(-0.13, 0.13) * nominal_gap
            generated_times.append(authored)
        self.event_times = sorted(generated_times)
        self.lasers = []
        diagonal = math.hypot(self.arena[2] - self.arena[0], self.arena[3] - self.arena[1])
        for index, event_time in enumerate(self.event_times):
            angle = self.rng.uniform(0.0, math.pi)
            # Independent crossed pairs occasionally create genuine pressure;
            # they are laser-to-laser patterns, not traps fitted to the runner.
            if index and index % 6 == 5:
                angle = (float(self.lasers[-1]["angle"]) + self.rng.uniform(0.78, 1.20)) % math.pi
            center = (
                self.rng.uniform(self.arena[0] + self.width * 0.12, self.arena[2] - self.width * 0.12),
                self.rng.uniform(self.arena[1] + self.height * 0.13, self.arena[3] - self.height * 0.13),
            )
            self.lasers.append({
                "time": event_time,
                "angle": angle,
                "center": center,
                "speed": self.width * self.rng.uniform(0.20, 0.48),
                "direction": self.rng.choice((-1.0, 1.0)),
                "hue": index + self.seed % 19,
                "phase": self.rng.uniform(0.0, math.tau),
                "active_before": self.rng.uniform(0.065, 0.095),
                "active_after": self.rng.uniform(0.135, 0.195),
                "half_width": self.width * self.rng.uniform(0.0048, 0.0068),
                "half_length": diagonal * 0.72,
            })

        runner_rng = random.Random(self.seed ^ 0x4C415345)
        self.physics_dt = 1.0 / self.PHYSICS_HZ
        self.control_stride = self.PHYSICS_HZ // self.CONTROL_HZ
        self.reaction_horizon = 0.30
        self.max_speed = self.width * runner_rng.uniform(0.41, 0.47)
        self.max_acceleration = self.width * runner_rng.uniform(1.55, 1.85)
        self.drag_per_second = runner_rng.uniform(0.84, 0.90)
        self.wander_phase = runner_rng.uniform(0.0, math.tau)
        self.wander_phase_y = runner_rng.uniform(0.0, math.tau)
        self.initial_velocity = (
            self.width * runner_rng.uniform(-0.055, 0.055),
            self.height * runner_rng.uniform(-0.035, 0.035),
        )
        self.trajectory: list[tuple[float, float]] = []
        self.velocity_history: list[tuple[float, float]] = []
        self.acceleration_history: list[tuple[float, float]] = []
        self.laser_clearances = [float("inf")] * self.event_count
        self.laser_closest_times = list(self.event_times)
        self.simulated_collision_time: float | None = None
        self.simulated_collision_index: int | None = None
        self.simulated_crash_position: tuple[float, float] | None = None
        self._simulate_runner()

        # The displayed multiplier is derived from measured velocity, not
        # progress through the authored laser list.  A quarter of the runner's
        # physical speed limit is the stable 1x reference.
        speed_reference = max(1.0, self.max_speed * 0.25)
        running_ratio = 1.0
        self.speed_ratio_history: list[float] = []
        for velocity in self.velocity_history:
            running_ratio = max(running_ratio, math.hypot(*velocity) / speed_reference)
            self.speed_ratio_history.append(running_ratio)

        self.will_survive = self.simulated_collision_time is None
        self.position = list(self.trajectory[0])
        self.trail: list[tuple[float, float]] = []
        self.last_dodge = -10.0
        self.last_distance = self.width
        self.crashed = False
        self.crash_position: tuple[float, float] | None = None
        self.particle_clock = 0.0

    def _advance_particles(self, target_time: float) -> None:
        """Advance cosmetic debris on a fixed clock independent of render FPS."""
        target_time = max(self.particle_clock, min(self.duration, target_time))
        visual_dt = 1.0 / 120.0
        while self.particle_clock + 1e-9 < target_time:
            dt = min(visual_dt, target_time - self.particle_clock)
            damping = 0.982 ** (dt * 60.0)
            alive = []
            for particle in self.particles:
                particle["x"] = float(particle["x"]) + float(particle["vx"]) * dt
                particle["y"] = float(particle["y"]) + float(particle["vy"]) * dt
                particle["vx"] = float(particle["vx"]) * damping
                particle["vy"] = float(particle["vy"]) * damping + self.height * 0.06 * dt
                particle["life"] = float(particle["life"]) - dt
                if float(particle["life"]) > 0.0:
                    alive.append(particle)
            self.particles = alive
            self.particle_clock += dt

    @staticmethod
    def _limited(vector: tuple[float, float], limit: float) -> tuple[float, float]:
        magnitude = math.hypot(*vector)
        if magnitude <= limit or magnitude <= 1e-9:
            return vector
        scale = limit / magnitude
        return vector[0] * scale, vector[1] * scale

    @staticmethod
    def _point_segment_distance(
        point: tuple[float, float],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-9:
            return math.hypot(point[0] - start[0], point[1] - start[1])
        ratio = clamp(
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared,
            0.0,
            1.0,
        )
        closest = start[0] + dx * ratio, start[1] + dy * ratio
        return math.hypot(point[0] - closest[0], point[1] - closest[1])

    def position_at(self, time_sec: float) -> tuple[float, float]:
        sampled_time = clamp(time_sec, 0.0, self.duration)
        if self.simulated_collision_time is not None:
            sampled_time = min(sampled_time, self.simulated_collision_time)
        exact = sampled_time * self.PHYSICS_HZ
        lower = min(len(self.trajectory) - 1, max(0, int(math.floor(exact))))
        upper = min(len(self.trajectory) - 1, lower + 1)
        ratio = exact - lower
        return (
            lerp(self.trajectory[lower][0], self.trajectory[upper][0], ratio),
            lerp(self.trajectory[lower][1], self.trajectory[upper][1], ratio),
        )

    def velocity_at(self, time_sec: float) -> tuple[float, float]:
        sampled_time = clamp(time_sec, 0.0, self.duration)
        if self.simulated_collision_time is not None:
            sampled_time = min(sampled_time, self.simulated_collision_time)
        index = min(len(self.velocity_history) - 1, max(0, round(sampled_time * self.PHYSICS_HZ)))
        return self.velocity_history[index]

    def laser_line(self, laser, time_sec: float):
        tangent = (math.cos(float(laser["angle"])), math.sin(float(laser["angle"])))
        normal = (-tangent[1], tangent[0])
        travel = (time_sec - float(laser["time"])) * float(laser["speed"]) * float(laser["direction"])
        center = (float(laser["center"][0]) + normal[0] * travel, float(laser["center"][1]) + normal[1] * travel)
        return center, tangent, normal

    def laser_segment(self, laser, time_sec: float):
        center, tangent, normal = self.laser_line(laser, time_sec)
        half_length = float(laser["half_length"])
        return (
            (center[0] - tangent[0] * half_length, center[1] - tangent[1] * half_length),
            (center[0] + tangent[0] * half_length, center[1] + tangent[1] * half_length),
            normal,
        )

    def collision_distance(self, laser, point: tuple[float, float], time_sec: float) -> float:
        start, end, _ = self.laser_segment(laser, time_sec)
        return self._point_segment_distance(point, start, end)

    @staticmethod
    def laser_is_active(laser, time_sec: float) -> bool:
        return (
            float(laser["time"]) - float(laser["active_before"])
            <= time_sec
            <= float(laser["time"]) + float(laser["active_after"])
        )

    def _wander_target(self, time_sec: float) -> tuple[float, float]:
        return (
            self.cx + math.sin(time_sec * 0.73 + self.wander_phase) * self.width * 0.145,
            self.cy + math.sin(time_sec * 0.49 + self.wander_phase_y) * self.height * 0.105,
        )

    def _candidate_score(
        self,
        time_sec: float,
        position: tuple[float, float],
        velocity: tuple[float, float],
        acceleration: tuple[float, float],
        previous_acceleration: tuple[float, float],
    ) -> float:
        sample_dt = 0.055
        steps = max(1, round(self.reaction_horizon / sample_dt))
        px, py = position
        vx, vy = velocity
        minimum_clearance = self.width
        risk = 0.0
        boundary_penalty = 0.0
        drag = self.drag_per_second ** sample_dt
        x_low = self.arena[0] + self.runner_radius
        x_high = self.arena[2] - self.runner_radius
        y_low = self.arena[1] + self.runner_radius
        y_high = self.arena[3] - self.runner_radius
        for sample in range(1, steps + 1):
            future_time = time_sec + sample * sample_dt
            vx = (vx + acceleration[0] * sample_dt) * drag
            vy = (vy + acceleration[1] * sample_dt) * drag
            vx, vy = self._limited((vx, vy), self.max_speed)
            px += vx * sample_dt
            py += vy * sample_dt
            outside = max(x_low - px, px - x_high, y_low - py, py - y_high, 0.0)
            boundary_penalty += outside * outside * 90.0
            boundary_clearance = min(px - x_low, x_high - px, py - y_low, y_high - py)
            boundary_comfort = max(self.runner_radius * 1.7, self.width * 0.075)
            if boundary_clearance < boundary_comfort:
                risk += (boundary_comfort - boundary_clearance) ** 2 * 1.6
            for laser in self.lasers:
                if not self.laser_is_active(laser, future_time):
                    continue
                clearance = self.collision_distance(laser, (px, py), future_time)
                clearance -= self.runner_radius + float(laser["half_width"])
                minimum_clearance = min(minimum_clearance, clearance)
                comfort = self.runner_radius * 1.15
                if clearance < comfort:
                    risk += (comfort - clearance) ** 2 * (5.0 + sample * 0.35)
                if clearance <= 0.0:
                    risk += 160_000.0 + abs(clearance) * 12_000.0

        goal = self._wander_target(time_sec + self.reaction_horizon)
        goal_distance = math.hypot(px - goal[0], py - goal[1])
        acceleration_change = math.hypot(
            acceleration[0] - previous_acceleration[0],
            acceleration[1] - previous_acceleration[1],
        )
        # Once a beam is comfortably cleared, extra distance has no value.
        # Capping this reward stops the controller from discovering the arena
        # edges as a permanent, visually dull hiding place.
        useful_clearance = min(minimum_clearance, self.runner_radius * 2.1)
        return useful_clearance * 2.8 - risk - boundary_penalty - goal_distance * 0.10 - acceleration_change * 0.0012

    def _choose_acceleration(
        self,
        time_sec: float,
        position: tuple[float, float],
        velocity: tuple[float, float],
        previous_acceleration: tuple[float, float],
    ) -> tuple[float, float]:
        goal = self._wander_target(time_sec)
        desired_velocity = self._limited(
            ((goal[0] - position[0]) * 1.55, (goal[1] - position[1]) * 1.55),
            self.max_speed * 0.72,
        )
        base = self._limited(
            ((desired_velocity[0] - velocity[0]) * 4.4, (desired_velocity[1] - velocity[1]) * 4.4),
            self.max_acceleration,
        )
        candidates = [base, (0.0, 0.0), self._limited(previous_acceleration, self.max_acceleration)]
        for fraction in (0.58, 1.0):
            magnitude = self.max_acceleration * fraction
            for index in range(16):
                angle = math.tau * index / 16
                candidates.append((math.cos(angle) * magnitude, math.sin(angle) * magnitude))
        return max(
            candidates,
            key=lambda candidate: self._candidate_score(
                time_sec, position, velocity, candidate, previous_acceleration,
            ),
        )

    def _simulate_runner(self) -> None:
        x_low = self.arena[0] + self.runner_radius
        x_high = self.arena[2] - self.runner_radius
        y_low = self.arena[1] + self.runner_radius
        y_high = self.arena[3] - self.runner_radius
        position = (self.cx, self.cy)
        velocity = self._limited(self.initial_velocity, self.max_speed)
        acceleration = (0.0, 0.0)
        steps = max(1, math.ceil(self.duration * self.PHYSICS_HZ))
        drag = self.drag_per_second ** self.physics_dt
        self.trajectory = [position]
        self.velocity_history = [velocity]
        self.acceleration_history = [acceleration]

        for step in range(1, steps + 1):
            previous_time = (step - 1) * self.physics_dt
            if (step - 1) % self.control_stride == 0:
                acceleration = self._choose_acceleration(
                    previous_time, position, velocity, acceleration,
                )
                acceleration = self._limited(acceleration, self.max_acceleration)
            vx = (velocity[0] + acceleration[0] * self.physics_dt) * drag
            vy = (velocity[1] + acceleration[1] * self.physics_dt) * drag
            velocity = self._limited((vx, vy), self.max_speed)
            next_position = (
                position[0] + velocity[0] * self.physics_dt,
                position[1] + velocity[1] * self.physics_dt,
            )

            px, py = next_position
            if px < x_low or px > x_high:
                px = clamp(px, x_low, x_high)
                velocity = (-velocity[0] * 0.18, velocity[1])
            if py < y_low or py > y_high:
                py = clamp(py, y_low, y_high)
                velocity = (velocity[0], -velocity[1] * 0.18)
            next_position = (px, py)
            time_sec = min(self.duration, step * self.physics_dt)

            for index, laser in enumerate(self.lasers):
                if not self.laser_is_active(laser, time_sec):
                    continue
                distance = self.collision_distance(laser, next_position, time_sec)
                clearance = distance - self.runner_radius - float(laser["half_width"])
                if clearance < self.laser_clearances[index]:
                    self.laser_clearances[index] = clearance
                    self.laser_closest_times[index] = time_sec
                if clearance <= 0.0 and self.simulated_collision_time is None:
                    self.simulated_collision_time = time_sec
                    self.simulated_collision_index = index
                    self.simulated_crash_position = next_position

            position = next_position
            self.trajectory.append(position)
            self.velocity_history.append(velocity)
            self.acceleration_history.append(acceleration)
            if self.simulated_collision_time is not None:
                remaining = steps - step
                self.trajectory.extend([position] * remaining)
                self.velocity_history.extend([(0.0, 0.0)] * remaining)
                self.acceleration_history.extend([(0.0, 0.0)] * remaining)
                break

    def update(self, time_sec: float):
        time_sec = clamp(time_sec, 0.0, self.duration)
        collision_cutoff = self.simulated_collision_time
        resolved_until = time_sec if collision_cutoff is None else min(time_sec, collision_cutoff)
        while self.last_tick + 1 < self.event_count:
            index = self.last_tick + 1
            laser = self.lasers[index]
            resolved_at = float(laser["time"]) + float(laser["active_after"])
            if resolved_at >= resolved_until:
                break
            self._advance_particles(resolved_at)
            self.last_tick = index
            previous = self.active
            self.active = index + 1
            closest_time = self.laser_closest_times[index]
            contact = self.position_at(closest_time)
            clearance = self.laser_clearances[index]
            if not math.isfinite(clearance):
                clearance = self.collision_distance(laser, contact, closest_time)
                clearance -= self.runner_radius + float(laser["half_width"])
            self.last_distance = clearance + self.runner_radius + float(laser["half_width"])
            self.last_dodge = resolved_at
            frequency = 620.0 + (index % 8) * 58.0
            self.record_hit(resolved_at, frequency, 0.32 if clearance > self.width * 0.03 else 0.46, "clear")
            self.burst(*contact, color_for(self.theme, previous + index, self.total, 0.42), 7)

        if (
            not self.crashed
            and collision_cutoff is not None
            and time_sec >= collision_cutoff
            and self.simulated_crash_position is not None
        ):
            self._advance_particles(collision_cutoff)
            self.crashed = True
            self.crash_position = self.simulated_crash_position
            self.completed_at = collision_cutoff
            self.position = list(self.crash_position)
            if self.music_hits and collision_cutoff - self.music_hits[-1] < 0.065:
                # A decisive collision wins the debounce race against a clear
                # chime from the preceding beam; otherwise a real crash could
                # end with success audio purely because the events are close.
                self.music_hits[-1] = collision_cutoff
                self.events[-1] = (collision_cutoff, 92.0, 0.72, "impact")
            else:
                self.record_hit(collision_cutoff, 92.0, 0.72, "impact")
            self.burst(*self.crash_position, (255, 58, 92), 76)
        else:
            self.position = list(self.position_at(time_sec))

        final_resolve = max(
            float(laser["time"]) + float(laser["active_after"])
            for laser in self.lasers
        )
        if not self.crashed and time_sec >= final_resolve and self.completed_at is None:
            self._advance_particles(final_resolve)
            self.last_tick = self.event_count - 1
            self.active = self.total
            self.completed_at = final_resolve
            self.burst(*self.position, (255, 255, 255), 62)

        trail_time = collision_cutoff if self.crashed and collision_cutoff is not None else time_sec
        self.trail = [
            self.position_at(max(0.0, trail_time - (12 - index) * 0.031))
            for index in range(13)
        ]
        sampled_time = collision_cutoff if self.crashed and collision_cutoff is not None else time_sec
        speed_index = min(
            len(self.speed_ratio_history) - 1,
            max(0, round(sampled_time * self.PHYSICS_HZ)),
        )
        self.max_speed_ratio = self.speed_ratio_history[speed_index]
        self._advance_particles(time_sec)

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
            activation_start = float(laser["time"]) - float(laser["active_before"])
            activation_end = float(laser["time"]) + float(laser["active_after"])
            if time_sec < activation_start - 0.36 or time_sec > activation_end + 0.10:
                continue
            active_beam = self.laser_is_active(laser, time_sec)
            warning = time_sec < activation_start
            center, tangent, _ = self.laser_line(laser, time_sec)
            length = math.hypot(self.width, self.height)
            start = (center[0] - tangent[0] * length, center[1] - tangent[1] * length)
            end = (center[0] + tangent[0] * length, center[1] + tangent[1] * length)
            color = (255, 48 + index % 3 * 17, 91) if active_beam else (255, 177, 67)
            if warning:
                warning_progress = clamp(
                    (time_sec - (activation_start - 0.36)) / 0.36,
                    0.0,
                    1.0,
                )
                alpha = round(35 + 55 * warning_progress)
            elif active_beam:
                alpha = 255
            else:
                alpha = round(70 * clamp((activation_end + 0.10 - time_sec) / 0.10, 0.0, 1.0))
            bgd.line(
                (*start, *end),
                fill=(*color, min(150, alpha)),
                width=max(8, round(self.width * (0.029 if not active_beam else 0.047))),
            )
            bcd.line(
                (*start, *end),
                fill=(*color, alpha),
                width=max(2, round(self.width * (0.004 if not active_beam else 0.008))),
            )
            if active_beam:
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
        preview_velocity = (0.0, 0.0) if self.crashed else self.velocity_at(time_sec)
        for future_index, future_delta in enumerate((0.07, 0.14, 0.21), 1):
            # The small motion echoes extrapolate current inertia; they do not
            # reveal the controller's future decisions or draw a hidden path.
            fx = clamp(
                x + preview_velocity[0] * future_delta,
                self.arena[0] + self.runner_radius,
                self.arena[2] - self.runner_radius,
            )
            fy = clamp(
                y + preview_velocity[1] * future_delta,
                self.arena[1] + self.runner_radius,
                self.arena[3] - self.runner_radius,
            )
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
            self.height * SOCIAL_HOOK_CENTER_Y,
            hook,
            fitted_font(hook, round(self.width * 0.051), round(self.width * 0.030), round(self.width * 0.90), True),
            (255, 255, 255, 255),
            2,
        )
        centered(
            overlay,
            self.cx,
            self.height * 0.145,
            f"{self.active:03d} DODGED   |   {self.max_speed_ratio:.1f}X",
            font(max(10, round(self.width * 0.021)), True),
            (91, 226, 255, 235),
            1,
        )
        if pulse > 0.0 and not self.crashed and self.last_distance - self.runner_radius < self.width * 0.045:
            centered(
                overlay,
                self.cx,
                self.height * 0.176,
                "NEAR MISS +1",
                font(round(self.width * 0.027), True),
                (255, 208, 78, round(255 * pulse)),
                1,
            )
        if self.completed_at is not None:
            result = "LASER HIT!" if self.crashed else "FLAWLESS RUN!"
            color = (255, 76, 104, 255) if self.crashed else (105, 255, 211, 255)
            centered(
                overlay,
                self.cx,
                self.height * SOCIAL_RESULT_CENTER_Y,
                result,
                font(round(self.width * 0.055), True),
                color,
                2,
            )
        else:
            centered(
                overlay,
                self.cx,
                self.height * SOCIAL_FOOTER_CENTER_Y,
                "ONE TOUCH ENDS THE RUN",
                font(max(8, round(self.width * 0.017)), True),
                (180, 198, 225, 205),
                1,
            )
        return image.convert("RGB")


class BossBattle(BaseGame):
    """A deterministic rigid-body flail duel with energy-based damage.

    Nothing in this simulation reads an opponent position to steer a body or a
    weapon.  The two motors only apply torque around their own orb; every hit
    therefore comes from the seeded initial conditions, chain constraints and
    geometric collisions inside the arena.
    """

    game_name = "BOSS BATTLE"
    unit_name = "BOSS HP"
    PLAYER_CLASSES = ("THUNDER MACE", "PLASMA FLAIL", "VOID HAMMER")
    BOSS_CLASSES = ("WARDEN", "ION SENTINEL", "ABYSS CORE")
    PHYSICS_HZ = 240
    BOSS_DAMAGE_REFERENCE = 300.0

    def __init__(self, *args):
        super().__init__(*args)
        self.boss_max = float(self.total)
        self.boss_hp = self.boss_max
        self.player_max = 100.0
        self.player_hp = self.player_max
        self.player_class = self.PLAYER_CLASSES[self.seed % len(self.PLAYER_CLASSES)]
        self.boss_class = self.BOSS_CLASSES[(self.seed // 3) % len(self.BOSS_CLASSES)]

        left, top, right, bottom = self.arena_bounds()
        side = right - left
        phase = self.rng.uniform(-math.pi, math.pi)
        y_jitter = self.rng.uniform(-0.055, 0.055) * side
        speed = side * self.rng.uniform(0.24, 0.31)
        # The launch vectors are authored initial conditions, not feedback from
        # the rival's current position.  Once released, the bodies are free.
        self.player_body = {
            "position": [left + side * 0.285, top + side * 0.43 + y_jitter],
            "velocity": [speed, side * (0.08 + 0.055 * math.sin(phase))],
            "mass": 1.0,
            "radius": self.width * 0.058,
        }
        self.boss_body = {
            "position": [left + side * 0.715, top + side * 0.57 - y_jitter],
            "velocity": [-speed * self.rng.uniform(0.86, 1.10), -side * (0.07 + 0.06 * math.cos(phase))],
            "mass": 1.42,
            "radius": self.width * 0.086,
        }
        # Long reaches make contact possible across the square without moving
        # either fighter toward the other one. Whether the rotating masses
        # connect is still entirely decided by their phase and subsequent
        # collisions.
        player_chain = side * self.rng.uniform(0.285, 0.315)
        boss_chain = side * self.rng.uniform(0.275, 0.305)
        player_angle = phase * 0.23 - 1.02
        boss_angle = phase * 0.19 + math.pi + 0.94
        player_spin = side * self.rng.uniform(1.00, 1.19)
        boss_spin = -side * self.rng.uniform(0.95, 1.20)
        self.player_mace = self._make_mace(
            self.player_body,
            player_chain,
            self.width * 0.047,
            self.rng.uniform(0.58, 0.76),
            player_angle,
            player_spin,
        )
        self.boss_mace = self._make_mace(
            self.boss_body,
            boss_chain,
            self.width * 0.052,
            self.rng.uniform(0.66, 0.86),
            boss_angle,
            boss_spin,
        )
        self.player_motor_speed = player_spin * self.rng.uniform(0.91, 1.08)
        self.boss_motor_speed = boss_spin * self.rng.uniform(0.91, 1.08)
        self.player_motor_phase = self.rng.uniform(0.0, math.tau)
        self.boss_motor_phase = self.rng.uniform(0.0, math.tau)
        # The final 10% of a clip is an outcome hold, so the battle clock ends
        # here. A timeout winner is chosen only from physically remaining HP.
        self.battle_end = self.duration * 0.90
        self.physics_step = 0
        self.physics_dt = 1.0 / self.PHYSICS_HZ
        self.hit_history: list[dict[str, float | bool | str | tuple[float, float]]] = []
        self.last_hit_step = {"player": -10_000, "boss": -10_000}
        self.winner: str | None = None
        self.last_impact = -10.0
        self.last_damage = 0
        self.last_kind = "READY"
        self.last_attacker_player = True
        self.last_impact_position = (self.cx, self.cy)
        self.verdict_recorded = False
        self.music_outcome_at: float | None = None

    @staticmethod
    def _make_mace(owner, chain_length: float, radius: float, mass: float, angle: float, tangential_speed: float):
        radial = (math.cos(angle), math.sin(angle))
        tangent = (-radial[1], radial[0])
        return {
            "position": [
                owner["position"][0] + radial[0] * chain_length,
                owner["position"][1] + radial[1] * chain_length,
            ],
            "velocity": [
                owner["velocity"][0] + tangent[0] * tangential_speed,
                owner["velocity"][1] + tangent[1] * tangential_speed,
            ],
            "mass": mass,
            "radius": radius,
            "chain_length": chain_length,
        }

    @staticmethod
    def _dot(a, b) -> float:
        return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1])

    def _apply_motor(self, owner, mace, target_speed: float, phase: float, time_sec: float, dt: float):
        dx = float(mace["position"][0]) - float(owner["position"][0])
        dy = float(mace["position"][1]) - float(owner["position"][1])
        distance = max(1e-8, math.hypot(dx, dy))
        tangent = (-dy / distance, dx / distance)
        relative = (
            float(mace["velocity"][0]) - float(owner["velocity"][0]),
            float(mace["velocity"][1]) - float(owner["velocity"][1]),
        )
        current_speed = self._dot(relative, tangent)
        pulse = 0.84 + 0.16 * math.sin(time_sec * 1.73 + phase)
        desired = target_speed * pulse
        acceleration = clamp((desired - current_speed) * 8.0, -self.width * 9.5, self.width * 9.5)
        impulse = acceleration * dt
        mace["velocity"][0] += tangent[0] * impulse
        mace["velocity"][1] += tangent[1] * impulse
        recoil = float(mace["mass"]) / float(owner["mass"]) * 0.26
        owner["velocity"][0] -= tangent[0] * impulse * recoil
        owner["velocity"][1] -= tangent[1] * impulse * recoil

    def _constrain_chain(self, owner, mace):
        dx = float(mace["position"][0]) - float(owner["position"][0])
        dy = float(mace["position"][1]) - float(owner["position"][1])
        distance = max(1e-8, math.hypot(dx, dy))
        nx, ny = dx / distance, dy / distance
        inverse_owner = 1.0 / float(owner["mass"])
        inverse_mace = 1.0 / float(mace["mass"])
        inverse_total = inverse_owner + inverse_mace
        correction = (distance - float(mace["chain_length"])) / inverse_total
        owner["position"][0] += nx * correction * inverse_owner
        owner["position"][1] += ny * correction * inverse_owner
        mace["position"][0] -= nx * correction * inverse_mace
        mace["position"][1] -= ny * correction * inverse_mace

        radial_speed = (
            (float(mace["velocity"][0]) - float(owner["velocity"][0])) * nx
            + (float(mace["velocity"][1]) - float(owner["velocity"][1])) * ny
        )
        velocity_impulse = radial_speed / inverse_total
        owner["velocity"][0] += nx * velocity_impulse * inverse_owner
        owner["velocity"][1] += ny * velocity_impulse * inverse_owner
        mace["velocity"][0] -= nx * velocity_impulse * inverse_mace
        mace["velocity"][1] -= ny * velocity_impulse * inverse_mace

    def _confine(self, body, restitution: float):
        left, top, right, bottom = self.arena_bounds()
        radius = float(body["radius"])
        for axis, low, high in ((0, left + radius, right - radius), (1, top + radius, bottom - radius)):
            value = float(body["position"][axis])
            velocity = float(body["velocity"][axis])
            if value < low:
                body["position"][axis] = low
                if velocity < 0.0:
                    body["velocity"][axis] = -velocity * restitution
            elif value > high:
                body["position"][axis] = high
                if velocity > 0.0:
                    body["velocity"][axis] = -velocity * restitution

    def _resolve_pair(self, first, second, restitution: float) -> tuple[float, tuple[float, float]]:
        dx = float(second["position"][0]) - float(first["position"][0])
        dy = float(second["position"][1]) - float(first["position"][1])
        minimum = float(first["radius"]) + float(second["radius"])
        distance_squared = dx * dx + dy * dy
        if distance_squared >= minimum * minimum:
            return 0.0, (0.0, 0.0)
        if distance_squared <= 1e-12:
            nx, ny, distance = 1.0, 0.0, 0.0
        else:
            distance = math.sqrt(distance_squared)
            nx, ny = dx / distance, dy / distance
        inverse_first = 1.0 / float(first["mass"])
        inverse_second = 1.0 / float(second["mass"])
        inverse_total = inverse_first + inverse_second
        penetration = minimum - distance
        correction = penetration / inverse_total
        first["position"][0] -= nx * correction * inverse_first
        first["position"][1] -= ny * correction * inverse_first
        second["position"][0] += nx * correction * inverse_second
        second["position"][1] += ny * correction * inverse_second

        relative_x = float(second["velocity"][0]) - float(first["velocity"][0])
        relative_y = float(second["velocity"][1]) - float(first["velocity"][1])
        normal_speed = relative_x * nx + relative_y * ny
        if normal_speed >= 0.0:
            return 0.0, (
                (float(first["position"][0]) + float(second["position"][0])) * 0.5,
                (float(first["position"][1]) + float(second["position"][1])) * 0.5,
            )
        impulse = -(1.0 + restitution) * normal_speed / inverse_total
        first["velocity"][0] -= nx * impulse * inverse_first
        first["velocity"][1] -= ny * impulse * inverse_first
        second["velocity"][0] += nx * impulse * inverse_second
        second["velocity"][1] += ny * impulse * inverse_second
        reduced_mass = 1.0 / inverse_total
        energy = 0.5 * reduced_mass * normal_speed * normal_speed
        return energy, (
            float(first["position"][0]) + nx * float(first["radius"]),
            float(first["position"][1]) + ny * float(first["radius"]),
        )

    def _damage_from_impact(self, attacker: str, energy: float, position: tuple[float, float], time_sec: float):
        side = self.arena_bounds()[2] - self.arena_bounds()[0]
        energy_ratio = energy / max(1.0, side * side)
        # The threshold removes resting contacts. Above it, damage is a direct
        # monotonic function of measured normal kinetic energy.
        damage_fraction = clamp((energy_ratio - 0.004) * 1.08, 0.0, 0.31)
        if damage_fraction <= 0.0:
            return
        cooldown_steps = round(self.PHYSICS_HZ * 0.16)
        if self.physics_step - self.last_hit_step[attacker] < cooldown_steps:
            return
        self.last_hit_step[attacker] = self.physics_step
        player_attacks = attacker == "player"
        # Boss HP is a real difficulty setting.  Damage comes from measured
        # impact energy on a fixed reference scale; it must not grow in direct
        # proportion to the selected HP or 100/300/500 would be the exact same
        # fight with different numbers painted over it.
        damage_scale = self.BOSS_DAMAGE_REFERENCE if player_attacks else self.player_max
        damage = min(
            damage_scale * damage_fraction,
            self.boss_hp if player_attacks else self.player_hp,
        )
        if damage <= 0.0:
            return
        if player_attacks:
            self.boss_hp = max(0.0, self.boss_hp - damage)
            frequency = 475.0 + min(390.0, energy_ratio * 640.0)
        else:
            self.player_hp = max(0.0, self.player_hp - damage)
            frequency = 108.0 + min(190.0, energy_ratio * 300.0)
        kind = "CRITICAL" if damage_fraction >= 0.22 else ("SLAM" if damage_fraction >= 0.11 else "HIT")
        self.last_damage = max(1, round(damage))
        self.last_kind = kind
        self.last_attacker_player = player_attacks
        self.last_impact = time_sec
        self.last_impact_position = position
        self.hit_history.append({
            "time": time_sec,
            "player": player_attacks,
            "damage": damage,
            "energy": energy,
            "kind": kind,
            "position": position,
        })
        self.record_hit(time_sec, frequency, clamp(0.36 + energy_ratio, 0.36, 0.88), "impact")
        self.active = min(self.total, round(self.boss_max - self.boss_hp))
        if self.boss_hp <= 0.0 or self.player_hp <= 0.0:
            self.completed_at = time_sec
            if self.boss_hp <= 0.0 and self.player_hp <= 0.0:
                self.winner = "draw"
            else:
                self.winner = "player" if self.boss_hp <= 0.0 else "boss"
            self.active = min(self.total, round(self.boss_max - self.boss_hp))
            self._record_verdict(time_sec)

    def _record_verdict(self, time_sec: float):
        """Emit one non-collision cue at the instant the battle is decided."""
        if self.verdict_recorded or self.winner is None:
            return
        self.verdict_recorded = True
        verdict_time = clamp(time_sec, 0.0, self.duration)
        self.music_outcome_at = verdict_time
        frequency = 620.0
        if self.winner == "player":
            frequency = 740.0
        elif self.winner == "boss":
            frequency = 510.0
        self.events.append((verdict_time, frequency, 0.72, "victory"))

    def _physics_substep(self):
        dt = self.physics_dt
        time_sec = self.physics_step * dt
        side = self.arena_bounds()[2] - self.arena_bounds()[0]
        self._apply_motor(
            self.player_body,
            self.player_mace,
            self.player_motor_speed,
            self.player_motor_phase,
            time_sec,
            dt,
        )
        self._apply_motor(
            self.boss_body,
            self.boss_mace,
            self.boss_motor_speed,
            self.boss_motor_phase,
            time_sec,
            dt,
        )

        # Uniform gravity and tiny seeded arena gusts are environmental forces;
        # neither depends on the other combatant's position or velocity.
        gravity = side * 0.22
        for index, body in enumerate((self.player_body, self.boss_body, self.player_mace, self.boss_mace)):
            phase = self.player_motor_phase if index % 2 == 0 else self.boss_motor_phase
            gust_x = math.sin(time_sec * (0.79 + index * 0.07) + phase) * side * 0.020
            body["velocity"][0] += gust_x * dt
            body["velocity"][1] += gravity * dt
            retention = 0.9975 ** dt
            body["velocity"][0] *= retention
            body["velocity"][1] *= retention
            body["position"][0] += body["velocity"][0] * dt
            body["position"][1] += body["velocity"][1] * dt

        for _ in range(3):
            self._constrain_chain(self.player_body, self.player_mace)
            self._constrain_chain(self.boss_body, self.boss_mace)
            self._confine(self.player_body, 0.88)
            self._confine(self.boss_body, 0.86)
            self._confine(self.player_mace, 0.91)
            self._confine(self.boss_mace, 0.90)
        self._resolve_pair(self.player_body, self.boss_body, 0.82)
        self._resolve_pair(self.player_mace, self.boss_mace, 0.88)
        player_energy, player_contact = self._resolve_pair(self.boss_body, self.player_mace, 0.84)
        boss_energy, boss_contact = self._resolve_pair(self.player_body, self.boss_mace, 0.84)
        if self.completed_at is None:
            self._damage_from_impact("player", player_energy, player_contact, time_sec)
            self._damage_from_impact("boss", boss_energy, boss_contact, time_sec)
        self._constrain_chain(self.player_body, self.player_mace)
        self._constrain_chain(self.boss_body, self.boss_mace)
        self.physics_step += 1

    def _finish_timeout(self):
        if self.completed_at is not None:
            return
        self.completed_at = self.battle_end
        player_ratio = self.player_hp / self.player_max
        boss_ratio = self.boss_hp / self.boss_max
        if abs(player_ratio - boss_ratio) <= 1e-9:
            self.winner = "draw"
        else:
            self.winner = "player" if player_ratio > boss_ratio else "boss"
        self.active = min(self.total, round(self.boss_max - self.boss_hp))
        self._record_verdict(self.battle_end)

    def update(self, time_sec: float):
        target_step = max(self.physics_step, math.floor(max(0.0, time_sec) * self.PHYSICS_HZ + 1e-9))
        battle_step = round(self.battle_end * self.PHYSICS_HZ)
        while self.physics_step < target_step:
            if self.completed_at is None and self.physics_step >= battle_step:
                self._finish_timeout()
            self._physics_substep()
        if self.completed_at is None and time_sec >= self.battle_end:
            self._finish_timeout()
        self.active = min(self.total, round(self.boss_max - self.boss_hp))
        speeds = [
            math.hypot(float(body["velocity"][0]), float(body["velocity"][1]))
            for body in (self.player_body, self.boss_body, self.player_mace, self.boss_mace)
        ]
        self.max_speed_ratio = max(1.0, max(speeds) / max(1.0, self.width * 0.72))

    def attack_phase(self, time_sec: float):
        if not self.hit_history:
            return None, 0.0
        impact = min(self.hit_history, key=lambda item: abs(float(item["time"]) - time_sec))
        return impact, time_sec - float(impact["time"])

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

    def arena_bounds(self) -> tuple[float, float, float, float]:
        side = self.width * 0.92
        left = self.cx - side * 0.5
        top = self.height * 0.205
        return left, top, left + side, top + side

    def fighter_positions(self, time_sec: float, attack, delta: float) -> tuple[list[float], list[float]]:
        """Return simulated positions; render time never alters a trajectory."""
        return list(self.player_body["position"]), list(self.boss_body["position"])

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
        mass_position: tuple[float, float],
        mace_radius: float,
        color: tuple[int, int, int],
    ) -> tuple[float, float]:
        mace_x, mace_y = mass_position
        angle = math.atan2(mace_y - origin[1], mace_x - origin[0])
        glow_draw.line((*origin, mace_x, mace_y), fill=(*color, 135), width=max(9, round(core_radius * 0.58)))
        draw.line((*origin, mace_x, mace_y), fill=(1, 7, 9, 255), width=max(4, round(core_radius * 0.28)))
        draw.line((*origin, mace_x, mace_y), fill=(*color, 245), width=max(2, round(core_radius * 0.095)))
        chain_count = 7
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

        player_position, boss_position = self.fighter_positions(time_sec, None, 0.0)
        player_mace_position = list(self.player_mace["position"])
        boss_mace_position = list(self.boss_mace["position"])
        impact_pulse = clamp(1.0 - (time_sec - self.last_impact) * 5.2, 0.0, 1.0)
        shake = impact_pulse * self.width * (0.012 if self.last_kind == "CRITICAL" else 0.007)
        shake_x = math.sin(time_sec * 97.0 + self.seed) * shake
        shake_y = math.cos(time_sec * 83.0 + self.seed) * shake
        for position in (player_position, boss_position, player_mace_position, boss_mace_position):
            position[0] += shake_x
            position[1] += shake_y

        player_radius = float(self.player_body["radius"])
        boss_radius = float(self.boss_body["radius"])
        spin = time_sec * (3.4 + min(2.8, self.max_speed_ratio * 0.31)) + self.seed * 0.013

        # Motion streaks are derived from current physical velocities. They do
        # not predict, select or pull toward a future contact.
        for mace, position, color in (
            (self.player_mace, player_mace_position, player_color),
            (self.boss_mace, boss_mace_position, boss_color),
        ):
            vx, vy = float(mace["velocity"][0]), float(mace["velocity"][1])
            speed_ratio = clamp(math.hypot(vx, vy) / max(1.0, side * 1.25), 0.0, 1.0)
            for streak in range(3, 0, -1):
                trail = 0.025 * streak
                alpha = round((34 + 28 * streak) * speed_ratio)
                width = max(2, round(self.width * (0.004 + streak * 0.003)))
                gd.line(
                    (position[0] - vx * trail, position[1] - vy * trail, position[0], position[1]),
                    fill=(*color, alpha),
                    width=width,
                )

        self.draw_mace(
            draw,
            gd,
            tuple(player_position),
            player_radius,
            tuple(player_mace_position),
            float(self.player_mace["radius"]),
            player_color,
        )
        self.draw_mace(
            draw,
            gd,
            tuple(boss_position),
            boss_radius,
            tuple(boss_mace_position),
            float(self.boss_mace["radius"]),
            boss_color,
        )

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
            defender = (
                self.last_impact_position[0] + shake_x,
                self.last_impact_position[1] + shake_y,
            )
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
                debris_angle = debris_index * 2.399 + len(self.hit_history) * 0.71
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
            self.height * SOCIAL_HOOK_CENTER_Y,
            hook,
            fitted_font(hook, round(self.width * 0.047), round(self.width * 0.027), round(self.width * 0.91), True),
            (246, 255, 252, 255),
            2,
        )
        bar_y = self.height * 0.160
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
            defender = (
                self.last_impact_position[0] + shake_x,
                self.last_impact_position[1] + shake_y,
            )
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
            if self.winner == "draw":
                result = "PHYSICS DRAW!"
                result_color = (255, 232, 150)
            elif self.winner == "player":
                result = f"{self.player_class} WINS!"
                result_color = player_color
            else:
                result = f"{self.boss_class} WINS!"
                result_color = boss_color
            centered(
                overlay,
                self.cx,
                self.height * SOCIAL_RESULT_CENTER_Y,
                result,
                fitted_font(result, round(self.width * 0.054), round(self.width * 0.032), round(self.width * 0.88), True),
                (*result_color, 255),
                3,
            )
        else:
            centered(
                overlay,
                self.cx,
                self.height * SOCIAL_FOOTER_CENTER_Y,
                "NO AIM ASSIST  |  IMPACT ENERGY = DAMAGE",
                fitted_font(
                    "NO AIM ASSIST  |  IMPACT ENERGY = DAMAGE",
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
