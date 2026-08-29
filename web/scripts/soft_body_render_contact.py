"""Keep the final subdivided skin outside the rendered, animated obstacles.

This is a small surface correction after smoothing, not a physics solver or a
force toward a receiver. Native preflight still rejects an invalid spine.
"""

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from soft_body_stair_geometry import VOLUME_CONTACT

CONTACT_OFFSET = 0.003
MAX_RENDER_PENETRATION = 0.003
MAX_RENDER_CORRECTION = 0.08


def build_contact_targets(objects):
    """Snapshot evaluated local geometry and follow its original transforms.

    Current obstacles animate rigid transforms only. Reject future deforming
    targets rather than silently freezing their deformation in this snapshot.
    Weld the bevel caps before orienting normals, as in the contact query mesh.
    """
    objects = tuple(obj for obj in objects if obj.type in {"MESH", "CURVE"})
    volume_contact = bool(objects) and all(obj.get("contact_model") == VOLUME_CONTACT for obj in objects)
    if any(obj.get("contact_model") == VOLUME_CONTACT for obj in objects) and not volume_contact:
        raise ValueError("Closed-volume contact cannot mix validated stairs with unrelated solids")
    bpy.context.scene.frame_set(1)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    targets = []
    fixed_vertices, fixed_faces = [], []
    for original in objects:
        if original.type not in {"MESH", "CURVE"}:
            continue
        if original.data.animation_data or getattr(original.data, "shape_keys", None):
            raise ValueError(f"Deforming obstacle requires a live contact target: {original.name}")
        animation = original.animation_data
        if animation and any(curve.data_path.startswith("modifiers[") for curve in (
            tuple(animation.action.fcurves) if animation.action else ()
        ) + tuple(animation.drivers)):
            raise ValueError(f"Animated modifier requires a live contact target: {original.name}")
        mesh = bpy.data.meshes.new_from_object(original.evaluated_get(depsgraph), depsgraph=depsgraph)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            if volume_contact and (not bm.faces or not all(edge.is_manifold and edge.is_contiguous for edge in bm.edges)
                                   or bm.calc_volume(signed=True) <= 0):
                raise ValueError(f"Closed-volume contact requires watertight outward geometry: {original.name}")
            bm.to_mesh(mesh)
        finally:
            bm.free()
        ancestor = original
        animated = False
        while ancestor:
            animated = animated or bool(ancestor.animation_data or ancestor.constraints)
            ancestor = ancestor.parent
        if not animated:
            # One BVH for the fixed environment, rather than one expensive
            # modifier for every step. Keep each already oriented component.
            offset = len(fixed_vertices)
            transform = original.evaluated_get(depsgraph).matrix_world
            fixed_vertices.extend(transform @ vertex.co for vertex in mesh.vertices)
            fixed_faces.extend(tuple(offset + index for index in face.vertices) for face in mesh.polygons)
            bpy.data.meshes.remove(mesh)
            continue
        proxy = bpy.data.objects.new("Contact surface - " + original.name, mesh)
        bpy.context.collection.objects.link(proxy)
        proxy.hide_render = True
        proxy.display_type = "WIRE"
        if volume_contact:
            proxy["contact_model"] = VOLUME_CONTACT
        follow = proxy.constraints.new("COPY_TRANSFORMS")
        follow.target = original
        targets.append(proxy)
    if fixed_faces:
        mesh = bpy.data.meshes.new("Fixed contact surfaces")
        mesh.from_pydata(fixed_vertices, [], fixed_faces)
        mesh.update()
        proxy = bpy.data.objects.new("Contact surface - fixed environment", mesh)
        bpy.context.collection.objects.link(proxy)
        proxy.hide_render = True
        proxy.display_type = "WIRE"
        if volume_contact:
            proxy["contact_model"] = VOLUME_CONTACT
        targets.insert(0, proxy)
    return tuple(targets)


def add_final_surface_contact(body, targets):
    """Correct only inside vertices, after all smoothing modifiers."""
    targets = tuple(targets)
    if targets and all(target.get("contact_model") == VOLUME_CONTACT for target in targets):
        from soft_body_volume_contact import add_volume_contact
        add_volume_contact(body, targets)
        return
    for target in targets:
        contact = body.modifiers.new("Final skin contact", "SHRINKWRAP")
        contact.target = target
        contact.wrap_method = "NEAREST_SURFACEPOINT"
        contact.wrap_mode = "OUTSIDE"
        contact.offset = CONTACT_OFFSET


