"""Render a seeded five-stage Oopsi-style soft-body comparison.

Each seed resolves to a reproducible combination of shape, moving ramp, studio
palette, receiver, softness progression and deterministic constraint physics.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from soft_body_variants import SoftBodyVariant, variant_for_seed



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
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), required=True)
    parser.add_argument("--title", required=True)
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


def marble_material(variant: SoftBodyVariant):
    palette = variant.palette
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
    ramp.color_ramp.elements[0].color = (*palette.marble_base, 1)
    pre_vein = ramp.color_ramp.elements.new(0.41)
    pre_vein.color = (*tuple(channel * 0.97 for channel in palette.marble_base), 1)
    vein = ramp.color_ramp.elements.new(0.455)
    # Keep the stone readable at phone size without the near-black dashes that
    # a narrow procedural vein produces under Filmic High Contrast.
    vein.color = (
        *tuple(
            base * 0.72 + vein_channel * 0.28
            for base, vein_channel in zip(palette.marble_base, palette.marble_vein)
        ),
        1,
    )
    after_vein = ramp.color_ramp.elements.new(0.50)
    after_vein.color = (*tuple(channel * 0.98 for channel in palette.marble_base), 1)
    light = ramp.color_ramp.elements.new(0.61)
    light.color = (*palette.marble_light, 1)
    ramp.color_ramp.elements[-1].position = 0.75
    ramp.color_ramp.elements[-1].color = (*palette.marble_light, 1)
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
    ramp.color_ramp.elements[0].color = (*palette.background_low, 1)
    ramp.color_ramp.elements[1].position = 0.77
    ramp.color_ramp.elements[1].color = (*palette.background_high, 1)
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
    base = variant.palette.metal
    value = material(
        f"{variant.palette.label} liquid metal",
        (
            max(0.0, min(1.0, base[0] + variation)),
            max(0.0, min(1.0, base[1] + variation * 0.7)),
            max(0.0, min(1.0, base[2] + variation * 0.4)),
            1,
        ),
        metallic=1.0,
        roughness=variant.palette.metal_roughness,
        clearcoat=0.36,
    )
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 2.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.025
    bump.inputs["Distance"].default_value = 0.018
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
    collision_lift = 0.13 if collision else 0.0
    lip_scale = 0.84 if collision else 1.0
    wave = ramp.wave * math.sin(ramp.wave_frequency * local_x + ramp.wave_phase)
    return ramp.base + collision_lift + ramp.slope * local_x + wave + ramp.lip_rise * lip_scale * smooth_lip


def physics_ramp_height(local_x: float, variant: SoftBodyVariant) -> float:
    return ramp_height(local_x, variant, collision=True)


def ramp_points(variant: SoftBodyVariant, segments: int = 112):
    return [
        (variant.ramp.minimum + (variant.ramp.maximum - variant.ramp.minimum) * index / (segments - 1),)
        for index in range(segments)
    ]


def effective_ramp_exit_time(variant: SoftBodyVariant, trial_duration: float) -> float:
    # Presets were authored for three-second trials.  Longer cinematic trials
    # keep the ramp alive for multiple sweeps, then reserve the same natural
    # fall/landing window at the end.
    landing_window = 3.0 - variant.ramp.exit_time
    return max(0.8, trial_duration - landing_window)


def ramp_position(time: float, variant: SoftBodyVariant, trial_duration: float) -> float:
    ramp = variant.ramp
    period = ramp.sweep_period
    exit_time = effective_ramp_exit_time(variant, trial_duration)

    def sweep(at: float) -> float:
        return ramp.sweep_amplitude * math.sin(
            math.tau * at / period - math.pi / 2 + variant.motion_phase
        ) + ramp.secondary_amplitude * math.sin(
            math.tau * at / (period * 0.5) - 0.18 - variant.motion_phase * 0.5
        )

    if time <= exit_time:
        return sweep(time)
    exit_duration = 0.22
    ratio = max(0.0, min(1.0, (time - exit_time) / exit_duration))
    smooth = ratio * ratio * (3.0 - 2.0 * ratio)
    origin = sweep(exit_time)
    return origin + (ramp.exit_x - origin) * smooth


def ramp_velocity(time: float, variant: SoftBodyVariant, trial_duration: float) -> float:
    ramp = variant.ramp
    period = ramp.sweep_period
    exit_time = effective_ramp_exit_time(variant, trial_duration)
    if time <= exit_time:
        return (
            ramp.sweep_amplitude * math.tau / period
            * math.cos(math.tau * time / period - math.pi / 2 + variant.motion_phase)
            + ramp.secondary_amplitude * math.tau / (period * 0.5)
            * math.cos(math.tau * time / (period * 0.5) - 0.18 - variant.motion_phase * 0.5)
        )
    exit_duration = 0.22
    ratio = max(0.0, min(1.0, (time - exit_time) / exit_duration))
    origin = ramp_position(exit_time, variant, trial_duration)
    return (ramp.exit_x - origin) * 6.0 * ratio * (1.0 - ratio) / exit_duration


def ramp_slope(local_x: float, variant: SoftBodyVariant, collision: bool = False) -> float:
    ramp = variant.ramp
    lip = max(0.0, min(1.0, (local_x - ramp.minimum) / ramp.lip_width))
    lip_scale = 0.84 if collision else 1.0
    return (
        ramp.slope
        + ramp.wave * ramp.wave_frequency * math.cos(ramp.wave_frequency * local_x + ramp.wave_phase)
        + ramp.lip_rise * lip_scale * 6.0 * lip * (1.0 - lip) / ramp.lip_width
    )


def physics_ramp_slope(local_x: float, variant: SoftBodyVariant) -> float:
    return ramp_slope(local_x, variant, collision=True)


def add_ramp(marble, gold, variant: SoftBodyVariant, frame_end: int, fps: int, stage_frames: int):
    segments = 192
    half_width, thickness = variant.ramp.half_width, variant.ramp.thickness
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
        curve.bevel_depth = 0.025
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
        local_frame = (frame - 1) % stage_frames
        ramp.location.x = ramp_position(local_frame / fps, variant, stage_frames / fps)
        ramp.keyframe_insert("location", frame=frame)
    if ramp.animation_data and ramp.animation_data.action:
        for curve in ramp.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    return ramp


def capsule_geometry(
    variant: SoftBodyVariant,
    radial_segments: int = 48,
    cap_rings: int = 10,
    cylinder_rings: int = 16,
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


def collide_point(
    point: Vector,
    previous: Vector,
    radius: float,
    softness: float,
    time: float,
    dt: float,
    variant: SoftBodyVariant,
    trial_duration: float,
) -> tuple[Vector, Vector, float]:
    intensity = 0.0
    local_x = point.x - ramp_position(time, variant, trial_duration)
    if variant.ramp.minimum <= local_x <= variant.ramp.maximum:
        height = physics_ramp_height(local_x, variant)
        slope = physics_ramp_slope(local_x, variant)
        normal = Vector((-slope, 1.0)).normalized()
        signed_distance = (point.y - height) / math.sqrt(1.0 + slope * slope)
        if point.y > height - 0.55 and signed_distance < radius:
            point += normal * (radius - signed_distance)
            velocity = point - previous
            ramp_step = Vector((ramp_velocity(time, variant, trial_duration) * dt, 0.0))
            relative = velocity - ramp_step
            normal_speed = relative.dot(normal)
            intensity = max(intensity, abs(normal_speed) / max(dt, 1e-6))
            if normal_speed < 0.0:
                restitution = (0.36 - softness * 0.32) * variant.bounce_scale
                tangent = Vector((normal.y, -normal.x))
                velocity -= normal * ((1.0 + restitution) * normal_speed)
                target_tangent = ramp_step.dot(tangent)
                current_tangent = velocity.dot(tangent)
                coupling = (0.11 + (1.0 - softness) * 0.07) * variant.coupling_scale
                velocity += tangent * (target_tangent - current_tangent) * coupling
                velocity *= 0.92 - softness * 0.16
                previous = point - velocity

    # Thin circular rim first, followed by the shallow concave receiver.  The
    # opening remains real: misses continue below frame instead of landing on
    # an invisible cylinder cap.
    receiver = variant.receiver
    rim_major = (receiver.outer_radius + receiver.inner_radius) * 0.5
    rim_minor = (receiver.outer_radius - receiver.inner_radius) * 0.55
    for rim_x in (receiver.x - rim_major, receiver.x + rim_major):
        center = Vector((rim_x, receiver.top))
        delta = point - center
        minimum = radius + rim_minor
        if 1e-7 < delta.length < minimum:
            normal = delta.normalized()
            point = center + normal * minimum
            velocity = point - previous
            normal_speed = velocity.dot(normal)
            intensity = max(intensity, abs(normal_speed) / max(dt, 1e-6))
            if normal_speed < 0.0:
                velocity -= normal * ((1.42 - softness * 0.30) * normal_speed)
                previous = point - velocity * (0.88 - softness * 0.20)

    receiver_x = point.x - receiver.x
    if abs(receiver_x) < receiver.inner_radius and point.y < receiver.top + 0.34:
        ratio = abs(receiver_x) / receiver.inner_radius
        bowl_base = receiver.top - receiver.bowl_depth - 0.06
        height = bowl_base + receiver.bowl_depth * ratio * ratio
        slope = 2.0 * receiver.bowl_depth * receiver_x / (receiver.inner_radius * receiver.inner_radius)
        normal = Vector((-slope, 1.0)).normalized()
        signed_distance = (point.y - height) / math.sqrt(1.0 + slope * slope)
        if signed_distance < radius:
            point += normal * (radius - signed_distance)
            velocity = point - previous
            normal_speed = velocity.dot(normal)
            intensity = max(intensity, abs(normal_speed) / max(dt, 1e-6))
            if normal_speed < 0.0:
                velocity -= normal * ((1.30 - softness * 0.18) * normal_speed)
                velocity *= 0.74 - softness * 0.32
                previous = point - velocity
    return point, previous, intensity


def simulate_chain(softness_percent: int, frame_count: int, fps: int, variant: SoftBodyVariant):
    softness = softness_percent / 100.0
    node_count = 31
    half_length = variant.shape.cylinder_half + variant.shape.radius
    rest = 2.0 * half_length / (node_count - 1)
    rotation = variant.start_rotation
    points = []
    for index in range(node_count):
        local_x = -half_length + rest * index
        points.append(
            Vector(
                (
                    variant.start_x + math.cos(rotation) * local_x,
                    variant.start_height + math.sin(rotation) * local_x,
                )
            )
        )
    previous = [point.copy() for point in points]
    frames = []
    impact_memory = 0.0
    node_impact_memory = [0.0] * node_count
    trial_duration = frame_count / fps
    exit_time = effective_ramp_exit_time(variant, trial_duration)
    substeps = 18
    dt = 1.0 / (fps * substeps)
    iterations = max(32, round(80 - softness * 48))
    bend_strength = 0.98 - softness * 0.90
    horizontal_damping = 0.970 - softness * 0.075
    vertical_damping = 0.993 - softness * 0.005

    for frame in range(frame_count):
        frame_intensity = 0.0
        node_intensity = [0.0] * node_count
        if frame:
            for substep in range(substeps):
                time = ((frame - 1) + (substep + 1) / substeps) / fps
                for index in range(node_count):
                    velocity = points[index] - previous[index]
                    velocity.x *= horizontal_damping
                    velocity.y *= vertical_damping
                    # Moving ramps can otherwise catapult rigid presets outside
                    # the vertical frame before the comparison becomes legible.
                    # The cap behaves like air drag, not an invisible wall, and
                    # still leaves enough lateral motion for distinct outcomes.
                    max_horizontal_step = (2.65 - softness * 0.35) * dt
                    velocity.x = max(-max_horizontal_step, min(max_horizontal_step, velocity.x))
                    if time > exit_time:
                        velocity.x += (variant.receiver.x - points[index].x) * 0.65 * dt * dt
                    previous[index] = points[index].copy()
                    fall_boost = 1.28 if time > exit_time else 1.0
                    points[index] += velocity + Vector(
                        (0.0, -9.81 * variant.gravity_scale * fall_boost * dt * dt)
                    )

                for _ in range(iterations):
                    for index in range(node_count - 1):
                        constrain_distance(points, index, index + 1, rest)
                    for index in range(node_count - 2):
                        constrain_distance(points, index, index + 2, rest * 2.0, bend_strength)
                    for index in range(node_count):
                        profile = math.sin(math.pi * index / (node_count - 1))
                        radius = variant.shape.radius * (0.43 + 0.57 * math.sqrt(max(0.0, profile)))
                        points[index], previous[index], intensity = collide_point(
                            points[index], previous[index], radius, softness, time, dt, variant,
                            trial_duration,
                        )
                        frame_intensity = max(frame_intensity, intensity)
                        node_intensity[index] = max(node_intensity[index], intensity)
        impact_memory = max(min(1.0, frame_intensity / 8.0), impact_memory * (0.78 + softness * 0.13))
        for index in range(node_count):
            local_contact = min(1.0, node_intensity[index] / 6.5)
            node_impact_memory[index] = max(
                local_contact,
                node_impact_memory[index] * (0.76 + softness * 0.19),
            )
        frames.append(
            (
                [point.copy() for point in points],
                impact_memory,
                tuple(node_impact_memory),
            )
        )
    return frames


def skin_capsule(
    base_vertices,
    chain_points,
    softness: float,
    impact: float,
    node_impacts: tuple[float, ...],
    frame: int,
    variant: SoftBodyVariant,
):
    half_length = variant.shape.cylinder_half + variant.shape.radius
    node_count = len(chain_points)
    center = sum(chain_points, Vector((0.0, 0.0))) / node_count
    rigid_tangent = (chain_points[-1] - chain_points[0]).normalized()
    visible_deformation = softness ** 1.35
    displayed_points = []
    for index, point in enumerate(chain_points):
        local_x = -half_length + 2.0 * half_length * index / (node_count - 1)
        rigid_point = center + rigid_tangent * local_x
        displayed_points.append(rigid_point.lerp(point, visible_deformation))
    for _ in range(max(0, round(softness * 3.0))):
        smoothed = [displayed_points[0]]
        for index in range(1, node_count - 1):
            smoothed.append(
                displayed_points[index - 1] * 0.22
                + displayed_points[index] * 0.56
                + displayed_points[index + 1] * 0.22
            )
        smoothed.append(displayed_points[-1])
        displayed_points = smoothed
    smoothed_impacts = list(node_impacts)
    for _ in range(3):
        smoothed_impacts = [smoothed_impacts[0]] + [
            smoothed_impacts[index - 1] * 0.24
            + smoothed_impacts[index] * 0.52
            + smoothed_impacts[index + 1] * 0.24
            for index in range(1, node_count - 1)
        ] + [smoothed_impacts[-1]]
    result = []
    for base in base_vertices:
        x, y, z = base
        coordinate = max(0.0, min(node_count - 1.000001, (x + half_length) / (2.0 * half_length) * (node_count - 1)))
        first = int(math.floor(coordinate))
        second = min(node_count - 1, first + 1)
        blend = coordinate - first
        center = displayed_points[first].lerp(displayed_points[second], blend)
        local_impact = smoothed_impacts[first] * (1.0 - blend) + smoothed_impacts[second] * blend
        before = displayed_points[max(0, first - 1)]
        after = displayed_points[min(node_count - 1, second + 1)]
        tangent = (after - before).normalized()
        normal = Vector((-tangent.y, tangent.x))
        local_stretch = max(
            0.58,
            min(
                1.55,
                (after - before).length
                / max(0.001, 4.0 * half_length / (node_count - 1)),
            ),
        )
        volume_scale = max(0.78, min(1.28, 1.0 / math.sqrt(local_stretch)))
        u = x / half_length
        wrinkle = max(impact * 0.42, local_impact) * softness * softness
        axial_wrinkle = wrinkle * 0.034 * math.sin(
            u * math.pi * 4.2 + frame * 0.21 + variant.wrinkle_phase
        )
        angular = math.atan2(z, y)
        asymmetric = 1.0 + wrinkle * 0.048 * math.sin(
            angular * 3.0 + u * 5.3 + frame * 0.13 + variant.wrinkle_phase * 0.7
        )
        contact_compression = min(0.92, local_impact * softness ** 0.72)
        normal_scale = max(0.42, 1.0 - contact_compression * 0.62)
        depth_scale = min(1.52, 1.0 / math.sqrt(normal_scale))
        radius_scale = volume_scale * asymmetric
        center += normal * axial_wrinkle
        result.append(
            (
                center.x + normal.x * z * radius_scale * normal_scale,
                -0.04 + y * radius_scale * depth_scale,
                center.y + normal.y * z * radius_scale * normal_scale,
            )
        )
    return result


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
):
    base_vertices, faces = capsule_geometry(variant)
    simulated = simulate_chain(softness, end - start + 1, fps, variant)
    shapes = [
        skin_capsule(
            base_vertices,
            points,
            softness / 100.0,
            impact,
            node_impacts,
            index,
            variant,
        )
        for index, (points, impact, node_impacts) in enumerate(simulated)
    ]
    capsule = add_mesh(f"Sliding cylinder {softness}%", shapes[0], faces, gold)
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
    subdivision.levels = 1
    subdivision.render_levels = 2
    return capsule


def add_receiver(marble, gold, variant: SoftBodyVariant):
    segments = 128
    receiver = variant.receiver
    outer_radius, inner_radius = receiver.outer_radius, receiver.inner_radius
    top, bottom = receiver.top, -3.40
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

    rings = 24
    bowl_base = top - receiver.bowl_depth - 0.06
    bowl_vertices = [(receiver.x, 0.0, bowl_base)]
    for ring in range(1, rings + 1):
        ratio = ring / rings
        radius = inner_radius * ratio
        z = bowl_base + receiver.bowl_depth * ratio * ratio
        for segment in range(segments):
            angle = math.tau * segment / segments
            bowl_vertices.append((receiver.x + math.cos(angle) * radius, math.sin(angle) * radius, z))
    bowl_faces = []
    for segment in range(segments):
        bowl_faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
    for ring in range(1, rings):
        inner = 1 + (ring - 1) * segments
        outer = 1 + ring * segments
        for segment in range(segments):
            following = (segment + 1) % segments
            bowl_faces.append((inner + segment, outer + segment, outer + following, inner + following))
    bowl = add_mesh("Concave receiver interior", bowl_vertices, bowl_faces, marble)
    solidify = bowl.modifiers.new("Bowl thickness", "SOLIDIFY")
    solidify.thickness = 0.08

    bpy.ops.mesh.primitive_torus_add(
        major_segments=96,
        minor_segments=16,
        location=(receiver.x, 0.0, top),
        major_radius=(outer_radius + inner_radius) * 0.5,
        minor_radius=(outer_radius - inner_radius) * 0.52,
    )
    rim = bpy.context.object
    rim.name = "Champagne receiver rim"
    rim.data.materials.append(gold)
    for polygon in rim.data.polygons:
        polygon.use_smooth = True


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
    backdrop.scale = (7.5, 6.5, 1.0)
    backdrop.data.materials.append(value)
    return backdrop


def main() -> None:
    args = arguments()
    reset_scene()
    variant = variant_for_seed(args.seed)
    frame_end = max(5, round(args.duration * args.fps))
    if args.stage_softness is None:
        stages = variant.stages
        stage_frames = max(2, round(frame_end / len(stages)))
        frame_end = stage_frames * len(stages)
    else:
        stages = (min(variant.stages, key=lambda level: abs(level - args.stage_softness)),)
        stage_frames = frame_end

    gold = liquid_gold_material(args.seed, variant)
    marble = marble_material(variant)
    backdrop = background_material(variant)
    add_background(backdrop)
    add_receiver(marble, gold, variant)
    add_ramp(marble, gold, variant, frame_end, args.fps, stage_frames)
    for index, softness in enumerate(stages):
        start = 1 + index * stage_frames
        end = min(frame_end, (index + 1) * stage_frames)
        add_capsule(gold, softness, start, end, frame_end, args.fps, variant)

    bpy.ops.object.camera_add(location=(0.0, -14.8, 4.55))
    camera = bpy.context.object
    camera.name = "Fixed reference camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.35
    camera.data.lens = 70
    look_at(camera, (0.0, 0.0, 3.18))
    bpy.context.scene.camera = camera

    add_area("Large warm key", (-4.8, -6.5, 9.0), 1150, 5.2, variant.palette.key_light)
    add_area("Broad neutral fill", (4.8, -4.0, 6.6), 820, 4.5, variant.palette.fill_light)
    add_area("Metal rim light", (0.5, 2.8, 8.1), 1050, 3.6, (1.0, 0.83, 0.61))

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
    scene.eevee.motion_blur_shutter = 0.18
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
    scene.world.color = tuple(
        (low + high) * 0.5
        for low, high in zip(variant.palette.background_low, variant.palette.background_high)
    )
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "High Contrast"
    scene.view_settings.exposure = 0.34
    scene.view_settings.gamma = 1.0
    scene.render.use_file_extension = True

    frames = Path(args.frames)
    frames.mkdir(parents=True, exist_ok=True)
    suffix = str(stages[0]) if len(stages) == 1 else "comparison"
    bpy.ops.wm.save_as_mainfile(filepath=str(frames / f"soft-body-{suffix}.blend"))
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
