const DEFAULT_TIME_ZONE = 'Europe/Paris';
const GENERATION_WATCHDOG_GRACE_MINUTES = 10;
const RETRY_DELAY_MS = 20 * 60 * 1000;
const MAX_DISPATCH_ATTEMPTS = 3;
const RECORD_TTL_SECONDS = 8 * 24 * 60 * 60;

function parseTime(value) {
  const match = String(value || '').match(/^([01]\d|2[0-3]):([0-5]\d)$/u);
  if (!match) throw new Error(`Invalid scheduler time: ${value}`);
  return (Number(match[1]) * 60) + Number(match[2]);
}

export function localClock(value, timeZone = DEFAULT_TIME_ZONE) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value).reduce((result, part) => {
    if (part.type !== 'literal') result[part.type] = part.value;
    return result;
  }, {});
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minute: (Number(parts.hour) * 60) + Number(parts.minute),
  };
}

function earliestTime(channels, field, fallback) {
  return Math.min(...channels.map((channel) => parseTime(channel[field] || fallback)));
}

// Publishing at the same minute every single day is a machine signature, and
// the account this scheduler drives went out at 18:02 or 18:03 for a month.
// The offset is drawn from the day and the slot instead of at random, so
// every tick of the scheduler agrees on when the slot became due and the
// retry and native-run bookkeeping keeps working unchanged.
export const PUBLISH_JITTER_MINUTES = 60;

function digest(text) {
  let value = 2166136261;
  for (const character of text) {
    value = Math.imul(value ^ character.charCodeAt(0), 16777619) >>> 0;
  }
  return value;
}

export function publishJitter(date, slot, span = PUBLISH_JITTER_MINUTES) {
  const width = Number.isFinite(span) ? Math.max(0, Math.min(180, Math.trunc(span))) : PUBLISH_JITTER_MINUTES;
  if (!width) return 0;
  return digest(`${date}:${slot}`) % width;
}

// Jour 7 posts once a day at a time that moves across the whole window rather
// than around a slot, and never in the same hour as the day before. Each day's
// hour is derived from the previous day's, starting from a fixed epoch, so the
// dispatcher keeps no state and every tick of a day agrees on the minute,
// which leaves the retry and native-run bookkeeping below unchanged.
export const JOUR7_CONFIG_KEY = 'jour7-config-v1';
const JOUR7_EPOCH = '2026-10-01';
const DAY_MS = 24 * 60 * 60 * 1000;

export function jour7DueMinute(date, from = '09:00', to = '22:00') {
  const start = parseTime(from);
  const hours = Math.floor((parseTime(to) - start) / 60);
  if (hours < 2) throw new Error(`Invalid Jour 7 window: ${from}-${to}`);
  const target = Date.parse(`${date}T00:00:00Z`);
  if (!Number.isFinite(target)) throw new Error(`Invalid Jour 7 date: ${date}`);
  let hour = digest(`jour7:${JOUR7_EPOCH}`) % hours;
  for (let cursor = Date.parse(`${JOUR7_EPOCH}T00:00:00Z`) + DAY_MS; cursor <= target; cursor += DAY_MS) {
    const day = new Date(cursor).toISOString().slice(0, 10);
    hour = (hour + 1 + (digest(`jour7:${day}`) % (hours - 1))) % hours;
  }
  return start + (hour * 60) + (digest(`jour7:${date}:minute`) % 60);
}

export function jour7Operation(config, now) {
  if (config?.enabled !== true) return null;
  const timeZone = config.timeZone || DEFAULT_TIME_ZONE;
  const clock = localClock(now, timeZone);
  const dueMinute = jour7DueMinute(clock.date, config.from, config.to);
  return {
    id: 'jour7-publish',
    workflow: 'jour7-publish.yml',
    dueMinute,
    windowStart: dueMinute,
    windowEnd: 1439,
    eligible: clock.minute >= dueMinute,
    inputs: { schedule_date: clock.date, dry_run: config.dryRun === true ? 'true' : 'false' },
    date: clock.date,
    timeZone,
  };
}

