"""Shared closed staircase and hollow elbow geometry for display and physics.

The three depth lanes share one 2D path; no force steers a body into an outlet.
Only mesh-building functions need Blender, so presets can use these dimensions
from ordinary Python too.
"""

import math
from functools import lru_cache

RECEIVER_X = 2.55
RECEIVER_TOP = 1.55
OUTER_RADIUS = .44
INNER_RADIUS = .365
VOLUME_CONTACT = "closed-stair-volume-v1"


@lru_cache(maxsize=1)
def stair_outline():
    lefts = [-2.35 + index * .62 for index in range(7)]
    tops = [5.66 - index * .52 for index in range(7)]
    points = [(lefts[0], tops[0])]
    for index in range(7):
        right = lefts[index] + .70
        points.append((right, tops[index]))
        if index < 6:
            points.append((right, tops[index + 1]))
    points.append((lefts[-1] + .70, tops[-1] - .72))
    for index in reversed(range(7)):
        points.append((lefts[index], tops[index] - .72))
        if index:
            points.append((lefts[index], tops[index - 1] - .72))
    return tuple(points)


@lru_cache(maxsize=1)
def pipe_path():
    points = [(RECEIVER_X, RECEIVER_TOP), (RECEIVER_X, 1.0)]
    for index in range(1, 17):
        angle = math.pi * .5 * index / 16
        points.append((RECEIVER_X + .55 * (1 - math.cos(angle)), 1.0 - .55 * math.sin(angle)))
    points.append((3.6, .45))
    return tuple(points)


def path_normals(path):
    normals = []
    for index in range(len(path)):
        before, after = path[max(0, index - 1)], path[min(len(path) - 1, index + 1)]
        dx, dz = after[0] - before[0], after[1] - before[1]
        length = math.hypot(dx, dz)
        normals.append((-dz / length, dx / length))
    return tuple(normals)


def inside_stair(point):
    # The outline is exactly this union of seven overlapping solid blocks.
    return any(-2.35 + i * .62 < point.x < -2.35 + i * .62 + .70
               and 5.66 - i * .52 - .72 < point.y < 5.66 - i * .52 for i in range(7))


@lru_cache(maxsize=1)
def collision_segments():
    outline, path = stair_outline(), pipe_path()
    result = [(a, b, 0.0) for a, b in zip(outline, (*outline[1:], outline[0]))]
    for side in (-1, 1):
        wall = [(p[0] + n[0] * side * (OUTER_RADIUS + INNER_RADIUS) / 2,
                 p[1] + n[1] * side * (OUTER_RADIUS + INNER_RADIUS) / 2)
                for p, n in zip(path, path_normals(path))]
        result.extend((a, b, (OUTER_RADIUS - INNER_RADIUS) / 2) for a, b in zip(wall, wall[1:]))
    return tuple(result)


def project_inside_stair(point, previous, radius, closest_segment_point):
    """Recover a deep solid overlap without creating an impulse or teleporting to a goal."""
    if inside_stair(point):
        outline = stair_outline()
        nearest = min((closest_segment_point(point, a, b)
                       for a, b in zip(outline, (*outline[1:], outline[0]))),
                      key=lambda value: (point - value).length_squared)
        direction = nearest - point
        if direction.length > 1e-8:
            correction = nearest + direction.normalized() * (radius + .00001) - point
            point += correction
            previous += correction


def add_staircase(add_mesh, marble, variant):
    outline = stair_outline()
    half_depth = variant.ramp.half_width * 2.90
    count = len(outline)
    vertices = [(x, depth, z) for depth in (-half_depth, half_depth) for x, z in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index, following, following + count, index + count))
    block = add_mesh("Solid marble staircase", vertices, faces, marble, bevel_width=.018)
    for polygon in block.data.polygons:
        polygon.use_smooth = False
    block["contact_model"] = VOLUME_CONTACT
    return block


def add_curved_receivers(add_mesh, material, depth_offsets):
    import bmesh

    glass = material("Clear curved receiver glass", (.70, .84, .94, .12), roughness=.08, clearcoat=.45)
    glass.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = .12
    glass.blend_method = "BLEND"
    glass.shadow_method = "NONE"
    glass.use_screen_refraction = True
    rim = material("Polished curved receiver edge", (.20, .25, .29, 1), metallic=.15, roughness=.16)
    path = pipe_path()
    normals = path_normals(path)
    sides = 96
    tubes = []
    for depth in depth_offsets:
        vertices, faces = [], []
        for (x, z), (nx, nz) in zip(path, normals):
            for radius in (OUTER_RADIUS, INNER_RADIUS):
                for index in range(sides):
                    angle = math.tau * index / sides
                    vertices.append((x + nx * radius * math.cos(angle),
                                     depth + radius * math.sin(angle), z + nz * radius * math.cos(angle)))
        stride = sides * 2
        for ring in range(len(path) - 1):
            for side in range(sides):
                following = (side + 1) % sides
                a, b = ring * stride, (ring + 1) * stride
                faces.append((a + side, b + side, b + following, a + following))
                faces.append((a + sides + following, b + sides + following, b + sides + side, a + sides + side))
        for end in (0, len(path) - 1):
            base = end * stride
            for side in range(sides):
                following = (side + 1) % sides
                face = (base + side, base + following, base + sides + following, base + sides + side)
                faces.append(face if end == 0 else tuple(reversed(face)))
        tube = add_mesh("Hollow curved receiver", vertices, faces, glass)
        tube.data.materials.append(rim)
        for polygon in tube.data.polygons[-sides * 2:]:
            polygon.material_index = 1
        bm = bmesh.new()
        try:
            bm.from_mesh(tube.data)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(tube.data)
        finally:
            bm.free()
        tube["contact_model"] = VOLUME_CONTACT
        tubes.append(tube)
    return tuple(tubes)