def world_positions(evaluated, mesh):
    coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coordinates)
    transform = np.asarray(evaluated.matrix_world, dtype=np.float64)
    return coordinates.reshape((-1, 3)) @ transform[:3, :3].T + transform[:3, 3]


def possible_inside_vertices(positions, targets, depsgraph):
    """A point outside every closed obstacle AABB cannot be inside its solid.

    This conservative rejection checks every vertex in bulk; it is not frame
    or vertex sampling. Detailed signed queries remain for every candidate.
    """
    candidate = np.zeros(len(positions), dtype=bool)
    for target in targets:
        if target.type not in {"MESH", "CURVE"}:
            continue
        evaluated = target.evaluated_get(depsgraph)
        bounds = np.asarray([evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box])
        if not np.isfinite(bounds).all():
            raise ValueError("Invalid obstacle bounds")
        low, high = bounds.min(axis=0) - 1e-6, bounds.max(axis=0) + 1e-6
        candidate |= np.all((positions >= low) & (positions <= high), axis=1)
    return candidate


def inspect_rendered_surface(body, obstacle_surface, start, end):
    """Check every final vertex at every output frame, using render subdivision.

    The signed nearest-face test is a conservative numerical contact check,
    not proof of visual quality, occlusion or all possible mesh self-contact.
    """
    if any(modifier.type == "NODES" and modifier.name.startswith("Final skin contact") for modifier in body.modifiers):
        from soft_body_volume_contact import inspect_volume_surface
        return inspect_volume_surface(body, obstacle_surface, start, end)
    subdivisions = [(modifier, modifier.levels) for modifier in body.modifiers if modifier.type == "SUBSURF"]
    contacts = [(modifier, modifier.show_viewport) for modifier in body.modifiers
                if modifier.type == "SHRINKWRAP" and modifier.name.startswith("Final skin contact")]
    maximum, correction, vertices_checked = 0.0, 0.0, 0
    penetration_frame, correction_frame = None, None
    obstacle_surface.final_contact_targets()
    queried_vertices = 0
    try:
        for modifier, _level in subdivisions:
            modifier.levels = modifier.render_levels
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            tree = obstacle_surface.at_frame(frame)
            if tree is None:
                raise ValueError("Missing visible obstacle surface")
            for modifier, _visible in contacts:
                modifier.show_viewport = False
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = body.evaluated_get(depsgraph)
            uncorrected = evaluated.to_mesh()
            try:
                original_positions = world_positions(evaluated, uncorrected)
            finally:
                evaluated.to_mesh_clear()
            for modifier, visible in contacts:
                modifier.show_viewport = visible
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = body.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                if len(mesh.vertices) != len(original_positions):
                    raise ValueError("Final contact must not alter the skin topology")
                positions = world_positions(evaluated, mesh)
                if not np.isfinite(positions).all() or not np.isfinite(original_positions).all():
                    raise ValueError("Non-finite final skin coordinate")
                displacement = float(np.linalg.norm(positions - original_positions, axis=1).max(initial=0.0))
                if displacement > correction:
                    correction, correction_frame = displacement, frame
                candidates = positions[possible_inside_vertices(positions, obstacle_surface.objects, depsgraph)]
                queried_vertices += len(candidates)
                for position in candidates:
                    point = Vector(position)
                    hit, normal, _face, _distance = tree.find_nearest(point)
                    if hit is not None:
                        penetration = -(point - hit).dot(normal)
                        if penetration > maximum:
                            maximum, penetration_frame = penetration, frame
                vertices_checked += len(mesh.vertices)
            finally:
                evaluated.to_mesh_clear()
    finally:
        for modifier, level in subdivisions:
            modifier.levels = level
        for modifier, visible in contacts:
            modifier.show_viewport = visible
    return {
        "frames_checked": end - start + 1,
        "vertices_checked": vertices_checked,
        "queried_vertices": queried_vertices,
        "subdivision": max((modifier.render_levels for modifier, _level in subdivisions), default=0),
        "maximum_penetration": round(maximum, 6),
        "maximum_correction": round(correction, 6),
        "peak_penetration_frame": penetration_frame,
        "peak_correction_frame": correction_frame,
        "issues": (["rendered-skin-inside-obstacle"] if maximum > MAX_RENDER_PENETRATION else [])
                  + (["excessive-final-skin-correction"] if correction > MAX_RENDER_CORRECTION else []),
    }
