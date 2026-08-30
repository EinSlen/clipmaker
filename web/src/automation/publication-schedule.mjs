import { addDays, assertDate, assertTime, dateInTimeZone, isTimeDue } from './time.mjs';

// This scopes only the runner's copy. The saved dashboard configuration and
// daily job IDs stay unchanged, including private/public confirmations.
export function scopePublication(config, {
  scheduled = false, slot = '', expectedDate = '', now = new Date(),
} = {}) {
  const timeZone = config.timeZone || 'Europe/Paris';
  const today = dateInTimeZone(now, timeZone);
  const date = expectedDate ? assertDate(expectedDate) : today;
  if (slot) assertTime(slot);
  if (scheduled && expectedDate && date !== today) {
    throw new Error('Scheduled publication expired: refusing to publish a different day.');
  }
  const catchupDays = Math.max(1, Number(config.catchupDays) || 7);
  if (!scheduled && expectedDate && (date > today || date < addDays(today, -catchupDays))) {
    throw new Error(`Manual publication date must be within the last ${catchupDays} days.`);
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
