"""Deterministic visual and physics variants for Soft Body Slide.

The module intentionally contains no Blender dependency so the web renderer,
Blender scene and fast unit tests all resolve a seed to the exact same variant.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random


Color = tuple[float, float, float]
PHYSICS_HZ = 240
AIR_RETENTION_PER_SECOND = 0.992


def deformation_response(softness: float) -> tuple[float, float, float]:
    """Map a percentage to centreline, pressure and broad-buckling response.

    Buckling intentionally starts after the 25% stage: the reference keeps 0%
    rigid and 25% merely compliant, shows a clear bend at 50%, then reserves
    the recognisable multi-fold gel silhouette for 75/100%.
    """

    value = max(0.0, min(1.0, float(softness)))
    visible = value ** 0.92 * (0.97 - 0.05 * value)
    pressure = value ** 1.65
    buckling = max(0.0, (value - 0.32) / 0.68) ** 1.15
    return visible, pressure, buckling


def solver_timing(fps: int, softness: float) -> tuple[int, float, float, float]:
    """Return a render-FPS-independent clock and physical damping factors.

    ``internal_damping`` is only for velocity relative to the body's centre of
    mass.  ``air_drag`` acts on the centre of mass and intentionally retains
    almost all momentum during a ballistic flight.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    substeps = max(1, round(PHYSICS_HZ / fps))
    actual_hz = fps * substeps
    dt = 1.0 / actual_hz
    internal_retention_per_second = 0.70 - softness * 0.18
    internal_damping = internal_retention_per_second ** dt
    air_drag = AIR_RETENTION_PER_SECOND ** dt
    return substeps, dt, internal_damping, air_drag


def supported_body_damping(fps: int, softness: float) -> tuple[float, float]:
    """Return strong per-step damping while the body is still ramp-supported."""

    if fps <= 0:
        raise ValueError("fps must be positive")
    substeps = max(1, round(PHYSICS_HZ / fps))
    actual_hz = fps * substeps
    horizontal = 0.910 ** (60.0 / actual_hz)
    vertical = (0.993 - softness * 0.005) ** (60.0 / actual_hz)
    return horizontal, vertical


@dataclass(frozen=True)
class ShapePreset:
    key: str
    label: str
    radius: float
    cylinder_half: float
    groove: float
    bulge: float


@dataclass(frozen=True)
class RampPreset:
    key: str
    label: str
    minimum: float
    maximum: float
    base: float
    slope: float
    wave: float
    wave_frequency: float
    wave_phase: float
    lip_width: float
    lip_rise: float
    half_width: float
    thickness: float
    sweep_amplitude: float
    sweep_period: float
    secondary_amplitude: float
    exit_time: float
    exit_x: float


@dataclass(frozen=True)
class PalettePreset:
    key: str
    label: str
    metal: Color
    metal_roughness: float
    marble_base: Color
    marble_vein: Color
    marble_light: Color
    background_low: Color
    background_high: Color
    key_light: Color
    fill_light: Color


@dataclass(frozen=True)
class ReceiverPreset:
    key: str
    label: str
    x: float
    outer_radius: float
    inner_radius: float
    top: float
    bowl_depth: float


@dataclass(frozen=True)
class StageMotion:
    """Tiny seeded imperfections that keep repeated trials from looking cloned.

    The ranges are deliberately much smaller than the capsule radius.  Softness
    remains the meaningful variable within a comparison; the render seed owns
    the large scene differences.
    """

    spawn_x_offset: float
    spawn_height_offset: float
    rotation_offset: float
    linear_velocity_x: float
    linear_velocity_y: float
    angular_velocity: float
    ramp_phase_offset: float


@dataclass(frozen=True)
class SoftBodyVariant:
    key: str
    label: str
    stages: tuple[int, int, int, int, int]
    stage_key: str
    shape: ShapePreset
    ramp: RampPreset
    palette: PalettePreset
    receiver: ReceiverPreset
    start_x: float
    start_height: float
    start_rotation: float
    initial_spin: float
    gravity_scale: float
    bounce_scale: float
    coupling_scale: float
    motion_phase: float
    wrinkle_phase: float
    motion_seed: int


SHAPES = (
    # Preserve each preset's overall length while moving the silhouette toward
    # the reference's 3.8-4.3:1 capsule ratio. A slender body reads as one rod
    # even when 100% folds, rather than as three fused spheres.
    ShapePreset("classic-pill", "Classic pill", 0.228, 0.637, 0.12, 0.00),
    ShapePreset("slender-cylinder", "Slender cylinder", 0.225, 0.730, 0.08, 0.015),
    ShapePreset("plush-capsule", "Plush capsule", 0.230, 0.645, 0.045, 0.055),
    ShapePreset("rounded-barrel", "Rounded barrel", 0.228, 0.637, 0.13, 0.085),
    ShapePreset("rolled-gel", "Rolled gel", 0.234, 0.656, 0.065, -0.025),
)


