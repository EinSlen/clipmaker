import assert from 'node:assert/strict';
import test from 'node:test';
import worker, { generationDispatches, sealSession } from '../src/index.js';

const soft = { id: 'soft', enabled: true, game: { id: 'soft-body-slide', obstacle: 'v-stairs' } };
const flat = { id: 'flat', enabled: true, game: { id: 'ball-escape' } };

test('generate routes only active saved 3D assignments through the native pipeline', () => {
  const commands = generationDispatches({ dryRun: false, channels: [soft, { ...flat, enabled: false }] });
  assert.equal(commands.length, 1);
  assert.equal(commands[0].workflow, 'soft-body-artifact.yml');
  assert.equal(commands[0].inputs.use_cloud_config, 'true');
  assert.equal(commands[0].inputs.plan_only, 'false');
  assert.equal(commands[0].inputs.reuse_run_id, '');
  assert.equal(commands[0].inputs.chunk_size, '15');
});

test('mixed saved games generate both pipeline types, without publishing', () => {
  const commands = generationDispatches({ dryRun: false, channels: [soft, flat, { ...soft, id: 'second-3d' }] });
  assert.deepEqual(commands.map(command => command.workflow), ['soft-body-artifact.yml', 'daily-publisher.yml']);
  assert.deepEqual(commands[1].inputs, { action: 'generate', dry_run: 'false' });
});

test('test mode cannot start native renders or live 2D generation', () => {
  const commands = generationDispatches({ dryRun: true, channels: [soft, flat] });
  assert.equal(commands[0].inputs.plan_only, 'true');
  assert.equal(commands[1].inputs.dry_run, 'true');
});

test('a 2D-only plan keeps the existing generator and an empty plan is rejected', () => {
  assert.deepEqual(generationDispatches({ channels: [flat] }), [
    { workflow: 'daily-publisher.yml', inputs: { action: 'generate', dry_run: 'false' } },
  ]);
  assert.throws(() => generationDispatches(null), /Aucun compte actif/u);
  assert.throws(() => generationDispatches({ channels: [{ ...soft, enabled: false }] }), /Aucun compte actif/u);
});

async function authenticatedRequest(config, input = {}) {
  const env = {
    SESSION_SECRET: Buffer.alloc(32, 7).toString('base64url'),
    ALLOWED_LOGIN: 'EinSlen', DASHBOARD_ORIGIN: 'https://dashboard.test',
    REPOSITORY_OWNER: 'EinSlen', REPOSITORY_NAME: 'clipmaker',
    CONFIG: { get: async key => {
      if (key === 'github-app-config') return { client_id: 'test-client', client_secret: 'test-secret' };
      if (key === 'publisher-config-v1') return config;
      throw Error(`Unexpected config read: ${key}`);
    } },
  };
  const session = await sealSession({ access_token: 'test-token', login: 'EinSlen', session_expires_at: Date.now() + 60000 }, env);
  const request = new Request('https://worker.test/api/dispatch', {
    method: 'POST', headers: { Origin: env.DASHBOARD_ORIGIN, Authorization: `Bearer ${session}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow: 'daily-publisher.yml', inputs: { action: 'generate', ...input } }),
  });
  return { request, env };
}

test('the HTTP command uses the saved config, not injected client game or dry-run fields', async context => {
  const calls = [];
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(null, { status: 204 });
  });
  const { request, env } = await authenticatedRequest({ dryRun: true, channels: [soft] }, {
    game: 'ball-escape', use_cloud_config: 'false', plan_only: 'false', dry_run: 'false', force_youtube: 'true',
  });
  const response = await worker.fetch(request, env);
  assert.equal(response.status, 202);
  const payload = await response.json();
  assert.deepEqual(payload.workflows, ['soft-body-artifact.yml']);
  assert.match(payload.message, /sans rendu/u);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /soft-body-artifact\.yml\/dispatches$/u);
  assert.equal(calls[0].body.ref, 'main');
  assert.equal(calls[0].body.inputs.use_cloud_config, 'true');
  assert.equal(calls[0].body.inputs.plan_only, 'true');
  assert.equal(calls[0].body.inputs.force_youtube, undefined);
});

test('mixed HTTP generation waits for both GitHub dispatches and reports both', async context => {
  const calls = [];
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(null, { status: 204 });
  });
  const { request, env } = await authenticatedRequest({ dryRun: false, channels: [soft, flat] });
  const response = await worker.fetch(request, env);
  assert.equal(response.status, 202);
  const payload = await response.json();
  assert.equal(calls.length, 2);
  assert.match(payload.message, /3D et 2D/u);
  assert.equal(calls[1].body.inputs.action, 'generate');
  assert.equal(calls[1].body.inputs.dry_run, 'false');
});

test('a partial GitHub rejection clearly identifies the render already launched', async context => {
  let calls = 0;
  context.mock.method(globalThis, 'fetch', async () => ++calls === 1
    ? new Response(null, { status: 204 }) : new Response('{}', { status: 403 }));
  const { request, env } = await authenticatedRequest({ dryRun: false, channels: [soft, flat] });
  const response = await worker.fetch(request, env);
  assert.equal(response.status, 403);
  const payload = await response.json();
  assert.match(payload.error, /Déjà lancé : soft-body-artifact\.yml/u);
  assert.match(payload.error, /refusé daily-publisher\.yml/u);
  assert.equal(calls, 2);
});

test('missing saved accounts cannot return a false successful generation', async context => {
  const fetchMock = context.mock.method(globalThis, 'fetch', async () => { throw Error('Must not dispatch'); });
  const { request, env } = await authenticatedRequest({ dryRun: false, channels: [] });
  assert.equal((await worker.fetch(request, env)).status, 400);
  assert.equal(fetchMock.mock.calls.length, 0);
});
