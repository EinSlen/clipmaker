"""Conservative portrait-camera checks on the production physics samples.

These detect sustained off-camera action, not occlusion or artistic quality.
They never modify a trajectory, follow a body, or steer it toward a receiver.
"""

from functools import lru_cache
import math

from soft_body_variants import obstacle_specimen_depth_offsets


def camera_location(obstacle):
    if obstacle.key == "stair-cascade":
        return (obstacle.camera_target_x + 6.70, -11.50, 7.50)
    return (obstacle.camera_target_x + 1.05, -14.8, 7.25)


def _unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def _cross(first, second):
    return (first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0])


@lru_cache(maxsize=16)
def _camera_axes(obstacle):
    target = (obstacle.camera_target_x, 0.0, obstacle.camera_target_z)
    forward = _unit(tuple(b - a for a, b in zip(camera_location(obstacle), target)))
    right = _unit(_cross(forward, (0.0, 0.0, 1.0)))
    up = _cross(right, forward)
    return target, right, up


def project_point(point, obstacle):
    """Match the fixed Blender camera at the native 9:16 aspect ratio."""
    target, right, up = _camera_axes(obstacle)
    delta = tuple(a - b for a, b in zip(point, target))
    return (0.5 + sum(a * b for a, b in zip(delta, right)) / (obstacle.camera_scale * 9 / 16),
            0.5 + sum(a * b for a, b in zip(delta, up)) / obstacle.camera_scale)


def inspect_simulation_framing(simulations, variant, fps):
    """Check every output frame, with a generous envelope around each spine.

    A lower-frame exit is a legitimate result; one second of empty comparison
    footage is not. Multi-body trials stay readable while another body is
    finishing. A sustained side/top exit is rejected for each individual body.
    """
    depths = obstacle_specimen_depth_offsets(variant.obstacle.key)
    if fps <= 0 or len(simulations) != len(depths) or not simulations:
        raise ValueError("Framing requires every specimen and a positive FPS")
    frame_count = len(simulations[0]) - 1
    if frame_count < 1 or any(len(simulation) != frame_count + 1 for simulation in simulations):
        raise ValueError("Framing requires matching nonempty native timelines")
    radius = variant.shape.radius * 1.5
    pad_x = radius / (variant.obstacle.camera_scale * 9 / 16)
    pad_y = radius / variant.obstacle.camera_scale
    empty_run = longest_empty = longest_side = 0
    side_runs = [0] * len(simulations)
    for frame in range(frame_count):
        any_visible = False
        for body, (simulation, depth) in enumerate(zip(simulations, depths)):
            projected = [project_point((point[0], depth - 0.04, point[1]), variant.obstacle)
                         for point in simulation[frame][0]]
            min_x = min(point[0] for point in projected) - pad_x
            max_x = max(point[0] for point in projected) + pad_x
            min_y = min(point[1] for point in projected) - pad_y
            max_y = max(point[1] for point in projected) + pad_y
            side_exit = (max_x < 0.0 or min_x > 1.0 or min_y > 1.0) and max_y >= 0.0
            side_runs[body] = side_runs[body] + 1 if side_exit else 0
            longest_side = max(longest_side, side_runs[body])
            any_visible = any_visible or (max_x >= 0.0 and min_x <= 1.0 and max_y >= 0.0 and min_y <= 1.0)
        empty_run = 0 if any_visible else empty_run + 1
        longest_empty = max(longest_empty, empty_run)
    issues = []
    if longest_side > round(fps * 0.5):
        issues.append("body-left-camera-side")
    if longest_empty > fps:
        issues.append("empty-comparison-tail")
    return {"frames_checked": frame_count,
            "maximum_empty_seconds": round(longest_empty / fps, 4),
            "maximum_side_exit_seconds": round(longest_side / fps, 4),
            "issues": issues}
