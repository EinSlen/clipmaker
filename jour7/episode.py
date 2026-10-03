#!/usr/bin/env python3
"""Render one Jour 7 episode folder into a vertical MP4.

    python jour7/episode.py jour7/episodes/001-sommeil
    python jour7/episode.py jour7/episodes/001-sommeil --redo 2 5

The folder holds `episode.json`: a caption, then one entry per scene with the
line the narrator says, the day badge shown over it and what the picture
shows. Every missing `sNN.png` is drawn by FLUX.2 klein through the cloud
control Worker, from the character sheet and a finished scene for the style,
so the character stays the same from one scene to the next. `--redo` draws
the listed scenes again. The voice is Edge TTS, whose word boundaries drive
the highlighted captions, and the output is `<slug>.mp4` in the same folder.
"""

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CLOUD_API = os.environ.get("CLIPMAKER_CLOUD_API", "https://clipmaker-cloud-control.einslen.workers.dev")
VOICE = "fr-FR-VivienneMultilingualNeural"

FPS = 30
W, H = 1080, 1920
FADE = 0.35
LEAD = 0.12
TAIL = 0.9
ZOOM = 0.07
# FLUX sometimes leaves a paper edge around the drawing; the zoom never
# starts below this, so the edge stays outside the frame.
OVERSCAN = 1.04
MUSIC_GAIN_DB = -11
YELLOW = "&H003DC8FF&"
WHITE = "&H00FFFFFF&"
GREY = "&H00B9B9B9&"
PUNCTUATION = re.compile(r"^[^\w]+$")

STYLE = (
    "Draw her exactly like the young woman in image 1 (same face, round glasses, short wavy dark-brown bob, "
    "mustard-yellow hoodie, blue jeans). Image 2 is only a sheet of style samples: match its art style, never its "
    "content or layout. Hand-drawn children's storybook illustration, colored pencil and soft gouache on warm cream "
    "paper, visible pencil grain, warm palette, cozy. "
    "Full-bleed vertical illustration, she is in the upper-middle of the frame. "
    "No border, no frame, no text, no letters, no signature, no watermark."
)


def ass_time(seconds):
    centiseconds = int(round(seconds * 100))
    return (f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02d}:"
            f"{centiseconds // 100 % 60:02d}.{centiseconds % 100:02d}")


def shown(token):
    return token.strip(".,;:!?").replace("’", "'")


def layout(words, lines):
    """Tie every spoken word to its scene and return when each scene starts.

    Edge TTS drops punctuation from its word boundaries, so the script tokens
    without letters are skipped and the rest must line up one for one; a
    mismatch means the captions would drift, and it stops the render.
    """
    tokens = [(index, token) for index, line in enumerate(lines)
              for token in line.split() if not PUNCTUATION.match(token)]
    if len(tokens) != len(words):
        raise SystemExit(f"{len(tokens)} script words for {len(words)} spoken words")
    for word, (scene, token) in zip(words, tokens):
        word["scene"] = scene
        word["shown"] = shown(token)
        word["stop"] = token[-1] in ".,;:!?"
    words[-1]["stop"] = True
    starts = [0.0]
    for scene in range(1, len(lines)):
        first = next(word for word in words if word["scene"] == scene)
        starts.append(max(first["start"] - LEAD, starts[-1] + 1.0))
    return starts, words[-1]["end"] + TAIL


