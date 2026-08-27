#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { readPublisherConfig } from '../src/automation/config.mjs';
import { scopePublication } from '../src/automation/publication-schedule.mjs';

function option(name, fallback = '') {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1] ?? fallback;
}

async function main() {
  const configPath = path.resolve(option('--config'));
  const normalized = await readPublisherConfig(configPath, {});
  const raw = JSON.parse(await fs.readFile(configPath, 'utf8'));
  // Use the normalizer's defaults so raw and CLI configuration cannot disagree.
  raw.channels = raw.channels.map((channel, index) => ({
    ...channel, publishTime: normalized.channels[index].publishTime,
  }));
  const mode = option('--scheduled', 'false');
  if (!['true', 'false'].includes(mode)) throw new Error('Invalid scheduled mode.');
  const result = scopePublication(raw, {
    scheduled: mode === 'true', slot: option('--slot'), expectedDate: option('--date'),
  });
  await fs.writeFile(configPath, `${JSON.stringify(result.config, null, 2)}\n`, { mode: 0o600 });
  process.stdout.write(`${JSON.stringify({ date: result.date, channels: result.channels })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
