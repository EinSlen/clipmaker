"""
Background music helper.

Used by main.py and motivation.py to mix in a sad/trending TikTok track
on top of (or replacing) the original audio of a rendered video.

The music library lives in `web/public/music/` so it's shared with the web app.
"""
from __future__ import annotations

import os
import json
import random
import subprocess
from pathlib import Path
from typing import Optional, List

REPO_ROOT = Path(__file__).resolve().parent
MUSIC_DIR = REPO_ROOT / "web" / "public" / "music"
DATA_FILE = REPO_ROOT / "web" / "data" / "music.json"

AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg")


def list_tracks(vibe: Optional[str] = None) -> List[Path]:
    """Returns existing audio files in the shared music library, optionally
    filtered by a vibe declared in web/data/music.json."""
    if not MUSIC_DIR.exists():
        return []

    on_disk = {p.name: p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT}
    if not on_disk:
        return []

    declared = []
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            declared = data.get("tracks", []) or []
        except Exception:
            declared = []

    if vibe and declared:
        matching = []
        for d in declared:
            file_name = os.path.basename(d.get("file", ""))
            vibes = [v.lower() for v in d.get("vibe", [])]
            if file_name in on_disk and vibe.lower() in vibes:
                matching.append(on_disk[file_name])
        if matching:
            return matching

    return list(on_disk.values())


def pick_track(vibe: Optional[str] = None, exclude: Optional[List[str]] = None) -> Optional[Path]:
    tracks = list_tracks(vibe=vibe)
    if exclude:
        ex = {os.path.basename(p) for p in exclude}
        tracks = [t for t in tracks if t.name not in ex]
    return random.choice(tracks) if tracks else None


def mix_background_music(
    video_path: str,
    output_path: str,
    music_path: Optional[str] = None,
    vibe: Optional[str] = None,
    music_volume: float = 0.55,
    duck_original: float = 0.35,
) -> Optional[str]:
    """
    Mixes background music onto a finished video using ffmpeg.

    - If `music_path` is None, picks one at random for the given `vibe`
      (or any available track if no vibe match).
    - Ducks the original audio (multiplied by `duck_original`).
    - Loops music if it's shorter than the video.
    - Output is encoded with libx264 + aac, web-friendly.

    Returns the output path on success, None on failure.
    """
    chosen: Optional[Path] = Path(music_path) if music_path else pick_track(vibe=vibe)
    if not chosen or not chosen.exists():
        print(f"  ⚠ Aucune musique disponible (vibe={vibe!r}) — passe sans musique.")
        return None

    print(f"  🎵 Musique : {chosen.name} (volume {music_volume:.0%}, duck original {duck_original:.0%})")

    filter_complex = (
        f"[0:a]volume={duck_original:.2f}[a0];"
        f"[1:a]aloop=loop=-1:size=2e9,volume={music_volume:.2f}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(chosen),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: re-encode the video too in case stream copy refuses it.
        cmd_reencode = cmd[:cmd.index("-c:v") + 1] + ["libx264", "-preset", "medium", "-crf", "20"] + cmd[cmd.index("-c:a"):]
        result = subprocess.run(cmd_reencode, capture_output=True, text=True)
        if result.returncode != 0:
            print("  ❌ ffmpeg a échoué :", result.stderr[-500:])
            return None

    return str(output_path)


if __name__ == "__main__":
    # Quick smoke test
    print("Pistes disponibles :", [t.name for t in list_tracks()])
