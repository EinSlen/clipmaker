import test from 'node:test';
import assert from 'node:assert/strict';
import { assertEditAudioQuality } from './edit-audio-quality.mjs';

const clip = {
  requested_music_profile: 'edit-sad', music_profile: 'edit-sad', music_content_kind: 'spoken',
  music_provider: 'private-edit-library', music_mode: 'spoken-edit', music_generated: false,
  music_clearance: 'user-attested-cross-platform', music_language: 'en', music_has_vocals: true,
  music_sentence_reviewed: true, music_looped: false, music_excerpt_start: 0, music_excerpt_duration: 22,
  music_voice_start: 0.15, music_source_sha256: 'a'.repeat(64), music_track_id: 'a'.repeat(64),
  music_credit: 'Test credit', music_rights_evidence: 'Test license', music_source_url: 'Test source',
  music_selection_key: 'test:2026-08-31', music_preserves_original_mix: true, music_added_bed: false,
};
test('publisher accepts complete reviewed speech and rejects songs, loops, cuts and missing rights', () => {
  assert.doesNotThrow(() => assertEditAudioQuality(clip));
  for (const [field, value] of Object.entries({
    music_content_kind: 'song', music_provider: 'ncs', music_generated: true,
    music_looped: true, music_excerpt_start: 20, music_excerpt_duration: 30,
    music_sentence_reviewed: false, music_rights_evidence: '', music_source_sha256: '',
    music_credit: '', music_language: 'fr', music_added_bed: true, music_profile: 'edit-revenge',
  })) assert.throws(() => assertEditAudioQuality({ ...clip, [field]: value }), /Spoken edit/);
});
test('legacy instrumentals stay unchanged; edit-auto may choose either spoken mood', () => {
  assert.doesNotThrow(() => assertEditAudioQuality({ music_generated: true }));
  assert.doesNotThrow(() => assertEditAudioQuality({ ...clip, requested_music_profile: 'edit-auto', music_profile: 'edit-revenge' }));
});
