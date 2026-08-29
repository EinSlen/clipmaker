"""Closed-volume final contact for the solid staircase and hollow receivers.

Unlike Shrinkwrap OUTSIDE's nearest-face test, ray exits classify the whole
closed solid. Only validated, disjoint, outward-oriented components opt in.
Full ray parity audits every corrected vertex independently of this classifier.
"""
import bpy
import numpy as np
from mathutils import Vector


def inspect_volume_surface(body, obstacle_surface, start, end):
    """Independent full-vertex audit; deliberately retains production limits."""
    from soft_body_render_contact import (world_positions, possible_inside_vertices,
                                          MAX_RENDER_PENETRATION, MAX_RENDER_CORRECTION)
    from soft_body_stair_geometry import VOLUME_CONTACT
    subdivisions = [(modifier, modifier.levels) for modifier in body.modifiers if modifier.type == 'SUBSURF']
    contacts = [(modifier, modifier.show_viewport) for modifier in body.modifiers
                if modifier.type in {'NODES', 'SHRINKWRAP'} and modifier.name.startswith('Final skin contact')]
    maximum = correction = 0.0
    vertices_checked = queried = outside_moved = 0
    peak_penetration = peak_correction = None
    try:
        for modifier, _ in subdivisions:
            modifier.levels = modifier.render_levels
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            tree = obstacle_surface.at_frame(frame)
            if tree is None:
                raise ValueError('Missing visible obstacle surface')
            for modifier, _ in contacts:
                modifier.show_viewport = False
            evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                original = world_positions(evaluated, mesh)
            finally:
                evaluated.to_mesh_clear()
            for modifier, visible in contacts:
                modifier.show_viewport = visible
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = body.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                positions = world_positions(evaluated, mesh)
            finally:
                evaluated.to_mesh_clear()
            if positions.shape != original.shape or not np.isfinite(positions).all() or not np.isfinite(original).all():
                raise ValueError('Invalid final mesh topology or coordinates')
            distances = np.linalg.norm(positions - original, axis=1)
            displacement = float(distances.max(initial=0.0))
            if displacement > correction:
                correction, peak_correction = displacement, frame
            for index in np.flatnonzero(distances > .00001):
                if not point_inside_closed_surface(tree, Vector(original[index])):
                    outside_moved += 1
            candidates = positions[possible_inside_vertices(positions, obstacle_surface.objects, depsgraph)]
            for value in candidates:
                point = Vector(value)
                if point_inside_closed_surface(tree, point):
                    _hit, _normal, _face, distance = tree.find_nearest(point)
                    if distance > maximum:
                        maximum, peak_penetration = distance, frame
            vertices_checked += len(positions)
            queried += len(candidates)
    finally:
        for modifier, level in subdivisions:
            modifier.levels = level
        for modifier, visible in contacts:
            modifier.show_viewport = visible
    return {'frames_checked': end - start + 1, 'vertices_checked': vertices_checked,
            'queried_vertices': queried, 'subdivision': max((m.render_levels for m, _ in subdivisions), default=0),
            'maximum_penetration': round(maximum, 6), 'maximum_correction': round(correction, 6),
            'peak_penetration_frame': peak_penetration, 'peak_correction_frame': peak_correction,
            'contact_model': VOLUME_CONTACT,
            'outside_vertices_moved': outside_moved, 'classification': 'independent-three-ray-parity',
            'issues': (['rendered-skin-inside-obstacle'] if maximum > MAX_RENDER_PENETRATION else [])
                      + (['excessive-final-skin-correction'] if correction > MAX_RENDER_CORRECTION else [])
                      + (['outside-vertex-moved'] if outside_moved else [])}


