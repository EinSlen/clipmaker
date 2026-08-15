#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = fileURLToPath(new URL('.', import.meta.url));
const webDirectory = fileURLToPath(new URL('..', import.meta.url));
const python = process.env.PYTHON_BIN || 'python3';

const catalogCandidates = [
  {
    game: 'ball-escape', label: 'Ball Escape', seed: 9, difficulty: 14,
    duration: 15, theme: 'neon', soundPack: 'auto', musicMode: 'hit-reveal',
    expectedOutcome: 'escaped', editorialPriority: 1,
  },
  {
    game: 'shape-tunnel', label: 'Organic Escape', seed: 8, difficulty: 200,
    duration: 15, theme: 'neon', soundPack: 'asmr', musicMode: 'continuous',
    expectedOutcome: 'escaped', editorialPriority: 2,
  },
  {
    game: 'boss-battle', label: 'Boss Battle', seed: 10, difficulty: 300,
    duration: 15, theme: 'sunset', soundPack: 'impact', musicMode: 'hit-reveal',
    expectedOutcome: 'player', editorialPriority: 3,
  },
  {
    game: 'laser-dodge', label: 'Laser Dodge', seed: 0, difficulty: 24,
    duration: 15, theme: 'ice', soundPack: 'arcade', musicMode: 'hit-reveal',
    expectedOutcome: 'survived', editorialPriority: 4,
  },
];

const requestedGames = new Set(
  (process.env.CI_2D_GAMES || '').split(',').map((value) => value.trim()).filter(Boolean),
);
const candidates = requestedGames.size
  ? catalogCandidates.filter((candidate) => requestedGames.has(candidate.game))
  : catalogCandidates;
assert.ok(candidates.length > 0, 'CI_2D_GAMES did not match a supported engine');

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function run(command, args, { env = process.env, timeoutMs = 90 * 60_000, echo = true } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd: webDirectory, env, windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 10_000).unref();
    }, timeoutMs);
    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout = `${stdout}${text}`.slice(-4_000_000);
      if (echo) process.stdout.write(text);
    });
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      stderr = `${stderr}${text}`.slice(-4_000_000);
      if (echo) process.stderr.write(text);
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (code === 0) resolvePromise({ stdout, stderr });
      else reject(new Error(`${command} exited with ${code ?? signal}\n${stderr.slice(-4000)}`));
    });
  });
}

function lastJsonLine(text) {
  for (const line of text.trim().split(/\r?\n/).reverse()) {
    try {
      return JSON.parse(line);
    } catch {
      // Blender/FFmpeg progress may precede the renderer's final JSON line.
    }
  }
  throw new Error('Renderer did not return JSON metadata');
}

function fraction(value) {
  const [numerator, denominator = '1'] = String(value).split('/').map(Number);
  return numerator / denominator;
}

async function probeVideo(output) {
  const { stdout } = await run('ffprobe', [
    '-v', 'error', '-show_entries',
    'stream=codec_type,codec_name,width,height,pix_fmt,sample_rate,avg_frame_rate',
    '-show_entries', 'format=duration,size,bit_rate', '-of', 'json', output,
  ], { echo: false, timeoutMs: 60_000 });
  return JSON.parse(stdout);
}

async function probeAudio(output) {
  const { stderr: loudnessLog } = await run('ffmpeg', [
    '-hide_banner', '-nostats', '-i', output,
    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-',
  ], { echo: false, timeoutMs: 120_000 });
  const block = loudnessLog.match(/\{\s*"input_i"[\s\S]*?\}/)?.[0];
  const loudness = block ? JSON.parse(block) : {};
  const { stderr: silenceLog } = await run('ffmpeg', [
    '-hide_banner', '-nostats', '-i', output,
    '-af', 'silencedetect=noise=-50dB:d=0.25', '-f', 'null', '-',
  ], { echo: false, timeoutMs: 120_000 });
  const durations = [...silenceLog.matchAll(/silence_duration:\s*([0-9.]+)/g)]
    .map((match) => Number(match[1]));
  return {
    integratedLufs: Number(loudness.input_i),
    truePeakDb: Number(loudness.input_tp),
    longestSilenceSeconds: durations.length ? Math.max(...durations) : 0,
  };
}