def chunks(words, limit=15):
    """Group words into the short lines shown on screen, never across a pause."""
    groups, current = [], []
    for word in words:
        if current and (current[0]["scene"] != word["scene"] or len(current) == 3
                        or len(" ".join(item["shown"] for item in current + [word])) > limit):
            groups.append(current)
            current = []
        current.append(word)
        if word["stop"]:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def captions(words, starts, total, badges):
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,Poppins ExtraBold,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,3,5,30,30,0,1",
        "Style: Badge,Poppins ExtraBold,66,&H00FFFFFF,&H00FFFFFF,&H003A3AD6,&H00000000,0,0,0,0,100,100,2,0,3,17,0,5,0,0,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    groups = chunks(words)
    for number, group in enumerate(groups):
        following = groups[number + 1][0]["start"] if number + 1 < len(groups) else total
        end = min(following, group[-1]["end"] + 0.6) if group[-1]["stop"] else following
        begin = starts[group[0]["scene"]] if number == 0 else group[0]["start"]
        for position, word in enumerate(group):
            start = begin if position == 0 else word["start"]
            stop = group[position + 1]["start"] if position + 1 < len(group) else end
            parts = []
            for other, item in enumerate(group):
                colour = WHITE if other < position else YELLOW if other == position else GREY
                parts.append(f"{{\\c{colour}}}{item['shown']}")
            pop = "\\fscx112\\fscy112\\t(0,110,\\fscx100\\fscy100)" if position == 0 else ""
            lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(stop)},Cap,,0,0,0,,"
                         f"{{\\pos(540,1200){pop}}}" + " ".join(parts))
    for scene, label in enumerate(badges):
        if not label:
            continue
        stop = starts[scene + 1] if scene + 1 < len(starts) else total
        lines.append(f"Dialogue: 2,{ass_time(starts[scene] + 0.05)},{ass_time(stop - 0.05)},Badge,,0,0,0,,"
                     f"{{\\pos(540,1050)\\fscx135\\fscy135\\t(0,170,\\fscx100\\fscy100)}}{label}")
    return "\n".join(lines) + "\n"


def paper_edges(rows, limit):
    """Count the flat light lines at the start of `rows`, at most `limit`.

    FLUX sometimes frames the drawing with a band of blank paper. A line of
    that band is bright and nearly uniform; the first line that is not ends it.
    """
    count = 0
    for line in rows[:limit]:
        mean = sum(line) / len(line)
        spread = (sum((value - mean) ** 2 for value in line) / len(line)) ** 0.5
        if mean < 200 or spread > 12:
            break
        count += 1
    return count


def trim_paper(path):
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGB")
    small = image.convert("L").resize((96, 168))
    pixels = list(small.getdata())
    rows = [pixels[index * 96:(index + 1) * 96] for index in range(168)]
    columns = [pixels[index::96] for index in range(96)]
    top, bottom = paper_edges(rows, 25), paper_edges(rows[::-1], 25)
    left, right = paper_edges(columns, 15), paper_edges(columns[::-1], 15)
    # A pale wall or sky also makes flat light lines, but only on one or two
    # sides; the paper frame runs around the drawing.
    if sum(1 for band in (top, bottom, left, right) if band) < 3:
        return False
    scale_x, scale_y = image.width / 96, image.height / 168
    box = (round((left + 1) * scale_x) if left else 0, round((top + 1) * scale_y) if top else 0,
           image.width - (round((right + 1) * scale_x) if right else 0),
           image.height - (round((bottom + 1) * scale_y) if bottom else 0))
    image.crop(box).save(path)
    return True


def upload_token():
    token = os.environ.get("CLIPMAKER_UPLOAD_TOKEN", "")
    env_file = ROOT.parent / "web" / ".env.local"
    if not token and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPMAKER_UPLOAD_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"')
    if not token:
        raise SystemExit("CLIPMAKER_UPLOAD_TOKEN is needed to draw the scenes.")
    return token


def draw(prompt, destination, token):
    references = [base64.b64encode((ASSETS / name).read_bytes()).decode() for name in ("character.jpg", "style.jpg")]
    body = json.dumps({"task": "illustration", "input": {
        "prompt": f"{prompt} {STYLE}", "references": references, "width": 768, "height": 1344,
    }}).encode()
    request = urllib.request.Request(f"{CLOUD_API}/api/ai/run", data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Drawing {destination.name} failed ({error.code}): {error.read().decode()[:300]}")
    image = (payload.get("result") or {}).get("image")
    if not image:
        raise SystemExit(f"No image came back for {destination.name}: {str(payload)[:300]}")
    destination.write_bytes(base64.b64decode(image))


async def speak(text, voice, audio_path):
    import edge_tts

    words = []
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    with open(audio_path, "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"text": chunk["text"], "start": chunk["offset"] / 1e7,
                              "end": (chunk["offset"] + chunk["duration"]) / 1e7})
    return words


