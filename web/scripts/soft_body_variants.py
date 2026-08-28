"""Deterministic visual and physics variants for Soft Body Slide.

The module intentionally contains no Blender dependency so the web renderer,
Blender scene and fast unit tests all resolve a seed to the exact same variant.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from soft_body_stair_geometry import RECEIVER_X, RECEIVER_TOP, OUTER_RADIUS, INNER_RADIUS


Color = tuple[float, float, float]
PHYSICS_HZ = 240
AIR_RETENTION_PER_SECOND = 0.992
REFERENCE_SWEEP_SCALE = 1.35
# Static composition offset shared by the ramp and capsule. It never depends
# on the receiver or on the simulated body state.
REFERENCE_SCENE_OFFSET_X = 2.44
REFERENCE_STAGE_DURATIONS = (4.438, 3.804, 7.173, 7.675, 6.841)
REFERENCE_STAGE_DURATIONS_BY_OBSTACLE = {
    # Reuse the former frozen release holds for the slow final descent.
    # Keep the physical action in the first four comparisons essentially the
    # same length, and let 100% reach the outlet before the 30-second cut.
    "stair-cascade": (4.0, 5.4, 6.3, 6.3, 8.0),
    # Match the observed complete landings with static contact friction.
    # Reuse the former release holds for the two slower final comparisons.
    "v-stairs": (4.6, 5.5, 5.3, 7.5, 7.1),
    "peg-grid": (4.0, 6.0, 7.0, 7.0, 6.0),
}


def stage_release_delay(duration: float, obstacle_key: str) -> float:
    """Authored hold before gravity starts; never derived from the outcome."""
    if obstacle_key == "peg-grid":
        return min(0.65, max(0.0, duration - 4.50))
    return 0.0


def stage_duration_weights(
    stage_count: int,
    obstacle_key: str | None = None,
    stage_values: tuple[int, ...] | None = None,
):
    if stage_values is not None and (
        len(stage_values) != stage_count
        or any(not isinstance(value, int) or not 0 <= value <= 100 for value in stage_values)
    ):
        raise ValueError("stage_values must contain one valid percentage per stage")
    if stage_count != 5:
        return (1.0,) * stage_count
    weights = REFERENCE_STAGE_DURATIONS_BY_OBSTACLE.get(
        obstacle_key,
        REFERENCE_STAGE_DURATIONS,
    )
    if obstacle_key == "stair-cascade" and stage_values is not None:
        # The 85% capsule reaches the outlet slightly later than 75%.
        # Reuse 0.2 s of the middle stage's completed tail, keeping the full
        # 100% descent and the complete 30-second edit unchanged.
        transfer = 0.2 * max(0.0, min(1.0, (stage_values[3] - 75) / 10.0))
        return (weights[0], weights[1], weights[2] - transfer, weights[3] + transfer, weights[4])
    if obstacle_key == "v-stairs" and stage_values is not None:
        # 75% completes sooner than the 85% comparison used to calibrate the
        # base edit. Keep its full landing, but move the otherwise empty tail
        # to the slower 100% trial. This changes only the edit, not gravity,
        # friction or the trajectory; the complete movie remains 30 seconds.
        transfer = 0.8 * max(0.0, min(1.0, (85 - stage_values[3]) / 10.0))
        return (*weights[:3], weights[3] - transfer, weights[4] + transfer)
    return weights


def stage_frame_spans(
    frame_count: int,
    stage_count: int = 5,
    obstacle_key: str | None = None,
    stage_values: tuple[int, ...] | None = None,
) -> tuple[tuple[int, int], ...]:
    """Return one-based inclusive spans matching the reference's edit rhythm."""

    if frame_count < stage_count or stage_count <= 0:
        raise ValueError("frame_count must provide at least one frame per stage")
    weights = stage_duration_weights(stage_count, obstacle_key, stage_values)
    total = sum(weights)
    boundaries = [0]
    cumulative = 0.0
    for index, weight in enumerate(weights[:-1]):
        cumulative += weight
        remaining_stages = stage_count - index - 1
        boundaries.append(max(boundaries[-1] + 1, min(
            frame_count - remaining_stages, round(frame_count * cumulative / total),
        )))
    boundaries.append(frame_count)
    return tuple(
        (boundaries[index] + 1, boundaries[index + 1])
        for index in range(stage_count)
    )


