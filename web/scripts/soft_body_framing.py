"""Conservative portrait-camera checks on the production physics samples.

These detect sustained off-camera action, not occlusion or artistic quality.
They never modify a trajectory, follow a body, or steer it toward a receiver.
"""

from functools import lru_cache
import math

from soft_body_variants import obstacle_specimen_depth_offsets


def camera_location(obstacle):
    if obstacle.key == "stair-cascade":
        # Face the outlet lanes more directly, keeping their exits inside the
        # portrait frame. Preserve distance/elevation and never follow a body.
        distance = math.hypot(6.70, 11.50)
        angle = math.radians(60.0)
        return (obstacle.camera_target_x + distance * math.sin(angle),
                -distance * math.cos(angle), 7.50)
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


def inspect_stair_outlet(simulations, variant, fps):
    """Require a visible outlet-zone beat, not a guaranteed successful catch.

    Collision and framing checks alone accepted a 100% comparison cut halfway
    down the stairs. Observe each body's leading surface reaching the height
    of the outlet, followed by at least 0.35 s of visible footage. A miss is a
    valid result too; this never moves a body or tests it against a target X.
    The extra terminal physics sample is NOT a rendered frame.
    """
    if variant.obstacle.key != "stair-cascade":
        return None
    if fps <= 0 or len(simulations) != 3:
        raise ValueError("Stair outlet checks require three specimens and a positive FPS")
    frame_count = len(simulations[0]) - 1
    if frame_count < 1 or any(len(simulation) != frame_count + 1 for simulation in simulations):
        raise ValueError("Stair outlet checks require matching nonempty native timelines")
    required_intervals = math.ceil(0.35 * fps)
    bodies = []
    for body, simulation in enumerate(simulations, 1):
        first_frame = next((frame for frame, sample in enumerate(simulation[:-1])
                            if min(point[1] for point in sample[0]) - variant.shape.radius
                            <= variant.receiver.top), None)
        intervals = frame_count - 1 - first_frame if first_frame is not None else 0
        bodies.append({"body": body,
                       "first_outlet_frame": first_frame + 1 if first_frame is not None else None,
                       "observation_seconds": round(intervals / fps, 4),
                       "observed": first_frame is not None and intervals >= required_intervals})
    return {"bodies": bodies, "minimum_observation_seconds": 0.35,
            "issues": [] if all(body["observed"] for body in bodies) else ["unfinished-stair-descent"]}


def validate_stair_outlet_evidence(outlet, frame_count, fps):
    """Fail closed when imported metadata predates the complete-descent gate."""
    message = "Native 3D stair outlet observation was not validated"
    if (not isinstance(outlet, dict) or outlet.get("issues") != []
        or outlet.get("minimum_observation_seconds") != 0.35
        or not isinstance(outlet.get("bodies"), list) or len(outlet["bodies"]) != 3):
        raise ValueError(message)
    ids = set()
    for item in outlet["bodies"]:
        if not isinstance(item, dict):
            raise ValueError(message)
        body, first, seconds = item.get("body"), item.get("first_outlet_frame"), item.get("observation_seconds")
        if (type(body) is not int or body not in (1, 2, 3) or body in ids
            or item.get("observed") is not True or type(first) is not int
            or not 1 <= first <= frame_count - math.ceil(0.35 * fps)
            or type(seconds) not in (int, float) or not math.isfinite(seconds)
            or abs(seconds - round((frame_count - first) / fps, 4)) > 0.000051):
            raise ValueError(message)
        ids.add(body)


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
    outlet = inspect_stair_outlet(simulations, variant, fps)
    if outlet:
        issues.extend(outlet["issues"])
    return {"frames_checked": frame_count,
            "maximum_empty_seconds": round(longest_empty / fps, 4),
            "maximum_side_exit_seconds": round(longest_side / fps, 4),
            "outlet": outlet,
            "issues": issues}
