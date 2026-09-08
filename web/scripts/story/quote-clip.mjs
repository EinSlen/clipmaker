#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { generateImage } from './workers-ai.mjs';

// The quote format: one anonymous figure in a night street, one line of advice
// held on screen long enough to read twice, and the spoken sad edit the channel
// already clears for publication. Everything visual is generated on the free
// Workers AI allocation, so an episode costs nothing.
//
// The face is never blurred after the fact. A generated frame can simply not
// contain a face: the scenes below put the figure in silhouette, backlit or
// seen from behind, which reads as deliberate rather than as a moderation
// artefact, and no detector can fail on it.
const RECEIPT_PREFIX = 'CLIPMAKER_QUOTE:';
const WIDTH = 1080;
const HEIGHT = 1920;
const FPS = 30;
const WORK_WIDTH = 1620;
const WORK_HEIGHT = 2880;
// Roughly the widest a line can be before it stops reading at arm's length.
const LINE_CHARS = 20;

const SCENES = [
  'a lone figure seen from behind walking down a wet empty city street at night, orange sodium streetlights, heavy rain haze, face not visible, cinematic anamorphic, shallow depth of field, muted teal and amber grade',
  'silhouette of a man standing under a single streetlight in an empty parking lot at night, backlit, face completely in shadow, fog, cinematic, desaturated blue grade',
  'a hooded figure from behind on a bridge at night overlooking a distant city skyline, cold blue light, face not visible, film grain, cinematic wide shot',
  'a man sitting alone on the kerb of a dark street at night seen from behind, headlights passing, face not visible, rain on asphalt, moody cinematic lighting',
  'silhouette of a person walking away into a dim underpass, harsh overhead light behind them, face not visible, concrete texture, cold cinematic grade',
];

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
      if (code === 0) resolve({ stdout });
      else reject(new Error(`${path.basename(command)} exited with ${code}: ${stderr.slice(-1200)}`));
    });
  });
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

function fontFile() {
  if (process.env.STORY_FONT) return process.env.STORY_FONT;
  return process.platform === 'win32'
    ? 'C\\:/Windows/Fonts/arialbd.ttf'
    : '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';
}

function escapeDrawText(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/:/g, '\\:')
    .replace(/'/g, '’')
    .replace(/%/g, '\\%')
    .replace(/\n/g, ' ');
}

// drawtext cannot wrap, so the quote is broken into lines here and each line is
// drawn as its own filter, stacked around the middle of the frame.
export function wrap(quote, limit = LINE_CHARS) {
  const words = String(quote).trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > limit && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function quoteFilters(lines) {
  // One size for every line, driven by the longest, so the block reads as a
  // single paragraph rather than a ransom note.
  const longest = lines.reduce((max, line) => Math.max(max, line.length), 1);
  const size = Math.max(44, Math.min(104, Math.floor(920 / (longest * 0.56))));
  const step = Math.round(size * 1.32);
  const top = Math.round(HEIGHT / 2 - ((lines.length - 1) * step) / 2);
  return lines.map((line, index) => [
    'drawtext=',
    `fontfile='${fontFile()}'`,
    `:text='${escapeDrawText(line)}'`,
    `:fontcolor=white:fontsize=${size}`,
    ':borderw=6:bordercolor=black@0.85',
    ':shadowx=0:shadowy=5:shadowcolor=black@0.6',
    `:x=(w-text_w)/2:y=${top + index * step}-text_h/2`,
  ].join(''));
}

// A slow push with no drift. The quote has to stay readable, so the frame moves
// just enough to stop the shot looking like a photograph.
function kenBurns(duration) {
  const frames = Math.max(2, Math.round(duration * FPS));
  const span = 0.10;
  const step = (span / frames).toFixed(8);
  return [
    `scale=${WORK_HEIGHT}:${WORK_HEIGHT}:flags=lanczos`,
    `crop=${WORK_WIDTH}:${WORK_HEIGHT}`,
    `zoompan=z='min(1+${step}*on,${(1 + span).toFixed(3)})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=${frames}:s=${WORK_WIDTH}x${WORK_HEIGHT}:fps=${FPS}`,
    `scale=${WIDTH}:${HEIGHT}:flags=lanczos`,
    'setsar=1',
  ].join(',');
}

async function render(imageFile, outputFile, quote, duration) {
  const filters = [
    kenBurns(duration),
    // Pull the scene down and cool it so white text sits on top of it, then
    // darken the corners so the eye lands in the middle where the quote is.
    'eq=brightness=-0.10:contrast=1.10:saturation=0.82',
    'vignette=angle=PI/4',
    ...quoteFilters(wrap(quote)),
    'format=yuv420p',
  ].join(',');
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-loop', '1', '-t', duration.toFixed(3), '-i', imageFile,
    '-filter_complex', `[0:v]${filters}[v]`,
    '-map', '[v]',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', String(FPS),
    '-t', duration.toFixed(3),
    outputFile,
  ]);
}

