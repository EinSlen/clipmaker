import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { generateChannel, importRenderedJob, planForDate, publishChannel } from './orchestrator.mjs';
import { loadState, saveState } from './state.mjs';

async function fixture(t) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-selection-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const calls = [];
  const server = http.createServer(async (req, res) => {
    let body = '';
    for await (const chunk of req) body += chunk;
    const payload = JSON.parse(body || '{}');
    calls.push({ url: req.url, payload });
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(req.url === '/api/game/render'
      ? { ok: true, filename: `${payload.game}.mp4`, game: payload.title === 'WRONG' ? 'ball-escape' : payload.game, title: 'TEST', duration: 30 }
      : { ok: true, upload: { platformPostId: 'test-upload', raw: { privacy: 'private' } } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const channel = { id: 'main', enabled: true, game: { game: 'ball-escape', difficulty: 14 },
    youtube: { enabled: true, account: 'default', privacy: 'private', confirmPublic: false },
    tiktok: { enabled: true, username: 'clipmaker.test', visibility: 'private', confirmPublic: false } };
  const config = { dryRun: false, stateDir: directory, seedNamespace: 'test', retentionDays: 120,
    requestTimeoutMinutes: 1, baseUrl: `http://127.0.0.1:${server.address().port}`, channels: [channel] };
  const date = '2026-08-28';
  await generateChannel(config, channel, date);
  return { config, channel, date, calls, directory };
}

function evidence(seed) {
  const stages = [0, 25, 55, 75, 100];
  return { physics_preflight: 'passed', game: 'soft-body-slide', seed, duration: 30,
    render_width: 1080, render_height: 1920, render_fps: 30, output_fps: 30, frames: 900,
    variant_obstacle: 'peg-grid', softness_stages: stages,
    attempt_quality: stages.flatMap((softness, i) => [1, 2].map(body => ({
      stage: i + 1, softness, attempt: 1, body, start_frame: i * 180 + 1, end_frame: (i + 1) * 180,
      issues: [], surface: { inside_contacts: 0 },
      framing: { frames_checked: 180, maximum_empty_seconds: 0, maximum_side_exit_seconds: 0, issues: [] },
      rendered_surface: { frames_checked: 180, vertices_checked: 210946 * 180, subdivision: 3,
        maximum_penetration: 0, maximum_correction: 0.01, issues: [] },
      inter_body_contact: { frames_checked: 180, maximum_penetration: 0, issues: [] },
    }))) };
}

function manifest(config, channel, date) {
  const { seed } = planForDate(config, channel, date);
  return { date, channelId: channel.id, seed, filename: `soft-body-peg-grid-${seed}.mp4`,
    render: { duration: 30, raw: evidence(seed) } };
}

test('a changed game cannot publish the previous ready video', async t => {
  const { config, channel, date, calls, directory } = await fixture(t);
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  await assert.rejects(() => publishChannel(config, channel, date), /render selection changed/i);
  assert.equal(calls.length, 1, 'only the initial local render may have been called');
  assert.equal((await loadState(directory)).jobs[0].platforms.youtube.attempts, 0);
});

test('regeneration replaces an unattempted old selection but keeps its audit history', async t => {
  const { config, channel, date, calls, directory } = await fixture(t);
  const original = (await loadState(directory)).jobs[0];
  channel.game = { game: 'laser-dodge', difficulty: 22 };
  await generateChannel(config, channel, date);
  const job = (await loadState(directory)).jobs[0];
  assert.equal(calls.length, 2);
  assert.equal(calls[1].payload.game, 'laser-dodge');
  assert.equal(job.id, original.id);
  assert.equal(job.seed, original.seed);
  assert.deepEqual(job.renderRequest, channel.game);
  assert.equal(job.render.game, 'laser-dodge');
  assert.equal(job.previousRenders[0].filename, 'ball-escape.mp4');
  await generateChannel(config, channel, date);
  assert.equal(calls.length, 2, 'an unchanged selection is still idempotent');
});

test('a 3D import updates an unpublished old 2D plan as well as its video', async t => {
  const { config, channel, date, directory } = await fixture(t);
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  let copies = 0;
  await importRenderedJob(config, manifest(config, channel, date), { copyVideo: async () => { copies++; } });
  const job = (await loadState(directory)).jobs[0];
  assert.equal(copies, 1);
  assert.deepEqual(job.renderRequest, channel.game);
  assert.equal(job.render.game, 'soft-body-slide');
  assert.equal(job.platforms.youtube.attempts, 0);
});

test('a settings change cannot replace a partially or ambiguously uploaded video', async t => {
  const { config, channel, date, directory, calls } = await fixture(t);
  for (const status of ['published', 'failed', 'publishing']) {
    const state = await loadState(directory);
    Object.assign(state.jobs[0].platforms.youtube, { status, attempts: 1, receipt: { id: 'keep-this' } });
    state.jobs[0].status = 'partial';
    await saveState(directory, state);
    const before = await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8');
    channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
    await assert.rejects(() => generateChannel(config, channel, date), /render selection changed/i);
    await assert.rejects(() => publishChannel(config, channel, date), /render selection changed/i);
    let copied = false;
    await assert.rejects(() => importRenderedJob(config, manifest(config, channel, date), {
      copyVideo: async () => { copied = true; },
    }), /render selection changed/i);
    assert.equal(copied, false);
    assert.equal(await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8'), before);
    assert.equal(calls.length, 1);
  }
});

test('even a same-plan import leaves an in-flight video and receipts untouched', async t => {
  const { config, channel, date, directory } = await fixture(t);
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  const incoming = manifest(config, channel, date);
  await importRenderedJob(config, incoming);
  const state = await loadState(directory);
  Object.assign(state.jobs[0].platforms.youtube, { status: 'published', attempts: 1, receipt: { id: 'keep-this' } });
  state.jobs[0].status = 'partial';
  await saveState(directory, state);
  const before = await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8');
  let copied = false;
  const result = await importRenderedJob(config, incoming, { copyVideo: async () => { copied = true; } });
  assert.equal(result.skipped, true);
  assert.equal(copied, false);
  assert.equal(await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8'), before);
});

test('a forced catch-up can restore a validated video without changing a published receipt', async t => {
  const { config, channel, date, directory } = await fixture(t);
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  const incoming = manifest(config, channel, date);
  await importRenderedJob(config, incoming);
  const state = await loadState(directory);
  state.jobs[0].status = 'published';
  state.jobs[0].platforms.youtube = {
    ...state.jobs[0].platforms.youtube,
    status: 'published',
    receipt: { id: 'keep-this' },
  };
  await saveState(directory, state);
  const before = await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8');
  let copies = 0;
  const result = await importRenderedJob(config, incoming, {
    restorePublishedVideo: true,
    copyVideo: async () => { copies += 1; },
  });
  assert.equal(result.restoredVideo, true);
  assert.equal(copies, 1);
  assert.equal(await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8'), before);
});

test('failed import copy preserves the previous plan and state', async t => {
  const { config, channel, date, directory } = await fixture(t);
  const before = await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8');
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  await assert.rejects(() => importRenderedJob(config, manifest(config, channel, date), {
    copyVideo: async () => { throw Error('copy failed'); },
  }), /copy failed/);
  assert.equal(await fs.readFile(path.join(directory, 'publisher-state.json'), 'utf8'), before);
});

test('render field order and a schedule-only edit do not invalidate the video', async t => {
  const { config, channel, date, calls } = await fixture(t);
  channel.game = { difficulty: 14, game: 'ball-escape' };
  channel.publishTime = '20:00';
  await generateChannel(config, channel, date);
  assert.equal(calls.length, 1);
});

test('a completed day is not republished after an edit, even via forced upload', async t => {
  const { config, channel, date, calls } = await fixture(t);
  await publishChannel(config, channel, date);
  const before = calls.length;
  channel.game = { game: 'laser-dodge', difficulty: 22 };
  assert.equal((await generateChannel(config, channel, date)).reason, 'already-published');
  assert.equal((await publishChannel(config, channel, date)).reason, 'already-published');
  await assert.rejects(() => publishChannel(config, channel, date, { forcePlatforms: ['youtube'] }), /render selection changed/i);
  assert.equal(calls.length, before);
});

test('a failed render may use new settings when no upload was attempted', async t => {
  const { config, channel, date, calls, directory } = await fixture(t);
  const state = await loadState(directory);
  state.jobs[0].status = 'failed';
  state.jobs[0].render.status = 'failed';
  await saveState(directory, state);
  channel.game = { ...channel.game, title: 'NEW HOOK', difficulty: 18 };
  await generateChannel(config, channel, date);
  assert.equal(calls.at(-1).payload.title, 'NEW HOOK');
  assert.equal(calls.at(-1).payload.difficulty, 18);
  assert.deepEqual((await loadState(directory)).jobs[0].renderRequest, channel.game);
});

test('a renderer returning the wrong game cannot produce a ready job', async t => {
  const { config, channel, date, directory, calls } = await fixture(t);
  channel.game = { game: 'laser-dodge', difficulty: 22, title: 'WRONG' };
  await assert.rejects(() => generateChannel(config, channel, date), /wrong selected game/);
  assert.equal((await loadState(directory)).jobs[0].render.status, 'failed');
  await assert.rejects(() => publishChannel(config, channel, date), /not ready for publishing/);
  assert.equal(calls.length, 2);
});
