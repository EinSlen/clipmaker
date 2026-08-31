// Small, immutable, private PCM clips. No arbitrary URL fetching and no tokens
// in media URLs. CONFIG is already provisioned; no paid storage setup required.
export const EDIT_PROFILES = ['edit-auto', 'edit-sad', 'edit-revenge'];
export const CLIP_PREFIX = 'edit-audio-v1:';
export const USED_PREFIX = 'edit-audio-used-v1:';
export const MAX_CLIP_BYTES = 5_700_000;
const ID = /^[a-f0-9]{64}$/u;

export class AudioError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const fail = (message, status = 400) => { throw new AudioError(status, message); };

export async function boundedBytes(request, maximum) {
  if (Number(request.headers.get('Content-Length') || 0) > maximum) fail('Fichier trop volumineux.', 413);
  if (!request.body) fail('Fichier manquant.');
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) { await reader.cancel(); fail('Fichier trop volumineux.', 413); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
  return result;
}

export function inspectWav(bytes) {
  if (bytes.byteLength < 44 || bytes.byteLength > MAX_CLIP_BYTES) fail('WAV invalide ou trop volumineux.');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = (start, length) => new TextDecoder().decode(bytes.subarray(start, start + length));
  // Our browser encoder emits canonical PCM, which also prevents feeding an
  // arbitrary container/playlist to the runner's media decoder.
  if (text(0, 4) !== 'RIFF' || text(8, 8) !== 'WAVEfmt ' || text(36, 4) !== 'data'
    || view.getUint32(4, true) !== bytes.length - 8 || view.getUint32(16, true) !== 16
    || view.getUint16(20, true) !== 1 || view.getUint16(22, true) !== 2
    || view.getUint32(24, true) !== 48000 || view.getUint32(28, true) !== 192000
    || view.getUint16(32, true) !== 4 || view.getUint16(34, true) !== 16
    || view.getUint32(40, true) !== bytes.length - 44 || (bytes.length - 44) % 4) fail('WAV PCM stéréo 48 kHz attendu.');
  const duration = (bytes.length - 44) / 192000;
  if (duration < 10 || duration > 29.5) fail('Choisis un extrait complet de 10 à 29,5 secondes.');
  // Signal presence is not a speech detector; the owner explicitly reviews
  // spoken English and complete sentence boundaries in the import form.
  let peak = 0;
  for (let i = 44; i < bytes.length; i += 188) peak = Math.max(peak, Math.abs(view.getInt16(i, true)), Math.abs(view.getInt16(i + 2, true)));
  if (peak < 100) fail('Cet extrait est silencieux.');
  return duration;
}

function clean(value, maximum, label) {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum || /[\x00-\x1f]/u.test(value)) fail(`${label} invalide.`);
  return value.trim();
}

export function clipMetadata(raw, duration) {
  if (!raw || raw.speechReviewed !== true || raw.rightsConfirmed !== true) fail('Confirme les phrases complètes en anglais et les droits TikTok + YouTube.');
  if (!['sad', 'revenge'].includes(raw.mood) || !['voice-only', 'premixed'].includes(raw.mix)) fail('Type de voix invalide.');
  if (!['original', 'licensed'].includes(raw.rights)) fail('Précise les droits de réutilisation.');
  const data = {
    title: clean(raw.title, 80, 'Titre'), mood: raw.mood, mix: raw.mix,
    rights: raw.rights, rightsEvidence: clean(raw.rightsEvidence, 180, 'Justificatif des droits'),
    credit: clean(raw.credit, 160, 'Crédit'), source: clean(raw.source, 180, 'Source'),
    kind: 'spoken', language: 'en', speechReviewed: true, rightsConfirmed: true,
    duration, active: true, createdAt: new Date().toISOString(),
  };
  if (new TextEncoder().encode(JSON.stringify(data)).length > 950) fail('Raccourcis les informations de crédit/source.');
  return data;
}

