import assert from 'node:assert/strict';
import test from 'node:test';
import worker, { sealSession } from '../src/index.js';
import { CLIP_PREFIX, boundedBytes, chooseClip, clipMetadata, inspectWav, listClips, putClip } from '../src/edit-audio.js';

function wav(seconds = 12, signal = 1000) {
  const bytes = Buffer.alloc(44 + seconds * 192000);
  bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(2, 22);
  bytes.writeUInt32LE(48000, 24); bytes.writeUInt32LE(192000, 28); bytes.writeUInt16LE(4, 32);
  bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(bytes.length - 44, 40);
  // Technical signal only. Never claim this fixture is a real reviewed voice.
  for (let i = 44; i < bytes.length; i += 2) bytes.writeInt16LE(signal, i);
  return bytes;
}
const info = { title: 'Test fixture', mood: 'sad', mix: 'premixed', rights: 'original',
  source: 'Synthetic test fixture, not publishable speech', credit: 'Technical test only',
  rightsEvidence: 'Generated test signal', speechReviewed: true, rightsConfirmed: true };
function memoryKv() {
  const map = new Map();
  const stream = value => new Response(value).body;
  return { map,
    async put(key, value, options = {}) { map.set(key, { value: value instanceof ReadableStream ? await new Response(value).arrayBuffer() : value, metadata: options.metadata || null }); },
    async get(key, type) { const item = map.get(key); return !item ? null : type === 'json' ? JSON.parse(item.value) : type === 'stream' ? stream(item.value) : item.value; },
    async getWithMetadata(key, type) { return { value: await this.get(key, type), metadata: map.get(key)?.metadata || null }; },
    async list({ prefix }) { return { keys: [...map].filter(([key]) => key.startsWith(prefix)).map(([name, item]) => ({ name, metadata: item.metadata })), list_complete: true }; },
  };
}
function upload(audio = wav(), metadata = info, headers = {}) {
  const body = new FormData(); body.append('audio', new Blob([audio]), 'clip.wav'); body.append('metadata', JSON.stringify(metadata));
  return new Request('https://worker.test/api/edit-audio', { method: 'POST', body, headers });
}
async function setup() {
  const CONFIG = memoryKv();
  const env = { CONFIG, ALLOWED_LOGIN: 'EinSlen', DASHBOARD_ORIGIN: 'https://einslen.github.io',
    SESSION_SECRET: Buffer.alloc(32, 1).toString('base64url'), WORKFLOW_CONFIG_TOKEN: 'runner-test-only' };
  await CONFIG.put('github-app-config', JSON.stringify({ client_id: 'test', client_secret: 'test' }));
  const session = await sealSession({ login: 'EinSlen', access_token: 'test', session_expires_at: Date.now() + 600000 }, env);
  return { env, headers: { Origin: env.DASHBOARD_ORIGIN, Authorization: `Bearer ${session}` } };
}

