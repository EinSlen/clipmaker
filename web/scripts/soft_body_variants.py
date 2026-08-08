"""Deterministic visual and physics variants for Soft Body Slide.

The module intentionally contains no Blender dependency so the web renderer,
Blender scene and fast unit tests all resolve a seed to the exact same variant.
"""

from __future__ import annotations

from dataclasses import dataclass
import random


Color = tuple[float, float, float]


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
    gravity_scale: float
    bounce_scale: float
    coupling_scale: float
    motion_phase: float
    wrinkle_phase: float


SHAPES = (
    ShapePreset("classic-pill", "Classic pill", 0.37, 0.66, 0.15, 0.00),
    ShapePreset("slender-cylinder", "Slender cylinder", 0.30, 0.84, 0.10, 0.02),
    ShapePreset("plush-capsule", "Plush capsule", 0.43, 0.50, 0.055, 0.08),
    ShapePreset("rounded-barrel", "Rounded barrel", 0.39, 0.58, 0.18, 0.14),
    ShapePreset("rolled-gel", "Rolled gel", 0.35, 0.73, 0.08, -0.045),
)


RAMPS = (
    RampPreset("classic-lip", "Classic lip", -2.85, 2.95, 3.68, 0.13, 0.07, 0.78, -0.30, 0.58, 0.76, 0.68, 0.24, 3.08, 1.60, 0.14, 1.55, -6.0),
    RampPreset("double-wave", "Double wave", -3.05, 3.05, 3.64, 0.09, 0.22, 1.08, 0.25, 0.70, 0.62, 0.64, 0.22, 2.82, 1.48, 0.20, 1.60, -6.2),
    RampPreset("scoop-launch", "Scoop launch", -2.72, 3.18, 3.57, 0.17, 0.17, 0.72, -1.10, 0.48, 0.94, 0.72, 0.26, 3.24, 1.82, 0.10, 1.65, -6.3),
    RampPreset("roller-wave", "Roller wave", -3.18, 2.82, 3.70, 0.07, 0.27, 1.26, 0.70, 0.76, 0.56, 0.61, 0.20, 2.74, 1.40, 0.24, 1.48, -5.8),
    RampPreset("long-glide", "Long glide", -3.30, 3.24, 3.75, 0.055, 0.11, 0.55, -0.55, 0.64, 0.82, 0.70, 0.23, 3.12, 1.92, 0.08, 1.72, -6.5),
)


PALETTES = (
    PalettePreset("champagne", "Champagne studio", (0.78, 0.52, 0.16), 0.145, (0.90, 0.89, 0.85), (0.34, 0.37, 0.40), (0.97, 0.96, 0.91), (0.20, 0.27, 0.36), (0.50, 0.58, 0.67), (1.0, 0.92, 0.80), (0.74, 0.84, 1.0)),
    PalettePreset("rose-gold", "Rose gold studio", (0.76, 0.34, 0.22), 0.16, (0.91, 0.85, 0.82), (0.43, 0.34, 0.35), (0.98, 0.93, 0.90), (0.25, 0.20, 0.28), (0.58, 0.45, 0.52), (1.0, 0.78, 0.70), (0.78, 0.82, 1.0)),
    PalettePreset("platinum", "Platinum studio", (0.58, 0.67, 0.76), 0.12, (0.86, 0.89, 0.91), (0.28, 0.36, 0.43), (0.96, 0.98, 1.0), (0.16, 0.23, 0.30), (0.43, 0.55, 0.66), (0.82, 0.91, 1.0), (0.68, 0.82, 1.0)),
    PalettePreset("copper", "Copper studio", (0.70, 0.29, 0.075), 0.18, (0.90, 0.85, 0.76), (0.40, 0.31, 0.25), (0.98, 0.94, 0.84), (0.25, 0.22, 0.19), (0.58, 0.50, 0.42), (1.0, 0.79, 0.58), (0.78, 0.88, 0.98)),
    PalettePreset("pale-gold", "Pale gold studio", (0.86, 0.67, 0.25), 0.13, (0.88, 0.90, 0.84), (0.31, 0.39, 0.34), (0.97, 0.98, 0.92), (0.18, 0.28, 0.27), (0.46, 0.61, 0.56), (1.0, 0.94, 0.72), (0.72, 0.92, 0.92)),
)


RECEIVERS = (
    ReceiverPreset("classic-cup", "Classic cup", 0.0, 1.17, 1.05, 0.76, 0.46),
    ReceiverPreset("narrow-cup", "Narrow cup", -0.24, 1.04, 0.92, 0.72, 0.56),
    ReceiverPreset("wide-bowl", "Wide bowl", 0.22, 1.34, 1.21, 0.82, 0.35),
    ReceiverPreset("deep-pedestal", "Deep pedestal", -0.10, 1.13, 1.00, 0.90, 0.66),
)


STAGE_PRESETS = (
    ("classic", (0, 25, 50, 75, 100)),
    ("fine-middle", (0, 15, 45, 75, 100)),
    ("smooth-rise", (0, 20, 40, 70, 100)),
    ("late-extreme", (0, 30, 55, 85, 100)),
    ("wide-contrast", (0, 10, 35, 65, 100)),
)


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
        gravity_scale=gravity_scale,
        bounce_scale=bounce_scale,
        coupling_scale=coupling_scale,
        motion_phase=motion_phase,
        wrinkle_phase=wrinkle_phase,
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