// The spoken sad edit comes from the reviewed catalogue the channel already
// publishes, so the quote format inherits its rights metadata instead of
// introducing a second, uncleared music source.
function spokenEdit(wavFile, duration, seed, profile) {
  return new Promise((resolve, reject) => {
    const script = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/u, '$1')), 'quote_audio.py');
    const child = spawn(process.env.PYTHON_BIN || 'python', [
      script, '--output', wavFile, '--duration', duration.toFixed(3), '--seed', String(seed), '--profile', profile,
    ], { cwd: path.resolve(path.dirname(script), '..', '..'), windowsHide: true });
    let stdout = '';
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => process.stderr.write(chunk));
    child.on('error', reject);
    child.on('close', () => {
      const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith('CLIPMAKER_QUOTE_AUDIO:'));
      if (!line) {
        reject(new Error('quote_audio.py n a rien renvoye.'));
        return;
      }
      const parsed = JSON.parse(line.slice('CLIPMAKER_QUOTE_AUDIO:'.length));
      if (parsed.ok === false) reject(new Error(parsed.error || 'echec audio'));
      else resolve(parsed.metadata);
    });
  });
}

async function mux(videoFile, wavFile, outputFile, duration) {
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-i', videoFile, '-i', wavFile,
    '-map', '0:v', '-map', '1:a',
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
    '-t', duration.toFixed(3), '-shortest',
    outputFile,
  ]);
}

function seedFrom(text) {
  let hash = 0;
  for (const character of String(text)) hash = (hash * 31 + character.charCodeAt(0)) % 2147483647;
  return hash;
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const quote = String(args.quote || '').trim();
  if (!quote) throw new Error('--quote est requis.');
  const duration = Math.max(5, Math.min(20, Number(args.duration) || 10));
  const outputFile = path.resolve(process.cwd(), String(args.output || 'quote.mp4'));
  // The same quote always draws the same scene, so a regenerated post matches
  // the one that was reviewed.
  const seed = Number.isFinite(Number(args.seed)) && args.seed !== undefined
    ? Number(args.seed)
    : seedFrom(quote);
  const scene = args.scene ? String(args.scene) : SCENES[seed % SCENES.length];

  await fs.mkdir(path.dirname(outputFile), { recursive: true });
  const imageFile = `${outputFile.replace(/\.mp4$/i, '')}-scene.png`;
  const image = await generateImage(scene, seed);
  await fs.writeFile(imageFile, image);

  // Without a soundtrack the clip is still a finished vertical video, which is
  // what makes the look reviewable before the catalogue is reachable.
  const profile = args.noAudio ? null : String(args.profile || 'edit-sad');
  const silentFile = profile ? `${outputFile.replace(/\.mp4$/iu, '')}-silent.mp4` : outputFile;
  await render(imageFile, silentFile, quote, duration);

  let music = null;
  if (profile) {
    const wavFile = `${outputFile.replace(/\.mp4$/iu, '')}-voice.wav`;
    music = await spokenEdit(wavFile, duration, seed, profile);
    await mux(silentFile, wavFile, outputFile, duration);
    await fs.rm(silentFile, { force: true });
  }

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    quote,
    lines: wrap(quote),
    scene,
    seed,
    duration,
    imageFile,
    outputFile,
    music,
  })}\n`);
}

export { SCENES };

// Only run as a command. Importing the module has to stay free of side effects
// so the wrapping and the scene list can be unit tested.
if (process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1]))) {
  run().catch((error) => {
    process.stderr.write(`${error.stack || error.message}\n`);
    process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
    process.exit(1);
  });
}
