import { assertDate, assertTime, dateInTimeZone, isTimeDue } from './time.mjs';

// This scopes only the runner's copy. The saved dashboard configuration and
// daily job IDs stay unchanged, including private/public confirmations.
export function scopePublication(config, {
  scheduled = false, slot = '', expectedDate = '', now = new Date(),
} = {}) {
  const timeZone = config.timeZone || 'Europe/Paris';
  const date = dateInTimeZone(now, timeZone);
  if (slot) assertTime(slot);
  if (expectedDate && assertDate(expectedDate) !== date) {
    throw new Error('Scheduled publication expired: refusing to publish a different day.');
  }
  if (slot && !scheduled) throw new Error('A publication slot requires scheduled mode.');
  const scoped = structuredClone(config);
  for (const channel of scoped.channels || []) {
    if (!scheduled || channel.enabled === false) continue;
    const publishTime = assertTime(channel.publishTime || '18:00');
    channel.enabled = (!slot || publishTime === slot) && isTimeDue(publishTime, now, timeZone);
  }
  return { config: scoped, date, channels: (scoped.channels || [])
    .filter((channel) => channel.enabled !== false).map((channel) => channel.id) };
}
