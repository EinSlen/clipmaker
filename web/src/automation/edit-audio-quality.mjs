export function assertEditAudioQuality(metadata, duration = 30) {
  const requested = metadata?.requested_music_profile;
  const spoken = metadata?.music_content_kind === 'spoken';
  if (!String(requested || '').startsWith('edit-') && !spoken) return;
  if (!['edit-auto', 'edit-sad', 'edit-revenge'].includes(requested)
    || !['edit-sad', 'edit-revenge'].includes(metadata.music_profile)
    || (requested !== 'edit-auto' && metadata.music_profile !== requested)
    || !spoken || metadata.music_provider !== 'private-edit-library'
    || metadata.music_mode !== 'spoken-edit' || metadata.music_generated !== false
    || metadata.music_clearance !== 'user-attested-cross-platform'
    || metadata.music_language !== 'en' || metadata.music_sentence_reviewed !== true
    || metadata.music_looped !== false || metadata.music_excerpt_start !== 0
    || metadata.music_voice_start !== 0.15 || metadata.music_has_vocals !== true
    || !Number.isFinite(metadata.music_excerpt_duration) || metadata.music_excerpt_duration < 10
    || metadata.music_excerpt_duration > Math.min(29.5, duration - 0.3)
    || !/^[a-f0-9]{64}$/u.test(metadata.music_source_sha256 || '')
    || metadata.music_track_id !== metadata.music_source_sha256
    || !metadata.music_credit || !metadata.music_rights_evidence || !metadata.music_source_url
    || !metadata.music_selection_key
    || typeof metadata.music_preserves_original_mix !== 'boolean'
    || metadata.music_added_bed !== !metadata.music_preserves_original_mix) {
    throw new Error('Spoken edit publication blocked: missing complete speech, source integrity or cross-platform rights confirmation.');
  }
}