def add_volume_contact(body, targets):
    from soft_body_render_contact import CONTACT_OFFSET
    for target in targets:
        group = bpy.data.node_groups.new('Closed-volume surface contact', 'GeometryNodeTree')
        group.inputs.new('NodeSocketGeometry', 'Geometry')
        group.outputs.new('NodeSocketGeometry', 'Geometry')
        nodes, links = group.nodes, group.links
        source, output = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
        position = nodes.new('GeometryNodeInputPosition')
        info = nodes.new('GeometryNodeObjectInfo')
        info.transform_space = 'RELATIVE'
        info.inputs['Object'].default_value = target
        info.inputs['As Instance'].default_value = False
        votes = []
        for vector in ((1, .173, .317), (-.31, 1, .127), (.219, -.341, 1)):
            direction = Vector(vector).normalized()
            ray = nodes.new('GeometryNodeRaycast')
            ray.inputs['Ray Direction'].default_value = direction
            ray.inputs['Ray Length'].default_value = 100
            links.new(info.outputs['Geometry'], ray.inputs['Target Geometry'])
            links.new(position.outputs['Position'], ray.inputs['Source Position'])
            dot = nodes.new('ShaderNodeVectorMath')
            dot.operation = 'DOT_PRODUCT'
            dot.inputs[1].default_value = direction
            links.new(ray.outputs['Hit Normal'], dot.inputs[0])
            outward = nodes.new('ShaderNodeMath')
            outward.operation = 'GREATER_THAN'
            outward.inputs[1].default_value = 0
            links.new(dot.outputs['Value'], outward.inputs[0])
            vote = nodes.new('FunctionNodeBooleanMath')
            vote.operation = 'AND'
            links.new(ray.outputs['Is Hit'], vote.inputs[0])
            links.new(outward.outputs[0], vote.inputs[1])
            votes.append(vote.outputs[0])
        add_first, add_last = nodes.new('ShaderNodeMath'), nodes.new('ShaderNodeMath')
        add_first.operation = add_last.operation = 'ADD'
        links.new(votes[0], add_first.inputs[0])
        links.new(votes[1], add_first.inputs[1])
        links.new(add_first.outputs[0], add_last.inputs[0])
        links.new(votes[2], add_last.inputs[1])
        inside = nodes.new('ShaderNodeMath')
        inside.operation = 'GREATER_THAN'
        inside.inputs[1].default_value = 1.5
        links.new(add_last.outputs[0], inside.inputs[0])
        nearest = nodes.new('GeometryNodeProximity')
        nearest.target_element = 'FACES'
        links.new(info.outputs['Geometry'], nearest.inputs['Target'])
        links.new(position.outputs['Position'], nearest.inputs['Source Position'])
        # A point exactly on a face may register a zero-distance exit in
        # some ray directions but not others. Its nearest-point subtraction
        # is numerical noise, not an outward direction (native frame 83).
        # Keep that boundary point unchanged; do not add a tangential 3 mm
        # offset. This is 300x smaller than the unchanged penetration limit.
        away_from_boundary = nodes.new('ShaderNodeMath')
        away_from_boundary.operation = 'GREATER_THAN'
        away_from_boundary.inputs[1].default_value = .00001
        links.new(nearest.outputs['Distance'], away_from_boundary.inputs[0])
        strictly_inside = nodes.new('FunctionNodeBooleanMath')
        strictly_inside.operation = 'AND'
        links.new(inside.outputs[0], strictly_inside.inputs[0])
        links.new(away_from_boundary.outputs[0], strictly_inside.inputs[1])
        toward = nodes.new('ShaderNodeVectorMath')
        toward.operation = 'SUBTRACT'
        links.new(nearest.outputs['Position'], toward.inputs[0])
        links.new(position.outputs['Position'], toward.inputs[1])
        unit = nodes.new('ShaderNodeVectorMath')
        unit.operation = 'NORMALIZE'
        links.new(toward.outputs['Vector'], unit.inputs[0])
        margin = nodes.new('ShaderNodeVectorMath')
        margin.operation = 'SCALE'
        margin.inputs['Scale'].default_value = CONTACT_OFFSET
        links.new(unit.outputs['Vector'], margin.inputs[0])
        destination = nodes.new('ShaderNodeVectorMath')
        destination.operation = 'ADD'
        links.new(nearest.outputs['Position'], destination.inputs[0])
        links.new(margin.outputs['Vector'], destination.inputs[1])
        move = nodes.new('GeometryNodeSetPosition')
        links.new(source.outputs['Geometry'], move.inputs['Geometry'])
        links.new(strictly_inside.outputs[0], move.inputs['Selection'])
        links.new(destination.outputs['Vector'], move.inputs['Position'])
        links.new(move.outputs['Geometry'], output.inputs['Geometry'])
        modifier = body.modifiers.new('Final skin contact - closed volume', 'NODES')
        modifier.node_group = group



def point_inside_closed_surface(tree, point):
    """Three complete parity rays; unresolved rays fail conservatively."""
    inside_votes = 0
    for direction in (Vector((1.0, 0.173, 0.317)),
                      Vector((-0.31, 1.0, 0.127)),
                      Vector((0.219, -0.341, 1.0))):
        direction.normalize()
        origin, crossings = point.copy(), 0
        for _ in range(64):
            hit, _normal, _face, _distance = tree.ray_cast(origin, direction)
            if hit is None:
                break
            crossings += 1
            origin = hit + direction * 0.00001
        else:
            return True
        inside_votes += crossings % 2
    return inside_votes >= 2
