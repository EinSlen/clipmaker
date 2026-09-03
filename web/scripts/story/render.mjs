import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

const WIDTH = 1080;
const HEIGHT = 1920;
const FPS = 30;

function binary(name) {
  const override = name === 'ffmpeg' ? process.env.FFMPEG_PATH : process.env.FFPROBE_PATH;
  return override || name;
}

function execute(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-8000); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(`${path.basename(command)} exited with ${code}: ${stderr.slice(-1200)}`));
    });
  });
}

export async function probeDuration(file) {
  const { stdout } = await execute(binary('ffprobe'), [
    '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', file,
  ]);
  const seconds = Number(String(stdout).trim());
  if (!Number.isFinite(seconds) || seconds <= 0) throw new Error(`Unreadable duration for ${path.basename(file)}.`);
  return seconds;
}

async function hasAudio(file) {
  const { stdout } = await execute(binary('ffprobe'), [
    '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', file,
  ]);
  return /audio/.test(stdout);
}

function fontFile() {
  if (process.env.STORY_FONT) return process.env.STORY_FONT;
  return process.platform === 'win32'
    ? 'C\\:/Windows/Fonts/arialbd.ttf'
    : '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';
}

// ffmpeg wants the drive colon escaped, Python wants the plain path.
function fontPath() {
  return fontFile().replace('\\:', ':');
}

