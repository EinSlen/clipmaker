"""Cut the published Soft Body edit out of the complete native render.

Blender renders the whole 30 s timeline, because that is what the physics
evidence covers and what every gate upstream checks. What a viewer gets is an
edit of it. TikTok Studio measured the first automatic posts at about 40 % of
viewers gone after one second, 70 % after five, and 3 to 6 % reaching the end,
so every post stopped at the test audience of about 90 views. A third of the
render was frames in which nothing moves: the rigid take standing on the ring
for three seconds, soft takes resting, an empty studio once a body has gone
into the receiver. The edit keeps each take from its first movement to a short
beat after its last one, and opens on the final level's payoff before the
comparison starts.

Only the ends of a take are cut, never the middle, so what stays on screen is
the same continuous simulation the evidence covers, observed for fewer frames.
"""

from __future__ import annotations

import math
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# A pixel counts as moving when it changes by more than this many grey levels.
# Eevee renders a still studio identically from frame to frame, so the only
# change below it is the slow rocking of a body that has stopped.
MOTION_LEVEL = 8
# Measured at a quarter of the native width: the verdict is the same and the
# pass over 900 frames stays well under a minute.
MOTION_REDUCTION = 4
# A take is still once its motion falls under this share of its own busy
# level, so a family filmed from further away is judged on its own scale.
ACTIVE_RATIO = 0.4
ACTIVE_PERCENTILE = 0.9
SMOOTHING_FRAMES = 4
# The beat after the last movement is what lets a viewer read the outcome:
# the rigid capsule stuck on the ring, or the receiver that swallowed a body.
HOLD_SECONDS = 0.3
LEAD_SECONDS = 0.2
# The opening shows the last level arriving in its receiver, then cuts to 0%.
OPENING_BEFORE_SECONDS = 0.8
OPENING_AFTER_SECONDS = 0.4
PAYOFF_KINDS = frozenset({"receiver-entry", "receiver-contact"})


@dataclass(frozen=True)
class PublishedEdit:
    fps: int
    # Source frame numbers, in the order they are published.
    frames: tuple[int, ...]
    # Kept source range of every take, in timeline order.
    takes: tuple[tuple[int, int], ...]
    # Source range of the opening, and where the payoff lands in it.
    opening: tuple[int, int] | None
    opening_anchor: int | None
    # Published seconds, for the labels.
    opening_seconds: tuple[float, float] | None
    level_seconds: tuple[tuple[float, float], ...]

    @property
    def duration(self) -> float:
        return len(self.frames) / self.fps

    def summary(self) -> dict[str, object]:
        return {
            "version": 1,
            "frames": len(self.frames),
            "duration": round(self.duration, 3),
            "opening": list(self.opening) if self.opening else None,
            "takes": [list(take) for take in self.takes],
        }


def frame_motion(frames: Path, frame_count: int) -> tuple[float, ...]:
    """Share of pixels that visibly change from the previous frame.

    The first value is zero: frame 1 has nothing before it.
    """
    from PIL import Image, ImageChops

    threshold = [0] * (MOTION_LEVEL + 1) + [255] * (255 - MOTION_LEVEL)
    motion = []
    previous = None
    for index in range(1, frame_count + 1):
        with Image.open(frames / f"frame_{index:04d}.png") as image:
            current = image.convert("L").reduce(MOTION_REDUCTION)
        if previous is None:
            motion.append(0.0)
        else:
            changed = ImageChops.difference(current, previous).point(threshold)
            motion.append(changed.histogram()[255] / (current.width * current.height))
        previous = current
    return tuple(motion)


def active_span(motion: tuple[float, ...], first: int, last: int, fps: int) -> tuple[int, int]:
    """First and last frame of a take worth watching, with a beat either side."""
    # The first frame of a take differs from the take before it, and that
    # difference is the cut, not motion.
    values = [motion[frame - 1] for frame in range(first + 1, last + 1)]
    values = values[:1] + values
    ranked = sorted(values)
    busy = ranked[int(ACTIVE_PERCENTILE * (len(ranked) - 1))]
    if busy <= 0.0:
        return first, last
    threshold = ACTIVE_RATIO * busy
    active = []
    for index in range(len(values)):
        window = values[max(0, index - SMOOTHING_FRAMES):index + SMOOTHING_FRAMES + 1]
        if sum(window) / len(window) >= threshold:
            active.append(index)
    if not active:
        return first, last
    start = max(0, active[0] - round(LEAD_SECONDS * fps))
    end = min(len(values) - 1, active[-1] + round(HOLD_SECONDS * fps))
    return first + start, first + end


