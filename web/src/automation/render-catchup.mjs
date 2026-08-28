import { assertTime, dateInTimeZone, isTimeDue } from './time.mjs';

export function isTrustedDailyRender(run, { repository, defaultBranch }) {
  return Boolean(repository && defaultBranch && run
    && Number.isSafeInteger(run.id) && run.id > 0
    && run.status === 'completed' && run.conclusion === 'success'
    && ['schedule', 'workflow_dispatch'].includes(run.event)
    && run.head_repository?.full_name === repository
    && run.head_branch === defaultBranch
    && !run.pull_requests?.length
    && run.name === 'Soft Body 3D artifact'
    && run.path === '.github/workflows/soft-body-artifact.yml');
}

// Artifact names are readiness hints only. The publisher independently checks
// the manifest, seed, date and native physics evidence before any upload.
export function planRenderCatchup({ run, artifacts = [], availableArtifacts = artifacts,
  config, repository, defaultBranch, now = new Date() }) {
  const empty = (reason) => ({ reason, dispatches: [] });
  if (!isTrustedDailyRender(run, { repository, defaultBranch })) return empty('untrusted-render');
  if (config?.dryRun !== false) return empty('dry-run');
  const timeZone = config.timeZone || 'Europe/Paris';
  const date = dateInTimeZone(now, timeZone);
  const started = new Date(run.created_at);
  if (!Number.isFinite(started.getTime()) || started > now
    || dateInTimeZone(started, timeZone) !== date) return empty('expired-render');
  const names = (items) => new Set(items.filter(item => item.expired === false
    && Number(item.size_in_bytes) > 0).map(item => item.name));
  const current = names(artifacts);
  const ready = names(availableArtifacts);
  const channels = (config.channels || []).filter(channel => channel.enabled !== false
    && channel.game?.id === 'soft-body-slide');
  const artifactFor = channel => `soft-body-daily-${date}-${channel.id}`;
  const due = channels.filter(channel => isTimeDue(assertTime(channel.publishTime || '18:00'), now, timeZone));
  const touched = due.some(channel => current.has(artifactFor(channel))
    && (channel.youtube?.enabled === true || channel.tiktok?.enabled === true));
  const slots = [...new Set(due.map(channel => channel.publishTime || '18:00'))];
  // One dispatch avoids GitHub's global concurrency queue replacing a pending
  // slot when several late accounts become ready together. Empty slot means
  // all accounts already due; never changes their persisted configuration.
  const dispatches = touched && due.every(channel => ready.has(artifactFor(channel)))
    ? [{ workflow: 'daily-publisher.yml', ref: defaultBranch, inputs: {
      action: 'publish', dry_run: 'false', force_youtube: 'false',
      scheduled_publish: 'true', publish_slot: slots.length === 1 ? slots[0] : '', schedule_date: date,
    } }] : [];
  return { reason: dispatches.length ? 'ready' : 'nothing-due-and-ready', date, dispatches };
}
