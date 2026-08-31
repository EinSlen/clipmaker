import assert from 'node:assert/strict';
import test from 'node:test';
import { openSession, parseBearer, sealSession, validateDispatch } from '../src/index.js';
import { normalizePublisherConfig } from '../src/publisher-config.js';
import { localClock, runScheduler, schedulerOperations } from '../src/scheduler.js';

const secret = Buffer.from(Array.from({ length: 32 }, (_, index) => index + 1)).toString('base64url');
const env = { SESSION_SECRET: secret };

test('session encryption round-trips and rejects tampering', async () => {
  const original = {
    access_token: 'ghu_test',
    login: 'EinSlen',
    session_expires_at: Date.now() + 60_000,
  };
  const sealed = await sealSession(original, env);
  assert.equal((await openSession(sealed, env)).login, 'EinSlen');
  await assert.rejects(() => openSession(`${sealed}x`, env), /Session GitHub absente/u);
});

test('bearer parser requires an authorization header', () => {
  assert.equal(parseBearer(new Request('https://example.test', { headers: { Authorization: 'Bearer session' } })), 'session');
  assert.throws(() => parseBearer(new Request('https://example.test')), /Connexion GitHub requise/u);
});

test('daily dispatch is reduced to the safe server-side inputs', () => {
  assert.deepEqual(validateDispatch({
    workflow: 'daily-publisher.yml',
    inputs: { action: 'publish', dry_run: 'true', injected: 'ignored' },
  }), {
    workflow: 'daily-publisher.yml',
    inputs: { action: 'publish', dry_run: 'false' },
  });
});

test('soft body dispatch validates every editable input', () => {
  assert.deepEqual(validateDispatch({
    workflow: 'soft-body-artifact.yml',
    inputs: { obstacle: 'peg-grid', seed: '910104', samples: '64', chunk_size: '30', title: 'ignored' },
  }), {
    workflow: 'soft-body-artifact.yml',
    inputs: {
      obstacle: 'peg-grid',
      seed: '910104',
      samples: '64',
      chunk_size: '30',
      title: 'HOW SOFT CAN IT GET?',
    },
  });
  assert.throws(() => validateDispatch({
    workflow: 'soft-body-artifact.yml',
    inputs: { obstacle: '../bad', seed: 'x', samples: '999', chunk_size: '1' },
  }), /Obstacle 3D invalide/u);
});

test('unknown workflows are never forwarded', () => {
  assert.throws(() => validateDispatch({ workflow: 'evil.yml', inputs: {} }), /Workflow non autorisé/u);
});

test('health reports the last persisted scheduler tick', async () => {
  const lastTick = {
    status: 'ok',
    scheduledTime: '2026-08-25T17:40:00.000Z',
    completedAt: '2026-08-25T17:40:01.000Z',
    results: [{ operation: 'daily-publish', action: 'skip', reason: 'success', runId: 32874377702 }],
  };
  const worker = (await import('../src/index.js')).default;
  const response = await worker.fetch(new Request('https://worker.test/health'), {
    GITHUB_AUTOMATION_TOKEN: 'configured',
    CONFIG: {
      get: async (key, type) => {
        if (key === 'github-app-config') return '{}';
        if (key === 'scheduler-last-tick-v1') return type === 'json' ? lastTick : JSON.stringify(lastTick);
        return null;
      },
    },
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).lastTick, lastTick);
});

test('publisher config enforces one game and one assignment per account', () => {
  const base = {
    dryRun: false,
    timeZone: 'Europe/Paris',
    channels: [{
      id: 'soft-main',
      enabled: true,
      generateTime: '00:30',
      publishTime: '18:00',
      game: { id: 'soft-body-slide', difficulty: 100, duration: 30, obstacle: 'auto', title: 'HOW SOFT CAN IT GET?' },
      tiktok: { enabled: true, username: 'dvlad', visibility: 'private' },
      youtube: { enabled: true, account: 'default', privacy: 'private' },
    }],
  };
  const config = normalizePublisherConfig(base);
  assert.equal(config.channels[0].game.id, 'soft-body-slide');
  assert.equal(config.channels[0].game.duration, 30);
  assert.equal(config.channels[0].tiktok.username, 'dvlad');
  assert.equal(Object.hasOwn(config.channels[0].game, 'musicProfile'), false);
  for (const musicProfile of ['auto', 'revenge', 'sad-english', 'original']) {
    const withPlaylist = structuredClone(base);
    withPlaylist.channels[0].game.musicProfile = musicProfile;
    assert.equal(normalizePublisherConfig(withPlaylist).channels[0].game.musicProfile, musicProfile);
  }
  const invalidPlaylist = structuredClone(base);
  invalidPlaylist.channels[0].game.musicProfile = 'arbitrary-url';
  assert.throws(() => normalizePublisherConfig(invalidPlaylist), /Playlist vocale invalide/u);
  assert.throws(() => normalizePublisherConfig({
    ...base,
    channels: [...base.channels, { ...base.channels[0], id: 'duplicate' }],
  }), /déjà assigné/u);
});

