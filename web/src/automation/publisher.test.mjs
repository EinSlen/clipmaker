import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { readPublisherConfig } from './config.mjs';
import { generateChannel, planForDate, publishChannel, runDue } from './orchestrator.mjs';
import { loadState, saveState, withStateLock } from './state.mjs';
import { addDays, dateInTimeZone, isTimeDue } from './time.mjs';

async function temporaryDirectory(t) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-publisher-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  return directory;
}

function sampleChannel() {
  return {
    id: 'main',
    enabled: true,
    generateTime: '00:30',
    publishTime: '18:30',
    game: { game: 'ball-escape', difficulty: 14 },
    youtube: { enabled: false, account: 'default', privacy: 'private', confirmPublic: false },
    tiktok: { enabled: false, username: null, musicId: null, visibility: 'private', confirmPublic: false },
  };
}

test('date helpers are deterministic across month boundaries', () => {
  assert.equal(addDays('2026-08-31', 1), '2026-09-01');
  assert.equal(dateInTimeZone(new Date('2026-08-14T23:30:00Z'), 'Europe/Paris'), '2026-08-15');
  assert.equal(isTimeDue('18:30', new Date('2026-08-15T16:30:00Z'), 'Europe/Paris'), true);
});

test('daily plans are stable and keep one fixed game per account', () => {
  const config = { seedNamespace: 'test' };
  const channel = sampleChannel();
  const first = planForDate(config, channel, '2026-08-15');
  const repeated = planForDate(config, channel, '2026-08-15');
  const next = planForDate(config, channel, '2026-08-16');
  assert.deepEqual(first, repeated);
  assert.notEqual(first.seed, next.seed);
  assert.equal(first.renderRequest.game, 'ball-escape');
  assert.deepEqual(first.renderRequest, next.renderRequest);
});

test('configuration is safe by default and refuses unconfirmed public uploads', async (t) => {
  const directory = await temporaryDirectory(t);
  const configPath = path.join(directory, 'publisher.json');
  const base = {
    channels: [{
      id: 'main',
      game: { id: 'ball-escape' },
      youtube: { enabled: false, account: 'default', privacy: 'private' },
      tiktok: { enabled: false },
    }],
  };
  await fs.writeFile(configPath, JSON.stringify(base));
  const config = await readPublisherConfig(configPath, {});
  assert.equal(config.dryRun, true);
  assert.equal(config.channels[0].youtube.enabled, false);
  base.channels[0].youtube = { enabled: true, account: 'default', privacy: 'public' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /confirmPublic/);
  base.channels[0].youtube = { enabled: false, account: 'default', privacy: 'private' };
  base.channels[0].game = { id: 'laser-dodge', difficulty: 200 };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /laser-dodge difficulty/);
  base.channels[0].game = { id: 'ball-escape' };
  base.channels[0].tiktok = { enabled: true, username: 'clipmaker.test', visibility: 'public' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /TikTok public publishing/);
});

test('configuration enforces one game and one assignment per platform account', async (t) => {
  const directory = await temporaryDirectory(t);
  const configPath = path.join(directory, 'publisher.json');
  const base = {
    channels: [{
      id: 'ball-account',
      game: { id: 'ball-escape' },
      youtube: { enabled: true, account: 'main', privacy: 'private' },
      tiktok: { enabled: true, username: 'clipmaker.main', visibility: 'private' },
    }],
  };
  await fs.writeFile(configPath, JSON.stringify(base));
  const config = await readPublisherConfig(configPath, {});
  assert.equal(config.channels[0].game.game, 'ball-escape');

  base.channels[0].game = undefined;
  base.channels[0].rotation = [{ game: 'ball-escape' }, { game: 'laser-dodge' }];
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /exactly one fixed game/);

  base.channels[0].rotation = [{ game: 'ball-escape' }];
  await fs.writeFile(configPath, JSON.stringify(base));
  const legacy = await readPublisherConfig(configPath, {});
  assert.equal(legacy.channels[0].game.game, 'ball-escape');

  base.channels[0].game = { id: 'ball-escape' };
  delete base.channels[0].rotation;
  base.channels.push({
    id: 'laser-account',
    game: { id: 'laser-dodge' },
    youtube: { enabled: true, account: 'MAIN', privacy: 'private' },
    tiktok: { enabled: false },
  });
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /YouTube account.*both/);

  base.channels[1].youtube.enabled = false;
  base.channels[1].tiktok = { enabled: true, username: 'ClipMaker.Main', visibility: 'private' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /TikTok account.*both/);

  base.channels[1].enabled = false;
  await fs.writeFile(configPath, JSON.stringify(base));
  const disabledDuplicate = await readPublisherConfig(configPath, {});
  assert.equal(disabledDuplicate.channels.length, 2);
});