RAMPS = (
    RampPreset("classic-lip", "Classic lip", -2.85, 2.95, 3.68, 0.13, 0.07, 0.78, -0.30, 0.58, 0.76, 0.68, 0.24, 1.00, 2.00, 0.03, 1.55, -6.0),
    RampPreset("double-wave", "Double wave", -3.05, 3.05, 3.64, 0.09, 0.22, 1.08, 0.25, 0.70, 0.62, 0.64, 0.22, 1.10, 1.90, 0.04, 1.60, -6.2),
    RampPreset("scoop-launch", "Scoop launch", -2.72, 3.18, 3.57, 0.17, 0.17, 0.72, -1.10, 0.48, 0.94, 0.72, 0.26, 1.15, 1.90, 0.03, 1.65, -6.3),
    RampPreset("roller-wave", "Roller wave", -3.18, 2.82, 3.70, 0.07, 0.27, 1.26, 0.70, 0.76, 0.56, 0.61, 0.20, 1.80, 2.00, 0.08, 1.48, -5.8),
    RampPreset("long-glide", "Long glide", -3.30, 3.24, 3.75, 0.055, 0.11, 0.55, -0.55, 0.64, 0.82, 0.70, 0.23, 1.75, 1.95, 0.05, 1.72, -6.5),
)


PALETTES = (
    PalettePreset("champagne", "Champagne studio", (0.78, 0.52, 0.16), 0.145, (0.90, 0.89, 0.85), (0.34, 0.37, 0.40), (0.97, 0.96, 0.91), (0.20, 0.27, 0.36), (0.50, 0.58, 0.67), (1.0, 0.92, 0.80), (0.74, 0.84, 1.0)),
    PalettePreset("rose-gold", "Rose gold studio", (0.76, 0.34, 0.22), 0.16, (0.91, 0.85, 0.82), (0.43, 0.34, 0.35), (0.98, 0.93, 0.90), (0.25, 0.20, 0.28), (0.58, 0.45, 0.52), (1.0, 0.78, 0.70), (0.78, 0.82, 1.0)),
    PalettePreset("platinum", "Platinum studio", (0.58, 0.67, 0.76), 0.12, (0.86, 0.89, 0.91), (0.28, 0.36, 0.43), (0.96, 0.98, 1.0), (0.16, 0.23, 0.30), (0.43, 0.55, 0.66), (0.82, 0.91, 1.0), (0.68, 0.82, 1.0)),
    PalettePreset("copper", "Copper studio", (0.70, 0.29, 0.075), 0.18, (0.90, 0.85, 0.76), (0.40, 0.31, 0.25), (0.98, 0.94, 0.84), (0.25, 0.22, 0.19), (0.58, 0.50, 0.42), (1.0, 0.79, 0.58), (0.78, 0.88, 0.98)),
    PalettePreset("pale-gold", "Pale gold studio", (0.86, 0.67, 0.25), 0.13, (0.88, 0.90, 0.84), (0.31, 0.39, 0.34), (0.97, 0.98, 0.92), (0.18, 0.28, 0.27), (0.46, 0.61, 0.56), (1.0, 0.94, 0.72), (0.72, 0.92, 0.92)),
)


RECEIVERS = (
    ReceiverPreset("classic-cup", "Classic cup", -0.65, 1.17, 1.05, 0.76, 0.46),
    ReceiverPreset("narrow-cup", "Narrow cup", -0.72, 1.04, 0.92, 0.72, 0.56),
    ReceiverPreset("wide-bowl", "Wide bowl", -0.58, 1.34, 1.21, 0.82, 0.35),
    ReceiverPreset("deep-pedestal", "Deep pedestal", -0.65, 1.13, 1.00, 0.90, 0.66),
)


STAGE_PRESETS = (
    ("classic", (0, 25, 50, 75, 100)),
    ("fine-middle", (0, 15, 45, 75, 100)),
    ("smooth-rise", (0, 20, 40, 70, 100)),
    ("late-extreme", (0, 30, 55, 85, 100)),
    ("wide-contrast", (0, 10, 35, 65, 100)),
)


def stage_motion_for(variant: SoftBodyVariant, stage_index: int) -> StageMotion:
    """Resolve neutral, deterministic micro-variation for one comparison stage."""

    index = max(0, int(stage_index))
    mixed_seed = (variant.motion_seed ^ ((index + 1) * 0x9E3779B1)) & 0xFFFFFFFF
    rng = random.Random(mixed_seed)
    return StageMotion(
        spawn_x_offset=rng.uniform(-0.045, 0.045),
        spawn_height_offset=rng.uniform(-0.018, 0.018),
        rotation_offset=rng.uniform(-0.030, 0.030),
        linear_velocity_x=rng.uniform(-0.028, 0.028),
        linear_velocity_y=rng.uniform(-0.010, 0.010),
        angular_velocity=rng.uniform(-0.045, 0.045),
        ramp_phase_offset=rng.uniform(-0.012, 0.012),
    )


