#!/usr/bin/env node
import path from 'node:path';
import process from 'node:process';
import { readPublisherConfig } from '../src/automation/config.mjs';
import { assertDate, dateInTimeZone } from '../src/automation/time.mjs';
import { doctor, generate, publish, runDue, status } from '../src/automation/orchestrator.mjs';

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

async function sleep(milliseconds) {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'status';
  const configPath = path.resolve(option(args, '--config', process.env.PUBLISHER_CONFIG || 'config/publisher.json'));
  const channelId = option(args, '--channel');
  const forcedDryRun = args.includes('--dry-run') ? true : undefined;
  const read = () => readPublisherConfig(configPath);
  const config = await read();
  const date = assertDate(option(args, '--date', dateInTimeZone(new Date(), config.timeZone)));

  if (command === 'doctor') return output(await doctor(config));
  if (command === 'status') return output(await status(config));
  if (command === 'generate') return output(await generate(config, { date, channelId, dryRun: forcedDryRun }));
  if (command === 'publish') return output(await publish(config, { date, channelId, dryRun: forcedDryRun }));
  if (command === 'run') {
    const generated = await generate(config, { date, channelId, dryRun: forcedDryRun });
    const published = await publish(config, { date, channelId, dryRun: forcedDryRun });
    return output({ generated, published });
  }
  if (command === 'due') return output(await runDue(config, { channelId, dryRun: forcedDryRun }));
  if (command === 'daemon') {
    let stopping = false;
    process.on('SIGINT', () => { stopping = true; });
    process.on('SIGTERM', () => { stopping = true; });
    while (!stopping) {
      try {
        const current = await read();
        output({ at: new Date().toISOString(), results: await runDue(current, { channelId, dryRun: forcedDryRun }) });
        for (let elapsed = 0; elapsed < current.pollSeconds && !stopping; elapsed += 1) await sleep(1000);
      } catch (error) {
        output({ at: new Date().toISOString(), ok: false, error: error instanceof Error ? error.message : String(error) });
        await sleep(60_000);
      }
    }
    return;
  }
  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) })}\n`);
  process.exitCode = error?.code === 'PUBLISHER_BUSY' ? 75 : 1;
});
