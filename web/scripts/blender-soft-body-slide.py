"""Build and render an original premium soft-body slide scene in Blender."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


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


def material(name: str, color: tuple[float, float, float, float], metallic=0.0, roughness=0.4):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return value


def marble_material(name: str, warm: bool):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    nodes, links = value.node_tree.nodes, value.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.22
    base = nodes.new("ShaderNodeTexNoise")
    base.inputs["Scale"].default_value = 3.2
    base.inputs["Detail"].default_value = 6.0
    base.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.34
    ramp.color_ramp.elements[0].color = (0.025, 0.035, 0.055, 1) if not warm else (0.12, 0.055, 0.03, 1)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.72, 0.78, 0.82, 1) if not warm else (0.84, 0.62, 0.38, 1)
    coordinates = nodes.new("ShaderNodeTexCoord")
    links.new(coordinates.outputs["Generated"], base.inputs["Vector"])
    links.new(base.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    return value


def add_mesh(name: str, vertices, faces, value):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(value)
    bevel = obj.modifiers.new("Soft bevels", "BEVEL")
    bevel.width = 0.10
    bevel.segments = 4
    return obj


def add_ramp(value):
    profile = [(-3.5, 3.55), (-2.8, 3.28), (-1.9, 3.05), (-0.7, 3.02), (0.8, 3.25), (2.1, 3.68), (3.5, 4.25)]
    half_width, thickness = 1.65, 0.28
    vertices = []
    for x, z in profile:
        vertices.extend(((x, -half_width, z), (x, half_width, z), (x, -half_width, z - thickness), (x, half_width, z - thickness)))
    faces = []
    for index in range(len(profile) - 1):
        current, following = index * 4, (index + 1) * 4
        faces.extend((
            (current, following, following + 1, current + 1),
            (current + 2, current + 3, following + 3, following + 2),
            (current, current + 2, following + 2, following),
            (current + 1, following + 1, following + 3, current + 3),
        ))
    faces.extend(((0, 1, 3, 2), (len(vertices) - 4, len(vertices) - 2, len(vertices) - 1, len(vertices) - 3)))
    return add_mesh("Sculpted slide", vertices, faces, value)


def add_bowl_surface(center_x: float, value):
    rings, segments, radius = 10, 64, 1.72
    vertices = [(center_x, 0.0, -0.28)]
    for ring in range(1, rings + 1):
        ratio = ring / rings
        for segment in range(segments):
            angle = math.tau * segment / segments
            r = radius * ratio
            z = -0.28 + 0.60 * ratio * ratio
            vertices.append((center_x + math.cos(angle) * r, math.sin(angle) * r, z))
    faces = []
    for segment in range(segments):
        faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
    for ring in range(1, rings):
        inner = 1 + (ring - 1) * segments
        outer = 1 + ring * segments
        for segment in range(segments):
            following = (segment + 1) % segments
            faces.append((inner + segment, outer + segment, outer + following, inner + following))
    bowl = add_mesh("Concave marble bowl", vertices, faces, value)
    solidify = bowl.modifiers.new("Bowl thickness", "SOLIDIFY")
    solidify.thickness = 0.13
    bpy.context.view_layer.objects.active = bowl
    bowl.select_set(True)
    bpy.ops.object.shade_smooth()
    bowl.select_set(False)
    return bowl


def add_capsule(gold, softness: float, frame_end: int):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=(3.15, 0, 4.78))
    capsule = bpy.context.object
    capsule.name = "Procedural soft capsule"
    capsule.data.materials.append(gold)
    bpy.ops.object.shade_smooth()
    subdivision = capsule.modifiers.new("Polished surface", "SUBSURF")
    subdivision.levels = 2
    subdivision.render_levels = 2
    texture = bpy.data.textures.new("Soft deformation", type="CLOUDS")
    texture.noise_scale = 0.42
    displace = capsule.modifiers.new("Soft body deformation", "DISPLACE")
    displace.texture = texture
    displace.strength = 0.0
    displace.mid_level = 0.52

    keyframes = (
        (1, (3.15, 0, 4.78), (1.36, 0.46, 0.46), 0.0, 0.0),
        (round(frame_end * 0.24), (1.55, 0, 4.00), (1.36, 0.46, 0.46), -0.10, 0.0),
        (round(frame_end * 0.48), (-1.25, 0, 3.45), (1.36, 0.46, 0.46), -0.22, 0.0),
        (round(frame_end * 0.62), (-3.30, 0, 3.72), (1.30, 0.48, 0.46), -0.38, 0.01 * softness),
        (round(frame_end * 0.72), (-2.60, 0, 1.55), (1.26 - 0.18 * softness, 0.48 + 0.20 * softness, 0.46 - 0.10 * softness), -0.82, 0.025 * softness),
        (round(frame_end * 0.81), (-2.05, 0, 0.38), (1.20 + 0.40 * softness, 0.46 - 0.12 * softness, 0.46 - 0.20 * softness), -0.92, 0.08 * softness),
        (round(frame_end * 0.88), (-2.02, 0, 0.92), (1.20 - 0.24 * softness, 0.46 + 0.28 * softness, 0.46 + 0.18 * softness), -1.32, 0.045 * softness),
        (frame_end, (-2.00, 0, 0.38), (1.36 + 0.14 * softness, 0.46 - 0.05 * softness, 0.46 - 0.08 * softness), -1.50, 0.02 * softness),
    )
    for frame, location, scale, rotation, deformation in keyframes:
        capsule.location = location
        capsule.scale = scale
        capsule.rotation_euler = (0, rotation, 0)
        capsule.keyframe_insert("location", frame=frame)
        capsule.keyframe_insert("scale", frame=frame)
        capsule.keyframe_insert("rotation_euler", frame=frame)
        displace.strength = deformation
        displace.keyframe_insert("strength", frame=frame)
    for curve in capsule.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"
    return capsule


def add_text(body: str, location, size: float, value, depth: float = 0.012):
    bpy.ops.object.text_add(location=location, rotation=(math.pi / 2, 0, 0))
    text = bpy.context.object
    text.data.body = body
    text.data.align_x = "CENTER"
    text.data.align_y = "CENTER"
    text.data.size = size
    text.data.extrude = depth
    text.data.bevel_depth = min(0.005, depth * 0.35)
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
    look_at(obj, (-0.5, 0, 2.4))
    return obj


def main():
    args = arguments()
    reset_scene()
    theme = {
        "neon": ((0.025, 0.035, 0.065, 1), (0.98, 0.55, 0.08, 1), (0.18, 0.65, 1.0)),
        "sunset": ((0.08, 0.025, 0.035, 1), (1.0, 0.38, 0.10, 1), (1.0, 0.22, 0.45)),
        "ice": ((0.035, 0.055, 0.075, 1), (0.92, 0.72, 0.20, 1), (0.28, 0.72, 1.0)),
    }[args.theme]
    background_color, accent_color, light_color = theme
    background = material("Studio background", background_color, roughness=0.7)
    gold = material("Liquid gold", accent_color, metallic=0.94, roughness=0.08)
    champagne = material("Brushed champagne", (0.44, 0.33, 0.19, 1), metallic=0.82, roughness=0.24)
    marble = marble_material("Procedural marble", args.theme == "sunset")
    white = material("Typography", (0.96, 0.98, 1.0, 1), metallic=0.05, roughness=0.28)
    accent_text = material("Accent typography", (1.0, 0.62, 0.08, 1), metallic=0.1, roughness=0.2)
    accent_shader = accent_text.node_tree.nodes.get("Principled BSDF")
    accent_shader.inputs["Emission"].default_value = (1.0, 0.28, 0.015, 1)
    accent_shader.inputs["Emission Strength"].default_value = 1.6

    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 4.0, 3.0), rotation=(math.pi / 2, 0, 0))
    bpy.context.object.data.materials.append(background)
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -1.55))
    bpy.context.object.data.materials.append(background)
    add_ramp(champagne)

    bowl_x = -2.0
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=1.82, depth=1.45, location=(bowl_x, 0, -0.92))
    bowl_base = bpy.context.object
    bowl_base.name = "Marble receiver"
    bowl_base.data.materials.append(marble)
    bevel = bowl_base.modifiers.new("Receiver bevel", "BEVEL")
    bevel.width = 0.10
    bevel.segments = 5
    bpy.ops.object.shade_smooth()
    add_bowl_surface(bowl_x, marble)
    bpy.ops.mesh.primitive_torus_add(major_segments=96, minor_segments=20, location=(bowl_x, 0, 0.32), major_radius=1.76, minor_radius=0.07)
    bpy.context.object.data.materials.append(gold)

    frame_end = round(args.duration * args.fps)
    softness = max(0.0, min(1.0, args.softness / 100.0))
    add_capsule(gold, softness, frame_end)
    add_text("SOFT BODY SLIDE", (0, 3.60, 6.55), 0.52, white)
    add_text(f"{args.softness}% SOFTNESS", (0, 3.59, 5.96), 0.36, accent_text, 0.004)

    bpy.ops.object.camera_add(location=(0.2, -17.8, 5.35))
    camera = bpy.context.object
    camera.data.lens = 52
    camera.data.sensor_width = 36
    look_at(camera, (-0.25, 0, 2.30))
    bpy.context.scene.camera = camera
    add_area("Key light", (-5.0, -6.5, 9.0), 1100, 5.0, (1.0, 0.86, 0.66))
    add_area("Fill light", (5.5, -2.5, 5.8), 850, 4.0, light_color)
    add_area("Rim light", (0.0, 4.0, 7.5), 1250, 3.0, (1.0, 0.42, 0.16))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3
    scene.eevee.gtao_factor = 1.35
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.08
    scene.eevee.bloom_radius = 5.0
    scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.filepath = str(Path(args.frames) / "frame_")
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.film_transparent = False
    scene.world.color = background_color[:3]
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.35
    scene.view_settings.gamma = 1.0
    scene.render.use_file_extension = True
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.frames) / "soft-body-slide.blend"))
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
