import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { isTrustedDailyRender, planRenderCatchup } from './render-catchup.mjs';
import { catchUpRender } from '../../scripts/catch-up-render.mjs';

const identity = { repository: 'EinSlen/clipmaker', defaultBranch: 'main' };
const now = new Date('2026-08-28T18:15:00Z');
const run = { id: 123, name: 'Soft Body 3D artifact',
  path: '.github/workflows/soft-body-artifact.yml', status: 'completed', conclusion: 'success',
  event: 'workflow_dispatch', head_branch: 'main', head_repository: { full_name: identity.repository },
  created_at: '2026-08-28T00:07:00Z', pull_requests: [] };
const channel = (id, publishTime = '18:00') => ({ id, publishTime, enabled: true,
  game: { id: 'soft-body-slide' }, youtube: { enabled: true, privacy: 'private' },
  tiktok: { enabled: true, visibility: 'private' } });
const config = { dryRun: false, timeZone: 'Europe/Paris', channels: [channel('softbody-dvlad')] };
const artifact = (id = 'softbody-dvlad', date = '2026-08-28') => ({
  name: `soft-body-daily-${date}-${id}`, expired: false, size_in_bytes: 7200000,
});
const plan = overrides => planRenderCatchup({ ...identity, run, config, now,
  artifacts: [artifact()], ...overrides });

test('a late daily render resumes the normal scheduled publisher without forcing', () => {
  assert.equal(plan().reason, 'ready');
  assert.deepEqual(plan().dispatches, [{ workflow: 'daily-publisher.yml', ref: 'main', inputs: {
    action: 'publish', dry_run: 'false', force_youtube: 'false', scheduled_publish: 'true',
    publish_slot: '18:00', schedule_date: '2026-08-28',
  } }]);
});

test('foreign repositories, branches, failed runs and PRs cannot request publication', () => {
  for (const patch of [{ head_repository: { full_name: 'attacker/clipmaker' } },
    { head_branch: 'test' }, { event: 'pull_request' }, { conclusion: 'failure' },
    { status: 'in_progress' }, { name: 'other' }, { path: '.github/workflows/other.yml' },
    { pull_requests: [{ number: 1 }] }, { id: '../123' }]) {
    assert.equal(isTrustedDailyRender({ ...run, ...patch }, identity), false);
    assert.equal(plan({ run: { ...run, ...patch } }).dispatches.length, 0);
  }
});

test('manual previews, missing, expired or empty artifacts never qualify', () => {
  for (const artifacts of [[], [artifact('manual-3d')], [artifact('softbody-dvlad', '2026-08-27')],
    [{ ...artifact(), expired: true }], [{ ...artifact(), size_in_bytes: 0 }]]) {
    assert.equal(plan({ artifacts }).dispatches.length, 0);
  }
});

test('a current artifact name cannot revive an expired run or a future date', () => {
  for (const created_at of ['2026-08-27T12:00:00Z', '2026-08-29T00:00:00Z', 'invalid']) {
    assert.equal(plan({ run: { ...run, created_at } }).reason, 'expired-render');
  }
});

test('dry-run, disabled accounts, 2D selection and disconnected accounts stay idle', () => {
  for (const altered of [{ ...config, dryRun: true }, { ...config, dryRun: undefined },
    { ...config, channels: [{ ...channel('softbody-dvlad'), enabled: false }] },
    { ...config, channels: [{ ...channel('softbody-dvlad'), game: { id: 'ball-escape' } }] },
    { ...config, channels: [{ ...channel('softbody-dvlad'), youtube: {}, tiktok: {} }] }]) {
    assert.equal(plan({ config: altered }).dispatches.length, 0);
  }
});

test('Paris publication time is respected in summer and winter, never early', () => {
  assert.equal(plan({ now: new Date('2026-08-28T15:59:59Z') }).dispatches.length, 0);
  assert.equal(plan({ now: new Date('2026-08-28T16:00:00Z') }).dispatches.length, 1);
  const winter = { run: { ...run, created_at: '2026-12-28T00:07:00Z' },
    artifacts: [artifact('softbody-dvlad', '2026-12-28')] };
  assert.equal(plan({ ...winter, now: new Date('2026-12-28T16:59:00Z') }).dispatches.length, 0);
  assert.equal(plan({ ...winter, now: new Date('2026-12-28T17:00:00Z') }).dispatches.length, 1);
});

test('shared slots wait for every 3D account; sibling renders can supply readiness', () => {
  const multi = { ...config, channels: [channel('softbody-dvlad'), channel('second'), channel('later', '21:00')] };
  assert.equal(plan({ config: multi }).dispatches.length, 0);
  const ready = plan({ config: multi, availableArtifacts: [artifact(), artifact('second')] });
  assert.equal(ready.dispatches.length, 1);
  assert.equal(ready.dispatches[0].inputs.publish_slot, '18:00');
  assert.equal(plan({ config: multi, artifacts: [artifact('later')],
    availableArtifacts: [artifact(), artifact('second'), artifact('later')] }).dispatches.length, 0);
});

