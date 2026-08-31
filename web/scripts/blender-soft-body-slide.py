"""Render a seeded five-stage Oopsi-style soft-body comparison.

Each seed resolves to a reproducible combination of shape, moving ramp, studio
palette, receiver, softness progression and deterministic constraint physics.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from soft_body_variants import (
    OBSTACLE_KEYS,
    REFERENCE_SCENE_OFFSET_X,
    SoftBodyVariant,
    deformation_response,
    natural_ramp_exit_time,
    obstacle_collision_radius_scale,
    obstacle_drag_retention_per_second,
    obstacle_specimen_depth_offsets,
    obstacle_specimen_offsets,
    ramp_motion_state,
    solver_timing,
    stage_attempt_frame_spans,
    stage_frame_spans,
    stage_motion_for,
    stage_release_delay,
    stage_selection_for,
    supported_body_damping,
    variant_for_seed,
)
from soft_body_framing import camera_location, inspect_simulation_framing
from soft_body_render_contact import add_final_surface_contact, build_contact_targets, inspect_rendered_surface
from soft_body_volume_contact import point_inside_closed_surface
from soft_body_stair_geometry import add_staircase, add_curved_receivers, collision_segments, project_inside_stair



def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--softness", type=int, required=True)
    parser.add_argument("--stage-softness", type=int)
    parser.add_argument("--obstacle", choices=("auto",) + OBSTACLE_KEYS, default="auto")
    parser.add_argument("--events")
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Save the fully simulated .blend without rendering frames (for chunked native rendering).",
    )
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(
    name: str,
    color: tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.4,
    clearcoat: float = 0.0,
):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if shader.inputs.get("Clearcoat"):
        shader.inputs["Clearcoat"].default_value = clearcoat
        shader.inputs["Clearcoat Roughness"].default_value = 0.07
    return value


def mix_color(first, second, amount: float):
    """Blend seeded palettes toward the neutral OopsiLab studio treatment."""
    return tuple(a * (1.0 - amount) + b * amount for a, b in zip(first, second))


def marble_material(variant: SoftBodyVariant):
    palette = variant.palette
    marble_base = mix_color(palette.marble_base, (0.88, 0.88, 0.84), 0.72)
    marble_light = mix_color(palette.marble_light, (0.97, 0.96, 0.91), 0.72)
    marble_vein = mix_color(palette.marble_vein, (0.36, 0.38, 0.39), 0.62)
    value = bpy.data.materials.new(f"{palette.label} marble")
    value.use_nodes = True
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.28
    if shader.inputs.get("Clearcoat"):
        shader.inputs["Clearcoat"].default_value = 0.24

    coordinates = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.72, 0.72, 2.6)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.65
    noise.inputs["Detail"].default_value = 5.2
    noise.inputs["Roughness"].default_value = 0.64
    noise.inputs["Distortion"].default_value = 1.35
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*marble_base, 1)
    pre_vein = ramp.color_ramp.elements.new(0.41)
    pre_vein.color = (*tuple(channel * 0.97 for channel in marble_base), 1)
    vein = ramp.color_ramp.elements.new(0.455)
    # Keep the stone readable at phone size without the near-black dashes that
    # a narrow procedural vein produces under Filmic High Contrast.
    vein.color = (
        *tuple(
            base * 0.72 + vein_channel * 0.28
            for base, vein_channel in zip(marble_base, marble_vein)
        ),
        1,
    )
    after_vein = ramp.color_ramp.elements.new(0.50)
    after_vein.color = (*tuple(channel * 0.98 for channel in marble_base), 1)
    light = ramp.color_ramp.elements.new(0.61)
    light.color = (*marble_light, 1)
    ramp.color_ramp.elements[-1].position = 0.75
    ramp.color_ramp.elements[-1].color = (*marble_light, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.012
    bump.inputs["Distance"].default_value = 0.018
    links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return value


def background_material(variant: SoftBodyVariant):
    palette = variant.palette
    background_low = mix_color(palette.background_low, (0.36, 0.41, 0.47), 0.82)
    background_high = mix_color(palette.background_high, (0.55, 0.60, 0.65), 0.82)
    value = bpy.data.materials.new(f"{palette.label} clouded studio")
    value.use_nodes = True
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    output = nodes.get("Material Output")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.45
    noise.inputs["Detail"].default_value = 3.1
    noise.inputs["Roughness"].default_value = 0.75
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*background_low, 1)
    ramp.color_ramp.elements[1].position = 0.77
    ramp.color_ramp.elements[1].color = (*background_high, 1)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.72
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    nodes.remove(shader)
    return value


def liquid_gold_material(seed: int, variant: SoftBodyVariant):
    variation = ((seed % 997) / 996.0 - 0.5) * 0.025
    base = mix_color(variant.palette.metal, (0.93, 0.72, 0.32), 0.84)
    value = material(
        f"{variant.palette.label} liquid metal",
        (
            max(0.0, min(1.0, base[0] + variation)),
            max(0.0, min(1.0, base[1] + variation * 0.7)),
            max(0.0, min(1.0, base[2] + variation * 0.4)),
            1,
        ),
        metallic=1.0,
        roughness=max(0.18, min(0.23, variant.palette.metal_roughness * 1.28)),
        clearcoat=0.24,
    )
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 1.2
    bump = nodes.new("ShaderNodeBump")
    # The reference is polished liquid metal.  A microscopic imperfection keeps
    # highlights from looking computer-perfect without embossing fake ripples.
    bump.inputs["Strength"].default_value = 0.004
    bump.inputs["Distance"].default_value = 0.008
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    # Anisotropy and the large reflection cards produce a restrained central
    # groove-like highlight without the striped texture artifact of v3.
    if shader.inputs.get("Anisotropic"):
        shader.inputs["Anisotropic"].default_value = 0.23
    return value


def add_mesh(name: str, vertices, faces, values, bevel_width: float = 0.0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if not isinstance(values, (tuple, list)):
        values = (values,)
    for value in values:
        obj.data.materials.append(value)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if bevel_width:
        bevel = obj.modifiers.new("Soft bevel", "BEVEL")
        bevel.width = bevel_width
        bevel.segments = 3
    return obj


def ramp_height(local_x: float, variant: SoftBodyVariant, collision: bool = False) -> float:
    ramp = variant.ramp
    lip = max(0.0, min(1.0, (local_x - ramp.minimum) / ramp.lip_width))
    smooth_lip = lip * lip * (3.0 - 2.0 * lip)
    # Keep the collision shell on the visible marble.  The previous 13 cm
    # offset made the capsule visibly hover above it.
    collision_lift = 0.022 if collision else 0.0
    lip_scale = 0.96 if collision else 1.0
    wave = min(ramp.wave, 0.17) * math.sin(ramp.wave_frequency * local_x + ramp.wave_phase)
    return ramp.base + collision_lift + ramp.slope * local_x + wave + ramp.lip_rise * lip_scale * smooth_lip


def physics_ramp_height(local_x: float, variant: SoftBodyVariant) -> float:
    return ramp_height(local_x, variant, collision=True)


def ramp_points(variant: SoftBodyVariant, segments: int = 112):
    return [
        (variant.ramp.minimum + (variant.ramp.maximum - variant.ramp.minimum) * index / (segments - 1),)
        for index in range(segments)
    ]


def effective_ramp_exit_time(
    variant: SoftBodyVariant,
    trial_duration: float,
    phase_offset: float = 0.0,
) -> float:
    return natural_ramp_exit_time(variant, trial_duration, phase_offset)


def ramp_position(
    time: float,
    variant: SoftBodyVariant,
    trial_duration: float,
    phase_offset: float = 0.0,
) -> float:
    return ramp_motion_state(time, variant, trial_duration, phase_offset)[0]


def ramp_velocity(
    time: float,
    variant: SoftBodyVariant,
    trial_duration: float,
    phase_offset: float = 0.0,
) -> float:
    return ramp_motion_state(time, variant, trial_duration, phase_offset)[1]


def ramp_slope(local_x: float, variant: SoftBodyVariant, collision: bool = False) -> float:
    ramp = variant.ramp
    lip = max(0.0, min(1.0, (local_x - ramp.minimum) / ramp.lip_width))
    lip_scale = 0.84 if collision else 1.0
    return (
        ramp.slope
        + min(ramp.wave, 0.17) * ramp.wave_frequency * math.cos(ramp.wave_frequency * local_x + ramp.wave_phase)
        + ramp.lip_rise * lip_scale * 6.0 * lip * (1.0 - lip) / ramp.lip_width
    )


def physics_ramp_slope(local_x: float, variant: SoftBodyVariant) -> float:
    return ramp_slope(local_x, variant, collision=True)


def obstacle_segments(variant: SoftBodyVariant):
    """Return visible/collision-aligned line obstacles in the simulation plane."""
    return static_obstacle_segments(variant.obstacle.key)


@lru_cache(maxsize=16)
def static_obstacle_segments(key):
    if key == "peg-grid":
        # The source grid has a real landing rail, not a tube or an invisible
        # catch. Bodies finish the squeeze, land and slide during the payoff.
        return [((-3.15, 1.80), (3.15, 1.18), 0.085)]
    if key == "stair-cascade":
        return collision_segments()
    if key == "v-stairs":
        result = []
        for index in range(5):
            z = 5.62 - index * 0.46
            left_x = -3.18 + index * 0.46
            right_x = 3.18 - index * 0.46
            result.append(((left_x, z), (left_x + 0.62, z), 0.105))
            result.append(((right_x - 0.62, z), (right_x, z), 0.105))
        return result
    if key == "pipe-bend":
        # An open elbow assembled from short tangent segments.  The glass mesh
        # below uses these exact coordinates, so contacts never float.
        centerline = [
            (-0.85, 5.70), (-0.85, 5.15), (-0.82, 4.65), (-0.68, 4.24),
            (-0.42, 3.94), (-0.08, 3.75), (0.25, 3.55), (0.36, 3.24),
            (0.36, 2.92),
        ]
        knots = [Vector(point) for point in centerline]
        centerline = []
        for index in range(len(knots) - 1):
            a, b = knots[max(0, index - 1)], knots[index]
            c, d = knots[index + 1], knots[min(index + 2, len(knots) - 1)]
            for sample in range(4):
                u = sample / 4.0
                point = 0.5 * ((2.0 * b) + (-a + c) * u
                    + (2.0 * a - 5.0 * b + 4.0 * c - d) * u * u
                    + (-a + 3.0 * b - 3.0 * c + d) * u * u * u)
                centerline.append(tuple(point))
        centerline.append(tuple(knots[-1]))
        walls = []
        half_opening = 0.47
        normals = []
        for start, end in zip(centerline, centerline[1:]):
            tangent = (Vector(end) - Vector(start)).normalized()
            normals.append(Vector((-tangent.y, tangent.x)))
        offsets = []
        for index in range(len(centerline)):
            before = normals[max(0, index - 1)]
            after = normals[min(index, len(normals) - 1)]
            bisector = (before + after).normalized()
            offsets.append(bisector * (half_opening / max(0.25, bisector.dot(after))))
        # Adjacent segments share the SAME corner. Independently offset
        # tangents left small collider gaps, while the smoothed glass took a
        # different path altogether. Use a closed, joined polyline for both.
        for index in range(len(centerline) - 1):
            for side in (-1.0, 1.0):
                start = Vector(centerline[index]) + offsets[index] * side
                end = Vector(centerline[index + 1]) + offsets[index + 1] * side
                walls.append((tuple(start), tuple(end), 0.090))
        return walls
    return []


@lru_cache(maxsize=16)
def obstacle_segment_bounds(key):
    # Keep the original contact order and exact bounds, but do not recalculate
    # four min/max pairs millions of times while checking a smooth pipe.
    return tuple((start, end, thickness,
        min(start[0], end[0]), max(start[0], end[0]),
        min(start[1], end[1]), max(start[1], end[1]))
        for start, end, thickness in static_obstacle_segments(key))


@lru_cache(maxsize=16)
def static_obstacle_circles(key: str):
    if key == "peg-grid":
        circles = []
        for row in range(5):
            z = 5.15 - row * 0.62
            # A perfectly aligned lattice leaves uninterrupted vertical
            # corridors at x=+/-0.64.  A sufficiently soft specimen could then
            # miss all five rows without a single interaction.  Real peg-board
            # challenges stagger successive rows: alternate a small quarter-gap
            # offset so both reference lanes meet a peg from alternating sides.
            # This creates repeated, unscripted compression contacts while
            # preserving the same 0.44 opening and visible/collision geometry.
            row_offset = 0.0 if row % 2 == 0 else (0.16 if row % 4 == 1 else -0.16)
            for column in range(6):
                # A 0.44 opening accepts the flattened 15/25% presets while
                # remaining narrower than the rigid 0.45-0.468 diameter.
                # The old 0.41 throat trapped the 15% section between two
                # incompatible circle projections, folding and ejecting it.
                circles.append((Vector((-1.60 + row_offset + column * 0.64, z)), 0.10, Vector((0.0, 0.0)), 0.0))
        return tuple(circles)
    if key == "twin-gears":
        speed = math.tau / 3.40
        return (
            (Vector((-0.80, 3.78)), 0.60, Vector((0.0, 0.0)), -speed),
            (Vector((0.80, 3.78)), 0.60, Vector((0.0, 0.0)), speed),
        )
    if key == "pipe-bend":
        ring_x, ring_z = 0.36, 1.82
        return (
            (Vector((ring_x - 0.34, ring_z)), 0.15, Vector((0.0, 0.0)), 0.0),
            (Vector((ring_x + 0.34, ring_z)), 0.15, Vector((0.0, 0.0)), 0.0),
        )
    return ()


def obstacle_circles(time: float, variant: SoftBodyVariant):
    """Return (centre, radius, centre velocity, angular speed) colliders."""

    key = variant.obstacle.key
    if key in {"peg-grid", "twin-gears", "pipe-bend"}:
        return static_obstacle_circles(key)
    if key == "compression-ring":
        angle = math.tau * time / 1.72 - math.pi / 2
        # Keep 0.44 units between the closed rollers: the actual 45% preset
        # needs up to 0.4301, while its unsqueezed section is up to 0.468.
        # The former 0.40 opening had no feasible contact solution at that
        # preset and alternating projections tore the chain at the throat.
        half_gap = 0.92 - 0.12 * (0.5 + 0.5 * math.sin(angle))
        velocity = -0.12 * 0.5 * math.tau / 1.72 * math.cos(angle)
        return [
            (Vector((-half_gap, 3.82)), 0.58, Vector((-velocity, 0.0)), 0.0),
            (Vector((half_gap, 3.82)), 0.58, Vector((velocity, 0.0)), 0.0),
        ]
    return []


def nearby_obstacle_circles(point: Vector, time: float, variant: SoftBodyVariant):
    """Return only spatially relevant colliders for dense static grids."""

    if variant.obstacle.key != "peg-grid":
        return obstacle_circles(time, variant)
    circles = static_obstacle_circles("peg-grid")
    nearest_row = round((5.15 - point.y) / 0.62)
    nearest_column = round((point.x + 1.60) / 0.64)
    candidates = []
    for row in range(max(0, nearest_row - 1), min(4, nearest_row + 1) + 1):
        for column in range(
            max(0, nearest_column - 1),
            min(5, nearest_column + 1) + 1,
        ):
            candidates.append(circles[row * 6 + column])
    return tuple(candidates)


def add_ramp(
    marble,
    gold,
    variant: SoftBodyVariant,
    frame_end: int,
    fps: int,
    stage_spans: tuple[tuple[int, int, int], ...],
):
    segments = 192
    half_width, thickness = variant.ramp.half_width, variant.ramp.thickness * 0.68
    samples = [
        variant.ramp.minimum
        + (variant.ramp.maximum - variant.ramp.minimum) * index / (segments - 1)
        for index in range(segments)
    ]
    vertices = []
    for x in samples:
        z = ramp_height(x, variant)
        vertices.extend(
            (
                (x, -half_width, z),
                (x, half_width, z),
                (x, -half_width, z - thickness),
                (x, half_width, z - thickness),
            )
        )
    faces = []
    for index in range(segments - 1):
        current, following = index * 4, (index + 1) * 4
        faces.extend(
            (
                (current, following, following + 1, current + 1),
                (current + 2, current + 3, following + 3, following + 2),
                (current, current + 2, following + 2, following),
                (current + 1, following + 1, following + 3, current + 3),
            )
        )
    faces.extend(((0, 1, 3, 2), (len(vertices) - 4, len(vertices) - 2, len(vertices) - 1, len(vertices) - 3)))
    ramp = add_mesh("Moving S marble ramp", vertices, faces, marble, bevel_width=0.045)

    def edge_curve(name: str, y: float):
        curve = bpy.data.curves.new(name, type="CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = 0.012
        curve.bevel_resolution = 2
        spline = curve.splines.new("POLY")
        spline.points.add(len(samples) - 1)
        for point, x in zip(spline.points, samples):
            point.co = (x, y, ramp_height(x, variant) + 0.012, 1.0)
        obj = bpy.data.objects.new(name, curve)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(gold)
        return obj

    front_trim = edge_curve("Champagne front trim", -half_width - 0.006)
    back_trim = edge_curve("Champagne back trim", half_width + 0.006)
    for trim in (front_trim, back_trim):
        trim.parent = ramp

    for frame in range(1, frame_end + 1):
        stage_index, start, end = next(
            span for span in stage_spans if span[1] <= frame <= span[2]
        )
        local_frame = frame - start
        stage_frames = end - start + 1
        stage_motion = stage_motion_for(variant, stage_index)
        ramp.location.x = ramp_position(
            local_frame / fps,
            variant,
            stage_frames / fps,
            stage_motion.ramp_phase_offset,
        )
        ramp.keyframe_insert("location", frame=frame)
    if ramp.animation_data and ramp.animation_data.action:
        for curve in ramp.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    return ramp


def add_obstacle_geometry(
    marble, gold, variant: SoftBodyVariant, frame_end: int, fps: int,
    trial_spans: tuple[tuple[int, int, int], ...] = (),
):
    """Build the selected obstacle family from the same primitives as physics."""

    key = variant.obstacle.key
    if key == "moving-slide":
        return
    if key == "stair-cascade":
        return add_staircase(add_mesh, marble, variant)

    def local_time(frame):
        start = next((span[1] for span in trial_spans if span[1] <= frame <= span[2]), 1)
        return (frame - start) / fps

    if key == "pipe-bend":
        glass = material("Clear pipe glass", (0.66, 0.82, 0.92, 0.34), roughness=0.10, clearcoat=0.48)
        glass.blend_method = "BLEND"
        glass.use_screen_refraction = True
        walls = obstacle_segments(variant)
        for side in range(2):
            side_segments = walls[side::2]
            path = [side_segments[0][0], *[segment[1] for segment in side_segments]]
            curve = bpy.data.curves.new(f"Continuous glass pipe wall {side + 1}", type="CURVE")
            curve.dimensions = "3D"
            curve.resolution_u = 10
            curve.bevel_depth = 0.085
            curve.bevel_resolution = 5
            curve.use_fill_caps = True
            # The shared path is already smoothly sampled. A second NURBS
            # interpolation would move the visible glass off its colliders.
            spline = curve.splines.new("POLY")
            spline.points.add(len(path) - 1)
            for point, coordinate in zip(spline.points, path):
                point.co = (coordinate[0], 0.0, coordinate[1], 1.0)
            wall = bpy.data.objects.new(f"Continuous glass pipe wall {side + 1}", curve)
            bpy.context.collection.objects.link(wall)
            wall.data.materials.append(glass)
    else:
        for index, (start, end, thickness) in enumerate(obstacle_segments(variant)):
            midpoint = ((start[0] + end[0]) * 0.5, 0.0, (start[1] + end[1]) * 0.5)
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            angle = math.atan2(end[1] - start[1], end[0] - start[0])
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=midpoint, rotation=(0.0, -angle, 0.0))
            block = bpy.context.object
            block.name = f"{variant.obstacle.label} segment {index + 1}"
            lane_depth_scale = 2.90 if key == "stair-cascade" else 1.0
            block.dimensions = (
                length,
                variant.ramp.half_width * 2.0 * lane_depth_scale,
                thickness * 2.0,
            )
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            block.data.materials.append(gold if key == "peg-grid" else marble)
            bevel = block.modifiers.new("Marble edge", "BEVEL")
            bevel.width = min(0.045, thickness * 0.32)
            bevel.segments = 3

    circles = obstacle_circles(0.0, variant)
    if key == "peg-grid":
        glass = material("Peg board glass", (0.76, 0.86, 0.94, 0.10), roughness=0.16, clearcoat=0.28)
        glass.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.10
        glass.blend_method = "BLEND"
        if hasattr(glass, "shadow_method"):
            glass.shadow_method = "NONE"
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.34, 3.91))
        panel = bpy.context.object
        panel.name = "Transparent peg board"
        panel.dimensions = (4.18, 0.055, 3.18)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        panel.data.materials.append(glass)
        if hasattr(panel, "visible_shadow"):
            panel.visible_shadow = False
        bevel = panel.modifiers.new("Soft glass edge", "BEVEL")
        bevel.width = 0.035
        bevel.segments = 3
    if key == "pipe-bend":
        bpy.ops.mesh.primitive_torus_add(
            major_segments=96,
            minor_segments=24,
            location=(0.36, 0.0, 1.82),
            major_radius=0.34,
            minor_radius=0.15,
        )
        rebound_ring = bpy.context.object
        rebound_ring.name = "Physical rebound torus"
        rebound_ring.data.materials.append(gold)
        bevel = rebound_ring.modifiers.new("Rounded rebound edge", "BEVEL")
        bevel.width = 0.018
        bevel.segments = 2
        circles = ()
    for index, (center, radius, _velocity, _angular_speed) in enumerate(circles):
        gear_root = None
        if key == "twin-gears":
            gear_root = bpy.data.objects.new(f"Gear {index + 1} physical root", None)
            bpy.context.collection.objects.link(gear_root)
            gear_root.location = (center.x, 0.0, center.y)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=64,
            radius=radius - 0.15 if key == "twin-gears" else radius,
            depth=variant.ramp.half_width * 2.15,
            location=(center.x, 0.0, center.y),
            rotation=(math.pi / 2, 0.0, 0.0),
        )
        collider = bpy.context.object
        collider.name = f"{variant.obstacle.label} collider {index + 1}"
        collider.data.materials.append(marble if key == "peg-grid" else gold)
        if gear_root is not None:
            collider.parent = gear_root
            collider.location = (0.0, 0.0, 0.0)
        bevel = collider.modifiers.new("Polished obstacle edge", "BEVEL")
        bevel.width = 0.035
        bevel.segments = 3
        if key == "twin-gears":
            for tooth in range(16):
                angle = math.tau * tooth / 16
                bpy.ops.mesh.primitive_cube_add(
                    size=1.0,
                    location=(0.0, 0.0, 0.0),
                    rotation=(0.0, -angle, 0.0),
                )
                tooth_obj = bpy.context.object
                tooth_obj.name = f"Gear {index + 1} tooth {tooth + 1}"
                tooth_obj.dimensions = (0.22, variant.ramp.half_width * 1.8, 0.10)
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                tooth_obj.data.materials.append(marble)
                # Round the actual rendered/contact edge. At a sharp 90-degree
                # corner Shrinkwrap can misclassify distant outside vertices
                # and snap free-falling skin up to this rotating tooth.
                bevel = tooth_obj.modifiers.new("Rounded tooth edge", "BEVEL")
                bevel.width = 0.006
                bevel.segments = 3
                tooth_obj.parent = gear_root
                tooth_obj.location = (
                    math.cos(angle) * (radius - 0.10),
                    0.0,
                    math.sin(angle) * (radius - 0.10),
                )
            for frame in range(1, frame_end + 1):
                gear_root.rotation_euler[1] = _angular_speed * local_time(frame)
                gear_root.keyframe_insert("rotation_euler", index=1, frame=frame)
            if gear_root.animation_data and gear_root.animation_data.action:
                for curve in gear_root.animation_data.action.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "LINEAR"

    if key == "compression-ring":
        # Animate the two rollers with the exact analytic centres used by the
        # collider. Their motion compresses the body; it never targets the cup.
        roller_objects = [obj for obj in bpy.context.collection.objects if obj.name.startswith(variant.obstacle.label)]
        for frame in range(1, frame_end + 1):
            time = local_time(frame)
            states = obstacle_circles(time, variant)
            for obj, state in zip(roller_objects, states):
                obj.location.x = state[0].x
                obj.keyframe_insert("location", frame=frame)
        for obj in roller_objects:
            if obj.animation_data and obj.animation_data.action:
                for curve in obj.animation_data.action.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "LINEAR"


def capsule_geometry(
    variant: SoftBodyVariant,
    radial_segments: int = 64,
    cap_rings: int = 14,
    cylinder_rings: int = 24,
):
    radius = variant.shape.radius
    cylinder_half = variant.shape.cylinder_half
    rings: list[tuple[float, float]] = []
    for index in range(1, cap_rings + 1):
        angle = -math.pi / 2 + (math.pi / 2) * index / cap_rings
        rings.append((-cylinder_half + radius * math.sin(angle), radius * math.cos(angle)))
    for index in range(1, cylinder_rings):
        ratio = index / cylinder_rings
        rings.append((-cylinder_half + 2 * cylinder_half * ratio, radius))
    rings.append((cylinder_half, radius))
    for index in range(1, cap_rings):
        angle = (math.pi / 2) * index / cap_rings
        rings.append((cylinder_half + radius * math.sin(angle), radius * math.cos(angle)))

    vertices = [(-cylinder_half - radius, 0.0, 0.0)]
    total_half = cylinder_half + radius
    for x, ring_radius in rings:
        body_profile = max(0.0, 1.0 - (x / max(total_half, 1e-6)) ** 2)
        ring_radius *= 1.0 + variant.shape.bulge * body_profile
        for segment in range(radial_segments):
            angle = math.tau * segment / radial_segments
            front_angle = (angle - math.pi + math.pi) % math.tau - math.pi
            groove = math.exp(-((front_angle / 0.34) ** 2))
            groove_strength = variant.shape.groove * min(1.0, ring_radius / max(radius, 1e-6))
            shaped_radius = ring_radius * (1.0 - groove * groove_strength)
            vertices.append((x, math.cos(angle) * shaped_radius, math.sin(angle) * shaped_radius))
    vertices.append((cylinder_half + radius, 0.0, 0.0))

    faces = []
    first_ring = 1
    for segment in range(radial_segments):
        faces.append((0, first_ring + (segment + 1) % radial_segments, first_ring + segment))
    for ring in range(len(rings) - 1):
        current = 1 + ring * radial_segments
        following = current + radial_segments
        for segment in range(radial_segments):
            next_segment = (segment + 1) % radial_segments
            faces.append((current + segment, current + next_segment, following + next_segment, following + segment))
    right_pole = len(vertices) - 1
    last_ring = 1 + (len(rings) - 1) * radial_segments
    for segment in range(radial_segments):
        faces.append((last_ring + segment, last_ring + (segment + 1) % radial_segments, right_pole))
    return vertices, faces


def constrain_distance(points, first: int, second: int, target: float, strength: float = 1.0) -> None:
    delta = points[second] - points[first]
    length = max(delta.length, 1e-8)
    correction = delta * ((length - target) / length * 0.5 * strength)
    points[first] += correction
    points[second] -= correction


def limit_solver_velocity(velocity: Vector, dt: float, maximum_speed: float = 24.0) -> Vector:
    """Bound recycled Verlet energy while leaving authored impacts untouched."""

    maximum_step = maximum_speed * dt
    length = velocity.length
    if length <= maximum_step or length <= 1e-12:
        return velocity
    return velocity * (maximum_step / length)


def limit_solver_translation(
    points,
    previous,
    origin,
    maximum_step: float = 0.20,
) -> float:
    """Spread a pathological contact projection across fixed-clock ticks."""

    center_before = sum(origin, Vector((0.0, 0.0))) / len(origin)
    center_after = sum(points, Vector((0.0, 0.0))) / len(points)
    displacement = center_after - center_before
    distance = displacement.length
    if distance <= maximum_step or distance <= 1e-12:
        return 0.0
    correction = displacement * (maximum_step / distance - 1.0)
    for index in range(len(points)):
        points[index] += correction
        previous[index] += correction
    return distance - maximum_step


def constrain_self_collision(points, radii, neighbor_skip: int, softness: float) -> None:
    """Prevent distant sections of the capsule from passing through each other."""
    separation_scale = 0.96 - softness * 0.04
    for first in range(len(points) - neighbor_skip):
        for second in range(first + neighbor_skip, len(points)):
            delta = points[second] - points[first]
            distance = delta.length
            minimum = (radii[first] + radii[second]) * separation_scale
            if 1e-7 < distance < minimum:
                correction = delta * ((minimum - distance) / distance * 0.34)
                points[first] -= correction
                points[second] += correction


def smooth_centerline(points, rest: float, passes: int):
    """Remove solver chatter without shortening the physical rod."""
    result = [point.copy() for point in points]
    for _ in range(passes):
        center_before = sum(result, Vector((0.0, 0.0))) / len(result)
        smoothed = [result[0] * 0.84 + result[1] * 0.16]
        for index in range(1, len(result) - 1):
            smoothed.append(
                result[index - 1] * 0.14
                + result[index] * 0.72
                + result[index + 1] * 0.14
            )
        smoothed.append(result[-1] * 0.84 + result[-2] * 0.16)
        for projection in range(5):
            direction = range(len(smoothed) - 1) if projection % 2 == 0 else range(len(smoothed) - 2, -1, -1)
            for index in direction:
                constrain_distance(smoothed, index, index + 1, rest, 0.72)
        center_after = sum(smoothed, Vector((0.0, 0.0))) / len(smoothed)
        shift = center_before - center_after
        result = [point + shift for point in smoothed]
    return result


def resolve_obstacle_contact(
    point: Vector,
    previous: Vector,
    center: Vector,
    minimum: float,
    surface_step: Vector,
    softness: float,
    dt: float,
    resolve_velocity: bool,
) -> tuple[Vector, Vector, float, bool]:
    delta = point - center
    distance = delta.length
    if distance >= minimum:
        return point, previous, 0.0, False
    if distance > 1e-8:
        normal = delta / distance
    else:
        fallback = point - previous
        normal = fallback.normalized() if fallback.length > 1e-8 else Vector((0.0, 1.0))
    correction = normal * (minimum - distance)
    point += correction
    previous += correction
    intensity = 0.0
    if resolve_velocity:
        velocity = point - previous
        relative = velocity - surface_step
        normal_speed = relative.dot(normal)
        intensity = abs(normal_speed) / max(dt, 1e-6)
        if normal_speed < 0.0:
            normal_impulse = -(1.44 - softness * 0.25) * normal_speed
            velocity += normal * normal_impulse
            tangent = Vector((normal.y, -normal.x))
            tangent_error = surface_step.dot(tangent) - velocity.dot(tangent)
            friction_limit = normal_impulse * (0.055 + softness * 0.065)
            velocity += tangent * max(-friction_limit, min(friction_limit, tangent_error))
            previous = point - velocity
    return point, previous, intensity, True


def closest_segment_point(point: Vector, start, end) -> Vector:
    a, b = Vector(start), Vector(end)
    direction = b - a
    length_squared = direction.length_squared
    if length_squared <= 1e-12:
        return a
    progress = max(0.0, min(1.0, (point - a).dot(direction) / length_squared))
    return a + direction * progress


def collide_point(
    point: Vector,
    previous: Vector,
    radius: float,
    softness: float,
    time: float,
    dt: float,
    variant: SoftBodyVariant,
    trial_duration: float,
    ramp_phase_offset: float,
    resolve_velocity: bool,
) -> tuple[Vector, Vector, float, float, bool]:
    ramp_intensity = 0.0
    receiver_intensity = 0.0
    ramp_contact = False
    if variant.obstacle.key == "stair-cascade":
        project_inside_stair(point, previous, radius, closest_segment_point)
    ramp_x = ramp_position(time, variant, trial_duration, ramp_phase_offset)
    local_x = point.x - ramp_x
    if variant.obstacle.key == "moving-slide" and variant.ramp.minimum <= local_x <= variant.ramp.maximum:
        height = physics_ramp_height(local_x, variant)
        slope = physics_ramp_slope(local_x, variant)
        normal = Vector((-slope, 1.0)).normalized()
        signed_distance = (point.y - height) / math.sqrt(1.0 + slope * slope)
        previous_local_x = previous.x - ramp_x
        previous_on_ramp = variant.ramp.minimum <= previous_local_x <= variant.ramp.maximum
        previous_signed_distance = -math.inf
        if previous_on_ramp:
            previous_height = physics_ramp_height(previous_local_x, variant)
            previous_slope = physics_ramp_slope(previous_local_x, variant)
            previous_signed_distance = (
                (previous.y - previous_height)
                / math.sqrt(1.0 + previous_slope * previous_slope)
            )
        # The ramp top is one-sided. A body that has already fallen below it
        # must not be caught and teleported upward merely because the animated
        # ramp sweeps horizontally over its X coordinate. Preserve genuine
        # crossings from above and small resting/constraint overlaps.
        entered_from_top = previous_on_ramp and previous_signed_distance >= -0.02
        shallow_overlap = signed_distance >= -0.08
        if signed_distance < radius and (entered_from_top or shallow_overlap):
            ramp_contact = True
            correction = normal * (radius - signed_distance)
            point += correction
            # Positional projection is geometric, not kinetic. Preserve the
            # pre-projection velocity so deep overlap cannot create a catapult.
            previous += correction
            if resolve_velocity:
                velocity = point - previous
                ramp_step = Vector(
                    (ramp_velocity(time, variant, trial_duration, ramp_phase_offset) * dt, 0.0)
                )
                relative = velocity - ramp_step
                normal_speed = relative.dot(normal)
                ramp_intensity = max(ramp_intensity, abs(normal_speed) / max(dt, 1e-6))
                if normal_speed < 0.0:
                    # The moving reference ramp repeatedly relaunches the
                    # capsule.  A near-inelastic 0.14 response made ours settle
                    # on the marble for four seconds before a scripted-looking
                    # drop.  Keep rigid stages crisp and soft stages damped,
                    # while allowing both to become airborne after real hits.
                    # Rigid rods transfer more of the ramp's normal impulse
                    # into horizontal travel than folding bodies.  Keep the
                    # same 100% softness response, but trim the rigid rebound
                    # so deterministic floating-point differences cannot turn
                    # a valid fall into a sustained side/top camera exit.
                    restitution = (0.42 - softness * 0.18) * variant.bounce_scale
                    tangent = Vector((normal.y, -normal.x))
                    normal_impulse = -(1.0 + restitution) * normal_speed
                    velocity += normal * normal_impulse
                    target_tangent = ramp_step.dot(tangent)
                    tangent_error = target_tangent - velocity.dot(tangent)
                    friction = (0.045 + softness * 0.020) * variant.coupling_scale
                    tangent_impulse = max(
                        -normal_impulse * friction,
                        min(normal_impulse * friction, tangent_error),
                    )
                    velocity += tangent * tangent_impulse
                    previous = point - velocity

    if variant.obstacle.key != "moving-slide":
        for start, end, thickness, min_x, max_x, min_z, max_z in obstacle_segment_bounds(variant.obstacle.key):
            padding = radius + thickness + 0.06
            if (
                point.x < min_x - padding
                or point.x > max_x + padding
                or point.y < min_z - padding
                or point.y > max_z + padding
            ):
                continue
            point, previous, intensity, contact = resolve_obstacle_contact(
                point,
                previous,
                closest_segment_point(point, start, end),
                radius + thickness,
                Vector((0.0, 0.0)),
                softness,
                dt,
                resolve_velocity,
            )
            ramp_intensity = max(ramp_intensity, intensity)
            ramp_contact = ramp_contact or contact
        for center, obstacle_radius, center_velocity, angular_speed in nearby_obstacle_circles(
            point,
            time,
            variant,
        ):
            broadphase = radius + obstacle_radius + 0.06
            if abs(point.x - center.x) > broadphase or abs(point.y - center.y) > broadphase:
                continue
            delta = point - center
            tangent = Vector((-delta.y, delta.x)).normalized() if delta.length > 1e-8 else Vector((1.0, 0.0))
            surface_step = (center_velocity + tangent * angular_speed * obstacle_radius) * dt
            point, previous, intensity, contact = resolve_obstacle_contact(
                point,
                previous,
                center,
                radius + obstacle_radius,
                surface_step,
                softness,
                dt,
                resolve_velocity,
            )
            ramp_intensity = max(ramp_intensity, intensity)
            ramp_contact = ramp_contact or contact

    if variant.obstacle.key in {"peg-grid", "stair-cascade"}:
        # Stair elbows already belong to the shared physical segments; never
        # add the old straight receiver's invisible walls on top of them.
        return point, previous, ramp_intensity, receiver_intensity, ramp_contact

    # Thin circular rim first. The opening remains real: misses continue below
    # frame instead of landing on an invisible cylinder cap.
    receiver = variant.receiver
    rim_major = (receiver.outer_radius + receiver.inner_radius) * 0.5
    rim_minor = (receiver.outer_radius - receiver.inner_radius) * 0.55
    for rim_x in (receiver.x - rim_major, receiver.x + rim_major):
        center = Vector((rim_x, receiver.top))
        delta = point - center
        minimum = radius + rim_minor
        if 1e-7 < delta.length < minimum:
            normal = delta.normalized()
            corrected = center + normal * minimum
            correction = corrected - point
            point = corrected
            previous += correction
            if resolve_velocity:
                velocity = point - previous
                normal_speed = velocity.dot(normal)
                receiver_intensity = max(
                    receiver_intensity,
                    abs(normal_speed) / max(dt, 1e-6),
                )
                if normal_speed < 0.0:
                    restitution = 0.40 - softness * 0.24
                    normal_impulse = -(1.0 + restitution) * normal_speed
                    velocity += normal * normal_impulse
                    tangent = Vector((normal.y, -normal.x))
                    tangent_impulse = max(
                        -normal_impulse * (0.025 + softness * 0.030),
                        min(
                            normal_impulse * (0.025 + softness * 0.030),
                            -velocity.dot(tangent),
                        ),
                    )
                    velocity += tangent * tangent_impulse
                    previous = point - velocity

    # The receiver is an open tube.  Its two vertical marble walls can deflect
    # a capsule, but there is no invisible floor or sticky catch volume.
    wall_center_offset = (receiver.outer_radius + receiver.inner_radius) * 0.5
    wall_half_thickness = (receiver.outer_radius - receiver.inner_radius) * 0.5
    wall_bottom = 0.40 if variant.obstacle.key == "stair-cascade" else -3.55
    wall_top = receiver.top - rim_minor * 0.18
    if wall_bottom < point.y < wall_top:
        for side in (-1.0, 1.0):
            wall_x = receiver.x + side * wall_center_offset
            signed_distance = point.x - wall_x
            minimum = radius + wall_half_thickness
            if abs(signed_distance) < minimum:
                if abs(signed_distance) > 1e-7:
                    normal_x = 1.0 if signed_distance > 0.0 else -1.0
                else:
                    previous_distance = previous.x - wall_x
                    normal_x = 1.0 if previous_distance >= 0.0 else -1.0
                normal = Vector((normal_x, 0.0))
                corrected_x = wall_x + normal_x * minimum
                correction = Vector((corrected_x - point.x, 0.0))
                point.x = corrected_x
                previous += correction
                if resolve_velocity:
                    velocity = point - previous
                    normal_speed = velocity.dot(normal)
                    receiver_intensity = max(
                        receiver_intensity,
                        abs(normal_speed) / max(dt, 1e-6),
                    )
                    if normal_speed < 0.0:
                        restitution = 0.34 - softness * 0.20
                        normal_impulse = -(1.0 + restitution) * normal_speed
                        velocity += normal * normal_impulse
                        tangent = Vector((0.0, 1.0))
                        tangent_impulse = max(
                            -normal_impulse * (0.018 + softness * 0.022),
                            min(
                                normal_impulse * (0.018 + softness * 0.022),
                                -velocity.dot(tangent),
                            ),
                        )
                        velocity += tangent * tangent_impulse
                        previous = point - velocity
    return point, previous, ramp_intensity, receiver_intensity, ramp_contact


def _chain_ticks(
    softness_percent: int,
    frame_count: int,
    fps: int,
    variant: SoftBodyVariant,
    stage_index: int,
    instance_offset_x: float = 0.0,
    instance_rotation_offset: float = 0.0,
):
    softness = softness_percent / 100.0
    node_count = 41
    # The simulated spine covers the cylindrical section only.  Hemispherical
    # caps are reconstructed around its endpoints, so their collision radius
    # never collapses into the needle-like poles produced by the old solver.
    half_length = variant.shape.cylinder_half
    rest = 2.0 * half_length / (node_count - 1)
    stage_motion = stage_motion_for(variant, stage_index)
    rotation = variant.start_rotation + stage_motion.rotation_offset + instance_rotation_offset
    scene_offset = REFERENCE_SCENE_OFFSET_X if variant.obstacle.key == "moving-slide" else 0.0
    start_x = variant.start_x + scene_offset + stage_motion.spawn_x_offset + instance_offset_x
    start_height = variant.start_height + stage_motion.spawn_height_offset
    points = []
    for index in range(node_count):
        local_x = -half_length + rest * index
        points.append(
            Vector(
                (
                    start_x + math.cos(rotation) * local_x,
                    start_height + math.sin(rotation) * local_x,
                )
            )
        )
    substeps, dt, internal_damping, air_drag = solver_timing(fps, softness)
    center = sum(points, Vector((0.0, 0.0))) / node_count
    initial_linear_velocity = Vector(
        (stage_motion.linear_velocity_x, stage_motion.linear_velocity_y)
    )
    if variant.obstacle.key == "stair-cascade":
        initial_linear_velocity.x += 0.62
    elif variant.obstacle.key == "v-stairs":
        # The two reference specimens start on opposite arms and move toward
        # the centre.  Mirroring velocity is scene geometry, not receiver
        # steering: it depends only on which authored arm spawned the body.
        initial_linear_velocity.x += -0.24 if instance_offset_x > 2.0 else 0.24
    previous = []
    for point in points:
        radius_from_center = point - center
        authored_spin = variant.initial_spin + stage_motion.angular_velocity
        if variant.obstacle.key == "v-stairs" and instance_offset_x > 2.0:
            authored_spin *= -1.0
        angular_velocity = Vector(
            (-radius_from_center.y, radius_from_center.x)
        ) * authored_spin
        previous.append(point - (initial_linear_velocity + angular_velocity) * dt)
    supported_horizontal, supported_vertical = supported_body_damping(fps, softness)
    class SimulationFrames(list):
        """Rendered samples plus fixed-clock collision telemetry.

        This remains a normal list for all existing shape-key consumers.  The
        sidecar samples deliberately live at the physics rate, though, so
        render FPS can never quantise Foley event timestamps.
        """

    frames = SimulationFrames()
    frames.physics_samples = []
    frames.receiver_entries = []
    frames.physics_dt = dt
    impact_memory = 0.0
    node_impact_memory = [0.0] * node_count
    trial_duration = frame_count / fps
    release_delay = stage_release_delay(trial_duration, variant.obstacle.key)
    gravity_multiplier = {
        "stair-cascade": 0.62,
        "v-stairs": 0.25,
        "peg-grid": 0.42,
        "pipe-bend": 0.65,
        "twin-gears": 0.24,
        # These close-ups use a deliberate slow-motion physical timescale so
        # an outcome is still visible at the cut rather than 1-2 seconds of an
        # empty portrait frame.
        "compression-ring": 0.14,
    }.get(variant.obstacle.key, 1.0)
    # Static stairs already apply contact friction in collide_point. They
    # must not inherit the moving ramp's extra hold until a duration-derived
    # release window: changing the edit used to change the preceding fall.
    exit_time = 0.0 if variant.obstacle.key in {"v-stairs", "stair-cascade"} else effective_ramp_exit_time(
        variant,
        trial_duration,
        stage_motion.ramp_phase_offset,
    )
    released = False
    ramp_clear_substeps = 0
    support_grace_substeps = 0
    support_grace_limit = max(3, round(0.10 / dt))
    # Render FPS must never change the game outcome.  The previous code used
    # 24 solver steps *per rendered frame*, so a 30 FPS production render had
    # ten times more damping/constraints than a 3 FPS scout.  Keep a stable
    # physics clock and only sample it at the requested render cadence.
    iterations = max(40, round(88 - softness * 44))
    # Softness removes *bending* stiffness while the adjacent constraints keep
    # the gel nearly inextensible.  At 75/100 the chain must be free to fold at
    # an end-first impact; retaining the old 8%/3% long-range correction every
    # 1/240 s made even the nominal 100% body read as a rigid baton.
    target_bend = max(0.01, (1.0 - softness) ** 1.55)
    bend_strength = 1.0 - (1.0 - target_bend) ** (1.0 / iterations)
    target_long_bend = max(0.005, (1.0 - softness) ** 1.85)
    long_bend_strength = 1.0 - (1.0 - target_long_bend) ** (1.0 / iterations)
    # Soft material compresses at narrow passages. Keeping the collision radius
    # fully rigid made 100% softness unable to pass gaps that its visible mesh
    # clearly squeezed through. Adjacent constraints still conserve its volume.
    collision_radius = variant.shape.radius * obstacle_collision_radius_scale(
        softness,
        variant.obstacle.key,
    )
    collision_radii = [collision_radius] * node_count
    neighbor_skip = max(5, math.ceil(2.0 * variant.shape.radius * 0.86 / rest) + 1)
    physics_step = 0

    # Include a shared terminal sample at exactly ``trial_duration``. Without
    # it, a 3 fps scout stopped at 5.667 s while a 30 fps render reached
    # 5.967 s, which could change the visible outcome and final Foley event.
    for frame in range(frame_count + 1):
        frame_intensity = 0.0
        frame_ramp_intensity = 0.0
        frame_receiver_intensity = 0.0
        node_intensity = [0.0] * node_count
        if frame:
            for substep in range(substeps):
                # Count fixed simulation ticks rather than reconstructing time
                # from the render frame.  For 3 and 30 FPS this is the exact
                # same 240 Hz clock and therefore the same event timeline.
                physics_step += 1
                time = physics_step * dt
                if time <= release_delay:
                    frozen_center = sum(points, Vector((0.0, 0.0))) / node_count
                    frames.physics_samples.append(
                        (time, 0.0, 0.0, frozen_center.x, frozen_center.y)
                    )
                    continue
                previous_substep_points = [point.copy() for point in points]
                substep_ramp_intensity = 0.0
                substep_receiver_intensity = 0.0
                velocities = [point - old_point for point, old_point in zip(points, previous)]
                use_support_damping = not released and support_grace_substeps > 0
                if not use_support_damping:
                    raw_center_velocity = sum(velocities, Vector((0.0, 0.0))) / node_count
                    center_velocity = raw_center_velocity * air_drag
                    integrated_velocities = [
                        center_velocity
                        + (velocity - raw_center_velocity) * internal_damping
                        for velocity in velocities
                    ]
                else:
                    # Strong damping is legitimate while the moving marble is
                    # supporting the body.  It is permanently disabled after
                    # release, so it cannot bend the ballistic arc toward a cup.
                    integrated_velocities = [
                        Vector(
                            (
                                velocity.x * supported_horizontal,
                                velocity.y * supported_vertical,
                            )
                        )
                        for velocity in velocities
                    ]
                center_height = sum(point.y for point in points) / node_count
                if variant.obstacle.key == "peg-grid" and 2.20 <= center_height <= 5.72:
                    porous_retention = obstacle_drag_retention_per_second(
                        softness,
                        variant.obstacle.key,
                    ) ** dt
                    integrated_velocities = [
                        velocity * porous_retention
                        for velocity in integrated_velocities
                    ]
                # A positional contact can leave a pathological displacement
                # in Verlet's previous/current pair. Do not recycle that
                # numerical correction as more than three times the fastest
                # authored obstacle speed on the next fixed-clock tick.
                integrated_velocities = [
                    limit_solver_velocity(velocity, dt)
                    for velocity in integrated_velocities
                ]
                for index, velocity in enumerate(integrated_velocities):
                    previous[index] = points[index].copy()
                    points[index] += velocity + Vector(
                        (
                            0.0,
                            -9.81 * variant.gravity_scale * gravity_multiplier * dt * dt,
                        )
                    )

                substep_ramp_contact = False
                for iteration in range(iterations):
                    direction = range(node_count - 1) if iteration % 2 == 0 else range(node_count - 2, -1, -1)
                    for index in direction:
                        constrain_distance(points, index, index + 1, rest)
                    bend_direction = range(node_count - 2) if iteration % 2 == 0 else range(node_count - 3, -1, -1)
                    for index in bend_direction:
                        constrain_distance(points, index, index + 2, rest * 2.0, bend_strength)
                    for index in range(node_count - 4):
                        constrain_distance(points, index, index + 4, rest * 4.0, long_bend_strength)
                    if iteration % 2 == 0:
                        for index in range(node_count - 8):
                            constrain_distance(
                                points, index, index + 8, rest * 8.0, long_bend_strength * 0.30
                            )
                    if softness >= 0.45 and iteration % 4 == 0:
                        constrain_self_collision(points, collision_radii, neighbor_skip, softness)
                    for index in range(node_count):
                        radius = collision_radii[index]
                        (
                            points[index],
                            previous[index],
                            ramp_hit,
                            receiver_hit,
                            ramp_contact,
                        ) = collide_point(
                            points[index], previous[index], radius, softness, time, dt, variant,
                            trial_duration,
                            stage_motion.ramp_phase_offset,
                            iteration == 0,
                        )
                        substep_ramp_contact = substep_ramp_contact or ramp_contact
                        intensity = max(ramp_hit, receiver_hit)
                        substep_ramp_intensity = max(substep_ramp_intensity, ramp_hit)
                        substep_receiver_intensity = max(
                            substep_receiver_intensity,
                            receiver_hit,
                        )
                        frame_intensity = max(frame_intensity, intensity)
                        frame_ramp_intensity = max(frame_ramp_intensity, ramp_hit)
                        frame_receiver_intensity = max(frame_receiver_intensity, receiver_hit)
                        node_intensity[index] = max(node_intensity[index], intensity)
                if variant.obstacle.key in {"pipe-bend", "twin-gears", "moving-slide", "compression-ring"} and any(
                    abs((second - first).length / rest - 1.0) > 0.035
                    for first, second in zip(points, points[1:])
                ):
                    # The final collider projection can undo an adjacent
                    # length constraint in a tight bend OR a fast moving-ramp
                    # impact. Finish without bending targets fighting the
                    # contact surface.
                    # Numerical cleanup must not inject a new velocity.
                    before_cleanup = [point.copy() for point in points]
                    for cleanup in range(160):
                        error = max(abs((second - first).length / rest - 1.0)
                                    for first, second in zip(points, points[1:]))
                        if error < 0.035:
                            break
                        direction = range(node_count - 1) if cleanup % 2 == 0 else range(node_count - 2, -1, -1)
                        for index in direction:
                            constrain_distance(points, index, index + 1, rest)
                        for index in range(node_count):
                            points[index], _unused, *_telemetry = collide_point(
                                points[index], points[index].copy(), collision_radii[index],
                                softness, time, dt, variant, trial_duration,
                                stage_motion.ramp_phase_offset, False,
                            )
                    for index, origin in enumerate(before_cleanup):
                        previous[index] += points[index] - origin
                shared_tick = {
                    "points": points, "previous": previous,
                    "radius": variant.shape.radius, "rest": rest,
                    "variant": variant, "time": time, "dt": dt,
                    "softness": softness, "trial_duration": trial_duration,
                    "phase": stage_motion.ramp_phase_offset,
                    "collision_radii": collision_radii,
                    "coupled_impacts": [0.0] * node_count,
                }
                yield shared_tick
                # Sequential point/rod constraints can otherwise apply the
                # same external ramp correction to many nodes in one tick,
                # translating the complete body by half a world unit. Keep
                # contact resolution continuous; ordinary motion is far below
                # this 48-units/second safety envelope.
                limit_solver_translation(points, previous, previous_substep_points)
                for index, strength in enumerate(shared_tick["coupled_impacts"]):
                    node_intensity[index] = max(node_intensity[index], strength)
                    frame_intensity = max(frame_intensity, strength)
                    frame_ramp_intensity = max(frame_ramp_intensity, strength)
                    substep_ramp_intensity = max(substep_ramp_intensity, strength)
                if not released:
                    if substep_ramp_contact:
                        ramp_clear_substeps = 0
                        support_grace_substeps = support_grace_limit
                    else:
                        support_grace_substeps = max(0, support_grace_substeps - 1)
                        if time >= exit_time:
                            ramp_clear_substeps += 1
                            if ramp_clear_substeps >= 3:
                                released = True
                                support_grace_substeps = 0

                center_x = sum(point.x for point in points) / node_count
                center_y = sum(point.y for point in points) / node_count
                frames.physics_samples.append(
                    (
                        time,
                        substep_ramp_intensity,
                        substep_receiver_intensity,
                        center_x,
                        center_y,
                    )
                )

                # A clean receiver entry has no collision impulse.  Detect the
                # geometric crossing on the same fixed tick and linearly solve
                # its within-tick time instead of waiting for a rendered frame.
                receiver = variant.receiver
                radius = variant.shape.radius
                previous_low = min(point.y for point in previous_substep_points) - radius
                current_low = min(point.y for point in points) - radius
                drop = previous_low - current_low
                if variant.obstacle.key != "peg-grid" and previous_low > receiver.top >= current_low and drop > 1e-12:
                    crossing_ratio = max(
                        0.0,
                        min(1.0, (previous_low - receiver.top) / drop),
                    )
                    crossing_x = [
                        previous_point.x
                        + (current_point.x - previous_point.x) * crossing_ratio
                        for previous_point, current_point in zip(
                            previous_substep_points,
                            points,
                        )
                    ]
                    # A soft capsule enters progressively: one end crosses,
                    # bends on the rim, then the remaining body follows. Requiring
                    # every solver node plus a full radius to fit on the very
                    # first tick missed the visible 100% entry. Count a genuine
                    # entry once a clear majority of its spine is over the open
                    # aperture; this only records geometry and applies no force.
                    inside_fraction = sum(
                        abs(point_x - receiver.x) + radius < receiver.inner_radius
                        for point_x in crossing_x
                    ) / len(crossing_x)
                    if inside_fraction >= 0.70:
                        crossing_time = (physics_step - 1 + crossing_ratio) * dt
                        frames.receiver_entries.append(
                            (
                                crossing_time,
                                drop / dt,
                                sum(crossing_x) / node_count,
                            )
                        )
        # Contact deformation is sampled for shape keys, but its relaxation is
        # physical time rather than "per rendered frame".  This keeps the gel
        # response identical in a 3 fps scout and a 30 fps production render.
        impact_retention_per_second = 0.44 + softness * 0.28
        node_retention_per_second = 0.48 + softness * 0.30
        impact_memory = max(
            min(1.0, frame_intensity / 8.0),
            impact_memory * impact_retention_per_second ** (1.0 / fps),
        )
        for index in range(node_count):
            local_contact = min(1.0, node_intensity[index] / 6.5)
            node_impact_memory[index] = max(
                local_contact,
                node_impact_memory[index] * node_retention_per_second ** (1.0 / fps),
            )
        frames.append(
            (
                [point.copy() for point in points],
                impact_memory,
                tuple(node_impact_memory),
                frame_ramp_intensity,
                frame_receiver_intensity,
                sum(point.x for point in points) / node_count,
            )
        )
    return frames


def resolve_specimen_contacts(states, depths):
    """Resolve equal-mass body contacts on the same fixed physics tick."""
    pairs = []
    for first_index, first in enumerate(states):
        for second_index in range(first_index + 1, len(states)):
            second = states[second_index]
            minimum = first["radius"] + second["radius"]
            depth = depths[second_index] - depths[first_index]
            if abs(depth) >= minimum:
                continue
            separation = math.sqrt(minimum * minimum - depth * depth)
            a, b = first["points"], second["points"]
            if any(max(point[axis] for point in a) + separation < min(point[axis] for point in b)
                   or max(point[axis] for point in b) + separation < min(point[axis] for point in a)
                   for axis in range(2)):
                continue
            pairs.append((first, second, separation))
    if not pairs:
        return
    for iteration in range(16):
        for first, second, separation in pairs:
            for a_index, a in enumerate(first["points"]):
                for b_index, b in enumerate(second["points"]):
                    delta = b - a
                    if abs(delta.x) >= separation or abs(delta.y) >= separation:
                        continue
                    distance = delta.length
                    if distance >= separation:
                        continue
                    normal = delta / distance if distance > 1e-8 else Vector((1.0, 0.0))
                    correction = normal * ((separation - distance) * 0.5)
                    a -= correction
                    b += correction
                    first["previous"][a_index] -= correction
                    second["previous"][b_index] += correction
                    if iteration == 0:
                        a_velocity = a - first["previous"][a_index]
                        b_velocity = b - second["previous"][b_index]
                        closing = (b_velocity - a_velocity).dot(normal)
                        if closing < 0.0:
                            impulse = -closing * (1.15 - first["softness"] * 0.10) * 0.5
                            first["previous"][a_index] += normal * impulse
                            second["previous"][b_index] -= normal * impulse
                            strength = -closing / first["dt"]
                            first["coupled_impacts"][a_index] = max(first["coupled_impacts"][a_index], strength)
                            second["coupled_impacts"][b_index] = max(second["coupled_impacts"][b_index], strength)
        # Contact impulses must respect each rod's inextensible spine and the
        # same static obstacles; neither body can push the other into a step.
        for state in states:
            points, previous = state["points"], state["previous"]
            direction = range(len(points) - 1) if iteration % 2 == 0 else range(len(points) - 2, -1, -1)
            for index in direction:
                constrain_distance(points, index, index + 1, state["rest"])
            for index in range(len(points)):
                points[index], previous[index], *_unused = collide_point(
                    points[index], previous[index], state["collision_radii"][index],
                    state["softness"], state["time"], state["dt"], state["variant"],
                    state["trial_duration"], state["phase"], False,
                )


def simulate_chain(*args, **kwargs):
    """Single-body compatibility wrapper around the shared 240 Hz solver."""
    ticks = _chain_ticks(*args, **kwargs)
    while True:
        try:
            next(ticks)
        except StopIteration as completed:
            return completed.value


def simulate_specimens(softness, frame_count, fps, variant, stage_index):
    offsets = obstacle_specimen_offsets(variant.obstacle.key)
    depths = obstacle_specimen_depth_offsets(variant.obstacle.key)
    generators = [
        _chain_ticks(softness, frame_count, fps, variant, stage_index, offset,
                     (0.045 if index == 0 else -0.045) if len(offsets) > 1 else 0.0)
        for index, offset in enumerate(offsets)
    ]
    while True:
        states, completed = [], []
        for ticks in generators:
            try:
                states.append(next(ticks))
            except StopIteration as result:
                completed.append(result.value)
        if completed:
            if states:
                raise RuntimeError("Specimen physics clocks diverged")
            return completed
        resolve_specimen_contacts(states, depths)


def contact_events(
    simulated,
    softness: int,
    start: int,
    fps: int,
    variant: SoftBodyVariant,
):
    """Extract debounced Foley cues from the collisions actually simulated."""

    events = []
    stage_offset = (start - 1) / fps
    physics_samples = getattr(simulated, "physics_samples", None)
    physics_dt = float(getattr(simulated, "physics_dt", 1.0 / fps))
    if physics_samples is None:
        # Compatibility for hand-authored diagnostic traces. Production
        # simulations always provide the 240 Hz sidecar above.
        physics_samples = [
            (index / fps, sample[3], sample[4], sample[5])
            for index, sample in enumerate(simulated)
        ]

    def event_frame(local_time: float) -> int:
        local_frame = int(math.floor(local_time * fps + 0.5))
        return min(start + local_frame, start + len(simulated) - 2)

    minimum_gap = 0.14
    peak_radius = max(1, round(0.035 / physics_dt))
    obstacle_key = getattr(getattr(variant, "obstacle", None), "key", "moving-slide")
    primary_contact_kind = "ramp-contact" if obstacle_key == "moving-slide" else "obstacle-contact"
    for kind, sample_index, threshold in (
        (primary_contact_kind, 1, 0.32),
        ("receiver-contact", 2, 0.24),
    ):
        trace = [sample[sample_index] for sample in physics_samples]
        candidates = []
        for index, strength in enumerate(trace):
            left = max(0, index - peak_radius)
            right = min(len(trace), index + peak_radius + 1)
            local_peak = max(trace[left:right])
            # Pick the first sample of a flat maximum. This keeps a sustained
            # contact plateau from becoming render-rate-dependent chatter.
            first_peak = left + trace[left:right].index(local_peak)
            if strength >= threshold and strength == local_peak and index == first_peak:
                candidates.append((index, strength))

        selected = []
        for index, strength in candidates:
            sample_time = float(physics_samples[index][0])
            if (
                selected
                and sample_time - float(physics_samples[selected[-1][0]][0]) < minimum_gap
            ):
                if strength > selected[-1][1]:
                    selected[-1] = (index, strength)
            else:
                selected.append((index, strength))

        # Contact solvers can emit tiny residual peaks while resting.  Preserve
        # the meaningful impacts and cap pathological high-frequency chatter.
        event_limit = 6 if kind in {"ramp-contact", "obstacle-contact"} else 3
        strongest = sorted(selected, key=lambda item: item[1], reverse=True)[:event_limit]
        for index, strength in sorted(strongest):
            local_time = float(physics_samples[index][0])
            center_x = float(physics_samples[index][3])
            events.append(
                {
                    "time": stage_offset + local_time,
                    "frame": event_frame(local_time),
                    "kind": kind,
                    "strength": min(1.0, 0.18 + math.sqrt(strength) * 0.24),
                    "pan": max(-0.72, min(0.72, center_x / 4.2)),
                    "softness": softness,
                }
            )

    # A clean pass through the opening has no rim impulse, but it still has a
    # real geometric event: the lower capsule surface crosses the receiver top.
    # Emit one understated entry cue only when no rim/wall cue already covers it.
    receiver_entries = getattr(simulated, "receiver_entries", None)
    if receiver_entries is None:
        receiver_entries = []
        receiver = variant.receiver
        radius = variant.shape.radius
        for index in range(1, len(simulated)):
            previous_points = simulated[index - 1][0]
            current_points = simulated[index][0]
            previous_low = min(point.y for point in previous_points) - radius
            current_low = min(point.y for point in current_points) - radius
            drop = previous_low - current_low
            if previous_low > receiver.top >= current_low and drop > 1e-12:
                crossing_ratio = (previous_low - receiver.top) / drop
                crossing_x = [
                    previous_point.x
                    + (current_point.x - previous_point.x) * crossing_ratio
                    for previous_point, current_point in zip(previous_points, current_points)
                ]
                if max(
                    abs(point_x - receiver.x) + radius for point_x in crossing_x
                ) < receiver.inner_radius:
                    receiver_entries.append(
                        (
                            (index - 1 + crossing_ratio) / fps,
                            drop * fps,
                            sum(crossing_x) / len(crossing_x),
                        )
                    )

    for local_time, crossing_speed, center_x in receiver_entries:
        event_time = stage_offset + float(local_time)
        nearby_contact = any(
            event["kind"] == "receiver-contact"
            and abs(float(event["time"]) - event_time) <= 0.18
            for event in events
        )
        if not nearby_contact:
            events.append(
                {
                    "time": event_time,
                    "frame": event_frame(float(local_time)),
                    "kind": "receiver-entry",
                    "strength": min(0.68, 0.28 + float(crossing_speed) * 0.055),
                    "pan": max(-0.72, min(0.72, float(center_x) / 4.2)),
                    "softness": softness,
                }
            )
        break
    return sorted(events, key=lambda event: event["time"])


def simulation_quality(simulated, variant: SoftBodyVariant) -> dict[str, object]:
    """Return a publication gate derived from the actual fixed-clock motion."""

    expected_rest = 2.0 * variant.shape.cylinder_half / 40.0
    minimum_ratio = math.inf
    maximum_ratio = 0.0
    maximum_coordinate = 0.0
    maximum_side_or_top = 0.0
    finite = True
    centers_y = []
    for points, *_rest in simulated:
        centers_y.append(sum(point.y for point in points) / len(points))
        for point in points:
            finite = finite and math.isfinite(point.x) and math.isfinite(point.y)
            maximum_coordinate = max(maximum_coordinate, abs(point.x), abs(point.y))
            maximum_side_or_top = max(maximum_side_or_top, abs(point.x), point.y)
        for first, second in zip(points, points[1:]):
            ratio = (second - first).length / expected_rest
            minimum_ratio = min(minimum_ratio, ratio)
            maximum_ratio = max(maximum_ratio, ratio)

    physics_samples = getattr(simulated, "physics_samples", ())
    contact_peak = max((float(sample[1]) for sample in physics_samples), default=0.0)
    physics_centers = [
        (float(sample[3]), float(sample[4]))
        for sample in physics_samples
        if len(sample) >= 5
    ]
    maximum_physics_step = max(
        (
            math.dist(first, second)
            for first, second in zip(physics_centers, physics_centers[1:])
        ),
        default=0.0,
    )
    vertical_drop = centers_y[0] - min(centers_y) if centers_y else 0.0
    issues = []
    if not finite:
        issues.append("non-finite-coordinate")
    # The receiver is open underneath; a finished/missed specimen may keep
    # falling while its partners remain on screen. Lower exits are checked
    # by the shared framing gate, not mistaken for an upward/side escape.
    if maximum_side_or_top > 25.0:
        issues.append("left-scene-before-cut")
    if minimum_ratio < 0.82 or maximum_ratio > 1.18:
        issues.append("constraint-tear")
    if contact_peak < 0.20:
        issues.append("missed-obstacle")
    if vertical_drop < 0.65:
        issues.append("stalled-at-spawn")
    if maximum_physics_step > 0.35:
        issues.append("solver-teleport")
    return {
        "contact_peak": round(contact_peak, 4),
        "minimum_segment_ratio": round(minimum_ratio, 4),
        "maximum_segment_ratio": round(maximum_ratio, 4),
        "maximum_physics_step": round(maximum_physics_step, 4),
        "vertical_drop": round(vertical_drop, 4),
        "maximum_coordinate": round(maximum_coordinate, 4),
        "maximum_side_or_top": round(maximum_side_or_top, 4),
        "receiver_entries": len(getattr(simulated, "receiver_entries", ())),
        "first_receiver_entry": (
            round(float(simulated.receiver_entries[0][0]), 4)
            if getattr(simulated, "receiver_entries", ())
            else None
        ),
        "issues": issues,
    }


def skin_capsule(
    base_vertices,
    chain_points,
    softness: float,
    impact: float,
    node_impacts: tuple[float, ...],
    frame: int,
    variant: SoftBodyVariant,
):
    half_length = variant.shape.cylinder_half
    node_count = len(chain_points)
    rest = 2.0 * half_length / (node_count - 1)
    center = sum(chain_points, Vector((0.0, 0.0))) / node_count
    rigid_tangent = (chain_points[-1] - chain_points[0]).normalized()
    visible_deformation, contact_softness, buckling_softness = deformation_response(
        softness
    )
    displayed_points = []
    for index, point in enumerate(chain_points):
        local_x = -half_length + 2.0 * half_length * index / (node_count - 1)
        rigid_point = center + rigid_tangent * local_x
        displayed_points.append(rigid_point.lerp(point, visible_deformation))
    # Reconstruct a continuous rod rather than exposing individual solver
    # particles.  Broad folds survive while the bead-like high frequencies do
    # not, which is the defining visual difference in the OopsiLab reference.
    displayed_points = smooth_centerline(
        displayed_points,
        rest,
        max(0, round(softness * 6.0)),
    )
    smoothed_impacts = list(node_impacts)
    for _ in range(7):
        smoothed_impacts = [smoothed_impacts[0]] + [
            smoothed_impacts[index - 1] * 0.24
            + smoothed_impacts[index] * 0.52
            + smoothed_impacts[index + 1] * 0.24
            for index in range(1, node_count - 1)
        ] + [smoothed_impacts[-1]]
    # Contact-driven axial compression and broad pressure bending provide the
    # visible payoff expected from 75/100% gel.  The deformation comes solely
    # from measured node impulses: in free flight (or at 0%) this is exactly
    # zero.  Both operations preserve the chain centre, while the radius
    # compensation below approximately conserves volume.
    mean_impact = sum(smoothed_impacts) / node_count
    peak_impact = max(smoothed_impacts)
    contact_amount = contact_softness * min(
        0.18,
        mean_impact * 0.14 + peak_impact * 0.075,
    )
    buckling_profile = [0.0] * node_count
    contact_memory = 0.0
    if contact_amount > 1e-6:
        displayed_center = sum(displayed_points, Vector((0.0, 0.0))) / node_count
        display_axis = (displayed_points[-1] - displayed_points[0]).normalized()
        support_normal = Vector((-display_axis.y, display_axis.x))
        if support_normal.y < 0.0:
            support_normal.negate()
        # Pressure travels through the complete volume. The first mode is a
        # broad arch; two wide alternating lobes create the recognisable
        # 75/100% crumple from measured contact pressure. Their centres follow
        # the pressure centroid, never the receiver. Axial coordinates remain
        # monotonic, preventing V spikes and self-crossing loops.
        pressure_amplitude = (
            variant.shape.radius * contact_softness * peak_impact * 0.44
        )
        arch_weights = [
            4.0
            * (index / max(1, node_count - 1))
            * (1.0 - index / max(1, node_count - 1))
            for index in range(node_count)
        ]
        mean_arch = sum(arch_weights) / node_count
        pressure_total = sum(smoothed_impacts)
        pressure_centroid = (
            sum(
                index / max(1, node_count - 1) * value
                for index, value in enumerate(smoothed_impacts)
            )
            / max(pressure_total, 1e-8)
        )
        phase_shift = math.sin(variant.wrinkle_phase) * 0.045
        first_center = max(0.20, min(0.44, pressure_centroid - 0.16 + phase_shift))
        second_center = max(
            0.58,
            min(0.82, pressure_centroid + 0.23 - phase_shift * 0.35),
        )
        mode_values = []
        for index in range(node_count):
            coordinate = index / max(1, node_count - 1)
            envelope = 4.0 * coordinate * (1.0 - coordinate)
            first_lobe = math.exp(-((coordinate - first_center) / 0.16) ** 2)
            second_lobe = math.exp(-((coordinate - second_center) / 0.23) ** 2)
            mode_values.append(
                envelope * (first_lobe - 0.58 * second_lobe)
            )
        mean_mode = sum(mode_values) / node_count
        mode_values = [value - mean_mode for value in mode_values]
        mode_peak = max(1e-8, max(abs(value) for value in mode_values))
        buckling_profile = [value / mode_peak for value in mode_values]
        contact_memory = min(1.0, max(impact, mean_impact, peak_impact * 0.72))
        extreme_boost = 1.0 + 0.55 * buckling_softness ** 3
        buckling_amplitude = (
            variant.shape.radius
            * buckling_softness
            * contact_memory
            * (0.38 + peak_impact * 0.24)
            * extreme_boost
        )
        contact_shape = []
        for index, point in enumerate(displayed_points):
            relative = point - displayed_center
            axial = display_axis * relative.dot(display_axis)
            transverse = relative - axial
            pressure_offset = (arch_weights[index] - mean_arch) * pressure_amplitude
            buckling_offset = buckling_profile[index] * buckling_amplitude
            contact_shape.append(
                displayed_center
                + axial * (1.0 - contact_amount)
                + transverse
                + support_normal * (pressure_offset + buckling_offset)
            )
        for _ in range(3):
            contact_shape = [
                contact_shape[0] * 0.82 + contact_shape[1] * 0.18
            ] + [
                contact_shape[index - 1] * 0.18
                + contact_shape[index] * 0.64
                + contact_shape[index + 1] * 0.18
                for index in range(1, node_count - 1)
            ] + [
                contact_shape[-1] * 0.82 + contact_shape[-2] * 0.18
            ]
        correction = displayed_center - sum(
            contact_shape, Vector((0.0, 0.0))
        ) / node_count
        displayed_points = [point + correction for point in contact_shape]
    result = []
    for base in base_vertices:
        x, y, z = base
        axial_offset = 0.0
        if x <= -half_length:
            first = second = 0
            blend = 0.0
            axial_offset = x + half_length
        elif x >= half_length:
            first = second = node_count - 1
            blend = 0.0
            axial_offset = x - half_length
        else:
            coordinate = (x + half_length) / (2.0 * half_length) * (node_count - 1)
            first = int(math.floor(coordinate))
            second = min(node_count - 1, first + 1)
            blend = coordinate - first
        center = displayed_points[first].lerp(displayed_points[second], blend)
        local_impact = smoothed_impacts[first] * (1.0 - blend) + smoothed_impacts[second] * blend
        local_fold = (
            buckling_profile[first] * (1.0 - blend)
            + buckling_profile[second] * blend
        )
        before = displayed_points[max(0, first - 1)]
        after = displayed_points[min(node_count - 1, second + 1)]
        tangent = (after - before).normalized()
        normal = Vector((-tangent.y, tangent.x))
        center += tangent * axial_offset
        before_index = max(0, first - 1)
        after_index = min(node_count - 1, second + 1)
        expected_span = max(rest, (after_index - before_index) * rest)
        local_stretch = max(
            0.72,
            min(
                1.38,
                (after - before).length
                / max(0.001, expected_span),
            ),
        )
        volume_scale = max(0.88, min(1.15, 1.0 / math.sqrt(local_stretch)))
        contact_compression = min(0.78, local_impact * (0.20 + softness * 0.58))
        cross_radius = max(1e-5, math.sqrt(y * y + z * z))
        lower_weight = max(0.0, -z / cross_radius) ** 1.55
        upper_weight = max(0.0, z / cross_radius) ** 1.8
        # Flatten chiefly the contacting underside, not the whole ring.  The
        # orthogonal expansion approximates incompressible gel and removes the
        # implausible shrinking seen in the previous mesh.
        normal_scale = max(
            0.52,
            1.0 - contact_compression * (0.56 * lower_weight + 0.10 * upper_weight),
        )
        mean_height_scale = max(0.62, 1.0 - contact_compression * 0.30)
        depth_scale = min(1.28, 1.0 / math.sqrt(mean_height_scale))
        # Two asymmetric, contact-fed surface creases add the localized folds
        # visible in the reference without periodically changing the complete
        # radius. One crease lives chiefly on the upper skin and the opposing
        # one on the underside; the displaced volume expands out of plane.
        fold_contact = (
            buckling_softness
            * contact_memory
            * abs(local_fold)
            * (1.0 + 0.45 * buckling_softness ** 3)
        )
        fold_crease = min(0.18, fold_contact * (0.13 + local_impact * 0.05))
        crease_side = upper_weight if local_fold >= 0.0 else lower_weight
        normal_scale *= 1.0 - fold_crease * (0.22 + crease_side * 0.78)
        depth_scale = min(
            1.36,
            depth_scale / math.sqrt(max(0.72, 1.0 - fold_crease * 0.62)),
        )
        radius_scale = volume_scale
        result.append(
            (
                center.x + normal.x * z * radius_scale * normal_scale,
                -0.04 + y * radius_scale * depth_scale,
                center.y + normal.y * z * radius_scale * normal_scale,
            )
        )
    return result


class ObstacleSurface:
    """Ray-query the evaluated, visible mesh rather than a second approximation.

    Skin smoothing and pressure folds happen after the spine solver.  Rays
    from the physical spine to that skin keep the cosmetic deformation on
    the outside of the actual bevelled obstacle (including thin peg bars).
    """

    def __init__(self, objects):
        self.objects = tuple(objects)
        self.animated = any(
            obj.animation_data or (obj.parent and obj.parent.animation_data)
            for obj in self.objects
        )
        self.cached_frame = None
        self.tree = None
        self.render_targets = None

    def final_contact_targets(self):
        if self.render_targets is None:
            self.render_targets = build_contact_targets(self.objects)
        return self.render_targets

    def at_frame(self, frame):
        key = frame if self.animated else 0
        if self.cached_frame == key:
            return self.tree
        bpy.context.scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        vertices, faces = [], []
        for obj in self.objects:
            if obj.type not in {"MESH", "CURVE"}:
                continue
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            if mesh is None:
                continue
            try:
                bm = bmesh.new()
                bm.from_mesh(mesh)
                # Curve bevel caps duplicate the rim vertices. Recalculating
                # their normals as disconnected disks can turn an exterior
                # entry into a false inside-spine report. Weld only coincident
                # vertices in this temporary query mesh before orienting it.
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
                bm.to_mesh(mesh)
                bm.free()
                offset = len(vertices)
                vertices.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
                faces.extend(tuple(offset + index for index in face.vertices) for face in mesh.polygons)
            finally:
                evaluated.to_mesh_clear()
        self.tree = BVHTree.FromPolygons(vertices, faces, all_triangles=False) if faces else None
        self.cached_frame = key
        return self.tree


def constrain_visible_skin(shape, base_vertices, chain_points, variant, tree, depth_offset=0.0,
                           verify_closed_volume=False):
    """Clip only contact-side skin rays; leave free-flight vertices unchanged."""

    if tree is None:
        return shape, {"corrected_vertices": 0, "maximum_correction": 0.0, "inside_contacts": 0}
    half_length = variant.shape.cylinder_half
    margin = 0.008
    corrected = []
    count, inside = 0, 0
    maximum = 0.0
    anchor_membership = {}
    for base, position in zip(base_vertices, shape):
        coordinate = max(0.0, min(len(chain_points) - 1.0,
            (base[0] + half_length) / (2.0 * half_length) * (len(chain_points) - 1)))
        first = int(coordinate)
        second = min(first + 1, len(chain_points) - 1)
        spine = chain_points[first].lerp(chain_points[second], coordinate - first)
        anchor = Vector((spine.x, depth_offset - 0.04, spine.y))
        target = Vector((position[0], position[1] + depth_offset, position[2]))
        direction = target - anchor
        distance = direction.length
        if distance > 1e-8:
            direction /= distance
            hit, normal, _face, hit_distance = tree.ray_cast(anchor, direction, distance + margin)
            if hit is not None:
                starts_inside = normal.dot(direction) > 1e-4
                if verify_closed_volume:
                    # A folded companion can have a locally reversed face.
                    # Test its closed volume, not that face's orientation;
                    # all vertices in an axial ring share the same anchor.
                    key = tuple(anchor)
                    if key not in anchor_membership:
                        anchor_membership[key] = point_inside_closed_surface(tree, anchor)
                    starts_inside = anchor_membership[key]
                if starts_inside:
                    # This is an exit, not an entry: the physical spine is
                    # already inside a visible obstacle. Do not hide it with
                    # a huge cosmetic projection; fail the publication gate.
                    inside += 1
                else:
                    limited = anchor + direction * max(0.0, hit_distance - margin)
                    maximum = max(maximum, (target - limited).length)
                    target = limited
                    count += 1
        corrected.append((target.x, target.y - depth_offset, target.z))
    return corrected, {
        "corrected_vertices": count,
        "maximum_correction": maximum,
        "inside_contacts": inside,
    }


def capsule_frame_shape(base_vertices, faces, simulated, index, softness, variant,
                        obstacle_surface, frame, depth=0.0, companions=()):
    """Shared production/audit cage deformation and visible contact skin."""
    points, impact, nodes, *_rest = simulated[index]
    shape = skin_capsule(base_vertices, points, softness / 100.0, impact, nodes, index, variant)
    quality = {"corrected_vertices": 0, "maximum_correction": 0.0, "inside_contacts": 0}
    if obstacle_surface is None:
        return shape, quality
    tree = obstacle_surface.at_frame(frame)
    shape, quality = constrain_visible_skin(shape, base_vertices, points, variant, tree, depth)
    for companion, companion_depth in companions:
        other_points, other_impact, other_nodes, *_other = companion[index]
        other_shape = skin_capsule(base_vertices, other_points, softness / 100.0,
                                   other_impact, other_nodes, index, variant)
        other_shape, _other_quality = constrain_visible_skin(
            other_shape, base_vertices, other_points, variant, tree, companion_depth)
        other_tree = BVHTree.FromPolygons(
            [(x, y + companion_depth, z) for x, y, z in other_shape], faces, all_triangles=False)
        shape, contact = constrain_visible_skin(
            shape, base_vertices, points, variant, other_tree, depth, verify_closed_volume=True)
        quality["inside_contacts"] += contact["inside_contacts"]
        quality["maximum_correction"] = max(quality["maximum_correction"], contact["maximum_correction"])
        quality["corrected_vertices"] += contact["corrected_vertices"]
    return shape, quality


def specimen_geometry(vertices, faces, bounds_points=()):
    points = list(vertices) + list(bounds_points)
    low = tuple(min(vertex[axis] for vertex in points) for axis in range(3))
    high = tuple(max(vertex[axis] for vertex in points) for axis in range(3))
    return vertices, faces, low, high


def specimen_bounds_overlap(first, second):
    return all(first[3][axis] >= second[2][axis] and second[3][axis] >= first[2][axis] for axis in range(3))


def specimen_geometry_penetration(bodies):
    maximum = 0.0
    for first_index, first in enumerate(bodies):
        for second in bodies[first_index + 1:]:
            if not specimen_bounds_overlap(first, second):
                continue
            for source, target in ((first, second), (second, first)):
                tree = BVHTree.FromPolygons(target[0], target[1], all_triangles=False)
                for point in source[0]:
                    if any(point[axis] < target[2][axis] or point[axis] > target[3][axis] for axis in range(3)):
                        continue
                    hit, _normal, _face, distance = tree.find_nearest(point)
                    if hit is not None and distance > maximum and point_inside_closed_surface(tree, point):
                        maximum = distance
    return maximum


def inspect_specimen_intersections(objects, start, end):
    """Reject visible interpenetration between independently released bodies.

    The dense contact-corrected cage is checked at every output frame. AABB
    rejection keeps disjoint stair lanes cheap; closed-volume parity tests
    distinguish penetration from a point beside a concave contact crease.
    """
    if len(objects) < 2:
        return {"frames_checked": 0, "maximum_penetration": 0.0, "issues": []}
    modifiers = [(modifier, modifier.show_viewport) for obj in objects for modifier in obj.modifiers]
    maximum = 0.0
    peak_frame = None
    try:
        for modifier, _value in modifiers:
            modifier.show_viewport = False
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            bodies = []
            for obj in objects:
                evaluated = obj.evaluated_get(depsgraph)
                mesh = evaluated.to_mesh()
                try:
                    vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
                    faces = [tuple(face.vertices) for face in mesh.polygons]
                    bodies.append(specimen_geometry(vertices, faces))
                finally:
                    evaluated.to_mesh_clear()
            penetration = specimen_geometry_penetration(bodies)
            if penetration > maximum:
                maximum, peak_frame = penetration, frame
    finally:
        for modifier, value in modifiers:
            modifier.show_viewport = value
    return {
        "frames_checked": end - start + 1,
        "maximum_penetration": round(maximum, 6),
        "peak_frame": peak_frame,
        "issues": ["specimens-interpenetrate"] if maximum > 0.008 else [],
    }


def keyframe_visibility(obj, start: int, end: int, frame_end: int) -> None:
    obj.hide_render = start > 1
    obj.keyframe_insert("hide_render", frame=1)
    if start > 1:
        obj.keyframe_insert("hide_render", frame=start - 1)
    obj.hide_render = False
    obj.keyframe_insert("hide_render", frame=start)
    obj.keyframe_insert("hide_render", frame=end)
    if end < frame_end:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=end + 1)


def add_capsule(
    gold,
    softness: int,
    start: int,
    end: int,
    frame_end: int,
    fps: int,
    variant: SoftBodyVariant,
    stage_index: int,
    instance_index: int = 0,
    instance_offset_x: float = 0.0,
    instance_offset_y: float = 0.0,
    instance_rotation_offset: float = 0.0,
    render_subdivision: int = 3,
    obstacle_surface=None,
    precomputed_simulation=None,
    companion_simulations=(),
):
    base_vertices, faces = capsule_geometry(variant)
    simulated = precomputed_simulation if precomputed_simulation is not None else simulate_chain(
        softness,
        end - start + 1,
        fps,
        variant,
        stage_index,
        instance_offset_x,
        instance_rotation_offset,
    )
    events = contact_events(simulated, softness, start, fps, variant)
    quality = simulation_quality(simulated, variant)
    for event in events:
        event["body"] = instance_index + 1
    # The final state exists for FPS-independent outcome/event auditing at the
    # exact trial boundary. Keep only the preceding N samples as N visible
    # shape keys, otherwise Blender would compress N+1 states into N frames.
    visible_simulated = simulated[:-1]
    shapes = []
    surface_quality = {"corrected_vertices": 0, "maximum_correction": 0.0, "inside_contacts": 0}
    for index in range(len(visible_simulated)):
        shape, surface_sample = capsule_frame_shape(
            base_vertices, faces, simulated, index, softness, variant,
            obstacle_surface, start + index, instance_offset_y, companion_simulations,
        )
        surface_quality["corrected_vertices"] += surface_sample["corrected_vertices"]
        surface_quality["maximum_correction"] = max(
            surface_quality["maximum_correction"], surface_sample["maximum_correction"],
        )
        surface_quality["inside_contacts"] += surface_sample["inside_contacts"]
        shapes.append(shape)
    quality["surface"] = surface_quality
    if surface_quality["inside_contacts"]:
        quality["issues"].append("spine-inside-visible-obstacle")
    capsule = add_mesh(
        f"Sliding cylinder {softness}% body {instance_index + 1}",
        shapes[0],
        faces,
        gold,
    )
    capsule.location.y = instance_offset_y
    basis = capsule.shape_key_add(name="Basis")
    capsule.data.shape_keys.use_relative = False
    for index, shape in enumerate(shapes[1:], start=1):
        key = capsule.shape_key_add(name=f"Physics {index:03d}")
        for point, coordinate in zip(key.data, shape):
            point.co = coordinate
    keys = capsule.data.shape_keys
    keys.eval_time = basis.frame
    keys.keyframe_insert("eval_time", frame=start)
    keys.eval_time = keys.key_blocks[-1].frame
    keys.keyframe_insert("eval_time", frame=end)
    if keys.animation_data and keys.animation_data.action:
        for curve in keys.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    keyframe_visibility(capsule, start, end, frame_end)
    if capsule.animation_data and capsule.animation_data.action:
        for curve in capsule.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"
    subdivision = capsule.modifiers.new("Polished capsule surface", "SUBSURF")
    subdivision.subdivision_type = "CATMULL_CLARK"
    subdivision.levels = min(2, render_subdivision)
    subdivision.render_levels = render_subdivision
    if obstacle_surface is not None:
        add_final_surface_contact(capsule, obstacle_surface.final_contact_targets())
    return capsule, events, quality


def add_receiver(marble, gold, variant: SoftBodyVariant):
    if variant.obstacle.key == "peg-grid":
        return
    if variant.obstacle.key == "stair-cascade":
        return add_curved_receivers(add_mesh, material, obstacle_specimen_depth_offsets("stair-cascade"))
    add_receiver_tube(marble, gold, variant)


def add_receiver_tube(marble, gold, variant: SoftBodyVariant):
    segments = 128
    receiver = variant.receiver
    outer_radius, inner_radius = receiver.outer_radius, receiver.inner_radius
    top = receiver.top
    bottom = 0.40 if variant.obstacle.key == "stair-cascade" else -3.40
    vertices = []
    for segment in range(segments):
        angle = math.tau * segment / segments
        cosine, sine = math.cos(angle), math.sin(angle)
        vertices.extend(
            (
                (receiver.x + outer_radius * cosine, outer_radius * sine, top),
                (receiver.x + outer_radius * cosine, outer_radius * sine, bottom),
                (receiver.x + inner_radius * cosine, inner_radius * sine, top - 0.08),
                (receiver.x + inner_radius * cosine, inner_radius * sine, bottom),
            )
        )
    faces = []
    for segment in range(segments):
        following = (segment + 1) % segments
        current, next_index = segment * 4, following * 4
        faces.extend(
            (
                (current, next_index, next_index + 1, current + 1),
                (current + 2, current + 3, next_index + 3, next_index + 2),
                (current, current + 2, next_index + 2, next_index),
                (current + 1, next_index + 1, next_index + 3, current + 3),
            )
        )
    wall = add_mesh("Open marble receiver", vertices, faces, marble, bevel_width=0.035)

    bpy.ops.mesh.primitive_torus_add(
        major_segments=96,
        minor_segments=16,
        location=(receiver.x, 0.0, top),
        major_radius=(outer_radius + inner_radius) * 0.5,
        minor_radius=(outer_radius - inner_radius) * 0.28,
    )
    rim = bpy.context.object
    rim.name = "Champagne receiver rim"
    rim.data.materials.append(gold)
    for polygon in rim.data.polygons:
        polygon.use_smooth = True
    return wall, rim


def look_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(name: str, location, energy: float, size: float, color, target=(0.0, 0.0, 3.2)):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    data.color = color
    data.use_shadow = True
    if hasattr(data, "use_contact_shadow"):
        data.use_contact_shadow = True
        data.contact_shadow_bias = 0.01
        data.contact_shadow_thickness = 0.08
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def add_background(value):
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0.0, 3.2, 3.25), rotation=(math.pi / 2, 0.0, 0.0))
    backdrop = bpy.context.object
    backdrop.name = "Horizonless clouded backdrop"
    # The complete backdrop must cover the widened multi-body cameras too;
    # otherwise its lower edge exposes a dark world-colour "floor".
    backdrop.scale = (20.0, 20.0, 1.0)
    backdrop.data.materials.append(value)
    return backdrop


def add_camera(variant: SoftBodyVariant):
    target = variant.obstacle
    bpy.ops.object.camera_add(location=camera_location(target))
    camera = bpy.context.object
    camera.name = "Fixed reference camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = target.camera_scale
    camera.data.lens = 70
    look_at(camera, (target.camera_target_x, 0.0, target.camera_target_z))
    bpy.context.scene.camera = camera
    return camera


def main() -> None:
    args = arguments()
    args.frames = str(Path(args.frames).resolve())
    reset_scene()
    variant = variant_for_seed(args.seed, args.obstacle)
    frame_end = max(5, round(args.duration * args.fps))
    stages, stage_indices = stage_selection_for(variant, args.stage_softness)
    if args.stage_softness is None:
        spans = stage_frame_spans(frame_end, len(stages), variant.obstacle.key, stages)
    else:
        spans = ((1, frame_end),)

    stage_spans = tuple(
        (stage_index, start, end)
        for stage_index, (start, end) in zip(stage_indices, spans)
    )
    trial_spans = tuple(
        (stage_index + attempt_index * len(variant.stages), trial_start, trial_end)
        for softness, (stage_index, start, end) in zip(stages, stage_spans)
        for attempt_index, (trial_start, trial_end) in enumerate(
            stage_attempt_frame_spans(start, end, args.fps, variant.obstacle.key, softness)
        )
    )

    gold = liquid_gold_material(args.seed, variant)
    marble = marble_material(variant)
    backdrop = background_material(variant)
    add_background(backdrop)
    add_receiver(marble, gold, variant)
    if variant.obstacle.key == "moving-slide":
        add_ramp(marble, gold, variant, frame_end, args.fps, trial_spans)
    else:
        add_obstacle_geometry(marble, gold, variant, frame_end, args.fps, trial_spans)
    obstacle_surface = ObstacleSurface(
        obj for obj in bpy.context.collection.objects
        if obj.name != "Horizonless clouded backdrop"
    )
    all_events = []
    attempt_quality = []
    attempt_cut_frames = []
    for softness, (stage_index, start, end) in zip(stages, stage_spans):
        attempt_spans = stage_attempt_frame_spans(
            start,
            end,
            args.fps,
            variant.obstacle.key,
            softness,
        )
        for attempt_index, (attempt_start, attempt_end) in enumerate(attempt_spans):
            attempt_objects = []
            attempt_reports = []
            print(json.dumps({"phase": "simulate", "obstacle": variant.obstacle.key,
                              "softness": softness, "attempt": attempt_index + 1,
                              "start_frame": attempt_start, "end_frame": attempt_end}), flush=True)
            if attempt_index:
                attempt_cut_frames.append(attempt_start)
            specimen_offsets = obstacle_specimen_offsets(variant.obstacle.key)
            specimen_depths = obstacle_specimen_depth_offsets(variant.obstacle.key)
            simulations = simulate_specimens(
                softness, attempt_end - attempt_start + 1, args.fps, variant,
                stage_index + attempt_index * len(variant.stages),
            )
            framing = inspect_simulation_framing(simulations, variant, args.fps)
            for instance_index, instance_offset in enumerate(specimen_offsets):
                rotation_offset = 0.0
                if len(specimen_offsets) > 1:
                    rotation_offset = 0.045 if instance_index == 0 else -0.045
                _capsule, events, quality = add_capsule(
                    gold,
                    softness,
                    attempt_start,
                    attempt_end,
                    frame_end,
                    args.fps,
                    variant,
                    stage_index + attempt_index * len(variant.stages),
                    instance_index,
                    instance_offset,
                    specimen_depths[instance_index],
                    rotation_offset,
                    1 if args.width < 360 else 3,
                    obstacle_surface,
                    simulations[instance_index],
                    tuple((simulation, specimen_depths[index]) for index, simulation in enumerate(simulations) if index != instance_index),
                )
                all_events.extend(events)
                quality["framing"] = framing
                quality["issues"].extend(framing["issues"])
                attempt_objects.append(_capsule)
                attempt_reports.append({
                        "stage": stage_index + 1,
                        "softness": softness,
                        "attempt": attempt_index + 1,
                        "body": instance_index + 1,
                        "start_frame": attempt_start,
                        "end_frame": attempt_end,
                        **quality,
                })
            intersections = inspect_specimen_intersections(attempt_objects, attempt_start, attempt_end)
            for report in attempt_reports:
                report["inter_body_contact"] = intersections
                report["issues"].extend(intersections["issues"])
                attempt_quality.append(report)
            for capsule, report in zip(attempt_objects, attempt_reports):
                rendered_surface = inspect_rendered_surface(capsule, obstacle_surface, attempt_start, attempt_end)
                report["rendered_surface"] = rendered_surface
                report["issues"].extend(rendered_surface["issues"])
                print(json.dumps({"phase": "native-surface-checked", "body": capsule.name,
                                  "start_frame": attempt_start, "end_frame": attempt_end,
                                  **rendered_surface}), flush=True)

    if args.events:
        events_path = Path(args.events)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            json.dumps(
                {
                    "preflight_schema": 3,
                    "obstacle": variant.obstacle.key,
                    "fps": args.fps,
                    "duration": frame_end / args.fps,
                    "stages": list(stages),
                    "attempt_cuts": attempt_cut_frames,
                    "attempt_quality": attempt_quality,
                    "events": all_events,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    failed_attempts = [item for item in attempt_quality if item["issues"]]
    if failed_attempts:
        raise RuntimeError(
            "Soft-body publication preflight failed: "
            + json.dumps(failed_attempts, separators=(",", ":"))
        )

    add_camera(variant)

    key_color = mix_color(variant.palette.key_light, (1.0, 0.93, 0.83), 0.72)
    fill_color = mix_color(variant.palette.fill_light, (0.75, 0.86, 1.0), 0.72)
    add_area("Large warm key", (-4.8, -6.5, 9.0), 1220, 5.4, key_color)
    add_area("Broad neutral fill", (4.8, -4.0, 6.6), 880, 4.8, fill_color)
    add_area("Metal rim light", (0.5, 2.8, 8.1), 1080, 3.8, (1.0, 0.86, 0.66))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 2.5
    scene.eevee.gtao_factor = 1.05
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.008
    scene.eevee.bloom_radius = 2.0
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_ssr = True
    scene.eevee.ssr_quality = 1.0
    scene.eevee.ssr_max_roughness = 0.8
    if hasattr(scene.eevee, "use_high_quality_normals"):
        scene.eevee.use_high_quality_normals = True
    scene.eevee.use_motion_blur = True
    scene.eevee.motion_blur_shutter = 0.08
    scene.eevee.taa_render_samples = args.samples
    scene.eevee.shadow_cube_size = "4096"
    scene.eevee.shadow_cascade_size = "4096"
    scene.gravity = (0.0, 0.0, -9.81 * variant.gravity_scale)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    scene.render.dither_intensity = 1.0
    scene.render.filepath = str(Path(args.frames) / "frame_")
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.film_transparent = False
    studio_world = mix_color(
        tuple(
            (low + high) * 0.5
            for low, high in zip(variant.palette.background_low, variant.palette.background_high)
        ),
        (0.45, 0.51, 0.57),
        0.84,
    )
    scene.world.color = studio_world
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.38
    scene.view_settings.gamma = 1.0
    scene.render.use_file_extension = True

    frames = Path(args.frames)
    frames.mkdir(parents=True, exist_ok=True)
    suffix = str(stages[0]) if len(stages) == 1 else "comparison"
    bpy.ops.wm.save_as_mainfile(filepath=str(frames / f"soft-body-{suffix}.blend"))
    if not args.build_only:
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
