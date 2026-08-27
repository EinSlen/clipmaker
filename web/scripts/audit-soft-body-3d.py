#!/usr/bin/env python3
"""Run the production soft-body solver without rendering and audit its motion.

This script is executed by Blender because the renderer uses ``mathutils.Vector``.
It intentionally exercises the same attempt durations and seeded motion as a
30 fps, 30 second publication while sampling fewer display frames for speed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from soft_body_variants import (
    OBSTACLES,
    obstacle_specimen_depth_offsets,
    obstacle_specimen_offsets,
    stage_attempt_frame_spans,
    stage_frame_spans,
    variant_for_seed,
)


def load_renderer():
    path = SCRIPT_DIR / "blender-soft-body-slide.py"
    spec = importlib.util.spec_from_file_location("clipmaker_soft_body_renderer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="910104")
    parser.add_argument("--obstacles", default="all")
    parser.add_argument("--softness", default="all")
    parser.add_argument("--sample-fps", type=int, default=5)
    parser.add_argument("--production-fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output")
    parser.add_argument("--check-surface", action="store_true")
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(values)


def audit_attempt(
    renderer,
    variant,
    softness,
    stage_index,
    attempt_index,
    duration,
    sample_fps,
    production_fps,
    instance_index,
    instance_offset,
    check_surface,
):
    frame_count = max(1, round(duration * production_fps))
    motion_index = stage_index + attempt_index * len(variant.stages)
    simulated = renderer.simulate_chain(
        softness,
        frame_count,
        production_fps,
        variant,
        motion_index,
        instance_offset,
        (
            0.045
            if instance_index == 0 and len(obstacle_specimen_offsets(variant.obstacle.key)) > 1
            else -0.045
            if len(obstacle_specimen_offsets(variant.obstacle.key)) > 1
            else 0.0
        ),
    )
    surface = {"corrected_vertices": 0, "maximum_correction": 0.0, "inside_contacts": 0}
    if check_surface:
        renderer.reset_scene()
        marble = renderer.material("Audit marble", (0.7, 0.7, 0.7, 1.0))
        gold = renderer.material("Audit gold", (0.8, 0.5, 0.1, 1.0))
        renderer.add_receiver(marble, gold, variant)
        trial_spans = ((motion_index, 1, frame_count),)
        if variant.obstacle.key == "moving-slide":
            renderer.add_ramp(marble, gold, variant, frame_count, production_fps, trial_spans)
        else:
            renderer.add_obstacle_geometry(marble, gold, variant, frame_count, production_fps, trial_spans)
        obstacles = renderer.ObstacleSurface(renderer.bpy.context.collection.objects)
        base_vertices, _faces = renderer.capsule_geometry(variant)
        depth_offset = obstacle_specimen_depth_offsets(variant.obstacle.key)[instance_index]
        for index in range(0, len(simulated) - 1, max(1, round(production_fps / sample_fps))):
            points, impact, node_impacts, *_rest = simulated[index]
            shape = renderer.skin_capsule(base_vertices, points, softness / 100.0, impact, node_impacts, index, variant)
            _shape, sample = renderer.constrain_visible_skin(
                shape, base_vertices, points, variant, obstacles.at_frame(index + 1), depth_offset,
            )
            surface["corrected_vertices"] += sample["corrected_vertices"]
            surface["inside_contacts"] += sample["inside_contacts"]
            surface["maximum_correction"] = max(surface["maximum_correction"], sample["maximum_correction"])
    expected_rest = 2.0 * variant.shape.cylinder_half / 40.0
    minimum_ratio = math.inf
    maximum_ratio = 0.0
    maximum_coordinate = 0.0
    finite = True
    centers = []
    for points, *_rest in simulated:
        center_x = sum(point.x for point in points) / len(points)
        center_y = sum(point.y for point in points) / len(points)
        centers.append((center_x, center_y))
        for point in points:
            finite = finite and math.isfinite(point.x) and math.isfinite(point.y)
            maximum_coordinate = max(maximum_coordinate, abs(point.x), abs(point.y))
        for first, second in zip(points, points[1:]):
            ratio = (second - first).length / expected_rest
            minimum_ratio = min(minimum_ratio, ratio)
            maximum_ratio = max(maximum_ratio, ratio)

    physics_samples = simulated.physics_samples
    primary_peak = max((sample[1] for sample in physics_samples), default=0.0)
    receiver_peak = max((sample[2] for sample in physics_samples), default=0.0)
    start_y = centers[0][1]
    minimum_y = min(center[1] for center in centers)
    physics_centers = [(sample[3], sample[4]) for sample in physics_samples]
    travelled = max(
        math.dist(first, second)
        for first, second in zip(physics_centers, physics_centers[1:])
    ) if len(physics_centers) > 1 else 0.0
    issues = []
    if not finite:
        issues.append("non-finite-coordinate")
    if maximum_coordinate > 25.0:
        issues.append("left-scene-before-cut")
    if minimum_ratio < 0.82 or maximum_ratio > 1.18:
        issues.append("constraint-tear")
    if primary_peak < 0.20:
        issues.append("missed-obstacle")
    if start_y - minimum_y < 0.65:
        issues.append("stalled-at-spawn")
    if travelled > 0.35:
        issues.append("single-frame-teleport")
    if surface["inside_contacts"]:
        issues.append("spine-inside-visible-obstacle")
    return {
        "attempt": attempt_index + 1,
        "body": instance_index + 1,
        "duration": round(duration, 4),
        "primary_peak": round(primary_peak, 4),
        "receiver_peak": round(receiver_peak, 4),
        "receiver_entries": len(simulated.receiver_entries),
        "first_receiver_entry": (
            round(float(simulated.receiver_entries[0][0]), 4)
            if simulated.receiver_entries
            else None
        ),
        "minimum_segment_ratio": round(minimum_ratio, 4),
        "maximum_segment_ratio": round(maximum_ratio, 4),
        "maximum_coordinate": round(maximum_coordinate, 4),
        "vertical_drop": round(start_y - minimum_y, 4),
        "maximum_physics_step": round(travelled, 4),
        "terminal_center": [round(value, 4) for value in centers[-1]],
        "surface": surface if check_surface else None,
        "issues": issues,
    }


def main() -> int:
    args = arguments()
    if args.sample_fps <= 0 or args.production_fps <= 0 or args.duration <= 0:
        raise ValueError("FPS and duration must be positive")
    renderer = load_renderer()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    obstacle_filter = None if args.obstacles == "all" else {
        value.strip() for value in args.obstacles.split(",") if value.strip()
    }
    softness_filter = None if args.softness == "all" else {
        int(value.strip()) for value in args.softness.split(",") if value.strip()
    }
    unknown = (obstacle_filter or set()) - {obstacle.key for obstacle in OBSTACLES}
    if unknown or not seeds or softness_filter == set():
        raise ValueError(f"Empty or unknown audit selection: {sorted(unknown)}")
    if softness_filter is not None and any(value < 0 or value > 100 for value in softness_filter):
        raise ValueError("Softness must be between 0 and 100")
    production_frames = round(args.duration * args.production_fps)
    report = {
        "production": {
            "fps": args.production_fps,
            "duration": args.duration,
            "frames": production_frames,
        },
        "sample_fps": args.sample_fps,
        "surface_checked": args.check_surface,
        "complete": False,
        "runs": [],
    }

    def checkpoint():
        report["issue_count"] = sum(
            len(attempt["issues"])
            for run in report["runs"] for stage in run["stages"] for attempt in stage["attempts"]
        )
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for seed in seeds:
        for obstacle in OBSTACLES:
            if obstacle_filter is not None and obstacle.key not in obstacle_filter:
                continue
            variant = variant_for_seed(seed, obstacle.key)
            stage_spans = stage_frame_spans(
                production_frames,
                len(variant.stages),
                obstacle.key,
            )
            run = {
                "seed": seed,
                "obstacle": obstacle.key,
                "stages": [],
            }
            report["runs"].append(run)
            selected_stages = (
                tuple(enumerate(variant.stages)) if softness_filter is None else
                tuple((min(range(len(variant.stages)), key=lambda index: abs(variant.stages[index] - softness)), softness)
                      for softness in sorted(softness_filter))
            )
            for stage_index, softness in selected_stages:
                stage_span = stage_spans[stage_index]
                attempt_spans = stage_attempt_frame_spans(
                    stage_span[0],
                    stage_span[1],
                    args.production_fps,
                    obstacle.key,
                    softness,
                )
                stage = {
                    "softness": softness,
                    "attempt_count": len(attempt_spans),
                    "attempts": [],
                }
                run["stages"].append(stage)
                for attempt_index, attempt_span in enumerate(attempt_spans):
                    duration = (attempt_span[1] - attempt_span[0] + 1) / args.production_fps
                    for instance_index, instance_offset in enumerate(
                        obstacle_specimen_offsets(obstacle.key)
                    ):
                        stage["attempts"].append(
                            audit_attempt(
                                renderer,
                                variant,
                                softness,
                                stage_index,
                                attempt_index,
                                duration,
                                args.sample_fps,
                                args.production_fps,
                                instance_index,
                                instance_offset,
                                args.check_surface,
                            )
                        )
                        checkpoint()
                        print("CLIPMAKER_AUDIT_PROGRESS=" + json.dumps({
                            "seed": seed, "obstacle": obstacle.key, "softness": softness,
                            **stage["attempts"][-1],
                        }, separators=(",", ":")), flush=True)

    report["issue_count"] = sum(
        len(attempt["issues"])
        for run in report["runs"]
        for stage in run["stages"]
        for attempt in stage["attempts"]
    )
    report["complete"] = True
    rendered = json.dumps(report, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print("CLIPMAKER_SOFT_BODY_AUDIT=" + json.dumps(report, separators=(",", ":")))
    return 1 if report["issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