def event_frame(event: dict[str, object], fps: int) -> int:
    frame = event.get("frame")
    if isinstance(frame, (int, float)) and not isinstance(frame, bool):
        return int(frame)
    return math.floor(float(event["time"]) * fps) + 1


def payoff_frame(events: list[dict[str, object]], first: int, last: int, fps: int) -> int | None:
    """Frame where a take arrives: its receiver, or else its hardest contact."""
    inside = [event for event in events if first <= event_frame(event, fps) <= last]
    arrivals = [event for event in inside if event.get("kind") in PAYOFF_KINDS]
    if arrivals:
        return min(event_frame(event, fps) for event in arrivals)
    if inside:
        return event_frame(max(inside, key=lambda event: float(event.get("strength", 0.0))), fps)
    return None


def opening_span(
    events: list[dict[str, object]],
    attempts: tuple[tuple[int, int], ...],
    counts: tuple[int, ...],
    fps: int,
) -> tuple[int, int, int] | None:
    """The final level's payoff, shown before the comparison explains it."""
    for first, last in attempts[len(attempts) - counts[-1]:]:
        anchor = payoff_frame(events, first, last, fps)
        if anchor is not None:
            start = max(first + 1, anchor - round(OPENING_BEFORE_SECONDS * fps))
            end = min(last, anchor + round(OPENING_AFTER_SECONDS * fps))
            return start, end, anchor
    return None


def published_edit(
    motion: tuple[float, ...],
    attempts: tuple[tuple[int, int], ...],
    counts: tuple[int, ...],
    events: list[dict[str, object]],
    fps: int,
    cut: bool = True,
) -> PublishedEdit:
    """The published order of frames; ``cut=False`` keeps the native timeline."""
    if sum(counts) != len(attempts) or any(count < 1 for count in counts):
        raise ValueError("Every level must own at least one of the listed takes")
    frames: list[int] = []
    opening_window = opening_span(events, attempts, counts, fps) if cut else None
    if opening_window:
        frames.extend(range(opening_window[0], opening_window[1] + 1))
    opening_end = len(frames)
    takes = []
    take_starts = []
    for first, last in attempts:
        start, end = active_span(motion, first, last, fps) if cut else (first, last)
        take_starts.append(len(frames))
        frames.extend(range(start, end + 1))
        takes.append((start, end))
    level_seconds = []
    index = 0
    for count in counts:
        begin = take_starts[index]
        index += count
        finish = take_starts[index] if index < len(take_starts) else len(frames)
        level_seconds.append((begin / fps, finish / fps))
    return PublishedEdit(
        fps=fps,
        frames=tuple(frames),
        takes=tuple(takes),
        opening=opening_window[:2] if opening_window else None,
        opening_anchor=opening_window[2] if opening_window else None,
        opening_seconds=(0.0, opening_end / fps) if opening_window else None,
        level_seconds=tuple(level_seconds),
    )


def published_events(edit: PublishedEdit, events: list[dict[str, object]]) -> list[dict[str, object]]:
    """Move every collision to where its frame is published, once per showing.

    A contact on a cut frame is not seen, so it is not heard. A contact inside
    the opening is heard twice, because it is seen twice.
    """
    positions = defaultdict(list)
    for position, frame in enumerate(edit.frames):
        positions[frame].append(position)
    moved = []
    for event in events:
        frame = event_frame(event, edit.fps)
        offset = float(event["time"]) - (frame - 1) / edit.fps
        for position in positions.get(frame, ()):
            moved.append({**event, "time": position / edit.fps + offset, "frame": position + 1})
    return sorted(moved, key=lambda event: float(event["time"]))


def accent_times(edit: PublishedEdit, events: list[dict[str, object]]) -> tuple[float, ...]:
    """The surprise lands on the payoff of the opening, in the first second."""
    if edit.opening is None or edit.opening_anchor is None:
        return ()
    anchor = [event for event in events if event_frame(event, edit.fps) == edit.opening_anchor]
    offset = float(anchor[0]["time"]) - (edit.opening_anchor - 1) / edit.fps if anchor else 0.0
    return ((edit.opening_anchor - edit.opening[0]) / edit.fps + offset,)


def stage_published_frames(source: Path, destination: Path, edit: PublishedEdit) -> None:
    """Number the published frames from 1 without copying a render twice."""
    destination.mkdir(parents=True, exist_ok=False)
    for position, frame in enumerate(edit.frames, start=1):
        original = (source / f"frame_{frame:04d}.png").resolve()
        staged = destination / f"frame_{position:04d}.png"
        try:
            os.link(original, staged)
        except OSError:
            shutil.copyfile(original, staged)
