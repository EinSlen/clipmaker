import assert from 'node:assert/strict';
import test from 'node:test';
import { openSession, parseBearer, sealSession, validateDispatch } from '../src/index.js';
import { normalizePublisherConfig } from '../src/publisher-config.js';

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
