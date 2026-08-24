import crypto from 'node:crypto';
import {
  appendEvent,
  errorMessage,
  loadState,
  pruneState,
  publicState,
  saveState,
  withStateLock,
} from './state.mjs';
import { doctorEndpoints, renderVideo, uploadTiktok, uploadYoutube } from './api-client.mjs';
import { addDays, dateInTimeZone, isTimeDue } from './time.mjs';

function deterministicSeed(date, channelId, namespace) {
  const digest = crypto.createHash('sha256').update(`${namespace}:${channelId}:${date}`).digest();
  return (digest.readUInt32BE(0) & 0x7fffffff) || 1;
}

export function planForDate(config, channel, date) {
  return {
    id: `${date}:${channel.id}`,
    date,
    channelId: channel.id,
    seed: deterministicSeed(date, channel.id, config.seedNamespace),
    renderRequest: { ...channel.game },
  };
}

function newPlatformState(enabled) {
  return {
    enabled,
    status: enabled ? 'pending' : 'disabled',
    attempts: 0,
    lastAttemptAt: null,
    completedAt: null,
    error: null,
    receipt: null,
    raw: null,
  };
}

function safePlatformReceipt(platform, result) {
  const upload = result?.upload && typeof result.upload === 'object' ? result.upload : {};
  const id = String(upload.platformPostId || upload.id || '').trim();
  const releaseUrl = String(upload.releaseUrl || '').trim();
  const privacy = String(upload.raw?.privacy || result?.privacy || '').trim();
  const provider = String(upload.provider || '').trim();
  return {
    platform,
    ...(id ? { id } : {}),
    ...(releaseUrl ? { releaseUrl } : {}),
    ...(privacy ? { privacy } : {}),
    ...(provider ? { provider } : {}),
    recordedAt: new Date().toISOString(),
  };
}

function ensureJob(state, plan, channel) {
  let job = state.jobs.find((candidate) => candidate.id === plan.id);
  if (job) return job;
  job = {
    ...plan,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: 'planned',
    render: {
      status: 'pending',
      attempts: 0,
      lastAttemptAt: null,
      completedAt: null,
      error: null,
      filename: null,
      raw: null,
    },
    platforms: {
      youtube: newPlatformState(channel.youtube.enabled),
      tiktok: newPlatformState(channel.tiktok.enabled),
    },
  };
  state.jobs.push(job);
  return job;
}

function touch(job) {
  job.updatedAt = new Date().toISOString();
}

function oldestRetainedDate(config, date) {
  return addDays(date, -config.retentionDays);
}

function renderPayload(plan) {
  return {
    ...plan.renderRequest,
    seed: plan.seed,
  };
}

export async function generateChannel(config, channel, date, options = {}) {
  const dryRun = options.dryRun ?? config.dryRun;
  const plan = planForDate(config, channel, date);
  if (dryRun) {
    return { ok: true, dryRun: true, action: 'generate', channel: channel.id, plan };
  }
  return withStateLock(config.stateDir, async () => {
    const state = pruneState(await loadState(config.stateDir), oldestRetainedDate(config, date));
    const job = ensureJob(state, plan, channel);
    if (job.render.status === 'ready') {
      return { ok: true, skipped: true, reason: 'already-rendered', job: publicState({ ...state, jobs: [job] }).jobs[0] };
    }
    job.status = 'rendering';
    job.render.status = 'rendering';
    job.render.attempts += 1;
    job.render.lastAttemptAt = new Date().toISOString();
    job.render.error = null;
    touch(job);
    await saveState(config.stateDir, state);
    await appendEvent(config.stateDir, { type: 'render-started', jobId: job.id, attempt: job.render.attempts });
    try {
      // Once a job exists, its seed and render request are immutable. This
      // prevents a config edit after a failed attempt from changing the video
      // attached to the same daily idempotency key.
      const result = await renderVideo(config, renderPayload(job));
      job.render = {
        ...job.render,
        status: 'ready',
        completedAt: new Date().toISOString(),
        error: null,
        filename: result.filename,
        title: result.title,
        youtubeTitle: result.youtubeTitle,
        caption: result.caption,
        tags: result.tags,
        game: result.game,
        duration: result.duration,
        outcome: result.outcome,
        variantKey: result.variantKey,
        raw: result,
      };
      job.status = 'ready';
      touch(job);
      await saveState(config.stateDir, state);
      await appendEvent(config.stateDir, { type: 'render-ready', jobId: job.id, filename: result.filename });
      return { ok: true, dryRun: false, job: publicState({ ...state, jobs: [job] }).jobs[0] };
    } catch (error) {
      job.render.status = 'failed';
      job.render.error = errorMessage(error);
      job.status = 'failed';
      touch(job);
      await saveState(config.stateDir, state);
      await appendEvent(config.stateDir, { type: 'render-failed', jobId: job.id, error: job.render.error });
      throw error;
    }
  });
}

function enabledPlatformNames(channel) {
  return [
    ...(channel.youtube.enabled ? ['youtube'] : []),
    ...(channel.tiktok.enabled ? ['tiktok'] : []),
  ];
}

