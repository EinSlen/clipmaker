"""Build a premium five-stage soft-body comparison in Blender Eevee."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SOFTNESS_RATIOS = (0.0, 0.25, 0.50, 0.75, 1.0)


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
    parser.add_argument("--theme", choices=("neon", "sunset", "ice"), required=True)
    parser.add_argument("--title", required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.curves, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name: str, color: tuple[float, float, float, float], metallic=0.0, roughness=0.4, clearcoat=0.0):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if shader.inputs.get("Clearcoat"):
        shader.inputs["Clearcoat"].default_value = clearcoat
        shader.inputs["Clearcoat Roughness"].default_value = 0.08
    return value


def brushed_metal_material():
    value = material("Brushed silver ribbon", (0.53, 0.58, 0.66, 1), metallic=0.92, roughness=0.20, clearcoat=0.18)
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 78.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.42
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.035
    coordinates = nodes.new("ShaderNodeTexCoord")
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return value


def marble_material():
    value = bpy.data.materials.new("Ivory marble")
    value.use_nodes = True
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.24
    if shader.inputs.get("Clearcoat"):
        shader.inputs["Clearcoat"].default_value = 0.20
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.8
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.68
    noise.inputs["Distortion"].default_value = 0.16
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.24, 0.27, 0.31, 1)
    ramp.color_ramp.elements[1].position = 0.64
    ramp.color_ramp.elements[1].color = (0.83, 0.86, 0.88, 1)
    coordinates = nodes.new("ShaderNodeTexCoord")
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    return value


def add_mesh(name: str, vertices, faces, value, bevel_width=0.06):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(value)
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
    if bevel_width:
        bevel = obj.modifiers.new("Precision bevel", "BEVEL")
        bevel.width = bevel_width
        bevel.segments = 3
    normal = obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def ramp_height(x: float) -> float:
    normalized = (x + 3.65) / 7.30
    return 3.28 + 0.92 * normalized * normalized + 0.08 * math.sin(normalized * math.pi * 1.4)


def add_ramp(value):
    segments, half_width, thickness = 58, 1.38, 0.18
    vertices = []
    for index in range(segments):
        x = -3.65 + 7.30 * index / (segments - 1)
        z = ramp_height(x)
        vertices.extend(((x, -half_width, z), (x, half_width, z), (x, -half_width, z - thickness), (x, half_width, z - thickness)))
    faces = []
    for index in range(segments - 1):
        current, following = index * 4, (index + 1) * 4
        faces.extend((
            (current, following, following + 1, current + 1),
            (current + 2, current + 3, following + 3, following + 2),
            (current, current + 2, following + 2, following),
            (current + 1, following + 1, following + 3, current + 3),
        ))
    faces.extend(((0, 1, 3, 2), (len(vertices) - 4, len(vertices) - 2, len(vertices) - 1, len(vertices) - 3)))
    return add_mesh("Continuous sculpted ribbon", vertices, faces, value, 0.075)


def add_bowl_surface(center_x: float, radius: float, value):
    rings, segments = 12, 72
    vertices = [(center_x, 0.0, -0.32)]
    for ring in range(1, rings + 1):
        ratio = ring / rings
        for segment in range(segments):
            angle = math.tau * segment / segments
            current_radius = radius * ratio
            z = -0.32 + 0.53 * ratio * ratio
            vertices.append((center_x + math.cos(angle) * current_radius, math.sin(angle) * current_radius, z))
    faces = []
    for segment in range(segments):
        faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
    for ring in range(1, rings):
        inner = 1 + (ring - 1) * segments
        outer = 1 + ring * segments
        for segment in range(segments):
            following = (segment + 1) % segments
            faces.append((inner + segment, outer + segment, outer + following, inner + following))
    bowl = add_mesh("True concave receiver", vertices, faces, value, 0.035)
    solidify = bowl.modifiers.new("Receiver thickness", "SOLIDIFY")
    solidify.thickness = 0.10
    for polygon in bowl.data.polygons:
        polygon.use_smooth = True
    return bowl


def keyframe_visibility(obj, start: int, end: int, frame_end: int) -> None:
    if start > 1:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=1)
        obj.keyframe_insert("hide_render", frame=start - 1)
    obj.hide_render = False
    obj.keyframe_insert("hide_render", frame=start)
    obj.keyframe_insert("hide_render", frame=end)
    if end < frame_end:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=end + 1)


def add_capsule(gold, softness_percent: int, start: int, end: int, frame_end: int):
    softness = softness_percent / 100.0
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=(3.15, 0, 4.72))
    capsule = bpy.context.object
    capsule.name = f"Soft capsule {softness_percent}%"
    capsule.data.materials.append(gold)
    for polygon in capsule.data.polygons:
        polygon.use_smooth = True
    bend = capsule.modifiers.new("Contact bend", "SIMPLE_DEFORM")
    bend.deform_method = "BEND"
    bend.deform_axis = "X"
    subdivision = capsule.modifiers.new("Polished surface", "SUBSURF")
    subdivision.levels = 1
    subdivision.render_levels = 1
    texture = bpy.data.textures.new(f"Micro deformation {softness_percent}", type="CLOUDS")
    texture.noise_scale = 0.52
    displace = capsule.modifiers.new("Surface compression", "DISPLACE")
    displace.texture = texture
    displace.mid_level = 0.50

    span = max(1, end - start)
    def at(ratio: float) -> int:
        return min(end, start + round(span * ratio))

    rigid = (1.44, 0.43, 0.43)
    rigid_volume = rigid[0] * rigid[1] * rigid[2]
    impact_x = 1.44 + 1.00 * softness
    impact_y = 0.43 + 0.34 * softness
    impact = (impact_x, impact_y, rigid_volume / (impact_x * impact_y))
    rebound = (1.44 - 0.34 * softness, 0.43 + 0.08 * softness, 0.43 + 0.25 * softness)
    oversquash_x = 1.44 + 1.10 * softness
    oversquash_y = 0.43 + 0.38 * softness
    oversquash = (oversquash_x, oversquash_y, rigid_volume / (oversquash_x * oversquash_y))
    settle_x = 1.44 + 0.80 * softness
    settle_y = 0.43 + 0.28 * softness
    settle = (settle_x, settle_y, rigid_volume / (settle_x * settle_y))
    slide_quarter = (1.44 + 0.05 * softness, 0.43, 0.43 - 0.018 * softness)
    slide_mid = (1.44 + 0.10 * softness, 0.43, 0.43 - 0.035 * softness)
    slide_three_quarters = (1.44 + 0.14 * softness, 0.43, 0.43 - 0.048 * softness)
    slide_lip = (1.44 + 0.18 * softness, 0.43, 0.43 - 0.06 * softness)

    def on_ramp(x: float, scale, rotation: float, clearance: float = 0.04):
        vertical_extent = math.sqrt(
            (scale[0] * math.sin(rotation)) ** 2 + (scale[2] * math.cos(rotation)) ** 2
        )
        return (x, 0, ramp_height(x) + vertical_extent + clearance)

    keyframes = (
        (start, on_ramp(3.18, rigid, -0.08, 0.20), rigid, -0.08, 0.0, 0.0),
        (at(0.18), on_ramp(2.80, rigid, -0.13), rigid, -0.13, 0.06 * softness, 0.006 * softness),
        (at(0.30), on_ramp(1.60, slide_quarter, -0.18, 0.05), slide_quarter, -0.18, 0.12 * softness, 0.009 * softness),
        (at(0.42), on_ramp(0.25, slide_mid, -0.23, 0.05 + 0.04 * softness), slide_mid, -0.23, 0.18 * softness, 0.012 * softness),
        (at(0.51), on_ramp(-1.45, slide_three_quarters, -0.32, 0.06 + 0.08 * softness), slide_three_quarters, -0.32, 0.28 * softness, 0.015 * softness),
        (at(0.60), on_ramp(-3.30, slide_lip, -0.52, 0.08 + 0.18 * softness), slide_lip, -0.52, 0.42 * softness, 0.018 * softness),
        (at(0.72), (-2.82, 0, 1.72), (1.32 - 0.18 * softness, 0.43, 0.48 + 0.20 * softness), -1.10, 0.26 * softness, 0.015 * softness),
        (at(0.82), (-2.20, 0, 0.36 - 0.20 * softness), impact, -0.08, -0.24 * softness, 0.035 * softness),
        (at(0.89), (-2.20, 0, 0.83 + 0.30 * (1.0 - softness)), rebound, 0.12, 0.30 * softness, 0.020 * softness),
        (at(0.95), (-2.20, 0, 0.38 - 0.20 * softness), oversquash, -0.03, -0.16 * softness, 0.030 * softness),
        (end, (-2.20, 0, 0.43 - 0.22 * softness), settle, 0.0, 0.08 * softness, 0.012 * softness),
    )
    for frame, location, scale, rotation, bend_angle, deformation in keyframes:
        capsule.location = location
        capsule.scale = scale
        capsule.rotation_euler = (0, rotation, 0)
        capsule.keyframe_insert("location", frame=frame)
        capsule.keyframe_insert("scale", frame=frame)
        capsule.keyframe_insert("rotation_euler", frame=frame)
        bend.angle = bend_angle
        bend.keyframe_insert("angle", frame=frame)
        displace.strength = deformation
        displace.keyframe_insert("strength", frame=frame)
    keyframe_visibility(capsule, start, end, frame_end)
    if capsule.animation_data and capsule.animation_data.action:
        for curve in capsule.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT" if curve.data_path == "hide_render" else "BEZIER"
    return capsule


def add_text(body: str, location, size: float, value, depth: float = 0.008):
    bpy.ops.object.text_add(location=location, rotation=(math.pi / 2, 0, 0))
    text = bpy.context.object
    text.data.body = body
    text.data.align_x = "CENTER"
    text.data.align_y = "CENTER"
    text.data.size = size
    text.data.extrude = depth
    text.data.bevel_depth = min(0.004, depth * 0.35)
    text.data.materials.append(value)
    return text


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(name: str, location, energy: float, size: float, color):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, (-0.4, 0, 2.1))
    return obj


def add_cyclorama(value):
    width = 12.0
    profile = [(-5.0, -3.0), (1.7, -3.0), (2.8, -2.7), (3.6, -1.7), (4.0, -0.3), (4.0, 7.5)]
    vertices = []
    for y, z in profile:
        vertices.extend(((-width, y, z), (width, y, z)))
    faces = []
    for index in range(len(profile) - 1):
        current = index * 2
        faces.append((current, current + 2, current + 3, current + 1))
    cyclorama = add_mesh("Seamless studio cyclorama", vertices, faces, value, 0.32)
    for polygon in cyclorama.data.polygons:
        polygon.use_smooth = True
    return cyclorama


def main():
    args = arguments()
    reset_scene()
    palette = {
        "neon": ((0.22, 0.25, 0.30, 1), (0.95, 0.34, 0.055, 1), (0.56, 0.76, 1.0)),
        "sunset": ((0.29, 0.26, 0.26, 1), (0.96, 0.40, 0.075, 1), (1.0, 0.78, 0.58)),
        "ice": ((0.27, 0.32, 0.38, 1), (0.92, 0.54, 0.12, 1), (0.62, 0.84, 1.0)),
    }[args.theme]
    background_color, base_gold, rim_color = palette
    seed_variant = (args.seed % 997) / 996.0 - 0.5
    gold_color = (
        max(0.0, min(1.0, base_gold[0] + seed_variant * 0.06)),
        max(0.0, min(1.0, base_gold[1] + seed_variant * 0.10)),
        max(0.0, min(1.0, base_gold[2] - seed_variant * 0.025)),
        1.0,
    )
    background = material("Pearl studio", background_color, roughness=0.68)
    gold = material("Pale liquid gold", gold_color, metallic=0.92, roughness=0.11, clearcoat=0.42)
    silver = brushed_metal_material()
    marble = marble_material()

    add_cyclorama(background)
    add_ramp(silver)
    bowl_x, bowl_radius = -2.20, 1.48
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=bowl_radius + 0.08, depth=3.0, location=(bowl_x, 0, -1.52))
    receiver = bpy.context.object
    receiver.name = "Tall marble receiver"
    receiver.data.materials.append(marble)
    bevel = receiver.modifiers.new("Receiver edge", "BEVEL")
    bevel.width = 0.09
    bevel.segments = 5
    for polygon in receiver.data.polygons:
        polygon.use_smooth = True
    add_bowl_surface(bowl_x, bowl_radius, marble)
    bpy.ops.mesh.primitive_torus_add(major_segments=96, minor_segments=20, location=(bowl_x, 0, 0.21), major_radius=bowl_radius, minor_radius=0.055)
    bpy.context.object.data.materials.append(gold)

    frame_end = round(args.duration * args.fps)
    max_softness = max(0, min(100, args.softness))
    softness_stages = tuple(round(max_softness * ratio) for ratio in SOFTNESS_RATIOS)
    trial_span = frame_end / len(softness_stages)
    for index, softness in enumerate(softness_stages):
        start = 1 + round(index * trial_span)
        end = min(frame_end, round((index + 1) * trial_span))
        add_capsule(gold, softness, start, end, frame_end)
    # Typography is composited at 1080x1920 after rendering so it stays crisp
    # and never casts 3D shadows onto the cyclorama.

    bpy.ops.object.camera_add(location=(0.15, -18.8, 4.70))
    camera = bpy.context.object
    camera.data.lens = 58
    camera.data.sensor_width = 36
    look_at(camera, (-0.20, 0, 1.65))
    bpy.context.scene.camera = camera
    add_area("Large softbox", (-5.2, -6.0, 9.2), 1280, 5.5, (1.0, 0.94, 0.84))
    add_area("Cool fill", (5.5, -3.0, 6.0), 940, 4.2, rim_color)
    add_area("Gold rim", (0.2, 3.2, 7.8), 1120, 3.2, (1.0, 0.62, 0.30))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3
    scene.eevee.gtao_factor = 1.18
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.025
    scene.eevee.bloom_radius = 3.0
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_motion_blur = True
    scene.eevee.motion_blur_shutter = 0.35
    scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 32
    scene.render.filepath = str(Path(args.frames) / "frame_")
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.film_transparent = False
    scene.world.color = background_color[:3]
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.55
    scene.view_settings.gamma = 1.0
    scene.render.use_file_extension = True
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.frames) / "soft-body-comparison.blend"))
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
