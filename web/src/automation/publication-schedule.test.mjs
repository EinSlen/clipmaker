import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { scopePublication } from './publication-schedule.mjs';
import { cleanupPublishedRenders, publishedRenderFiles } from './render-cleanup.mjs';
import { doctor, generateChannel, publish } from './orchestrator.mjs';
import { loadState } from './state.mjs';

function config() {
  return {
    timeZone: 'Europe/Paris', dryRun: false, seedNamespace: 'test', retentionDays: 120,
    requestTimeoutMinutes: 5,
    channels: ['18:00', '20:00'].map((publishTime, index) => ({
      id: index ? 'late' : 'early', enabled: true, generateTime: '00:30', publishTime,
      game: { game: 'ball-escape' },
      youtube: { enabled: true, account: index ? 'late' : 'early', privacy: 'private', confirmPublic: false },
      tiktok: { enabled: false, username: null, visibility: 'private', confirmPublic: false },
    })),
  };
}

test('scheduled filtering keeps private settings and the saved config intact', () => {
  const raw = config();
  const original = JSON.stringify(raw);
  const scoped = scopePublication(raw, { scheduled: true, slot: '18:00', now: new Date('2026-08-28T16:00:00Z') });
  assert.deepEqual(scoped.channels, ['early']);
  assert.deepEqual(scoped.config.channels[0], raw.channels[0]);
  assert.equal(JSON.stringify(raw), original);
  assert.equal(scoped.config.channels[1].enabled, false);
  assert.deepEqual(scopePublication(raw, { scheduled: true, slot: '20:00', now: new Date('2026-08-28T16:00:00Z') }).channels, []);
  assert.deepEqual(scopePublication(raw, { scheduled: true, now: new Date('2026-08-28T16:07:00Z') }).channels, ['early']);
  assert.deepEqual(scopePublication(raw, { scheduled: true, now: new Date('2026-08-28T18:07:00Z') }).channels, ['early', 'late']);
  assert.deepEqual(scopePublication(raw, { now: new Date('2026-08-28T10:00:00Z') }).channels, ['early', 'late']);
  raw.channels[1].enabled = false;
  assert.deepEqual(scopePublication(raw, { scheduled: true, now: new Date('2026-08-28T18:07:00Z') }).channels, ['early']);
});

test('winter time, malformed slots and expired dates cannot publish tomorrow by mistake', () => {
  const raw = config();
  assert.deepEqual(scopePublication(raw, { scheduled: true, now: new Date('2026-12-28T17:00:00Z') }).channels, ['early']);
  assert.deepEqual(scopePublication(raw, { scheduled: true, now: new Date('2026-08-28T22:00:00Z') }).channels, []);
  assert.throws(() => scopePublication(raw, { scheduled: true, slot: '20:99' }), /Invalid time/u);
  assert.throws(() => scopePublication(raw, { slot: '18:00' }), /requires scheduled/u);
  assert.throws(() => scopePublication(raw, {
    scheduled: true, expectedDate: '2026-08-28', now: new Date('2026-08-28T22:00:00Z'),
  }), /expired/u);
});

test('cleanup selects only fully published, unshared, safe video names', () => {
  const complete = (filename) => ({ status: 'published', render: { filename }, platforms: {
    youtube: { enabled: true, status: 'published' }, tiktok: { enabled: false, status: 'disabled' },
  } });
  assert.deepEqual(publishedRenderFiles({ jobs: [
    complete('done.mp4'), complete('done.mp4'), complete('../outside.mp4'), complete('C:\\outside.mp4'),
    complete('/outside.mp4'), complete('metadata.json'), complete('shared.mp4'),
    { ...complete('shared.mp4'), status: 'partial' },
    { ...complete('unfinished.mp4'), platforms: { youtube: { enabled: true, status: 'pending' } } },
  ] }), ['done.mp4']);
});

test('the workflow CLI validates before changing its isolated configuration copy', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-scope-cli-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const configPath = path.join(root, 'publisher.json');
  const raw = config();
  raw.channels.forEach((channel) => { channel.game = { id: 'ball-escape' }; });
  const original = JSON.stringify(raw);
  await fs.writeFile(configPath, original);
  const script = fileURLToPath(new URL('../../scripts/scope-publisher.mjs', import.meta.url));
  const invalid = spawnSync(process.execPath, [script, '--config', configPath, '--scheduled', 'true', '--slot', '20:99'], { encoding: 'utf8' });
  assert.equal(invalid.status, 1);
  assert.equal(await fs.readFile(configPath, 'utf8'), original);
  const manual = spawnSync(process.execPath, [script, '--config', configPath, '--scheduled', 'false', '--slot', '', '--date', ''], { encoding: 'utf8' });
  assert.equal(manual.status, 0, manual.stderr);
  assert.deepEqual(JSON.parse(manual.stdout).channels, ['early', 'late']);
  assert.deepEqual(JSON.parse(await fs.readFile(configPath, 'utf8')), raw);
});