test('canonical PCM keeps stereo and rejects silent/malformed/long recordings', () => {
  assert.equal(inspectWav(wav()), 12);
  assert.throws(() => inspectWav(wav(12, 0)), /silencieux/);
  assert.throws(() => inspectWav(wav(30)), /volumineux|secondes/);
  assert.throws(() => inspectWav(wav().subarray(0, 100)), /WAV/);
  const mono = wav(); mono.writeUInt16LE(1, 22);
  assert.throws(() => inspectWav(mono), /stéréo/);
});
test('reviewed speech and cross-platform rights are explicit, not inferred from a link', () => {
  for (const field of ['speechReviewed', 'rightsConfirmed']) assert.throws(() => clipMetadata({ ...info, [field]: false }, 12), /Confirme/);
  for (const field of ['source', 'credit', 'rightsEvidence']) assert.throws(() => clipMetadata({ ...info, [field]: '' }, 12), /invalide/);
  assert.throws(() => clipMetadata({ ...info, mood: 'singing' }, 12), /Type/);
});
test('bounded upload enforces streamed size even without Content-Length', async () => {
  const request = new Request('https://test', { method: 'POST', body: new ReadableStream({ start(c) { c.enqueue(new Uint8Array(12)); c.close(); } }), duplex: 'half' });
  await assert.rejects(() => boundedBytes(request, 10), /volumineux/);
});
test('upload is immutable, content-addressed and duplicates do not enter the rotation', async () => {
  const kv = memoryKv(); const clip = await putClip(upload(), kv);
  assert.match(clip.id, /^[a-f0-9]{64}$/); assert.equal(clip.duration, 12);
  await assert.rejects(() => putClip(upload(), kv), /déjà présent/);
  assert.equal((await listClips(kv)).length, 1);
});
test('rotation covers the pool, separates moods and pins retries despite library additions', async () => {
  const kv = memoryKv();
  for (let i = 1; i <= 4; i++) await putClip(upload(wav(12, i * 1000), { ...info, mood: i === 4 ? 'revenge' : 'sad' }), kv);
  const request = { profile: 'edit-sad', channel: 'one', date: '2026-08-31', seed: 1 };
  const first = await chooseClip(kv, request);
  const second = await chooseClip(kv, { ...request, date: '2026-09-01' });
  const third = await chooseClip(kv, { ...request, date: '2026-09-02' });
  assert.equal(new Set([first.id, second.id, third.id]).size, 3);
  await putClip(upload(wav(12, 5000)), kv);
  assert.deepEqual(await chooseClip(kv, { ...request, seed: 99 }), first);
  assert.equal((await chooseClip(kv, { ...request, profile: 'edit-revenge' })).mood, 'revenge');
  kv.map.get(CLIP_PREFIX + first.id).metadata.active = false;
  await assert.rejects(() => chooseClip(kv, request), /désactivé/);
});
test('empty libraries and malformed dates fail without a song fallback', async () => {
  const req = { profile: 'edit-sad', channel: 'one', date: '2026-08-31', seed: 1 };
  await assert.rejects(() => chooseClip(memoryKv(), req), /Aucune voix/);
  await assert.rejects(() => chooseClip(memoryKv(), { ...req, date: '2026-99-99' }), /invalide/);
  await assert.rejects(() => chooseClip(memoryKv(), { ...req, profile: 'sad-english' }), /invalide/);
});
test('seed-scoped previews accept a stable date and vary across video identities', async () => {
  const kv = memoryKv();
  for (let i = 1; i <= 4; i++) await putClip(upload(wav(12, i * 1000)), kv);
  const selected = [];
  for (let seed = 910100; seed < 910116; seed++) {
    const request = { profile: 'edit-sad', channel: `preview-${seed}`, date: '1970-01-01', seed };
    const clip = await chooseClip(kv, request);
    selected.push(clip.id);
    assert.deepEqual(await chooseClip(kv, request), clip);
  }
  assert.equal(new Set(selected).size, 4);
});
test('private API imports, serves and deactivates without exposing credentials', async () => {
  const { env, headers } = await setup();
  const uploaded = await worker.fetch(upload(wav(), info, headers), env);
  assert.equal(uploaded.status, 201);
  const { clip } = await uploaded.json();
  const result = await worker.fetch(new Request(`https://worker.test/api/edit-audio/${clip.id}`, { headers }), env);
  assert.equal(result.status, 200); assert.equal(result.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(Buffer.from(await result.arrayBuffer()), wav());
  const malformed = await worker.fetch(new Request(`https://worker.test/api/edit-audio/${clip.id}`, { method: 'POST', headers, body: '{' }), env);
  assert.equal(malformed.status, 400);
  assert.equal((await listClips(env.CONFIG))[0].active, true);
  const deactivated = await worker.fetch(new Request(`https://worker.test/api/edit-audio/${clip.id}`, { method: 'POST', headers, body: JSON.stringify({ active: false }) }), env);
  assert.equal(deactivated.status, 200);
  const runner = await worker.fetch(new Request(`https://worker.test/api/workflow/edit-audio/${clip.id}`, { headers: { Authorization: 'Bearer runner-test-only' } }), env);
  assert.equal(runner.status, 409);
});
test('audio endpoints reject public access, wrong origins and runner writes', async () => {
  const { env, headers } = await setup();
  assert.equal((await worker.fetch(new Request('https://worker.test/api/edit-audio'), env)).status, 403);
  assert.equal((await worker.fetch(new Request('https://worker.test/api/edit-audio', { headers: { ...headers, Origin: 'https://evil.test' } }), env)).status, 403);
  assert.equal((await worker.fetch(new Request('https://worker.test/api/workflow/edit-audio'), env)).status, 401);
  assert.notEqual((await worker.fetch(new Request('https://worker.test/api/workflow/edit-audio', { method: 'POST', headers: { Authorization: 'Bearer runner-test-only' }, body: '{}' }), env)).status, 201);
  assert.equal((await listClips(env.CONFIG)).length, 0);
});