def stage_time_spans(
    duration: float,
    stage_count: int = 5,
    obstacle_key: str | None = None,
    stage_values: tuple[int, ...] | None = None,
) -> tuple[tuple[float, float], ...]:
    """Return second-based label spans with the same reference timing."""

    if duration <= 0.0 or stage_count <= 0:
        raise ValueError("duration and stage_count must be positive")
    weights = stage_duration_weights(stage_count, obstacle_key, stage_values)
    total = sum(weights)
    boundaries = [0.0]
    cumulative = 0.0
    for weight in weights[:-1]:
        cumulative += weight
        boundaries.append(duration * cumulative / total)
    boundaries.append(duration)
    return tuple(zip(boundaries, boundaries[1:]))


def stage_attempt_frame_spans(
    start: int,
    end: int,
    fps: int,
    obstacle_key: str,
    softness: int,
) -> tuple[tuple[int, int], ...]:
    """Split a long level into complete, reference-style physical attempts.

    Several source scenes release more than one specimen at the same softness.
    Doing the same prevents a body that has already left the camera from
    leaving half of a seven-second level empty. Cuts only happen between whole
    rendered frames and never leave a short unfinished tail.
    """

    if fps <= 0 or start <= 0 or end < start:
        raise ValueError("invalid attempt span")
    # These references repeat the test with multiple specimens *at once*.
    # Splitting them again in time created four/six bodies per level and cut
    # trajectories before their payoff.  Keep one complete physical take.
    if obstacle_key in {"stair-cascade", "v-stairs", "peg-grid"}:
        return ((start, end),)
    # Keep the reference edit readable: the two short opening comparisons run
    # once, while the three longer softness levels repeat twice.  Previous
    # obstacle-specific shortcuts could leave a 2.2 s remainder after a 5 s
    # stair attempt, cutting the second body halfway down the obstacle.  Equal
    # spans and a strict two-attempt ceiling guarantee complete actions and the
    # repeated 50/55% comparison visible in the source videos.
    target_seconds = {
        "moving-slide": 4.20,
        "v-stairs": 3.45,
        "pipe-bend": 3.35,
        "peg-grid": 4.05,
        "twin-gears": 3.25,
        "compression-ring": 3.20,
    }.get(obstacle_key, 6.0)
    if obstacle_key == "peg-grid" and softness >= 50:
        target_seconds = 3.25
    if obstacle_key == "stair-cascade":
        target_seconds = 3.45
    minimum_complete_seconds = {
        "moving-slide": 3.00,
        "stair-cascade": 3.05,
        "v-stairs": 3.05,
        "pipe-bend": 3.00,
        "peg-grid": 3.00,
        "twin-gears": 3.00,
        "compression-ring": 3.00,
    }.get(obstacle_key, target_seconds)
    frame_count = end - start + 1
    duration = frame_count / fps
    attempt_count = max(1, min(2, round(duration / target_seconds)))
    while attempt_count > 1 and duration / attempt_count < minimum_complete_seconds:
        attempt_count -= 1
    boundaries = [
        start + round(frame_count * index / attempt_count)
        for index in range(attempt_count + 1)
    ]
    return tuple(
        (boundaries[index], boundaries[index + 1] - 1)
        for index in range(attempt_count)
    )


def deformation_response(softness: float) -> tuple[float, float, float]:
    """Map a percentage to centreline, pressure and broad-buckling response.

    Buckling intentionally starts after the 25% stage: the reference keeps 0%
    rigid and 25% merely compliant, shows a clear bend at 50%, then reserves
    the recognisable multi-fold gel silhouette for 75/100%.
    """

    value = max(0.0, min(1.0, float(softness)))
    visible = value ** 0.92 * (0.97 - 0.05 * value)
    pressure = value ** 1.65
    # The reference already shows a small, readable bend at 25% when a
    # cylinder starts entering a narrow peg opening.  Keep that response
    # subtle, while reserving the large multi-fold silhouette for 75/100%.
    buckling = max(0.0, (value - 0.18) / 0.82) ** 1.25
    return visible, pressure, buckling