export function schedulerOperations(config, now) {
  const channels = (config?.channels || []).filter((channel) => channel.enabled !== false);
  if (!channels.length) return [];

  const timeZone = config.timeZone || DEFAULT_TIME_ZONE;
  const clock = localClock(now, timeZone);
  const publishMinute = earliestTime(channels, 'publishTime', '18:00');
  const operations = [];
  const softBodyChannels = channels.filter((channel) => channel.game?.id === 'soft-body-slide');
  const twoDimensionalChannels = channels.filter((channel) => channel.game?.id !== 'soft-body-slide');
  const dryRun = Boolean(config.dryRun);

  if (softBodyChannels.length) {
    const dueMinute = earliestTime(softBodyChannels, 'generateTime', '00:07');
    operations.push({
      id: 'soft-body-3d',
      workflow: 'soft-body-artifact.yml',
      dueMinute,
      windowStart: Math.max(0, dueMinute - 5),
      windowEnd: Math.max(dueMinute, publishMinute - 60),
      eligible: clock.minute >= dueMinute + GENERATION_WATCHDOG_GRACE_MINUTES && clock.minute < publishMinute - 60,
      inputs: {
        use_cloud_config: 'true',
        plan_only: dryRun ? 'true' : 'false',
        reuse_run_id: '',
        obstacle: 'peg-grid',
        seed: '910104',
        samples: '64',
        chunk_size: '15',
        title: 'HOW SOFT CAN IT GET?',
      },
    });
  }

  if (twoDimensionalChannels.length) {
    const dueMinute = earliestTime(twoDimensionalChannels, 'generateTime', '00:30');
    operations.push({
      id: 'daily-generate',
      workflow: 'daily-publisher.yml',
      dueMinute,
      windowStart: Math.max(0, dueMinute - 5),
      windowEnd: Math.max(dueMinute, publishMinute - 15),
      eligible: clock.minute >= dueMinute + GENERATION_WATCHDOG_GRACE_MINUTES && clock.minute < publishMinute - 15,
      inputs: { action: 'generate', dry_run: dryRun ? 'true' : 'false', force_youtube: 'false' },
    });
  }

  // A successful early account must not mark a later account's slot complete.
  // Keep the existing default key stable while accounts are added or disabled.
  for (const slot of [...new Set(channels.map((channel) => channel.publishTime || '18:00'))].sort()) {
    // The slot keeps its name so the runner still matches it against the
    // saved publishTime and the retry bookkeeping is untouched. Only the
    // minute the slot becomes due moves, and it moves the same way for every
    // tick of a given day. The workflow's own GitHub cron stays a safety net
    // and ignores the offset, so a day where that cron is punctual publishes
    // at its hour instead; in practice it has been running hours late, which
    // is why this dispatcher exists at all.
    const dueMinute = Math.min(1439, parseTime(slot) + publishJitter(clock.date, slot, config.publishJitterMinutes));
    operations.push({
      id: slot === '18:00' ? 'daily-publish' : `daily-publish-${slot.replace(':', '')}`,
      workflow: 'daily-publisher.yml',
      dueMinute,
      windowStart: dueMinute,
      windowEnd: 1439,
      eligible: clock.minute >= dueMinute,
      inputs: {
        action: 'publish', dry_run: dryRun ? 'true' : 'false', force_youtube: 'false',
        scheduled_publish: 'true', publish_slot: slot, schedule_date: clock.date,
      },
    });
  }

  return operations.map((operation) => ({ ...operation, date: clock.date, timeZone }));
}

function clockInsideWindow(run, operation) {
  if (!run?.created_at) return false;
  const clock = localClock(new Date(run.created_at), operation.timeZone);
  return clock.date === operation.date
    && clock.minute >= operation.windowStart
    && clock.minute <= operation.windowEnd;
}

function nativeRun(runs, operation) {
  return runs
    .filter((run) => run.event === 'schedule' && clockInsideWindow(run, operation))
    .filter((run) => operation.inputs.action !== 'publish' || !run.display_title
      || run.display_title === 'Daily TikTok and YouTube publisher'
      || run.display_title === 'ClipMaker · scheduled publish')
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0] || null;
}