test('two real local publisher cycles preserve the later video and do not upload twice', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-slot-test-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const renders = path.join(root, 'renders');
  await fs.mkdir(renders);
  const uploads = [];
  const accountChecks = [];
  const server = http.createServer(async (request, response) => {
    response.setHeader('content-type', 'application/json');
    if (request.url === '/api/tiktok/accounts') return response.end(JSON.stringify({ ok: true, accounts: [] }));
    if (request.url.startsWith('/api/youtube/status')) {
      accountChecks.push(new URL(request.url, 'http://localhost').searchParams.get('account'));
      return response.end(JSON.stringify({ ok: true, dryRun: false, readyForLiveUpload: true }));
    }
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString());
    if (request.url === '/api/game/render') {
      const filename = `video-${body.seed}.mp4`;
      await fs.writeFile(path.join(renders, filename), 'isolated test fixture');
      return response.end(JSON.stringify({ ok: true, filename, game: 'ball-escape' }));
    }
    uploads.push(body.account);
    response.end(JSON.stringify({ ok: true, upload: { id: `test-${body.account}` } }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const raw = { ...config(), stateDir: path.join(root, 'state'), configPath: path.join(root, 'config', 'publisher.json'),
    baseUrl: `http://127.0.0.1:${server.address().port}` };
  for (const channel of raw.channels) await generateChannel(raw, channel, '2026-08-28');
  const before = await loadState(raw.stateDir);
  const laterFilename = before.jobs.find((job) => job.channelId === 'late').render.filename;
  const early = scopePublication(raw, { scheduled: true, slot: '18:00', now: new Date('2026-08-28T16:00:00Z') }).config;
  assert.equal((await doctor(early)).ok, true);
  assert.deepEqual(accountChecks, ['early']);
  await publish(early, { date: '2026-08-28' });
  assert.equal((await cleanupPublishedRenders(early, { dryRun: true })).removed.length, 0);
  assert.equal((await cleanupPublishedRenders(early)).removed.length, 1);
  assert.equal(await fs.readFile(path.join(renders, laterFilename), 'utf8'), 'isolated test fixture');
  await publish(early, { date: '2026-08-28' }); // A retry reads the stored receipt.
  assert.deepEqual(uploads, ['early']);
  const late = scopePublication(raw, { scheduled: true, slot: '20:00', now: new Date('2026-08-28T18:00:00Z') }).config;
  await publish(late, { date: '2026-08-28' });
  assert.deepEqual(uploads, ['early', 'late']);
  assert.equal((await cleanupPublishedRenders(late)).removed.length, 1);
  assert.equal((await loadState(raw.stateDir)).jobs.every((job) => job.status === 'published'), true);
});

test('the workflow scopes imports and account checks before publishing and retains pending videos', async () => {
  const relative = '.github/workflows/daily-publisher.yml';
  const paths = [
    ...(process.env.REPO_ROOT ? [path.join(process.env.REPO_ROOT, relative)] : []),
    fileURLToPath(new URL(`../../../${relative}`, import.meta.url)),
    fileURLToPath(new URL(`../../${relative}`, import.meta.url)),
  ];
  let source;
  for (const candidate of paths) {
    try { source = await fs.readFile(candidate, 'utf8'); break; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  assert.ok(source);
  assert.ok(source.indexOf('- name: Scope publication') < source.indexOf("- name: Import today's"));
  assert.ok(source.indexOf('- name: Scope publication') < source.indexOf('- name: Check connected accounts'));
  assert.match(source, /scheduled_publish:[\s\S]*schedule_date:/u);
  assert.ok(source.includes('today="$PUBLISH_DATE"'));
  assert.ok(source.includes('extra+=(--date "$PUBLISH_DATE")'));
  assert.ok(source.includes('publisher.mjs cleanup'));
  assert.doesNotMatch(source, /find web\/renders.*-delete/u);
});