def obstacle_collision_radius_scale(softness: float, obstacle_key: str) -> float:
    """Return the physical cross-section available to narrow obstacles.

    A soft body's visible volume is conserved by the skinning pass, but its
    collision cross-section must be allowed to flatten.  Peg-grid openings in
    the source are deliberately sized so 0% is blocked, 25% starts entering,
    and 50%+ can squeeze through.  Other obstacles retain the conservative
    collision envelope used by the general solver.
    """

    value = max(0.0, min(1.0, float(softness)))
    general = 1.0 - value * 0.18
    if obstacle_key in {"peg-grid", "twin-gears"}:
        # 25% can visibly enter but remains fractionally wider than the gap;
        # from 50% onward the flattened cross-section clears the opening.
        return min(general, 1.0 - 0.28 * value ** 0.62)
    return general


def obstacle_drag_retention_per_second(softness: float, obstacle_key: str) -> float:
    """Model repeated bar friction while a partly soft body crosses a grid."""

    value = max(0.0, min(1.0, float(softness)))
    if obstacle_key != "peg-grid" or value < 0.18 or value >= 0.50:
        return 1.0
    progress = (value - 0.18) / 0.32
    return math.exp(math.log(1e-6) * (1.0 - progress) + math.log(0.18) * progress)


def obstacle_specimen_offsets(obstacle_key: str) -> tuple[float, ...]:
    """Match obstacle references that release multiple bodies together."""

    if obstacle_key == "peg-grid":
        return (-0.64, 0.64)
    if obstacle_key == "stair-cascade":
        return (-0.18, 0.0, 0.18)
    if obstacle_key == "v-stairs":
        return (0.0, 5.50)
    return (0.0,)


def obstacle_specimen_depth_offsets(obstacle_key: str) -> tuple[float, ...]:
    """Place parallel reference specimens on distinct visible 3D lanes."""

    if obstacle_key == "stair-cascade":
        return (-1.15, 0.0, 1.15)
    return (0.0,) * len(obstacle_specimen_offsets(obstacle_key))


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
    """Return light contact damping without gluing the body to the ramp.

    The reference relies on the moving marble repeatedly launching the body.
    Heavy support damping made our capsule settle on the surface for most of a
    trial, which removed the airborne relaunches that make the comparison read
    as a physics simulation.
    """

    if fps <= 0:
        raise ValueError("fps must be positive")
    substeps = max(1, round(PHYSICS_HZ / fps))
    actual_hz = fps * substeps
    horizontal = 0.990 ** (60.0 / actual_hz)
    vertical = (0.998 - softness * 0.001) ** (60.0 / actual_hz)
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
class ObstaclePreset:
    """One complete Oopsi-style physical setup, not a cosmetic skin."""

    key: str
    label: str
    source_video: str
    start_x: float
    start_height: float
    receiver_x: float
    camera_target_x: float
    camera_target_z: float
    camera_scale: float


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
    obstacle: ObstaclePreset
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
    RampPreset("scoop-launch", "Scoop launch", -2.72, 3.18, 3.57, 0.12, 0.17, 0.72, -1.10, 0.48, 0.65, 0.72, 0.26, 1.15, 1.90, 0.03, 1.65, -6.3),
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
    ReceiverPreset("deep-pedestal", "Deep pedestal", -0.65, 1.33, 1.20, 0.90, 0.66),
)


OBSTACLES = (
    ObstaclePreset("moving-slide", "Moving marble slide", "7653094317728271636", 0.30, 6.48, -1.20, 0.55, 3.12, 11.80),
    ObstaclePreset("stair-cascade", "Triple capsule stair run", "7635638193169222933", -2.00, 6.45, RECEIVER_X, 0.30, 3.35, 14.20),
    ObstaclePreset("v-stairs", "Double V staircase", "7671635370747940116", -2.75, 6.90, 0.0, 0.0, 2.80, 12.80),
    ObstaclePreset("pipe-bend", "Transparent pipe bend", "7662762295776333076", -0.85, 6.52, 0.36, 0.0, 3.45, 9.50),
    ObstaclePreset("peg-grid", "Soft body peg grid", "7670929910126447893", 0.0, 6.48, 0.0, 0.0, 3.35, 10.10),
    ObstaclePreset("twin-gears", "Counter-rotating gears", "7647848877403409684", 0.0, 6.45, 0.0, 0.0, 3.35, 9.50),
    ObstaclePreset("compression-ring", "Compression ring", "7635255329932053780", 0.05, 6.40, 0.0, 0.0, 3.35, 9.50),
)
OBSTACLE_KEYS = tuple(item.key for item in OBSTACLES)
AUTO_OBSTACLE_KEYS = ("moving-slide", "stair-cascade", "v-stairs", "peg-grid")
AUTO_OBSTACLES = tuple(item for item in OBSTACLES if item.key in AUTO_OBSTACLE_KEYS)


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