test('public uploads require an explicit confirmation', () => {
  assert.throws(() => normalizePublisherConfig({
    channels: [{
      id: 'public-test',
      game: { id: 'ball-escape', difficulty: 14, duration: 15, title: 'CAN IT ESCAPE?' },
      tiktok: { enabled: true, username: 'dvlad', visibility: 'public', confirmPublic: false },
      youtube: { enabled: false, account: 'default', privacy: 'private' },
    }],
  }), /doit être confirmée/u);
});

test('scheduler follows Europe/Paris across summer time', () => {
  assert.deepEqual(localClock(new Date('2026-08-25T16:10:00Z'), 'Europe/Paris'), {
    date: '2026-08-25',
    minute: 18 * 60 + 10,
  });
});

test('Cloudflare makes publication due at the exact configured minute', () => {
  const config = {
    dryRun: false,
    timeZone: 'Europe/Paris',
    channels: [{
      id: 'softbody-dvlad', enabled: true, generateTime: '00:07', publishTime: '18:00',
      game: { id: 'soft-body-slide' },
    }],
  };
  const beforeDue = schedulerOperations(config, new Date('2026-08-25T15:59:00Z'));
  assert.equal(beforeDue.find((item) => item.id === 'daily-publish').eligible, false);
  const atDue = schedulerOperations(config, new Date('2026-08-25T16:00:00Z'));
  assert.equal(atDue.find((item) => item.id === 'daily-publish').eligible, true);
  assert.equal(atDue.find((item) => item.id === 'soft-body-3d').eligible, false);
});

test('scheduler skips a delayed native run instead of dispatching a duplicate', async () => {
  const writes = [];
  const config = {
    dryRun: false,
    timeZone: 'Europe/Paris',
    channels: [{
      id: 'softbody-dvlad', enabled: true, generateTime: '00:07', publishTime: '18:00',
      game: { id: 'soft-body-slide' },
    }],
  };
  const env = {
    REPOSITORY_OWNER: 'EinSlen',
    REPOSITORY_NAME: 'clipmaker',
    CONFIG: {
      get: async (key) => key === 'publisher-config-v1' ? config : null,
      put: async (...args) => writes.push(args),
    },
    github: async () => ({
      response: new Response('{}', { status: 200 }),
      payload: {
        workflow_runs: [{
          id: 32874377702,
          event: 'schedule',
          status: 'in_progress',
          conclusion: null,
          created_at: '2026-08-25T16:50:45Z',
        }],
      },
    }),
  };
  const result = await runScheduler({ env, token: 'test', now: new Date('2026-08-25T17:00:00Z') });
  assert.deepEqual(result, [{ operation: 'daily-publish', action: 'skip', reason: 'active', runId: 32874377702 }]);
  assert.equal(writes.length, 0);
});

test('scheduler dispatches once when GitHub missed the publication window', async () => {
  const calls = [];
  const config = {
    dryRun: false,
    timeZone: 'Europe/Paris',
    channels: [{
      id: 'softbody-dvlad', enabled: true, generateTime: '00:07', publishTime: '18:00',
      game: { id: 'soft-body-slide' },
    }],
  };
  const env = {
    REPOSITORY_OWNER: 'EinSlen',
    REPOSITORY_NAME: 'clipmaker',
    CONFIG: {
      get: async (key) => key === 'publisher-config-v1' ? config : null,
      put: async (...args) => calls.push(['put', ...args]),
    },
    github: async (path, options = {}) => {
      calls.push([options.method || 'GET', path, options.body]);
      if (options.method === 'POST') {
        return { response: new Response(null, { status: 204 }), payload: null };
      }
      return { response: new Response('{}', { status: 200 }), payload: { workflow_runs: [] } };
    },
  };
  const result = await runScheduler({ env, token: 'test', now: new Date('2026-08-25T16:00:00Z') });
  assert.equal(result[0].action, 'dispatch');
  assert.equal(calls.filter(([method]) => method === 'POST').length, 1);
  assert.equal(calls.filter(([method]) => method === 'put').length, 1);
});
