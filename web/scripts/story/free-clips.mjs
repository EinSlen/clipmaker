#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { generateImage, generateVideo } from './workers-ai.mjs';

// Free replacement for the days the metered clip provider has no credits left.
// It fulfils the contract minimax-agent.cjs already fulfils, filling the plan's
// clips directory with clip-NN.mp4, so assemble-episode.mjs never learns which
// source produced them. Everything goes through the Workers AI binding the
// runner already authenticates against, inside the daily free allocation.
//
// Generated video is the first choice, because a still is visibly a still. The
// Ken Burns path stays underneath it: an exhausted daily allocation should cost
// the episode its motion, never its publication.
const RECEIPT_PREFIX = 'CLIPMAKER_STILL:';
const WIDTH = 1080;
const HEIGHT = 1920;
const FPS = 30;
// Ken Burns crops inside a larger frame, so the pan never reaches an edge.
const WORK_WIDTH = 1620;
const WORK_HEIGHT = 2880;

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

function kenBurns(index, duration) {
  const frames = Math.max(2, Math.round(duration * FPS));
  const span = 0.16;
  const step = (span / frames).toFixed(8);
  // Alternating the zoom direction stops a run of stills from reading as one
  // long push, which is what betrays a slideshow.
  const zoom = index % 2 === 0
    ? `min(1+${step}*on,${(1 + span).toFixed(3)})`
    : `max(${(1 + span).toFixed(3)}-${step}*on,1)`;
  const drift = index % 4 < 2 ? '+' : '-';
  return [
    `scale=${WORK_HEIGHT}:${WORK_HEIGHT}:flags=lanczos`,
    `crop=${WORK_WIDTH}:${WORK_HEIGHT}`,
    `zoompan=z='${zoom}':x='iw/2-(iw/zoom/2)${drift}(iw*0.02*on/${frames})':y='ih/2-(ih/zoom/2)':d=${frames}:s=${WORK_WIDTH}x${WORK_HEIGHT}:fps=${FPS}`,
    `scale=${WIDTH}:${HEIGHT}:flags=lanczos`,
    'setsar=1',
  ].join(',');
}

