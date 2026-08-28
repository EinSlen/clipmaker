import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { publisherRunnerDryRun } from '../../scripts/publisher-runner-mode.mjs';

test('a live or queued dispatch cannot override the saved dry-run safety switch', () => {
  for (const event of ['schedule', 'workflow_dispatch']) {
    for (const dryRun of [undefined, null, true, 'false']) {
      assert.equal(publisherRunnerDryRun({ dryRun }, event, 'false'), true);
    }
    assert.equal(publisherRunnerDryRun({ dryRun: false }, event, 'false'), false);
  }
  assert.equal(publisherRunnerDryRun({ dryRun: false }, 'workflow_dispatch', 'true'), true);
  assert.equal(publisherRunnerDryRun({ dryRun: false }, 'workflow_dispatch', true), true);
});

test('the runner CLI rereads the latest saved configuration without mutating it', async t => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-runner-mode-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const config = path.join(directory, 'publisher.json');
  const cli = fileURLToPath(new URL('../../scripts/publisher-runner-mode.mjs', import.meta.url));
  const invoke = () => spawnSync(process.execPath, [cli, config], { encoding: 'utf8',
    env: { ...process.env, GITHUB_EVENT_NAME: 'workflow_dispatch', MANUAL_DRY_RUN: 'false' } });
  await fs.writeFile(config, '{"dryRun":false}');
  assert.equal(invoke().stdout.trim(), 'false');
  await fs.writeFile(config, '{"dryRun":true}');
  const paused = invoke();
  assert.equal(paused.status, 0, paused.stderr);
  assert.equal(paused.stdout.trim(), 'true');
  assert.equal(await fs.readFile(config, 'utf8'), '{"dryRun":true}');
});

test('the publisher uses one effective mode for imports, both adapters and notifications', async () => {
  const source = await fs.readFile(new URL('../../../.github/workflows/daily-publisher.yml', import.meta.url), 'utf8');
  assert.ok(source.includes('publisher_dry_run="$(node web/scripts/publisher-runner-mode.mjs web/config/publisher.json)"'));
  assert.ok(source.includes("steps.runtime.outputs.dry_run == 'false'"));
  assert.ok(source.includes('--env YOUTUBE_API_DRY_RUN="$publisher_dry_run"'));
  assert.ok(source.includes('--env PUBLISHER_DRY_RUN="$publisher_dry_run"'));
  assert.ok(source.includes('EFFECTIVE_DRY_RUN: ${{ steps.runtime.outputs.dry_run }}'));
  assert.ok(source.includes('[ "$EFFECTIVE_DRY_RUN" = "true" ]'));
});