test('TikTok upload uses the pinned fork CLI contract and an admin token', async () => {
  const routePath = new URL('../app/api/tiktok/upload/route.ts', import.meta.url);
  const source = await fs.readFile(routePath, 'utf8');
  assert.match(source, /'--users', username/);
  assert.match(source, /'--visibility'/);
  assert.match(source, /x-clipmaker-upload-token/);
  assert.doesNotMatch(source, /'--user', username/);
});

test('state writes atomically and rejects a concurrent publisher', async (t) => {
  const directory = await temporaryDirectory(t);
  await saveState(directory, { version: 1, updatedAt: null, jobs: [{ id: 'one' }] });
  assert.equal((await loadState(directory)).jobs[0].id, 'one');
  await withStateLock(directory, async () => {
    await assert.rejects(() => withStateLock(directory, async () => {}), /already running/);
  });
});

test('dry-run due planning never creates state or performs network writes', async (t) => {
  const directory = await temporaryDirectory(t);
  const config = {
    dryRun: true,
    timeZone: 'Europe/Paris',
    seedNamespace: 'test',
    stateDir: directory,
    catchupDays: 2,
    retentionDays: 120,
    channels: [sampleChannel()],
  };
  const results = await runDue(config, { now: new Date('2026-08-15T17:00:00Z') });
  assert.equal(results.length, 2);
  assert.equal(results.every((result) => result.dryRun), true);
  assert.deepEqual((await loadState(directory)).jobs, []);
});

test('a partial platform failure retries only the missing upload', async (t) => {
  const directory = await temporaryDirectory(t);
  const calls = { render: 0, youtube: 0, tiktok: 0 };
  const server = http.createServer((request, response) => {
    response.setHeader('content-type', 'application/json');
    if (request.url === '/api/game/render') {
      calls.render += 1;
      response.end(JSON.stringify({
        ok: true,
        filename: 'daily.mp4',
        title: 'Can It Escape?',
        youtubeTitle: 'Can It Escape? #shorts',
        caption: 'Can it escape? #satisfying',
        tags: ['#satisfying'],
        game: 'ball-escape',
        duration: 15,
        outcome: 'escaped',
      }));
      return;
    }
    if (request.url === '/api/youtube/upload') {
      calls.youtube += 1;
      response.end(JSON.stringify({ ok: true, upload: { id: 'youtube-one' } }));
      return;
    }
    if (request.url === '/api/tiktok/upload') {
      calls.tiktok += 1;
      if (calls.tiktok === 1) {
        response.statusCode = 503;
        response.end(JSON.stringify({ ok: false, error: 'temporary TikTok failure' }));
      } else {
        response.end(JSON.stringify({ ok: true, upload: { id: 'tiktok-one' } }));
      }
      return;
    }
    response.statusCode = 404;
    response.end(JSON.stringify({ ok: false, error: 'not found' }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const address = server.address();
  assert(address && typeof address === 'object');

  const channel = sampleChannel();
  channel.youtube.enabled = true;
  channel.tiktok = {
    enabled: true,
    username: 'clipmaker.test',
    musicId: null,
    visibility: 'private',
    confirmPublic: false,
  };
  const config = {
    dryRun: false,
    baseUrl: `http://127.0.0.1:${address.port}`,
    requestTimeoutMinutes: 1,
    timeZone: 'Europe/Paris',
    seedNamespace: 'test',
    stateDir: directory,
    catchupDays: 2,
    retentionDays: 120,
    channels: [channel],
  };
  const date = '2026-08-15';

  await generateChannel(config, channel, date);
  const repeated = await generateChannel(config, channel, date);
  assert.equal(repeated.skipped, true);
  assert.equal(calls.render, 1);

  await assert.rejects(() => publishChannel(config, channel, date), /temporary TikTok failure/);
  let job = (await loadState(directory)).jobs[0];
  assert.equal(job.status, 'partial');
  assert.equal(job.platforms.youtube.status, 'published');
  assert.equal(job.platforms.tiktok.status, 'failed');

  await publishChannel(config, channel, date);
  job = (await loadState(directory)).jobs[0];
  assert.equal(job.status, 'published');
  assert.equal(calls.youtube, 1);
  assert.equal(calls.tiktok, 2);
});
