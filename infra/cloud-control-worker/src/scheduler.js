const DEFAULT_TIME_ZONE = 'Europe/Paris';
const GENERATION_WATCHDOG_GRACE_MINUTES = 10;
const RETRY_DELAY_MS = 20 * 60 * 1000;
const MAX_DISPATCH_ATTEMPTS = 3;
const RECORD_TTL_SECONDS = 8 * 24 * 60 * 60;

function parseTime(value) {
  const match = String(value || '').match(/^(\d{2}):(\d{2})$/u);
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

  operations.push({
    id: 'daily-publish',
    workflow: 'daily-publisher.yml',
    dueMinute: publishMinute,
    windowStart: Math.max(0, publishMinute - 5),
    windowEnd: 1439,
    eligible: clock.minute >= publishMinute,
    inputs: { action: 'publish', dry_run: dryRun ? 'true' : 'false', force_youtube: 'false' },
  });

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
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0] || null;
}

function dispatchedRun(runs, record) {
  if (!record?.dispatchedAt) return null;
  const lower = Date.parse(record.dispatchedAt) - (2 * 60 * 1000);
  const upper = Date.parse(record.dispatchedAt) + (15 * 60 * 1000);
  return runs
    .filter((run) => run.event === 'workflow_dispatch')
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
    + `/actions/workflows/${encodeURIComponent(workflow)}/runs?per_page=30`;
  const { response, payload } = await env.github(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`GitHub run lookup failed (${response.status}): ${payload?.message || 'unknown error'}`);
  return payload.workflow_runs || [];
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
  const config = await env.CONFIG.get('publisher-config-v1', 'json');
  if (!config) throw new Error('Publisher configuration is missing.');
  const operations = schedulerOperations(config, now).filter((operation) => operation.eligible);
  const results = [];

  for (const operation of operations) {
    const recordKey = `scheduler:${operation.date}:${operation.id}`;
    const [record, runs] = await Promise.all([
      env.CONFIG.get(recordKey, 'json'),
      listRuns(env, token, operation.workflow),
    ]);
    const observed = dispatchedRun(runs, record) || nativeRun(runs, operation);
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

