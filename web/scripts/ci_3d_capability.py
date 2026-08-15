#!/usr/bin/env python3
"""Measure whether a GitHub-hosted runner can produce the final 3D video.

The probe has two independent parts:

* every obstacle is constructed and simulated in Blender at smoke settings;
* three frames are rendered at the real 1080x1920 / 128-sample quality.

The native timings are extrapolated to the 900 frames of a 30 second Short.
The result is a capability report, not a low-resolution video presented as a
production render.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from soft_body_variants import OBSTACLE_KEYS, variant_for_seed


SCRIPT_DIR = Path(__file__).resolve().parent


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=910104)
    parser.add_argument("--obstacle", choices=("auto",) + OBSTACLE_KEYS, default="moving-slide")
    parser.add_argument("--max-hours", type=float, default=5.25)
    parser.add_argument("--smoke-timeout-minutes", type=float, default=18.0)
    parser.add_argument("--benchmark-timeout-minutes", type=float, default=120.0)
    return parser.parse_args()


def run(command: list[str], timeout_minutes: float) -> float:
    started = time.perf_counter()
    subprocess.run(command, check=True, timeout=timeout_minutes * 60.0)
    return time.perf_counter() - started


def blender_scene_command(
    blender: str,
    frames: Path,
    events: Path,
    seed: int,
    obstacle: str,
    *,
    duration: float,
    fps: int,
    width: int,
    height: int,
    samples: int,
    softness: int,
) -> list[str]:
    return [
        blender,
        "--background",
        "--factory-startup",
        "--python",
        str(SCRIPT_DIR / "blender-soft-body-slide.py"),
        "--",
        "--frames",
        str(frames),
        "--events",
        str(events),
        "--duration",
        str(duration),
        "--fps",
        str(fps),
        "--width",
        str(width),
        "--height",
        str(height),
        "--samples",
        str(samples),
        "--seed",
        str(seed),
        "--softness",
        str(softness),
        "--stage-softness",
        str(softness),
        "--obstacle",
        obstacle,
        "--theme",
        "sunset",
        "--title",
        "CLOUD CAPABILITY TEST",
        "--build-only",
    ]


def write_report(output: Path, result: dict[str, object]) -> None:
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    rows = []
    for item in result.get("obstacle_smokes", []):
        rows.append(
            f"| `{item['obstacle']}` | {'PASS' if item['ok'] else 'FAIL'} | "
            f"{item.get('seconds', 0):.1f} s |"
        )
    obstacle_table = "\n".join(rows) or "| — | FAIL | 0 s |"
    native = result.get("native_benchmark") or {}
    estimate = result.get("estimated_final_hours")
    estimate_label = f"{estimate:.2f} h" if isinstance(estimate, (int, float)) else "indisponible"
    verdict = "COMPATIBLE" if result.get("feasible") else "TROP LENT POUR UN RUNNER GITHUB"
    error = result.get("error")
    report = f"""# Test de capacité 3D GitHub

**Verdict : {verdict}**

- Seed : `{result.get('seed')}`
- Obstacle chronométré : `{result.get('resolved_obstacle')}`
- Qualité chronométrée : 1080×1920, 128 samples Eevee
- Moyenne par image native : {native.get('average_frame_seconds', 0):.2f} s
- Projection pour 900 images : **{estimate_label}**
- Budget maximal du workflow : {result.get('max_hours')} h

La projection part de trois images réellement rendues en qualité finale. Les PNG
natifs sont inclus dans l'artefact. Un smoke minuscule n'est jamais considéré
comme une vidéo publiable.

## Construction réelle de tous les obstacles