def render(folder, episode, words):
    lines = [scene["line"] for scene in episode["scenes"]]
    starts, total = layout(words, lines)
    (folder / "captions.ass").write_text(
        captions(words, starts, total, [scene.get("badge") for scene in episode["scenes"]]), encoding="utf-8")
    bounds = starts + [total]
    inputs, graph = [], []
    for index in range(len(lines)):
        begin = bounds[index] - (FADE if index else 0)
        length = bounds[index + 1] - begin
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", f"s{index:02d}.png"]
        ramp = f"{ZOOM}*t/{length:.3f}" if index % 2 == 0 else f"{ZOOM}-{ZOOM}*t/{length:.3f}"
        graph.append(
            f"[{index}:v]scale=w='ceil(max({W}/iw,{H}/ih)*iw*{OVERSCAN}*(1+{ramp})/2)*2':h=-2:eval=frame:flags=lanczos,"
            f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,setsar=1,fps={FPS},format=yuv420p[v{index}]")
    previous = "v0"
    for index in range(1, len(lines)):
        graph.append(f"[{previous}][v{index}]xfade=transition=fade:duration={FADE}:"
                     f"offset={bounds[index] - FADE:.3f}[x{index}]")
        previous = f"x{index}"
    # Relative, because a Windows drive colon would split the filter options.
    fonts = Path(os.path.relpath(ASSETS, folder)).as_posix()
    graph.append(f"[{previous}]ass=captions.ass:fontsdir={fonts}[vout]")
    voice, music = len(lines), len(lines) + 1
    graph.append(f"[{voice}:a]loudnorm=I=-14:TP=-2:LRA=11,aresample=48000,aformat=channel_layouts=stereo,"
                 f"apad,atrim=0:{total:.3f}[voice]")
    graph.append(f"[{music}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
                 f"volume={MUSIC_GAIN_DB}dB,afade=t=in:d=0.4,afade=t=out:st={total - 1.2:.3f}:d=1.2[bed]")
    graph.append("[voice][bed]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.89[aout]")
    output = f"{episode['slug']}.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", *inputs, "-i", "voice.mp3", "-stream_loop", "-1",
        "-i", str(ASSETS / "piano-636366.mp3"), "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow",
        "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-movflags", "+faststart", output,
    ], cwd=folder, check=True)
    return folder / output, total


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--redo", type=int, nargs="*", default=[], help="scene numbers to draw again")
    args = parser.parse_args()
    folder = args.folder.resolve()
    episode = json.loads((folder / "episode.json").read_text(encoding="utf-8"))
    scenes = episode["scenes"]

    token = None
    for index, scene in enumerate(scenes):
        image = folder / f"s{index:02d}.png"
        if index in args.redo or not image.exists():
            token = token or upload_token()
            print(f"drawing scene {index}", flush=True)
            draw(scene["picture"], image, token)
            if trim_paper(image):
                print(f"trimmed the paper edge of scene {index}", flush=True)

    text = " ".join(scene["line"] for scene in scenes)
    spoken = folder / "words.json"
    cached = json.loads(spoken.read_text(encoding="utf-8")) if spoken.exists() else {}
    voice = episode.get("voice", VOICE)
    if cached.get("text") != text or cached.get("voice") != voice or not (folder / "voice.mp3").exists():
        words = asyncio.run(speak(text, voice, folder / "voice.mp3"))
        spoken.write_text(json.dumps({"text": text, "voice": voice, "words": words}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    else:
        words = cached["words"]

    output, total = render(folder, episode, words)
    print(f"{output} {total:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