function dispatchedRun(runs, record, operation) {
  if (!record?.dispatchedAt) return null;
  // Current GitHub API returns the actual run ID. Never substitute a nearby
  // manual generation/test run when that known run is not in the response.
  if (record.runId) return runs.find((run) => String(run.id) === String(record.runId)) || null;
  const lower = Date.parse(record.dispatchedAt) - (2 * 60 * 1000);
  const upper = Date.parse(record.dispatchedAt) + (15 * 60 * 1000);
  return runs
    .filter((run) => run.event === 'workflow_dispatch')
    .filter((run) => operation.inputs.action !== 'publish'
      || run.display_title === `ClipMaker · publish ${operation.inputs.publish_slot}`)
    .filter((run) => {
      const created = Date.parse(run.created_at);
      return created >= lower && created <= upper;
    })
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0] || null;
}

function runOutcome(run) {
  if (!run) return 'missing';
  if (run.status !== 'completed') return 'active';
  return run.conclusion === 'success' ? 'success' : 'failed';
}

async function listRuns(env, token, workflow) {
  const path = `/repos/${encodeURIComponent(env.REPOSITORY_OWNER)}/${encodeURIComponent(env.REPOSITORY_NAME)}`
    + `/actions/workflows/${encodeURIComponent(workflow)}/runs?per_page=30&branch=main`;
  const { response, payload } = await env.github(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`GitHub run lookup failed (${response.status}): ${payload?.message || 'unknown error'}`);
  return (payload.workflow_runs || []).filter((run) => !run.head_branch || run.head_branch === 'main');
}

async function dispatch(env, token, operation) {
  const path = `/repos/${encodeURIComponent(env.REPOSITORY_OWNER)}/${encodeURIComponent(env.REPOSITORY_NAME)}`
    + `/actions/workflows/${encodeURIComponent(operation.workflow)}/dispatches`;
  const { response, payload } = await env.github(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: 'main', inputs: operation.inputs }),
  });
  if (!response.ok) throw new Error(`GitHub workflow dispatch failed (${response.status}): ${payload?.message || 'unknown error'}`);
  return payload;
}

export async function runScheduler({ env, token, now = new Date() }) {
  const [config, jour7] = await Promise.all([
    env.CONFIG.get('publisher-config-v1', 'json'),
    env.CONFIG.get(JOUR7_CONFIG_KEY, 'json'),
  ]);
  if (!config) throw new Error('Publisher configuration is missing.');
  const operations = [...schedulerOperations(config, now), jour7Operation(jour7, now)]
    .filter((operation) => operation?.eligible);
  const results = [];

  for (const operation of operations) {
    const recordKey = `scheduler:${operation.date}:${operation.id}`;
    const [record, runs] = await Promise.all([
      env.CONFIG.get(recordKey, 'json'),
      listRuns(env, token, operation.workflow),
    ]);
    const observed = dispatchedRun(runs, record, operation) || nativeRun(runs, operation);
    const outcome = runOutcome(observed);

    if (outcome === 'active' || outcome === 'success') {
      results.push({ operation: operation.id, action: 'skip', reason: outcome, runId: observed.id });
      continue;
    }

    const attempts = Number(record?.attempts || 0);
    const lastDispatch = Date.parse(record?.dispatchedAt || 0);
    const retryReady = !lastDispatch || now.getTime() - lastDispatch >= RETRY_DELAY_MS;
    if (!retryReady || attempts >= MAX_DISPATCH_ATTEMPTS) {
      results.push({ operation: operation.id, action: 'skip', reason: attempts >= MAX_DISPATCH_ATTEMPTS ? 'retry-limit' : 'retry-wait' });
      continue;
    }

    const payload = await dispatch(env, token, operation);
    const nextRecord = {
      operation: operation.id,
      workflow: operation.workflow,
      date: operation.date,
      dispatchedAt: now.toISOString(),
      attempts: attempts + 1,
      runId: payload?.workflow_run_id || payload?.id || null,
    };
    await env.CONFIG.put(recordKey, JSON.stringify(nextRecord), { expirationTtl: RECORD_TTL_SECONDS });
    results.push({ operation: operation.id, action: 'dispatch', attempt: nextRecord.attempts, runId: nextRecord.runId });
  }

  return results;
}