| Obstacle | État | Temps Blender |
|---|---:|---:|
{obstacle_table}
"""
    if error:
        report += f"\n## Erreur 3D\n\n```text\n{error}\n```\n"
    (output / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = arguments()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = output / "work"
    work.mkdir(exist_ok=True)
    blender = os.environ.get("BLENDER_BIN", "blender")
    requested_obstacle = None if args.obstacle == "auto" else args.obstacle
    resolved = variant_for_seed(args.seed, requested_obstacle).obstacle.key
    result: dict[str, object] = {
        "ok": False,
        "feasible": False,
        "seed": args.seed,
        "requested_obstacle": args.obstacle,
        "resolved_obstacle": resolved,
        "max_hours": args.max_hours,
        "obstacle_smokes": [],
        "native_benchmark": None,
        "estimated_final_hours": None,
    }

    try:
        obstacle_smokes: list[dict[str, object]] = []
        for index, obstacle in enumerate(OBSTACLE_KEYS):
            smoke_root = work / f"smoke-{obstacle}"
            frames = smoke_root / "frames"
            events = smoke_root / "events.json"
            frames.mkdir(parents=True, exist_ok=True)
            print(f"[3D {index + 1}/{len(OBSTACLE_KEYS)}] Building {obstacle}...", flush=True)
            try:
                elapsed = run(
                    blender_scene_command(
                        blender,
                        frames,
                        events,
                        args.seed + index,
                        obstacle,
                        duration=6.0,
                        fps=3,
                        width=180,
                        height=320,
                        samples=1,
                        softness=25,
                    ),
                    args.smoke_timeout_minutes,
                )
                blend_candidates = tuple(frames.glob("soft-body-*.blend"))
                payload = json.loads(events.read_text(encoding="utf-8"))
                if len(blend_candidates) != 1 or not isinstance(payload.get("events"), list):
                    raise RuntimeError("Blender scene or collision telemetry is missing")
                obstacle_smokes.append(
                    {
                        "obstacle": obstacle,
                        "ok": True,
                        "seconds": elapsed,
                        "scene": blend_candidates[0].name,
                    }
                )
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                obstacle_smokes.append(
                    {"obstacle": obstacle, "ok": False, "seconds": 0.0, "error": str(error)}
                )
            finally:
                shutil.rmtree(smoke_root, ignore_errors=True)
        result["obstacle_smokes"] = obstacle_smokes

        benchmark_root = work / "native-benchmark"
        frames = benchmark_root / "frames"
        events = benchmark_root / "events.json"
        frames.mkdir(parents=True, exist_ok=True)
        print("[3D benchmark] Building the 100% softness production scene...", flush=True)
        build_seconds = run(
            blender_scene_command(
                blender,
                frames,
                events,
                args.seed,
                args.obstacle,
                duration=6.0,
                fps=6,
                width=1080,
                height=1920,
                samples=128,
                softness=100,
            ),
            args.smoke_timeout_minutes,
        )
        blend = frames / "soft-body-100.blend"
        if not blend.is_file():
            raise RuntimeError("The native benchmark .blend was not created")

        native_output = output / "native-frames"
        print("[3D benchmark] Rendering three native production frames...", flush=True)
        run(
            [
                blender,
                "--background",
                str(blend),
                "--python",
                str(SCRIPT_DIR / "blender-ci-benchmark.py"),
                "--",
                "--output",
                str(native_output),
                "--frames",
                "8,10,12",
                "--width",
                "1080",
                "--height",
                "1920",
                "--samples",
                "128",
            ],
            args.benchmark_timeout_minutes,
        )
        native = json.loads(
            (native_output / "native-frame-timings.json").read_text(encoding="utf-8")
        )
        average_frame_seconds = float(native["average_frame_seconds"])
        # A production Short contains 30 seconds x 30 genuinely rendered
        # frames. Five six-second stages also cost about five benchmark builds.
        estimated_seconds = average_frame_seconds * 900.0 + build_seconds * 5.0
        estimated_hours = estimated_seconds / 3600.0
        smokes_ok = all(bool(item["ok"]) for item in obstacle_smokes)
        result.update(
            {
                "ok": True,
                "feasible": smokes_ok and estimated_hours <= args.max_hours,
                "native_benchmark": native,
                "benchmark_scene_build_seconds": build_seconds,
                "estimated_final_hours": estimated_hours,
            }
        )
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
        write_report(output, result)

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