async function publishYoutube(config, channel, job) {
  return uploadYoutube(config, {
    filename: job.render.filename,
    title: job.render.youtubeTitle || `${job.render.title || 'Satisfying simulation'} #shorts`,
    description: job.render.caption || job.render.title || '',
    tags: job.render.tags || [],
    privacy: channel.youtube.privacy,
    confirmPublic: channel.youtube.confirmPublic,
    account: channel.youtube.account,
  }, process.env.CLIPMAKER_UPLOAD_TOKEN || '');
}

async function publishTiktok(config, channel, job) {
  const caption = [job.render.caption || job.render.title || '', ...(job.render.tags || [])]
    .filter(Boolean)
    .join(' ')
    .slice(0, 2000);
  return uploadTiktok(config, {
    filename: job.render.filename,
    username: channel.tiktok.username,
    caption,
    visibility: channel.tiktok.visibility,
    confirmPublic: channel.tiktok.confirmPublic,
    ...(channel.tiktok.musicId ? { musicId: channel.tiktok.musicId } : {}),
  }, process.env.CLIPMAKER_UPLOAD_TOKEN || '');
}

export async function publishChannel(config, channel, date, options = {}) {
  const dryRun = options.dryRun ?? config.dryRun;
  const plan = planForDate(config, channel, date);
  if (dryRun) {
    return {
      ok: true,
      dryRun: true,
      action: 'publish',
      channel: channel.id,
      jobId: plan.id,
      targets: enabledPlatformNames(channel),
    };
  }
  return withStateLock(config.stateDir, async () => {
    const state = await loadState(config.stateDir);
    const job = state.jobs.find((candidate) => candidate.id === plan.id);
    if (!job) throw new Error(`No generated job exists for ${plan.id}.`);
    if (job.render?.status !== 'ready' || !job.render.filename) {
      throw new Error(`Job ${plan.id} is not ready for publishing.`);
    }
    const enabled = enabledPlatformNames(channel);
    if (!enabled.length) {
      return { ok: true, skipped: true, reason: 'no-enabled-targets', jobId: job.id };
    }
    const forced = new Set(options.forcePlatforms || []);
    for (const platform of forced) {
      if (!enabled.includes(platform)) {
        throw new Error(`Cannot force disabled platform ${platform} for ${channel.id}.`);
      }
      const target = job.platforms[platform];
      target.status = 'pending';
      target.completedAt = null;
      target.error = null;
      target.receipt = null;
      target.raw = null;
      await appendEvent(config.stateDir, { type: 'publish-forced', jobId: job.id, platform });
    }
    job.status = 'publishing';
    touch(job);
    await saveState(config.stateDir, state);
    const errors = [];
    for (const platform of enabled) {
      const target = job.platforms[platform];
      if (target.status === 'published') continue;
      target.status = 'publishing';
      target.attempts += 1;
      target.lastAttemptAt = new Date().toISOString();
      target.error = null;
      await saveState(config.stateDir, state);
      await appendEvent(config.stateDir, { type: 'publish-started', jobId: job.id, platform, attempt: target.attempts });
      try {
        const result = platform === 'youtube'
          ? await publishYoutube(config, channel, job)
          : await publishTiktok(config, channel, job);
        target.status = 'published';
        target.completedAt = new Date().toISOString();
        target.receipt = safePlatformReceipt(platform, result);
        target.raw = result;
        touch(job);
        // Persist each platform independently before touching the next one so
        // a crash cannot erase a completed YouTube result while TikTok runs.
        await saveState(config.stateDir, state);
        await appendEvent(config.stateDir, { type: 'publish-complete', jobId: job.id, platform });
      } catch (error) {
        target.status = 'failed';
        target.error = errorMessage(error);
        errors.push(`${platform}: ${target.error}`);
        touch(job);
        await saveState(config.stateDir, state);
        await appendEvent(config.stateDir, { type: 'publish-failed', jobId: job.id, platform, error: target.error });
      }
    }
    const statuses = enabled.map((platform) => job.platforms[platform].status);
    job.status = statuses.every((status) => status === 'published')
      ? 'published'
      : statuses.some((status) => status === 'published')
        ? 'partial'
        : 'failed';
    touch(job);
    await saveState(config.stateDir, state);
    if (errors.length) throw new Error(errors.join(' | '));
    return { ok: true, job: publicState({ ...state, jobs: [job] }).jobs[0] };
  });
}