// The clips carry no speech, and render.mjs already pads a silent segment when
// a shot has no audio stream, so nothing downstream has to change.
async function renderStill(imageFile, outputFile, index, duration) {
  const filters = [kenBurns(index, duration), 'eq=saturation=1.06:contrast=1.04', 'format=yuv420p'].join(',');
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

async function probeDuration(file) {
  const { stdout } = await execute(binary('ffprobe'), [
    '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file,
  ]);
  return Number(String(stdout).trim());
}

async function downloadTo(url, file) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Telechargement du clip : HTTP ${response.status}.`);
  await fs.writeFile(file, Buffer.from(await response.arrayBuffer()));
}

// The model is asked for a vertical clip, but the container it returns carries
// no guarantee about frame rate or exact length, and concat refuses segments
// that disagree, so every clip is re-encoded to the one contract the pipeline
// accepts.
async function normaliseVideo(inputFile, outputFile, duration) {
  const filters = [
    `scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos`,
    `crop=${WIDTH}:${HEIGHT}`,
    'setsar=1',
    'format=yuv420p',
  ].join(',');
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-i', inputFile,
    '-filter_complex', `[0:v]${filters}[v]`,
    '-map', '[v]',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', String(FPS),
    '-t', duration.toFixed(3),
    outputFile,
  ]);
}

// A regenerated episode has to look identical to the first attempt, so the seed
// is derived from the episode rather than drawn at random.
function seedFor(episode, index) {
  const key = `${episode.seriesId || 'story'}-${episode.episode || 0}-${index}`;
  let hash = 0;
  for (const character of key) hash = (hash * 31 + character.charCodeAt(0)) % 2147483647;
  return hash;
}

function label(index) {
  return String(index + 1).padStart(2, '0');
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.plan) throw new Error('--plan est requis.');
  const planDir = path.resolve(process.cwd(), String(args.plan));
  const episode = JSON.parse(await fs.readFile(path.join(planDir, 'episode.json'), 'utf8'));
  const prompts = (await fs.readFile(path.join(planDir, 'prompts.txt'), 'utf8'))
    .split(/\n\n---\n\n/)
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (!prompts.length) throw new Error(`Aucun prompt dans ${planDir}.`);

  const duration = Math.max(5, Math.min(15, Number(episode.clipSeconds) || 10));
  const clipsDir = path.join(planDir, 'clips');
  const stillsDir = path.join(planDir, 'stills');
  await fs.mkdir(clipsDir, { recursive: true });
  await fs.mkdir(stillsDir, { recursive: true });

  // Generated video is opt-in, not the default: the account's Workers AI
  // catalogue exposes no video category today, so trying it first would spend a
  // failing request per clip on every run. Set STORY_FREE_MODE=auto once the
  // model answers, or =video to make its absence a hard failure.
  const mode = String(process.env.STORY_FREE_MODE || 'still').toLowerCase();
  const planned = Math.min(Number(args.limit) || prompts.length, prompts.length);
  const failed = [];
  const sources = [];
  let produced = 0;
  for (let index = 0; index < planned; index += 1) {
    const outputFile = path.join(clipsDir, `clip-${label(index)}.mp4`);
    const seed = seedFor(episode, index);
    let done = false;

    if (mode !== 'still') {
      try {
        const url = await generateVideo(prompts[index], { duration, seed });
        const rawFile = path.join(stillsDir, `raw-${label(index)}.mp4`);
        await downloadTo(url, rawFile);
        await normaliseVideo(rawFile, outputFile, duration);
        // A model that returns a shorter clip than it was asked for cannot be
        // stretched, and a silently short shot would slide the whole montage,
        // so it is treated as a miss and the still renderer covers the slot at
        // exactly the planned length.
        const actual = await probeDuration(outputFile);
        if (!Number.isFinite(actual) || actual < duration - 0.5) {
          throw new Error(`Clip trop court : ${Number.isFinite(actual) ? actual.toFixed(2) : '?'}s pour ${duration}s.`);
        }
        done = true;
        sources.push('video');
        process.stderr.write(`Clip ${label(index)} genere en video.\n`);
      } catch (error) {
        if (mode === 'video') {
          failed.push({ clip: index + 1, error: error.message });
          process.stderr.write(`Clip ${label(index)} echoue : ${error.message}\n`);
          continue;
        }
        process.stderr.write(`Clip ${label(index)} repli sur image fixe : ${error.message}\n`);
      }
    }

    if (!done) {
      try {
        const image = await generateImage(prompts[index], seed);
        const imageFile = path.join(stillsDir, `still-${label(index)}.png`);
        await fs.writeFile(imageFile, image);
        await renderStill(imageFile, outputFile, index, duration);
        done = true;
        sources.push('still');
        process.stderr.write(`Clip ${label(index)} rendu depuis une image fixe.\n`);
      } catch (error) {
        failed.push({ clip: index + 1, error: error.message });
        process.stderr.write(`Clip ${label(index)} echoue : ${error.message}\n`);
      }
    }

    if (done) produced += 1;
  }

  // Fewer clips than planned is fine, the assembler merges the narration
  // groups. Zero is not: there would be nothing to publish.
  if (!produced) throw new Error(`Aucun clip produit sur ${planned} demande(s).`);

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    // The daily report has to say whether the episode moved or was a slideshow,
    // because that is the difference a viewer notices first.
    source: sources.includes('video') ? (sources.includes('still') ? 'mixed' : 'video') : 'still',
    sources,
    planDir,
    clipsDir,
    planned,
    produced,
    failed,
    clipSeconds: duration,
  })}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exit(1);
});
