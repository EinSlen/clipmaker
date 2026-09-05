#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { randomUUID } from 'node:crypto';
import { readPublisherConfig } from '../src/automation/config.mjs';
import { cleanupPublishedRenders } from '../src/automation/render-cleanup.mjs';
import { assertDate, dateInTimeZone } from '../src/automation/time.mjs';
import { doctor, generate, importRenderedJob, publish, runDue, status, validateRenderedManifest } from '../src/automation/orchestrator.mjs';

function option(args, name, fallback = undefined) {
  const index = args.indexOf(name);
  if (index < 0) return fallback;
  const value = args[index + 1];
  if (!value || value.startsWith('--')) throw new Error(`${name} needs a value.`);
  return value;
}

function output(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

// Accounts are isolated from each other, so a single failure is reported and
// named in the daily ticket while the others still publish. The run only turns
// red when nothing at all could be generated or published.
function reportChannels(results) {
  output(results);
  const entries = Array.isArray(results) ? results : Object.values(results).flat();
  if (entries.length && entries.every((entry) => entry?.ok === false)) process.exitCode = 1;
}

async function sleep(milliseconds) {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function writeHeartbeat(config, state, error = null) {
  try {
    await fs.mkdir(config.stateDir, { recursive: true });
    const target = path.join(config.stateDir, 'daemon-heartbeat.json');
    const temporary = `${target}.${process.pid}.tmp`;
    await fs.writeFile(temporary, `${JSON.stringify({
      at: new Date().toISOString(),
      state,
      pid: process.pid,
      ...(error ? { error } : {}),
    })}\n`);
    await fs.rename(temporary, target);
  } catch {
    // A heartbeat must never stop rendering or publishing.
  }
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'status';
  const configPath = path.resolve(option(args, '--config', process.env.PUBLISHER_CONFIG || 'config/publisher.json'));
  const channelId = option(args, '--channel');
  const skipGame = option(args, '--skip-game');
  const skipGames = skipGame ? [skipGame] : [];
  const forcePlatform = option(args, '--force-platform');
  if (forcePlatform && !['youtube', 'tiktok'].includes(forcePlatform)) {
    throw new Error(`Unsupported forced platform: ${forcePlatform}.`);
  }
  const forcePlatforms = forcePlatform ? [forcePlatform] : [];
  const forcedDryRun = args.includes('--dry-run') ? true : undefined;
  const read = () => readPublisherConfig(configPath);
  const config = await read();
  const date = assertDate(option(args, '--date', dateInTimeZone(new Date(), config.timeZone)));

  if (command === 'doctor') return output(await doctor(config));
  if (command === 'status') return output(await status(config));
  if (command === 'cleanup') return output(await cleanupPublishedRenders(config, { dryRun: forcedDryRun }));
  if (command === 'generate') return reportChannels(await generate(config, { date, channelId, dryRun: forcedDryRun, skipGames }));
  if (command === 'publish') {
    return reportChannels(await publish(config, { date, channelId, dryRun: forcedDryRun, forcePlatforms, skipGames }));
  }
  if (command === 'import-3d') {
    const manifestPath = path.resolve(option(args, '--manifest'));
    const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    const manifestDirectory = path.dirname(manifestPath);
    const source = path.resolve(manifestDirectory, String(manifest.video || ''));
    const filename = path.basename(source);
    if (!filename || source !== path.join(manifestDirectory, filename)) throw new Error('Invalid imported video path.');
    // An invalid import must not overwrite a previously validated ready video.
    validateRenderedManifest(config, { ...manifest, filename });
    const renderDirectory = path.resolve(path.dirname(config.configPath), '../renders');
    const destination = path.join(renderDirectory, filename);
    return output(await importRenderedJob(config, { ...manifest, filename }, {
      restorePublishedVideo: args.includes('--restore-published-video'),
      copyVideo: async () => {
      if (!(await fs.stat(source)).isFile()) throw new Error('Imported video must be a file.');
      if (source === destination) return;
      await fs.mkdir(renderDirectory, { recursive: true });
      const temporary = path.join(renderDirectory, `.import-${randomUUID()}.tmp`);
      try {
        await fs.copyFile(source, temporary);
        await fs.rename(temporary, destination);
      } finally {
        await fs.rm(temporary, { force: true });
      }
      },
    }));
  }
  if (command === 'run') {
    const generated = await generate(config, { date, channelId, dryRun: forcedDryRun, skipGames });
    const published = await publish(config, { date, channelId, dryRun: forcedDryRun, forcePlatforms, skipGames });
    return reportChannels({ generated, published });
  }
  if (command === 'due') return output(await runDue(config, { channelId, dryRun: forcedDryRun }));
  if (command === 'daemon') {
    let stopping = false;
    let current = config;
    process.on('SIGINT', () => { stopping = true; });
    process.on('SIGTERM', () => { stopping = true; });
    while (!stopping) {
      try {
        current = await read();
        await writeHeartbeat(current, 'running');
        const heartbeatTimer = setInterval(() => {
          void writeHeartbeat(current, 'running');
        }, 30_000);
        heartbeatTimer.unref?.();
        let results;
        try {
          results = await runDue(current, { channelId, dryRun: forcedDryRun });
        } finally {
          clearInterval(heartbeatTimer);
        }
        output({ at: new Date().toISOString(), results });
        await writeHeartbeat(current, 'running');
        for (let elapsed = 0; elapsed < current.pollSeconds && !stopping; elapsed += 1) await sleep(1000);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        output({ at: new Date().toISOString(), ok: false, error: message });
        await writeHeartbeat(current, 'error', message);
        await sleep(60_000);
      }
    }
    await writeHeartbeat(current, 'stopped');
    return;
  }
  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) })}\n`);
  process.exitCode = error?.code === 'PUBLISHER_BUSY' ? 75 : 1;
});