test('several late slots use one due-only dispatch without overrunning the concurrency queue', () => {
  const multi = { ...config, channels: [channel('softbody-dvlad'), channel('second', '19:00')] };
  const result = plan({ config: multi, artifacts: [artifact(), artifact('second')] });
  assert.equal(result.dispatches.length, 1);
  assert.equal(result.dispatches[0].inputs.publish_slot, '');
  assert.equal(result.dispatches[0].inputs.scheduled_publish, 'true');
  assert.equal(plan({ config: multi }).dispatches.length, 0);
});

function fixture(overrides = {}) {
  const calls = [], logs = [];
  const event = { repository: { default_branch: 'main' }, workflow_run: run };
  const env = { GITHUB_EVENT_NAME: 'workflow_run', GITHUB_REPOSITORY: identity.repository,
    GH_TOKEN: 'test-gh-secret', CLIPMAKER_UPLOAD_TOKEN: 'test-cloud-secret' };
  const request = async (url, options) => {
    calls.push({ url, options });
    assert.equal(options.redirect, 'error');
    if (url.endsWith('/bootstrap')) {
      assert.equal(options.headers.Authorization, 'Bearer test-cloud-secret');
      return Response.json({ config, sessionsBundle: 'sensitive-session-never-logged' });
    }
    assert.equal(options.headers.Authorization, 'Bearer test-gh-secret');
    if (url.endsWith('/dispatches')) return new Response(null, { status: 204 });
    if (url.endsWith('/runs/123')) return Response.json(run);
    if (url.includes('/artifacts?')) return Response.json({ total_count: 1, artifacts: [artifact()] });
    if (url.includes('/soft-body-artifact.yml/runs?')) return Response.json({ workflow_runs: [run] });
    throw new Error('Unexpected request');
  };
  return { calls, logs, args: { event, env, request, clock: () => now, log: message => logs.push(message), ...overrides } };
}

test('runner integration dispatches once, forwards no sessions, and never extracts artifacts', async () => {
  const { calls, logs, args } = fixture();
  await catchUpRender(args);
  const posts = calls.filter(call => call.options.method === 'POST');
  assert.equal(posts.length, 1);
  assert.deepEqual(JSON.parse(posts[0].options.body), {
    ref: 'main', inputs: plan().dispatches[0].inputs,
  });
  assert.ok(calls.every(call => !call.url.endsWith('/zip')));
  assert.doesNotMatch(logs.join('\n'), /secret|sensitive-session/);
});

test('untrusted event exits before loading any credential or configuration', async () => {
  const { calls, args } = fixture();
  args.event = { ...args.event, workflow_run: { ...run, head_branch: 'preview' } };
  await catchUpRender(args);
  assert.equal(calls.length, 0);
});

test('runner finds the final artifact beyond the first hundred native chunks', async () => {
  const { calls, args } = fixture();
  const original = args.request;
  args.request = async (url, options) => {
    if (url.includes('/artifacts?') && url.endsWith('page=1')) {
      calls.push({ url, options });
      return Response.json({ total_count: 101, artifacts: Array.from({ length: 100 },
        (_, index) => ({ ...artifact(), name: `native-chunk-${index}` })) });
    }
    return original(url, options);
  };
  await catchUpRender(args);
  assert.equal(calls.filter(call => call.options.method === 'POST').length, 1);
  assert.ok(calls.some(call => call.url.includes('/artifacts?') && call.url.endsWith('page=2')));
});

test('a dispatch HTTP failure is reported without retrying or forcing a platform', async () => {
  const { calls, args } = fixture();
  const original = args.request;
  args.request = async (url, options) => {
    if (url.endsWith('/dispatches')) {
      calls.push({ url, options });
      return new Response('sensitive response must not be included', { status: 403 });
    }
    return original(url, options);
  };
  await assert.rejects(catchUpRender(args), /^Error: GitHub request failed \(403\).$/);
  assert.equal(calls.filter(call => call.options.method === 'POST').length, 1);
});

test('changed GitHub provenance fails before the cloud bootstrap', async () => {
  const { calls, args } = fixture();
  args.request = async (url) => { calls.push(url); return Response.json({ ...run, head_branch: 'preview' }); };
  await assert.rejects(catchUpRender(args), /provenance/);
  assert.equal(calls.length, 1);
});

test('a midnight rollover during API checks cancels the catch-up', async () => {
  const { calls, args } = fixture();
  let clocks = 0;
  args.clock = () => clocks++ ? new Date('2026-08-28T22:01:00Z') : now;
  await catchUpRender(args);
  assert.equal(calls.filter(call => call.options.method === 'POST').length, 0);
});

test('workflow runs trusted default branch code and preserves publisher safeguards', async () => {
  const hook = await fs.readFile(new URL('../../../.github/workflows/late-render-catchup.yml', import.meta.url), 'utf8');
  assert.match(hook, /workflows: \[Soft Body 3D artifact\]/);
  assert.match(hook, /head_repository.full_name == github.repository/);
  assert.match(hook, /ref: \$\{\{ github.event.repository.default_branch \}\}/);
  assert.match(hook, /persist-credentials: false/);
  assert.doesNotMatch(hook, /ref:.*head_sha|download-artifact|workflow_dispatch:/);
});