def ramp_sweep_state(
    time: float,
    variant: SoftBodyVariant,
    phase_offset: float = 0.0,
) -> tuple[float, float]:
    """Return the unforced sinusoidal ramp position and velocity."""

    ramp = variant.ramp
    period = ramp.sweep_period
    phase = variant.motion_phase + phase_offset
    primary_angle = math.tau * time / period - math.pi / 2 + phase
    secondary_angle = math.tau * time / (period * 0.5) - 0.18 - phase * 0.5
    position = (
        ramp.sweep_amplitude * math.sin(primary_angle)
        + ramp.secondary_amplitude * math.sin(secondary_angle)
    )
    velocity = (
        ramp.sweep_amplitude * math.tau / period * math.cos(primary_angle)
        + ramp.secondary_amplitude * math.tau / (period * 0.5) * math.cos(secondary_angle)
    )
    return position, velocity


def natural_ramp_exit_time(
    variant: SoftBodyVariant,
    trial_duration: float,
    phase_offset: float = 0.0,
) -> float:
    """Preserve the authored release window without choosing a target side."""

    landing_window = max(1.72, 3.0 - variant.ramp.exit_time)
    return max(0.8, trial_duration - landing_window)


def ramp_motion_state(
    time: float,
    variant: SoftBodyVariant,
    trial_duration: float,
    phase_offset: float = 0.0,
) -> tuple[float, float]:
    """Return a C1 ramp path that coasts off-screen with inherited velocity."""

    exit_time = natural_ramp_exit_time(variant, trial_duration, phase_offset)
    if time <= exit_time:
        return ramp_sweep_state(time, variant, phase_offset)
    origin, exit_velocity = ramp_sweep_state(exit_time, variant, phase_offset)
    elapsed = time - exit_time
    return origin + exit_velocity * elapsed, exit_velocity


def variant_for_seed(seed: int) -> SoftBodyVariant:
    """Return a stable cross-product variant; adjacent seeds change every axis."""

    positive = abs(int(seed))
    shape = SHAPES[positive % len(SHAPES)]
    ramp = RAMPS[(positive * 3 + positive // 5 + 1) % len(RAMPS)]
    palette = PALETTES[(positive * 7 + positive // 11 + 2) % len(PALETTES)]
    receiver = RECEIVERS[(positive * 5 + positive // 7 + 1) % len(RECEIVERS)]
    stage_key, stages = STAGE_PRESETS[(positive * 11 + positive // 13 + 3) % len(STAGE_PRESETS)]
    rng = random.Random(positive ^ 0x5F7B0D17)
    start_x = 0.30 + rng.uniform(-0.34, 0.34)
    start_height = 6.48 + rng.uniform(-0.20, 0.28)
    start_rotation = rng.uniform(-0.24, 0.18)
    gravity_scale = rng.uniform(0.92, 1.10)
    bounce_scale = rng.uniform(0.90, 1.12)
    coupling_scale = rng.uniform(0.88, 1.16)
    motion_phase = rng.uniform(-0.16, 0.16)
    wrinkle_phase = rng.uniform(0.0, 6.283185307179586)
    # Give each *render* one shared, deterministic release attitude.  A tiny
    # non-zero tilt and spin make the first support contact arrive at one end
    # of the capsule, allowing genuinely soft stages to crumple while every
    # stage still receives the same fair initial condition.  This seed-level
    # motion is deliberately unrelated to the receiver position.
    release_rng = random.Random(positive ^ 0xA31C5E7B)
    minimum_tilt = release_rng.uniform(0.10, 0.15)
    if abs(start_rotation) < minimum_tilt:
        fallback_sign = -1.0 if release_rng.random() < 0.5 else 1.0
        start_rotation = math.copysign(
            minimum_tilt,
            start_rotation if abs(start_rotation) > 1e-9 else fallback_sign,
        )
    initial_spin = math.copysign(release_rng.uniform(0.20, 0.34), start_rotation)
    key = f"{shape.key}--{ramp.key}--{palette.key}--{receiver.key}--{stage_key}"
    label = f"{shape.label} · {ramp.label} · {palette.label}"
    return SoftBodyVariant(
        key=key,
        label=label,
        stages=stages,
        stage_key=stage_key,
        shape=shape,
        ramp=ramp,
        palette=palette,
        receiver=receiver,
        start_x=start_x,
        start_height=start_height,
        start_rotation=start_rotation,
        initial_spin=initial_spin,
        gravity_scale=gravity_scale,
        bounce_scale=bounce_scale,
        coupling_scale=coupling_scale,
        motion_phase=motion_phase,
        wrinkle_phase=wrinkle_phase,
        motion_seed=positive ^ 0x5F7B0D17,
    )


def variant_summary(variant: SoftBodyVariant) -> dict[str, object]:
    return {
        "variant_key": variant.key,
        "variant_label": variant.label,
        "variant_shape": variant.shape.key,
        "variant_ramp": variant.ramp.key,
        "variant_palette": variant.palette.key,
        "variant_receiver": variant.receiver.key,
        "stage_preset": variant.stage_key,
        "softness_stages": list(variant.stages),
    }
