"""Render one physically simulated stage of the Oopsi-style soft-body test.

The orchestrator launches Blender once per softness level.  Keeping every trial
in its own scene makes the cloth cache deterministic, cheap enough for a CPU
VPS, and prevents hidden simulations from influencing later stages.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


CANONICAL_SOFTNESS = (0, 25, 50, 75, 100)
RAMP_MIN = -2.85
RAMP_MAX = 2.95
RAMP_LIP_WIDTH = 0.55
RAMP_LIP_RISE = 0.78


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


def marble_material():
    value = bpy.data.materials.new("Quiet ivory marble")
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
    ramp.color_ramp.elements[0].color = (0.90, 0.89, 0.85, 1)
    pre_vein = ramp.color_ramp.elements.new(0.41)
    pre_vein.color = (0.84, 0.84, 0.81, 1)
    vein = ramp.color_ramp.elements.new(0.455)
    vein.color = (0.34, 0.37, 0.40, 1)
    after_vein = ramp.color_ramp.elements.new(0.50)
    after_vein.color = (0.88, 0.88, 0.85, 1)
    light = ramp.color_ramp.elements.new(0.61)
    light.color = (0.94, 0.93, 0.89, 1)
    ramp.color_ramp.elements[-1].position = 0.75
    ramp.color_ramp.elements[-1].color = (0.97, 0.96, 0.91, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    bump.inputs["Distance"].default_value = 0.035
    links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return value


def background_material():
    value = bpy.data.materials.new("Clouded blue-grey studio")
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
    ramp.color_ramp.elements[0].color = (0.20, 0.27, 0.36, 1)
    ramp.color_ramp.elements[1].position = 0.77
    ramp.color_ramp.elements[1].color = (0.50, 0.58, 0.67, 1)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 0.72
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    nodes.remove(shader)
    return value


def liquid_gold_material(seed: int):
    variation = ((seed % 997) / 996.0 - 0.5) * 0.025
    value = material(
        "Champagne liquid metal",
        (0.78 + variation, 0.52 + variation * 0.7, 0.16, 1),
        metallic=1.0,
        roughness=0.145,
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


def ramp_height(local_x: float) -> float:
    lip = max(0.0, min(1.0, (local_x - RAMP_MIN) / RAMP_LIP_WIDTH))
    smooth_lip = lip * lip * (3.0 - 2.0 * lip)
    return 3.70 + 0.14 * local_x + RAMP_LIP_RISE * smooth_lip


def physics_ramp_height(local_x: float) -> float:
    lip = max(0.0, min(1.0, (local_x - RAMP_MIN) / 0.78))
    smooth_lip = lip * lip * (3.0 - 2.0 * lip)
    return 3.86 + 0.14 * local_x + 0.62 * smooth_lip


def ramp_points(segments: int = 112):
    return [
        (RAMP_MIN + (RAMP_MAX - RAMP_MIN) * index / (segments - 1),)
        for index in range(segments)
    ]


def ramp_position(time: float) -> float:
    # The source video gives each trial roughly six seconds.  ClipMaker keeps
    # the whole comparison to fifteen, so the same sweep is time-compressed.
    period = 1.60
    if time <= period:
        return 3.08 * math.sin(math.tau * time / period - math.pi / 2) + 0.14 * math.sin(
            math.tau * time / (period * 0.5) - 0.18
        )
    exit_duration = 0.22
    ratio = max(0.0, min(1.0, (time - period) / exit_duration))
    smooth = ratio * ratio * (3.0 - 2.0 * ratio)
    return -3.105 + (-6.0 + 3.105) * smooth


def ramp_velocity(time: float) -> float:
    period = 1.60
    if time <= period:
        return (
            3.08 * math.tau / period * math.cos(math.tau * time / period - math.pi / 2)
            + 0.14 * math.tau / (period * 0.5) * math.cos(math.tau * time / (period * 0.5) - 0.18)
        )
    exit_duration = 0.22
    ratio = max(0.0, min(1.0, (time - period) / exit_duration))
    return (-6.0 + 3.105) * 6.0 * ratio * (1.0 - ratio) / exit_duration


def ramp_slope(local_x: float) -> float:
    lip = max(0.0, min(1.0, (local_x - RAMP_MIN) / RAMP_LIP_WIDTH))
    return 0.14 + RAMP_LIP_RISE * 6.0 * lip * (1.0 - lip) / RAMP_LIP_WIDTH


def physics_ramp_slope(local_x: float) -> float:
    lip = max(0.0, min(1.0, (local_x - RAMP_MIN) / 0.78))
    return 0.14 + 0.62 * 6.0 * lip * (1.0 - lip) / 0.78


def add_ramp(marble, gold, frame_end: int, fps: int, stage_frames: int):
    segments, half_width, thickness = 112, 0.68, 0.24
    samples = [RAMP_MIN + (RAMP_MAX - RAMP_MIN) * index / (segments - 1) for index in range(segments)]
    vertices = []
    for x in samples:
        z = ramp_height(x)
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
            point.co = (x, y, ramp_height(x) + 0.012, 1.0)
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
        ramp.location.x = ramp_position(local_frame / fps)
        ramp.keyframe_insert("location", frame=frame)
    if ramp.animation_data and ramp.animation_data.action:
        for curve in ramp.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    return ramp


def capsule_geometry(
    radius: float = 0.37,
    cylinder_half: float = 0.66,
    radial_segments: int = 24,
    cap_rings: int = 6,
    cylinder_rings: int = 8,
):
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
    for x, ring_radius in rings:
        for segment in range(radial_segments):
            angle = math.tau * segment / radial_segments
            front_angle = (angle - math.pi + math.pi) % math.tau - math.pi
            groove = math.exp(-((front_angle / 0.34) ** 2))
            groove_strength = 0.15 * min(1.0, ring_radius / max(radius, 1e-6))
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
) -> tuple[Vector, Vector, float]:
    intensity = 0.0
    local_x = point.x - ramp_position(time)
    if RAMP_MIN <= local_x <= RAMP_MAX:
        height = physics_ramp_height(local_x)
        slope = physics_ramp_slope(local_x)
        normal = Vector((-slope, 1.0)).normalized()
        signed_distance = (point.y - height) / math.sqrt(1.0 + slope * slope)
        if point.y > height - 0.55 and signed_distance < radius:
            point += normal * (radius - signed_distance)
            velocity = point - previous
            ramp_step = Vector((ramp_velocity(time) * dt, 0.0))
            relative = velocity - ramp_step
            normal_speed = relative.dot(normal)
            intensity = max(intensity, abs(normal_speed) / max(dt, 1e-6))
            if normal_speed < 0.0:
                restitution = 0.36 - softness * 0.32
                tangent = Vector((normal.y, -normal.x))
                velocity -= normal * ((1.0 + restitution) * normal_speed)
                target_tangent = ramp_step.dot(tangent)
                current_tangent = velocity.dot(tangent)
                coupling = 0.11 + (1.0 - softness) * 0.07
                velocity += tangent * (target_tangent - current_tangent) * coupling
                velocity *= 0.92 - softness * 0.16
                previous = point - velocity

    # Thin circular rim first, followed by the shallow concave receiver.  The
    # opening remains real: misses continue below frame instead of landing on
    # an invisible cylinder cap.
    for rim_x in (-1.11, 1.11):
        center = Vector((rim_x, 0.76))
        delta = point - center
        minimum = radius + 0.065
        if 1e-7 < delta.length < minimum:
            normal = delta.normalized()
            point = center + normal * minimum
            velocity = point - previous
            normal_speed = velocity.dot(normal)
            intensity = max(intensity, abs(normal_speed) / max(dt, 1e-6))
            if normal_speed < 0.0:
                velocity -= normal * ((1.42 - softness * 0.30) * normal_speed)
                previous = point - velocity * (0.88 - softness * 0.20)

    if abs(point.x) < 1.05 and point.y < 1.10:
        ratio = abs(point.x) / 1.05
        height = 0.22 + 0.46 * ratio * ratio
        slope = 0.92 * point.x / (1.05 * 1.05)
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


def simulate_chain(softness_percent: int, frame_count: int, fps: int):
    softness = softness_percent / 100.0
    node_count = 19
    half_length = 1.03
    rest = 2.0 * half_length / (node_count - 1)
    rotation = -0.14
    points = []
    for index in range(node_count):
        local_x = -half_length + rest * index
        points.append(Vector((0.42 + math.cos(rotation) * local_x, 6.56 + math.sin(rotation) * local_x)))
    previous = [point.copy() for point in points]
    frames = []
    impact_memory = 0.0
    substeps = 7
    dt = 1.0 / (fps * substeps)
    iterations = max(5, round(22 - softness * 15))
    bend_strength = 0.98 - softness * 0.90
    horizontal_damping = 0.970 - softness * 0.075
    vertical_damping = 0.993 - softness * 0.005

    for frame in range(frame_count):
        frame_intensity = 0.0
        if frame:
            for substep in range(substeps):
                time = ((frame - 1) + (substep + 1) / substeps) / fps
                for index in range(node_count):
                    velocity = points[index] - previous[index]
                    velocity.x *= horizontal_damping
                    velocity.y *= vertical_damping
                    previous[index] = points[index].copy()
                    points[index] += velocity + Vector((0.0, -9.81 * dt * dt))

                for _ in range(iterations):
                    for index in range(node_count - 1):
                        constrain_distance(points, index, index + 1, rest)
                    for index in range(node_count - 2):
                        constrain_distance(points, index, index + 2, rest * 2.0, bend_strength)
                    for index in range(node_count):
                        profile = math.sin(math.pi * index / (node_count - 1))
                        radius = 0.16 + 0.21 * math.sqrt(max(0.0, profile))
                        points[index], previous[index], intensity = collide_point(
                            points[index], previous[index], radius, softness, time, dt
                        )
                        frame_intensity = max(frame_intensity, intensity)
        impact_memory = max(min(1.0, frame_intensity / 8.0), impact_memory * (0.78 + softness * 0.13))
        frames.append(([point.copy() for point in points], impact_memory))
    return frames


def skin_capsule(base_vertices, chain_points, softness: float, impact: float, frame: int):
    half_length = 1.03
    node_count = len(chain_points)
    center = sum(chain_points, Vector((0.0, 0.0))) / node_count
    rigid_tangent = (chain_points[-1] - chain_points[0]).normalized()
    visible_deformation = softness ** 1.35
    displayed_points = []
    for index, point in enumerate(chain_points):
        local_x = -half_length + 2.0 * half_length * index / (node_count - 1)
        rigid_point = center + rigid_tangent * local_x
        displayed_points.append(rigid_point.lerp(point, visible_deformation))
    result = []
    for base in base_vertices:
        x, y, z = base
        coordinate = max(0.0, min(node_count - 1.000001, (x + half_length) / (2.0 * half_length) * (node_count - 1)))
        first = int(math.floor(coordinate))
        second = min(node_count - 1, first + 1)
        blend = coordinate - first
        center = displayed_points[first].lerp(displayed_points[second], blend)
        before = displayed_points[max(0, first - 1)]
        after = displayed_points[min(node_count - 1, second + 1)]
        tangent = (after - before).normalized()
        normal = Vector((-tangent.y, tangent.x))
        local_stretch = max(0.58, min(1.55, (after - before).length / max(0.001, 2.0 * 2.06 / (node_count - 1))))
        volume_scale = max(0.78, min(1.28, 1.0 / math.sqrt(local_stretch)))
        u = x / half_length
        wrinkle = impact * softness * softness
        axial_wrinkle = wrinkle * 0.075 * math.sin(u * math.pi * 4.2 + frame * 0.21)
        angular = math.atan2(z, y)
        asymmetric = 1.0 + wrinkle * 0.12 * math.sin(angular * 3.0 + u * 5.3 + frame * 0.13)
        radius_scale = volume_scale * asymmetric
        center += normal * axial_wrinkle
        result.append(
            (
                center.x + normal.x * z * radius_scale,
                -0.04 + y * radius_scale,
                center.y + normal.y * z * radius_scale,
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


def add_capsule(gold, softness: int, start: int, end: int, frame_end: int, fps: int):
    base_vertices, faces = capsule_geometry()
    simulated = simulate_chain(softness, end - start + 1, fps)
    shapes = [
        skin_capsule(base_vertices, points, softness / 100.0, impact, index)
        for index, (points, impact) in enumerate(simulated)
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
    subdivision.levels = 0
    subdivision.render_levels = 1
    return capsule


def add_receiver(marble, gold):
    segments = 72
    outer_radius, inner_radius = 1.17, 1.05
    top, bottom = 0.76, -3.40
    vertices = []
    for segment in range(segments):
        angle = math.tau * segment / segments
        cosine, sine = math.cos(angle), math.sin(angle)
        vertices.extend(
            (
                (outer_radius * cosine, outer_radius * sine, top),
                (outer_radius * cosine, outer_radius * sine, bottom),
                (inner_radius * cosine, inner_radius * sine, top - 0.08),
                (inner_radius * cosine, inner_radius * sine, bottom),
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

    rings = 12
    bowl_vertices = [(0.0, 0.0, 0.22)]
    for ring in range(1, rings + 1):
        ratio = ring / rings
        radius = inner_radius * ratio
        z = 0.22 + 0.46 * ratio * ratio
        for segment in range(segments):
            angle = math.tau * segment / segments
            bowl_vertices.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
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
        location=(0.0, 0.0, top),
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
    frame_end = max(5, round(args.duration * args.fps))
    if args.stage_softness is None:
        stages = CANONICAL_SOFTNESS
        stage_frames = max(2, round(frame_end / len(stages)))
        frame_end = stage_frames * len(stages)
    else:
        stages = (min(CANONICAL_SOFTNESS, key=lambda level: abs(level - args.stage_softness)),)
        stage_frames = frame_end

    gold = liquid_gold_material(args.seed)
    marble = marble_material()
    backdrop = background_material()
    add_background(backdrop)
    add_receiver(marble, gold)
    add_ramp(marble, gold, frame_end, args.fps, stage_frames)
    for index, softness in enumerate(stages):
        start = 1 + index * stage_frames
        end = min(frame_end, (index + 1) * stage_frames)
        add_capsule(gold, softness, start, end, frame_end, args.fps)

    bpy.ops.object.camera_add(location=(0.0, -14.8, 4.55))
    camera = bpy.context.object
    camera.name = "Fixed reference camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.35
    camera.data.lens = 70
    look_at(camera, (0.0, 0.0, 3.18))
    bpy.context.scene.camera = camera

    add_area("Large warm key", (-4.8, -6.5, 9.0), 1150, 5.2, (1.0, 0.92, 0.80))
    add_area("Broad neutral fill", (4.8, -4.0, 6.6), 820, 4.5, (0.74, 0.84, 1.0))
    add_area("Metal rim light", (0.5, 2.8, 8.1), 1050, 3.6, (1.0, 0.83, 0.61))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 2.5
    scene.eevee.gtao_factor = 1.05
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.018
    scene.eevee.bloom_radius = 2.0
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_motion_blur = True
    scene.eevee.motion_blur_shutter = 0.28
    scene.eevee.taa_render_samples = args.samples
    scene.gravity = (0.0, 0.0, -9.81)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 34
    scene.render.filepath = str(Path(args.frames) / "frame_")
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.film_transparent = False
    scene.world.color = (0.34, 0.38, 0.44)
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.48
    scene.view_settings.gamma = 1.0
    scene.render.use_file_extension = True

    frames = Path(args.frames)
    frames.mkdir(parents=True, exist_ok=True)
    suffix = str(stages[0]) if len(stages) == 1 else "comparison"
    bpy.ops.wm.save_as_mainfile(filepath=str(frames / f"soft-body-{suffix}.blend"))
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