export async function listClips(kv) {
  const clips = [];
  let cursor;
  do {
    const page = await kv.list({ prefix: CLIP_PREFIX, limit: 100, ...(cursor ? { cursor } : {}) });
    for (const key of page.keys) {
      const id = key.name.slice(CLIP_PREFIX.length);
      if (ID.test(id) && key.metadata?.kind === 'spoken') clips.push({ id, ...key.metadata });
    }
    if (clips.length > 200) fail('Bibliothèque limitée à 200 extraits.', 409);
    cursor = page.cursor;
    if (!page.list_complete && !cursor) fail('Bibliothèque temporairement indisponible.', 503);
    if (page.list_complete) break;
  } while (true);
  return clips;
}

export async function putClip(request, kv) {
  const bytes = await boundedBytes(request, MAX_CLIP_BYTES + 12_000);
  let form;
  try { form = await new Response(bytes, { headers: { 'Content-Type': request.headers.get('Content-Type') || '' } }).formData(); }
  catch { fail('Import audio invalide.'); }
  const file = form.get('audio');
  if (!file || typeof file.arrayBuffer !== 'function' || file.size > MAX_CLIP_BYTES) fail('Fichier audio manquant.');
  const audio = new Uint8Array(await file.arrayBuffer());
  let raw;
  try { raw = JSON.parse(String(form.get('metadata') || '')); } catch { fail('Informations audio invalides.'); }
  const metadata = clipMetadata(raw, inspectWav(audio));
  const id = [...new Uint8Array(await crypto.subtle.digest('SHA-256', audio))].map(b => b.toString(16).padStart(2, '0')).join('');
  const existing = await kv.get(CLIP_PREFIX + id, 'stream');
  if (existing) { await existing.cancel(); fail('Cet extrait est déjà présent dans la bibliothèque.', 409); }
  if ((await listClips(kv)).length >= 200) fail('Bibliothèque pleine (200 extraits).', 409);
  await kv.put(CLIP_PREFIX + id, audio, { metadata });
  return { id, ...metadata };
}

export async function readClip(kv, id) {
  if (!ID.test(id)) fail('Identifiant audio invalide.');
  const result = await kv.getWithMetadata(CLIP_PREFIX + id, 'stream');
  if (!result.value || result.metadata?.kind !== 'spoken') fail('Extrait introuvable.', 404);
  return result;
}

export async function chooseClip(kv, request) {
  const { profile, channel, date, seed, duration = 30 } = request || {};
  if (!EDIT_PROFILES.includes(profile) || !/^[a-z0-9][a-z0-9_-]{1,63}$/u.test(channel || '')
    || !/^\d{4}-\d{2}-\d{2}$/u.test(date || '') || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date
    || !Number.isSafeInteger(seed) || duration !== 30) fail('Sélection vocale invalide.');
  const selectionKey = `edit-selection-v1:${channel}:${date}:${profile}`;
  const pinned = await kv.get(selectionKey, 'json');
  if (pinned) {
    const { metadata, value } = await readClip(kv, pinned.id);
    await value.cancel();
    if (!metadata.active) fail('L’extrait prévu a été désactivé. Aucun remplacement automatique.', 409);
    await kv.put(USED_PREFIX + pinned.id, '1', { expirationTtl: 125 * 86400 });
    return pinned;
  }
  const pool = (await listClips(kv)).filter(clip => clip.active && (profile === 'edit-auto' || profile === `edit-${clip.mood}`));
  if (!pool.length) fail('Aucune voix d’edit disponible. Importe un extrait parlé et autorisé dans la bibliothèque audio.', 409);
  const encoder = new TextEncoder();
  const deck = await Promise.all(pool.map(async clip => ({ clip, order: [...new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(`${channel}:${profile}:${clip.id}`)))].map(b => b.toString(16).padStart(2, '0')).join('') })));
  deck.sort((a, b) => a.order.localeCompare(b.order));
  const day = Math.floor(Date.parse(date) / 86400000);
  const chosen = deck[((day % deck.length) + deck.length) % deck.length].clip;
  const selection = { ...chosen, profile, selectionKey, poolSize: pool.length, sha256: chosen.id };
  await kv.put(selectionKey, JSON.stringify(selection), { expirationTtl: 120 * 86400 });
  await kv.put(USED_PREFIX + chosen.id, '1', { expirationTtl: 125 * 86400 });
  return selection;
}