export async function importRenderedJob(config, manifest) {
  if (!manifest || typeof manifest !== 'object') throw new Error('Invalid rendered job manifest.');
  const date = String(manifest.date || '');
  const channelId = String(manifest.channelId || '');
  const channel = config.channels.find((candidate) => candidate.enabled && candidate.id === channelId);
  if (!channel) throw new Error(`Unknown or disabled rendered channel: ${channelId}`);
  if (channel.game.game !== 'soft-body-slide') throw new Error(`Imported renders are only accepted for 3D channels: ${channelId}`);
  const plan = planForDate(config, channel, date);
  if (Number(manifest.seed) !== plan.seed) throw new Error(`Seed mismatch for imported job ${plan.id}.`);
  const filename = String(manifest.filename || '');
  if (!/^soft-body-[a-z0-9_-]+-\d+\.mp4$/u.test(filename)) throw new Error('Invalid imported render filename.');
  return withStateLock(config.stateDir, async () => {
    const state = pruneState(await loadState(config.stateDir), oldestRetainedDate(config, date));
    const job = ensureJob(state, plan, channel);
    if (job.status === 'published') return { ok: true, skipped: true, reason: 'already-published', jobId: job.id };
    const render = manifest.render && typeof manifest.render === 'object' ? manifest.render : {};
    job.render = {
      ...job.render,
      status: 'ready',
      completedAt: new Date().toISOString(),
      error: null,
      filename,
      title: String(render.title || channel.game.title || 'HOW SOFT CAN IT GET?'),
      youtubeTitle: String(render.youtubeTitle || `${render.title || channel.game.title || 'HOW SOFT CAN IT GET?'} #shorts`),
      caption: String(render.caption || '0% to 100% soft body comparison. Did you predict the ending?'),
      tags: Array.isArray(render.tags) ? render.tags.map(String).slice(0, 12) : ['#softbody', '#satisfying', '#shorts'],
      game: 'soft-body-slide',
      duration: Number(render.duration || 30),
      outcome: String(render.outcome || 'comparison-complete'),
      variantKey: String(render.variantKey || channel.game.obstacle || 'auto'),
      raw: render.raw && typeof render.raw === 'object' ? render.raw : render,
    };
    job.status = 'ready';
    touch(job);
    await saveState(config.stateDir, state);
    await appendEvent(config.stateDir, { type: 'render-imported', jobId: job.id, filename });
    return { ok: true, job: publicState({ ...state, jobs: [job] }).jobs[0] };
  });
}

function selectedChannels(config, channelId, skipGames = []) {
  const skipped = new Set(skipGames);
  const channels = config.channels.filter((channel) => channel.enabled
    && (!channelId || channel.id === channelId)
    && !skipped.has(channel.game.game));
  if (channelId && !channels.length) throw new Error(`Unknown or disabled channel: ${channelId}`);
  return channels;
}

export async function generate(config, { date = dateInTimeZone(new Date(), config.timeZone), channelId, dryRun, skipGames = [] } = {}) {
  const results = [];
  for (const channel of selectedChannels(config, channelId, skipGames)) {
    results.push(await generateChannel(config, channel, date, { dryRun }));
  }
  return results;
}

export async function publish(config, {
  date = dateInTimeZone(new Date(), config.timeZone),
  channelId,
  dryRun,
  forcePlatforms = [],
} = {}) {
  const results = [];
  for (const channel of selectedChannels(config, channelId)) {
    results.push(await publishChannel(config, channel, date, { dryRun, forcePlatforms }));
  }
  return results;
}

async function pendingDates(config, channel, today) {
  const state = await loadState(config.stateDir);
  const minimum = addDays(today, -config.catchupDays);
  return state.jobs
    .filter((job) => job.channelId === channel.id && job.date >= minimum && job.date <= today)
    .filter((job) => job.render?.status === 'ready' && job.status !== 'published')
    .map((job) => job.date)
    .sort();
}

export async function runDue(config, { now = new Date(), channelId, dryRun } = {}) {
  const today = dateInTimeZone(now, config.timeZone);
  const report = [];
  for (const channel of selectedChannels(config, channelId)) {
    if (isTimeDue(channel.generateTime, now, config.timeZone)) {
      try {
        report.push(await generateChannel(config, channel, today, { dryRun }));
      } catch (error) {
        report.push({ ok: false, action: 'generate', channel: channel.id, error: errorMessage(error) });
      }
    }
    if (isTimeDue(channel.publishTime, now, config.timeZone)) {
      const dates = (dryRun ?? config.dryRun) ? [today] : await pendingDates(config, channel, today);
      for (const date of dates) {
        try {
          report.push(await publishChannel(config, channel, date, { dryRun }));
        } catch (error) {
          report.push({ ok: false, action: 'publish', channel: channel.id, date, error: errorMessage(error) });
        }
      }
    }
  }
  return report;
}

export async function status(config) {
  return publicState(await loadState(config.stateDir));
}

export async function doctor(config) {
  const channels = [];
  for (const channel of config.channels) {
    channels.push({
      id: channel.id,
      enabled: channel.enabled,
      game: channel.game.game,
      targets: {
        youtube: channel.youtube.enabled,
        tiktok: channel.tiktok.enabled,
      },
      endpoints: await doctorEndpoints(config, channel),
    });
  }
  return {
    ok: channels.every((channel) => (
      !channel.enabled || (
        channel.endpoints.app?.ok !== false
        && channel.endpoints.youtube?.ok !== false
        && channel.endpoints.tiktok?.ok !== false
      )
    )),
    dryRun: config.dryRun,
    baseUrl: config.baseUrl,
    stateDir: config.stateDir,
    uploadTokenConfigured: Boolean(process.env.CLIPMAKER_UPLOAD_TOKEN),
    youtubePublicAllowed: process.env.YOUTUBE_ALLOW_PUBLIC_UPLOAD === 'true',
    channels,
  };
}
