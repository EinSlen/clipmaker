import assert from 'node:assert/strict';
import test from 'node:test';
import { openSession, parseBearer, sealSession, validateDispatch } from '../src/index.js';

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