// One Python call per clip returns the exact x of every word, measured in the
// very font ffmpeg draws with, so the highlight cannot drift off the word.
function measureGroups(groups, maxSize = 74, maxWidth = 960) {
  if (!groups.length) return Promise.resolve([]);
  const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
  const script = path.join(path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, '$1'), 'caption_metrics.py');
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script], { windowsHide: true });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-2000); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`caption_metrics exited with ${code}: ${stderr.slice(-400)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout).groups || []);
      } catch (error) {
        reject(new Error(`caption_metrics returned invalid JSON: ${error.message}`));
      }
    });
    child.stdin.end(JSON.stringify({
      font: fontPath(),
      maxSize,
      maxWidth,
      canvas: WIDTH,
      groups,
    }));
  });
}

function escapeDrawText(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/:/g, '\\:')
    .replace(/'/g, '’')
    .replace(/%/g, '\\%')
    .replace(/\n/g, ' ');
}

// drawtext cannot wrap, so the size has to come from the string length. The
// ratios are the measured average advance of the bold faces used below.
function fitFontSize(text, maxSize, ratio, available = 960) {
  const length = Math.max(1, String(text).length);
  return Math.max(28, Math.min(maxSize, Math.floor(available / (length * ratio))));
}

// Three or four words at a time is what reads best at arm's length on a phone.
function captionChunks(narration, duration) {
  const words = String(narration).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const perChunk = words.length > 18 ? 4 : 3;
  const chunks = [];
  for (let index = 0; index < words.length; index += perChunk) {
    chunks.push(words.slice(index, index + perChunk).join(' '));
  }
  const slice = duration / chunks.length;
  return chunks.map((text, index) => ({
    text,
    from: index * slice,
    to: index === chunks.length - 1 ? duration : (index + 1) * slice,
  }));
}

// Cues carry real timings measured on the voice, so they are used as they are.
// Without them the narration is spread evenly, which is the best a text only
// pipeline can do but never matches what is actually said.
function captionFilters(narration, duration, cues = null) {
  const timeline = Array.isArray(cues) && cues.length
    ? cues.filter((cue) => cue.text && Number.isFinite(cue.from) && Number.isFinite(cue.to))
    : captionChunks(narration, duration);
  return timeline.map(({ text, from, to }) => [
    'drawtext=',
    `fontfile='${fontFile()}'`,
    `:text='${escapeDrawText(text)}'`,
    `:fontcolor=white:fontsize=${fitFontSize(text, 74, 0.56)}:line_spacing=12`,
    ':borderw=7:bordercolor=black@0.92',
    ':shadowx=0:shadowy=4:shadowcolor=black@0.55',
    ':x=(w-text_w)/2:y=h*0.72',
    `:enable='between(t,${from.toFixed(3)},${to.toFixed(3)})'`,
  ].join(''));
}

// Two passes over the same line. The first paints the whole group in white so
// it can be read ahead, the second repaints only the word being pronounced with
// its own red background, and since drawtext filters apply in order that second
// pass lands on top.
function karaokeFilters(cue, group) {
  const placed = group?.words || [];
  if (!placed.length) return [];
  const size = group.size || 74;
  const common = [
    `fontfile='${fontFile()}'`,
    `:fontsize=${size}`,
    `:y=h*0.72`,
  ].join('');
  const plain = placed.map((word) => [
    'drawtext=',
    common,
    `:text='${escapeDrawText(word.text)}'`,
    `:x=${word.x}`,
    ':fontcolor=white:borderw=7:bordercolor=black@0.92',
    ':shadowx=0:shadowy=4:shadowcolor=black@0.55',
    `:enable='between(t,${cue.from.toFixed(3)},${cue.to.toFixed(3)})'`,
  ].join(''));
  const spoken = placed.map((word, index) => {
    const timing = cue.words?.[index];
    if (!timing) return null;
    const from = Number(timing.start);
    const to = Math.max(Number(timing.end), from + 0.12);
    return [
      'drawtext=',
      common,
      `:text='${escapeDrawText(word.text)}'`,
      `:x=${word.x}`,
      ':fontcolor=white:borderw=0',
      ':box=1:boxcolor=red@0.92:boxborderw=14',
      `:enable='between(t,${from.toFixed(3)},${to.toFixed(3)})'`,
    ].join('');
  }).filter(Boolean);
  return [...plain, ...spoken];
}

function titleOverlay(title, seconds = 2.6) {
  return [
    'drawtext=',
    `fontfile='${fontFile()}'`,
    `:text='${escapeDrawText(title)}'`,
    `:fontcolor=white:fontsize=${fitFontSize(title, 86, 0.66)}:borderw=8:bordercolor=black@0.95`,
    ':x=(w-text_w)/2:y=h*0.13',
    `:enable='between(t,0.25,${seconds.toFixed(2)})'`,
  ].join('');
}

function creditOverlay(author, seconds = 4.2) {
  const line = `idée de ${author}`;
  return [
    'drawtext=',
    `fontfile='${fontFile()}'`,
    `:text='${escapeDrawText(line)}'`,
    `:fontcolor=white@0.96:fontsize=${fitFontSize(line, 46, 0.55)}:borderw=5:bordercolor=black@0.9`,
    ':x=(w-text_w)/2:y=h*0.215',
    `:enable='between(t,0.6,${seconds.toFixed(2)})'`,
  ].join('');
}

function concatEntry(file) {
  const normalised = file.replace(/\\/g, '/');
  return `file '${normalised.split("'").join("'\\''")}'`;
}

async function concatShots(files, workDir, outputFile) {
  const listFile = path.join(workDir, 'concat.txt');
  await fs.writeFile(listFile, `${files.map(concatEntry).join('\n')}\n`, 'utf8');
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-f', 'concat', '-safe', '0', '-i', listFile,
    '-c', 'copy', outputFile,
  ]);
}

// Word timings unlock the karaoke highlight; a cue without them keeps the plain
// single line, and a failed measurement falls back to it too rather than
// dropping the subtitles altogether.
async function clipCaptions(narration, duration, cues) {
  const usable = Array.isArray(cues) ? cues : [];
  if (!usable.some((cue) => cue.words?.length)) return captionFilters(narration, duration, cues);
  const groups = usable.map((cue) => (cue.words || []).map((word) => word.text));
  const measured = await measureGroups(groups).catch(() => []);
  return usable.flatMap((cue, index) => (
    cue.words?.length && measured[index]?.words?.length
      ? karaokeFilters(cue, measured[index])
      : captionFilters('', 0, [cue])
  ));
}

// Generated clips already carry their own dialogue, so nothing is spoken over
// them: they are only reframed to 9:16 and captioned.
async function renderClip({ index, clipFile, narration, cues = null, outputFile, overlays = [] }) {
  const duration = await probeDuration(clipFile);
  // A generator that returns a mute clip would otherwise fail the filtergraph,
  // and concat needs every segment to carry the same streams, so the missing
  // track is replaced by silence of the same length.
  const audible = await hasAudio(clipFile);
  const captions = await clipCaptions(narration, duration, cues);
  const filters = [
    `scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=increase`,
    `crop=${WIDTH}:${HEIGHT}`,
    'eq=saturation=1.04',
    ...captions,
    ...overlays,
    'format=yuv420p',
  ].join(',');
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-i', clipFile,
    ...(audible ? [] : ['-f', 'lavfi', '-t', duration.toFixed(3), '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']),
    '-filter_complex', audible
      ? `[0:v]${filters}[v];[0:a]aresample=48000,apad=pad_dur=0.05[a]`
      : `[0:v]${filters}[v];[1:a]aresample=48000[a]`,
    '-map', '[v]', '-map', '[a]',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', String(FPS),
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2',
    '-t', duration.toFixed(3),
    outputFile,
  ]);
  return { duration, file: outputFile };
}

export async function renderClipEpisode({ clips, title, credit, workDir, outputFile }) {
  await fs.mkdir(workDir, { recursive: true });
  const rendered = [];
  for (const [index, clip] of clips.entries()) {
    const overlays = [];
    if (index === 0) {
      overlays.push(titleOverlay(title));
      if (credit) overlays.push(creditOverlay(credit));
    }
    rendered.push(await renderClip({
      index,
      clipFile: clip.file,
      narration: clip.narration,
      cues: clip.cues || null,
      outputFile: path.join(workDir, `clip-${String(index).padStart(2, '0')}.mp4`),
      overlays,
    }));
  }
  const assembled = path.join(workDir, 'assembled.mp4');
  await concatShots(rendered.map((entry) => entry.file), workDir, assembled);
  await fs.copyFile(assembled, outputFile);
  return {
    duration: Number(rendered.reduce((total, entry) => total + entry.duration, 0).toFixed(2)),
    clips: rendered.length,
  };
}
