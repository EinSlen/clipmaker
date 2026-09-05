#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { generateImage } from './workers-ai.mjs';

// Free fallback for the days the clip provider has no credits left. It fulfils
// the contract minimax-agent.cjs already fulfils, filling the plan's clips
// directory with clip-NN.mp4, so assemble-episode.mjs never learns which source
// produced them. Images come from the Workers AI binding the runner already
// authenticates against, so the episode costs nothing beyond the daily quota.
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
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-8000); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
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

  const planned = Math.min(Number(args.limit) || prompts.length, prompts.length);
  const failed = [];
  let produced = 0;
  for (let index = 0; index < planned; index += 1) {
    const outputFile = path.join(clipsDir, `clip-${label(index)}.mp4`);
    try {
      const image = await generateImage(prompts[index], seedFor(episode, index));
      const imageFile = path.join(stillsDir, `still-${label(index)}.png`);
      await fs.writeFile(imageFile, image);
      await renderStill(imageFile, outputFile, index, duration);
      produced += 1;
      process.stderr.write(`Clip ${label(index)} rendu depuis une image fixe.\n`);
    } catch (error) {
      failed.push({ clip: index + 1, error: error.message });
      process.stderr.write(`Clip ${label(index)} echoue : ${error.message}\n`);
    }
  }

  // Fewer clips than planned is fine, the assembler merges the narration
  // groups. Zero is not: there would be nothing to publish.
  if (!produced) throw new Error(`Aucun clip produit sur ${planned} demande(s).`);

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    source: 'still',
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
