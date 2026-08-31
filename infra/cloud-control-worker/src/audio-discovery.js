// The authorized runner performs speech analysis. This endpoint verifies its
// bounded evidence and hashes; it never labels that analysis as human review.
import { AudioError, CLIP_PREFIX, MAX_CLIP_BYTES, USED_PREFIX, boundedBytes, inspectWav, listClips } from './edit-audio.js';

export const DISCOVERY_VERSION = 'freesound-whisper-v1';
export const COLLECTION_KEY = 'edit-collection-v1';
export const AUDIT_PREFIX = 'edit-audit-v1:';
const HASH = /^[a-f0-9]{64}$/u;
const SOURCE = /^https:\/\/freesound\.org\/people\/([A-Za-z0-9_.-]+)\/sounds\/([0-9]+)\/$/u;
const LICENSE = /^https:\/\/creativecommons\.org\/(?:licenses\/by\/(?:2\.0|2\.5|3\.0|4\.0)|publicdomain\/zero\/1\.0)\/$/u;
const fail = (message, status = 400) => { throw new AudioError(status, message); };
const digest = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
const encode = text => new TextEncoder().encode(text);
const words = text => String(text).toLowerCase().replaceAll('’', "'").match(/[a-z]+(?:'[a-z]+)?/gu) || [];

export async function collectionState(kv) {
  const raw = await kv.get(COLLECTION_KEY, 'json') || {};
  const state = {
    enabled: raw.enabled !== false,
    cursor: Number.isSafeInteger(raw.cursor) && raw.cursor >= 0 ? raw.cursor : 0,
    seen: Array.isArray(raw.seen) ? raw.seen.filter(id => /^[0-9]{1,12}$/u.test(id)).slice(-2000) : [],
    status: ['not-run', 'ok', 'no-new-clips', 'degraded', 'capacity'].includes(raw.status) ? raw.status : 'not-run',
  };
  for (const key of ['startedAt', 'completedAt']) if (typeof raw[key] === 'string' && Number.isFinite(Date.parse(raw[key]))) state[key] = raw[key];
  for (const key of ['imported', 'searched', 'examined', 'duplicates']) if (Number.isSafeInteger(raw[key]) && raw[key] >= 0) state[key] = raw[key];
  if (raw.rejected && typeof raw.rejected === 'object' && !Array.isArray(raw.rejected)) state.rejected = raw.rejected;
  if (Array.isArray(raw.errors)) state.errors = raw.errors.slice(0, 30);
  return state;
}

export async function saveCollection(request, kv, runner) {
  let data;
  try { data = JSON.parse(new TextDecoder().decode(await boundedBytes(request, 24000))); }
  catch (error) { if (error instanceof AudioError) throw error; fail('État de collecte invalide.'); }
  const previous = await collectionState(kv);
  if (!runner) {
    if (typeof data.enabled !== 'boolean' || Object.keys(data).length !== 1) fail('Activation de collecte invalide.');
    await kv.put(COLLECTION_KEY, JSON.stringify({ ...previous, enabled: data.enabled }));
  } else {
    if (data.version !== DISCOVERY_VERSION || !['ok', 'no-new-clips', 'degraded', 'capacity'].includes(data.status)
      || !Number.isSafeInteger(data.cursor) || data.cursor < previous.cursor || data.cursor > previous.cursor + 3
      || !Array.isArray(data.seen) || data.seen.length > 60 || data.seen.some(id => !/^[0-9]{1,12}$/u.test(id))
      || !['startedAt', 'completedAt'].every(key => typeof data[key] === 'string' && Number.isFinite(Date.parse(data[key])))
      || !['imported', 'searched', 'examined', 'duplicates'].every(key => Number.isSafeInteger(data[key]) && data[key] >= 0 && data[key] <= 100)
      || !Array.isArray(data.errors) || data.errors.length > 30 || data.errors.some(x => !/^[a-z0-9-]{1,80}$/u.test(x))
      || !data.rejected || typeof data.rejected !== 'object' || Array.isArray(data.rejected)
      || Object.entries(data.rejected).some(([k, v]) => !/^[a-z-]{1,80}$/u.test(k) || !Number.isSafeInteger(v) || v < 0 || v > 100)) fail('Rapport de collecte invalide.');
    // Only explicit report fields are persisted. A runner cannot enable a
    // paused collection or write arbitrary settings/accounts via this route.
    await kv.put(COLLECTION_KEY, JSON.stringify({ enabled: previous.enabled,
      version: data.version, cursor: data.cursor, status: data.status,
      startedAt: data.startedAt, completedAt: data.completedAt,
      imported: data.imported, searched: data.searched, examined: data.examined, duplicates: data.duplicates,
      rejected: data.rejected, errors: data.errors,
      seen: [...new Set([...previous.seen, ...data.seen])].slice(-2000),
    }));
  }
  return collectionState(kv);
}

export async function validateDiscovery(raw, audit, duration, audioId) {
  const source = SOURCE.exec(raw?.source || '');
  const speech = audit?.speech;
  if (!raw || raw.reviewMode !== DISCOVERY_VERSION || raw.speechReviewed !== false || raw.rightsConfirmed !== false
    || raw.rights !== 'licensed' || raw.mix !== 'voice-only' || !['sad', 'revenge'].includes(raw.mood)
    || !source || raw.sourceId !== source[2] || !LICENSE.test(raw.rightsEvidence || '')
    || !audit || audit.version !== DISCOVERY_VERSION || audit.source !== raw.source || audit.sourceId !== raw.sourceId
    || audit.audioSha256 !== audioId || !HASH.test(audit.sourceSha256 || '') || !HASH.test(audit.indexSha256 || '')
    || !/^[a-f0-9-]{36}$/u.test(audit.openverseId || '')
    || !new RegExp(`^https://cdn\\.freesound\\.org/previews/[0-9]+/${raw.sourceId}_[0-9]+-hq\\.mp3$`, 'u').test(audit.media || '')
    || audit.licenseEvidence?.license !== raw.rightsEvidence || audit.licenseEvidence?.originalClaim !== true
    || !HASH.test(audit.licenseEvidence?.pageSha256 || '')
    || typeof audit.licenseEvidence?.description !== 'string' || audit.licenseEvidence.description.length > 4000
    || !Number.isFinite(Date.parse(audit.checkedAt))
    || !speech || speech.language !== 'en' || speech.model !== 'faster-whisper-small' || speech.mood !== raw.mood
    || speech.wholeRecording !== true || speech.repeatedTakes !== false
    || !Number.isFinite(speech.languageProbability) || speech.languageProbability < .9 || speech.languageProbability > 1
    || !Number.isFinite(speech.wordConfidence) || speech.wordConfidence < .82 || speech.wordConfidence > 1
    || !Number.isFinite(speech.start) || speech.start < .1 || !Number.isFinite(speech.end) || speech.end > duration - .12
    || (speech.end - speech.start) / duration < .35
    || typeof speech.transcript !== 'string' || speech.transcript.length > 1200
    || !Number.isFinite(audit.levels?.duration) || Math.abs(audit.levels.duration - duration) > .002
    || !Number.isFinite(audit.levels?.rms) || audit.levels.rms < .002 || audit.levels.rms > 1
    || !Number.isFinite(audit.levels?.clippedFraction) || audit.levels.clippedFraction < 0 || audit.levels.clippedFraction > .002) fail('Preuves automatiques de voix/licence incomplètes.');
  const tokens = words(speech.transcript);
  const grams = tokens.slice(3).map((_, i) => tokens.slice(i, i + 4).join(' '));
  if (tokens.length !== speech.wordCount || tokens.length < 12 || tokens.length > 90 || new Set(tokens).size < 9
    || new Set(['a', 'an', 'the', 'to', 'of', 'and', 'but', 'or', 'with', 'for']).has(tokens.at(-1))
    || new Set(grams).size / grams.length < .9 || await digest(encode(tokens.join(' '))) !== speech.transcriptSha256) fail('Transcription répétée ou incohérente.');
  for (const [key, limit] of [['title', 80], ['credit', 160]]) {
    if (typeof raw[key] !== 'string' || !raw[key].trim() || raw[key].length > limit || /[\x00-\x1f]/u.test(raw[key])) fail('Crédit/titre invalide.');
  }
  if (!raw.credit.includes(source[1]) || !raw.credit.includes(raw.title) || !raw.credit.includes('CC') || !raw.credit.includes(raw.source)) fail('Attribution du créateur absente.');
  const metadata = { title: raw.title, mood: raw.mood, mix: 'voice-only', rights: 'licensed',
    rightsEvidence: raw.rightsEvidence, credit: raw.credit, source: raw.source, sourceId: raw.sourceId,
    kind: 'spoken', language: 'en', speechReviewed: false, rightsConfirmed: false, reviewMode: DISCOVERY_VERSION,
    auditSha256: await digest(encode(JSON.stringify(audit))), duration, active: true, createdAt: new Date().toISOString() };
  if (encode(JSON.stringify(metadata)).length > 1010) fail('Métadonnées audio trop longues.');
  return metadata;
}

export async function importDiscoveredClip(request, kv) {
  if (!(await collectionState(kv)).enabled) fail('Collecte automatique en pause.', 409);
  const bytes = await boundedBytes(request, MAX_CLIP_BYTES + 24000);
  let form, raw, audit;
  try {
    form = await new Response(bytes, { headers: { 'Content-Type': request.headers.get('Content-Type') || '' } }).formData();
    raw = JSON.parse(String(form.get('metadata'))); audit = JSON.parse(String(form.get('audit')));
  } catch { fail('Import automatique invalide.'); }
  const file = form.get('audio');
  if (!file || typeof file.arrayBuffer !== 'function' || file.size > MAX_CLIP_BYTES) fail('Audio absent.');
  const audio = new Uint8Array(await file.arrayBuffer());
  const id = await digest(audio);
  const metadata = await validateDiscovery(raw, audit, inspectWav(audio), id);
  // Two immutable indexes detect new encodings of the same source/words.
  // GitHub's single collector concurrency group serializes imports. KV is not
  // used as a distributed lock; retries of the same import are idempotent.
  const sourceKey = `edit-discovered-source-v1:${raw.sourceId}`;
  const transcriptKey = `edit-discovered-text-v1:${audit.speech.transcriptSha256}`;
  const [sourceId, textId, existing] = await Promise.all([
    kv.get(sourceKey), kv.get(transcriptKey), kv.getWithMetadata(CLIP_PREFIX + id, 'stream'),
  ]);
  if (existing.value) {
    await existing.value.cancel();
    if (existing.metadata?.reviewMode !== DISCOVERY_VERSION || existing.metadata.sourceId !== raw.sourceId) fail('Doublon d’un autre extrait.', 409);
    // Repair indexes after a partially completed import before acknowledging.
    await kv.put(sourceKey, id); await kv.put(transcriptKey, id);
    return { id, ...existing.metadata, duplicate: true };
  }
  if (sourceId || textId) fail('Source ou paroles déjà importées.', 409);
  let library = await listClips(kv);
  if (library.length >= 175) {
    await pruneDiscoveredClips(kv, library);
    library = await listClips(kv);
  }
  if (library.length >= 190) fail('Bibliothèque pleine : collecte suspendue, sons existants conservés.', 409);
  // Audit is written first. An audit orphan is safe; unaudited audio is not.
  await kv.put(AUDIT_PREFIX + id, JSON.stringify(audit));
  await kv.put(CLIP_PREFIX + id, audio, { metadata });
  await kv.put(sourceKey, id);
  await kv.put(transcriptKey, id);
  return { id, ...metadata };
}

export async function pruneDiscoveredClips(kv, supplied, now = new Date()) {
  const library = supplied || await listClips(kv);
  const threshold = now.getTime() - 130 * 86400_000;
  const candidates = library.filter(clip => clip.reviewMode === DISCOVERY_VERSION
    && Number.isFinite(Date.parse(clip.createdAt)) && Date.parse(clip.createdAt) < threshold)
    .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt));
  let removed = 0;
  for (const clip of candidates) {
    if (library.length - removed <= 165 || await kv.get(USED_PREFIX + clip.id)) continue;
    const audit = await kv.get(AUDIT_PREFIX + clip.id, 'json');
    // An incomplete audit must be kept for investigation instead of becoming
    // an unsafe partially-deleted source index.
    if (audit?.sourceId !== clip.sourceId || !HASH.test(audit?.speech?.transcriptSha256 || '')) continue;
    await kv.delete(CLIP_PREFIX + clip.id);
    await kv.delete(AUDIT_PREFIX + clip.id);
    await kv.delete(`edit-discovered-source-v1:${clip.sourceId}`);
    await kv.delete(`edit-discovered-text-v1:${audit.speech.transcriptSha256}`);
    await kv.delete(USED_PREFIX + clip.id);
    removed += 1;
  }
  return removed;
}
