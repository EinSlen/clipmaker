import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { readPublisherConfig } from './config.mjs';
import { planForDate } from './orchestrator.mjs';

test('vocal playlists round-trip into daily requests without mutating legacy plans', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-playlist-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const file = path.join(root, 'publisher.json');
  const raw = { channels: [{ id: 'soft-test', game: { id: 'soft-body-slide' } }] };
  await fs.writeFile(file, JSON.stringify(raw));
  const legacy = await readPublisherConfig(file, {});
  assert.equal(Object.hasOwn(legacy.channels[0].game, 'musicProfile'), false);
  for (const musicProfile of ['auto', 'revenge', 'sad-english', 'original']) {
    raw.channels[0].game.musicProfile = musicProfile;
    await fs.writeFile(file, JSON.stringify(raw));
    const config = await readPublisherConfig(file, {});
    const plan = planForDate(config, config.channels[0], '2026-08-31');
    assert.equal(plan.renderRequest.musicProfile, musicProfile);
  }
  raw.channels[0].game.musicProfile = 'https://untrusted.test/playlist';
  await fs.writeFile(file, JSON.stringify(raw));
  await assert.rejects(() => readPublisherConfig(file, {}), /Invalid musicProfile/);
});
