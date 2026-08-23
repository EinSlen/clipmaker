#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { readPublisherConfig } from '../src/automation/config.mjs';
import { buildPublisherSummary } from '../src/automation/summary.mjs';

function option(args, name, fallback = undefined) {
  const index = args.indexOf(name);
  if (index < 0) return fallback;
  const value = args[index + 1];
  if (!value || value.startsWith('--')) throw new Error(`${name} needs a value.`);
  return value;
}

async function readOptionalJson(filePath) {
  if (!filePath) return null;
  try {
    return JSON.parse(await fs.readFile(path.resolve(filePath), 'utf8'));
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw error;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const configPath = path.resolve(option(args, '--config'));
  const outputPath = path.resolve(option(args, '--output'));
  let config = { channels: [], timeZone: 'Europe/Paris' };
  let configurationError = null;
  try {
    config = await readPublisherConfig(configPath);
  } catch (error) {
    configurationError = error instanceof Error ? error.message : String(error);
  }
  const summary = buildPublisherSummary({
    operation: option(args, '--operation', 'unknown'),
    config,
    doctor: await readOptionalJson(option(args, '--doctor')),
    status: await readOptionalJson(option(args, '--status')),
    configurationError,
  });
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, summary, 'utf8');
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