def stage_selection_for(variant: SoftBodyVariant, softness: int | None = None):
    """An explicit preview percentage is exact, not rounded to a preset."""
    if softness is None:
        return variant.stages, tuple(range(len(variant.stages)))
    if not isinstance(softness, int) or not 0 <= softness <= 100:
        raise ValueError("Preview softness must be an integer between 0 and 100")
    motion_index = min(range(len(variant.stages)), key=lambda index: abs(variant.stages[index] - softness))
    return (softness,), (motion_index,)


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
    position = REFERENCE_SCENE_OFFSET_X + REFERENCE_SWEEP_SCALE * (
        ramp.sweep_amplitude * math.sin(primary_angle)
        + ramp.secondary_amplitude * math.sin(secondary_angle)
    )
    velocity = REFERENCE_SWEEP_SCALE * (
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
    """Return the continuous reference-style sweep for the complete trial.

    The earlier authored exit made the ramp abruptly stop oscillating and
    coast away near the end of every stage.  That guaranteed a clean drop but
    also made all five trials look choreographed.  A perpetual sweep lets the
    capsule leave the edge, rebound, miss or enter solely from contact physics.
    """

    del trial_duration
    return ramp_sweep_state(time, variant, phase_offset)


def variant_for_seed(seed: int, obstacle_key: str | None = None) -> SoftBodyVariant:
    """Return a stable cross-product variant; adjacent seeds change every axis."""

    positive = abs(int(seed))
    shape = SHAPES[positive % len(SHAPES)]
    ramp = RAMPS[(positive * 3 + positive // 5 + 1) % len(RAMPS)]
    palette = PALETTES[(positive * 7 + positive // 11 + 2) % len(PALETTES)]
    receiver = RECEIVERS[(positive * 5 + positive // 7 + 1) % len(RECEIVERS)]
    if obstacle_key and obstacle_key != "auto":
        obstacle = next((item for item in OBSTACLES if item.key == obstacle_key), None)
        if obstacle is None:
            raise ValueError(f"Unknown soft-body obstacle family: {obstacle_key}")
    else:
        obstacle = AUTO_OBSTACLES[
            (positive * 13 + positive // 17 + 4) % len(AUTO_OBSTACLES)
        ]
    receiver = ReceiverPreset(
        receiver.key,
        receiver.label,
        obstacle.receiver_x,
        receiver.outer_radius,
        receiver.inner_radius,
        receiver.top,
        receiver.bowl_depth,
    )
    if obstacle.key == "stair-cascade":
        # The three hollow elbows and their collision walls share dimensions.
        receiver = ReceiverPreset(receiver.key + "-curved-triple", "Triple curved clear receivers",
                                  RECEIVER_X, OUTER_RADIUS, INNER_RADIUS, RECEIVER_TOP, 0.0)
    stage_key, stages = STAGE_PRESETS[(positive * 11 + positive // 13 + 3) % len(STAGE_PRESETS)]
    rng = random.Random(positive ^ 0x5F7B0D17)
    start_x = obstacle.start_x + rng.uniform(-0.12, 0.12)
    start_height = obstacle.start_height + rng.uniform(-0.08, 0.12)
    if obstacle.key in {"v-stairs", "pipe-bend", "peg-grid", "twin-gears", "compression-ring"}:
        start_rotation = math.pi / 2 + rng.uniform(-0.10, 0.10)
    else:
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
    if obstacle.key not in {"pipe-bend", "peg-grid", "twin-gears", "compression-ring"} and abs(start_rotation) < minimum_tilt:
        fallback_sign = -1.0 if release_rng.random() < 0.5 else 1.0
        start_rotation = math.copysign(
            minimum_tilt,
            start_rotation if abs(start_rotation) > 1e-9 else fallback_sign,
        )
    initial_spin = math.copysign(release_rng.uniform(0.20, 0.34), start_rotation)
    key = f"{obstacle.key}--{shape.key}--{ramp.key}--{palette.key}--{receiver.key}--{stage_key}"
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
        obstacle=obstacle,
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
        "variant_obstacle": variant.obstacle.key,
        "variant_obstacle_label": variant.obstacle.label,
        "variant_source_video": variant.obstacle.source_video,
        "stage_preset": variant.stage_key,
        "softness_stages": list(variant.stages),
    }