async function main() {
  const outputDirectory = resolve(argument('--output', './ci-artifacts/2d'));
  mkdirSync(outputDirectory, { recursive: true });
  const results = [];
  const renderEnvironment = {
    ...process.env,
    GAME_RENDER_WIDTH: process.env.CI_2D_WIDTH || '1080',
    GAME_RENDER_HEIGHT: process.env.CI_2D_HEIGHT || '1920',
    GAME_RENDER_FPS: process.env.CI_2D_FPS || '60',
    GAME_VIDEO_PRESET: process.env.CI_2D_PRESET || 'slow',
    GAME_VIDEO_CRF: process.env.CI_2D_CRF || '15',
  };
  const expectedOutputFps = Number(renderEnvironment.GAME_RENDER_FPS);
  const failures = [];

  for (const [index, candidate] of candidates.entries()) {
    const output = resolve(outputDirectory, `${candidate.game}-production.mp4`);
    process.stdout.write(
      `\n[2D ${index + 1}/${candidates.length}] ${candidate.label} — native production render\n`,
    );
    try {
      const { stdout } = await run(python, [
        resolve(scriptDirectory, 'render-ball-escape.py'),
        '--output', output,
        '--game', candidate.game,
        '--duration', String(candidate.duration),
        '--difficulty', String(candidate.difficulty),
        '--seed', String(candidate.seed),
        '--theme', candidate.theme,
        '--sound-pack', candidate.soundPack,
        '--music-mode', candidate.musicMode,
        '--title', 'CAN IT ESCAPE?',
      ], { env: renderEnvironment });
      const metadata = lastJsonLine(stdout);
      const probe = await probeVideo(output);
      const audioMetrics = await probeAudio(output);
      const video = probe.streams.find((stream) => stream.codec_type === 'video');
      const audio = probe.streams.find((stream) => stream.codec_type === 'audio');

      assert.equal(metadata.ok, true);
      assert.equal(metadata.game, candidate.game);
      assert.equal(metadata.outcome, candidate.expectedOutcome);
      assert.ok(metadata.events > 0);
      assert.ok(metadata.music_hits > 0);
      assert.equal(video.codec_name, 'h264');
      assert.equal(video.width, 1080);
      assert.equal(video.height, 1920);
      assert.equal(video.pix_fmt, 'yuv420p');
      assert.ok(fraction(video.avg_frame_rate) >= expectedOutputFps - 0.1);
      assert.equal(audio.codec_name, 'aac');
      assert.equal(audio.sample_rate, '48000');
      assert.ok(audioMetrics.integratedLufs >= -18 && audioMetrics.integratedLufs <= -12);
      assert.ok(audioMetrics.truePeakDb <= -1.0);
      assert.ok(audioMetrics.longestSilenceSeconds < 3.0);

      results.push({
        ...candidate,
        qa: 'PASS',
        output: output.split(/[\\/]/).at(-1),
        actualDuration: Number(probe.format.duration),
        sizeBytes: Number(probe.format.size),
        videoBitrate: Number(probe.format.bit_rate),
        events: metadata.events,
        musicHits: metadata.music_hits,
        outcome: metadata.outcome,
        completedAt: metadata.completed_at,
        ...audioMetrics,
      });
    } catch (error) {
      const message = String(error?.message || error).slice(0, 2_000);
      failures.push({ game: candidate.game, error: message });
      results.push({
        ...candidate,
        qa: 'FAIL',
        output: output.split(/[\\/]/).at(-1),
        error: message,
      });
      process.stderr.write(`[2D ${candidate.label}] QA FAILED: ${message}\n`);
    }
  }

  const recommendation = results.filter((item) => item.qa === 'PASS')
    .sort((first, second) => first.editorialPriority - second.editorialPriority)[0];
  const payload = {
    ok: failures.length === 0,
    quality: 'production',
    recommendation: recommendation?.game ?? null,
    note: 'Technical readiness is verified; audience performance still requires real private/public A/B posts.',
    failures,
    games: results,
  };
  writeFileSync(resolve(outputDirectory, 'results.json'), JSON.stringify(payload, null, 2));
  const rows = results.map((item) => {
    if (item.qa === 'FAIL') {
      const error = item.error.replace(/[|\r\n]+/g, ' ').slice(0, 180);
      return `| ${item.label} | — | — | — | — | ${item.output} | FAIL: ${error} |`;
    }
    return `| ${item.label} | ${item.outcome} | ${item.events} | ${item.integratedLufs.toFixed(1)} LUFS | `
      + `${item.longestSilenceSeconds.toFixed(2)} s | ${(item.sizeBytes / 1_000_000).toFixed(1)} Mo | PASS |`;
  }).join('\n');
  const recommendationLine = recommendation
    ? `**Candidat prioritaire : ${recommendation.label}.** Il possède la boucle la plus
immédiatement lisible pour le premier test de compte. Organic Escape est le
second candidat.`
    : '**Aucun candidat n’a passé la QA de publication.**';
  const report = `# Candidats 2D en qualité publication

| Jeu | Issue physique | Événements | Son | Silence max | Fichier | QA |
|---|---:|---:|---:|---:|---:|---:|
${rows}

${recommendationLine} Cette priorité est éditoriale ; seul un A/B test de vraies
publications permettra de mesurer les vues, la rétention et les abonnements.

Chaque fichier marqué PASS est un vrai export 1080×1920 à 60 fps avec H.264,
audio AAC 48 kHz, issue physique et safe zones vérifiées par la suite de tests.
`;
  writeFileSync(resolve(outputDirectory, 'report.md'), report);
  process.stdout.write(`\n${JSON.stringify(payload, null, 2)}\n`);
  if (failures.length) {
    throw new Error(`${failures.length} production candidate(s) failed QA`);
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
