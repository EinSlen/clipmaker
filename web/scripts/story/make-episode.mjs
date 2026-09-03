#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(HERE, '..', '..');
const RECEIPT_PREFIX = 'CLIPMAKER_MAKE:';

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

// The Minimax agent needs a real window, so on a Linux runner it goes through
// Xvfb exactly like the TikTok comment scraper does.
function launcher(scriptArgs, needsWindow) {
  if (needsWindow && process.platform === 'linux' && !process.env.DISPLAY) {
    return {
      command: 'xvfb-run',
      args: ['-a', '--server-args=-screen 0 1500x980x24', process.execPath, ...scriptArgs],
    };
  }
  return { command: process.execPath, args: scriptArgs };
}

// Each stage prints one receipt line on stdout and streams progress on stderr,
// so the child output is mirrored live and only the receipt is parsed.
function stage(script, args, prefix, { needsWindow = false } = {}) {
  return new Promise((resolve, reject) => {
    const { command, args: commandArgs } = launcher([path.join(HERE, script), ...args], needsWindow);
    const child = spawn(command, commandArgs, {
      cwd: WEB_DIR,
      env: process.env,
      windowsHide: true,
    });
    let stdout = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
      process.stderr.write(chunk);
    });
    child.stderr.on('data', (chunk) => process.stderr.write(chunk));
    child.on('error', reject);
    child.on('close', () => {
      const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith(prefix));
      if (!line) {
        reject(new Error(`${script} n a rien renvoye.`));
        return;
      }
      const parsed = JSON.parse(line.slice(prefix.length));
      if (parsed.ok === false) reject(new Error(`${script} : ${parsed.error || 'echec'}`));
      else resolve(parsed);
    });
  });
}

function forward(args, keys) {
  const forwarded = [];
  for (const [flag, key] of keys) {
    if (args[key] !== undefined) forwarded.push(`--${flag}`, String(args[key]));
  }
  return forwarded;
}

async function run() {
  const args = parseArgs(process.argv.slice(2));

  const plan = args.fromPlan
    ? { planDir: path.resolve(WEB_DIR, String(args.fromPlan)) }
    : await stage('plan-episode.mjs', forward(args, [
      ['series', 'series'],
      ['channel', 'channel'],
      ['tiktok-user', 'tiktokUser'],
      ['date', 'date'],
      ['seconds', 'seconds'],
      ['theme', 'theme'],
      ['output-dir', 'outputDir'],
    ]), 'CLIPMAKER_PLAN:');

  if (args.planOnly) {
    process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: true, stage: 'plan', ...plan })}\n`);
    return;
  }

  // Read back from the plan rather than from the plan receipt, so resuming with
  // --from-plan reports exactly as much as a full run.
  const written = JSON.parse(await fs.readFile(path.join(plan.planDir, 'episode.json'), 'utf8'));

  const clips = await stage('minimax-agent.cjs', [
    'plan', '--plan', plan.planDir,
    ...forward(args, [['limit', 'limit'], ['timeout', 'timeout']]),
  ], 'CLIPMAKER_MINIMAX:', { needsWindow: true });

  const episode = await stage('assemble-episode.mjs', [
    '--plan', plan.planDir,
    ...forward(args, [['output-dir', 'outputDir']]),
    ...(args.keepAssets ? ['--keep-assets'] : []),
  ], 'CLIPMAKER_STORY:');

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    source: 'clips',
    planDir: plan.planDir,
    seriesId: episode.seriesId,
    seriesTitle: episode.seriesTitle,
    episode: episode.episode,
    filename: episode.filename,
    outputFile: episode.outputFile,
    duration: episode.duration,
    title: episode.title,
    youtubeTitle: episode.youtubeTitle,
    caption: episode.caption,
    tags: episode.tags,
    clipsRequested: clips.planned,
    clipsUsed: episode.clips,
    clipsFailed: clips.failed,
    steeredBy: episode.steeredBy,
    commentsSeen: (written.comments || []).length,
    commentSources: written.commentSources || [],
  })}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exit(1);
});
