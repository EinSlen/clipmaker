import crypto from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
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
import { assertNative3dQuality } from './native-3d-quality.mjs';
import { publicationCopy } from './edit-captions.mjs';

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

function newRenderState() {
  return { status: 'pending', attempts: 0, lastAttemptAt: null, completedAt: null,
    error: null, filename: null, raw: null };
}

function matchesRenderPlan(job, plan) {
  return job.seed === plan.seed && isDeepStrictEqual(job.renderRequest, plan.renderRequest)
    && (!job.render?.game || job.render.game === plan.renderRequest.game);
}

function publicationStarted(job) {
  return ['publishing', 'partial', 'published'].includes(job.status)
    || Object.values(job.platforms || {}).some(target => Number(target.attempts) > 0
      || ['publishing', 'published'].includes(target.status) || target.lastAttemptAt || target.completedAt || target.receipt);
}

function selectionChangedError(job) {
  const instruction = publicationStarted(job)
    ? 'An upload has already been attempted; restore the original selection to finish or retry it. The new selection applies to the next day.'
    : 'Generate the newly selected game before publishing; the previous video will not be sent.';
  const error = new Error(`Render selection changed for ${job.id}. ${instruction}`);
  error.code = 'RENDER_SELECTION_CHANGED';
  return error;
}

async function refreshUnpublishedSelection(config, job, plan, channel) {
  if (matchesRenderPlan(job, plan)) return;
  if (publicationStarted(job)) throw selectionChangedError(job);
  const previous = { seed: job.seed, renderRequest: job.renderRequest,
    filename: job.render?.filename || null, replacedAt: new Date().toISOString() };
  await appendEvent(config.stateDir, { type: 'render-selection-changed', jobId: job.id, previous,
    renderRequest: plan.renderRequest });
  Object.assign(job, plan, { status: 'planned', render: newRenderState(),
    previousRenders: [...(job.previousRenders || []), previous],
    platforms: { youtube: newPlatformState(channel.youtube.enabled), tiktok: newPlatformState(channel.tiktok.enabled) } });
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
    render: newRenderState(),
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
    if (job.status === 'published') {
      return { ok: true, skipped: true, reason: 'already-published', jobId: job.id };
    }
    await refreshUnpublishedSelection(config, job, plan, channel);
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
      // Selection may change before the first upload attempt, never during
      // a partial publication. Regeneration retains the same daily key.
      const result = await renderVideo(config, renderPayload(job));
      if (result.game !== job.renderRequest.game) throw new Error('Renderer returned the wrong selected game.');
      if (job.renderRequest.game === 'soft-body-slide') {
        assertNative3dQuality(result.native3d, { seed: job.seed, ...job.renderRequest });
      }
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
        // publicState drops `raw`, and the daily notification is built from the
        // public status, so what the ticket has to report is promoted here.
        story: result.story ? {
          series: result.story.series ?? null,
          episode: result.story.episode ?? null,
          clipsRequested: result.story.clipsRequested ?? null,
          clipsFailed: (result.story.clipsFailed || []).length,
        } : null,
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
  const copy = job.publicationCopy || job.render;
  return uploadYoutube(config, {
    filename: job.render.filename,
    title: copy.youtubeTitle || `${job.render.title || 'Satisfying simulation'} #shorts`,
    description: copy.caption || job.render.title || '',
    tags: copy.tags || [],
    privacy: channel.youtube.privacy,
    confirmPublic: channel.youtube.confirmPublic,
    account: channel.youtube.account,
  }, process.env.CLIPMAKER_UPLOAD_TOKEN || '');
}

async function publishTiktok(config, channel, job) {
  const copy = job.publicationCopy || job.render;
  const caption = [copy.caption || job.render.title || '', ...(copy.tags || [])]
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
    if (!matchesRenderPlan(job, plan)) {
      if (!forced.size && enabled.every(platform => job.platforms[platform]?.status === 'published')) {
        return { ok: true, skipped: true, reason: 'already-published', jobId: job.id };
      }
      throw selectionChangedError(job);
    }
    if ((job.render.game === 'soft-body-slide' || job.renderRequest.game === 'soft-body-slide')
      && (forced.size || enabled.some((platform) => job.platforms[platform].status !== 'published'))) {
      assertNative3dQuality(job.render.raw?.native3d || job.render.raw, { seed: job.seed, ...job.renderRequest });
    }
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
    if (!publicationStarted(job)) {
      // Freeze the same description before the first platform request. A
      // partial retry never changes already accepted copy or drops credits.
      job.publicationCopy = publicationCopy({ style: channel.captionStyle, channelId: channel.id,
        date: job.date, seed: job.seed, raw: job.render.raw?.native3d || job.render.raw });
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

export function validateRenderedManifest(config, manifest) {
  if (!manifest || typeof manifest !== 'object') throw new Error('Invalid rendered job manifest.');
  const date = String(manifest.date || '');
  const channelId = String(manifest.channelId || '');
  const channel = config.channels.find((candidate) => candidate.enabled && candidate.id === channelId);
  if (!channel) throw new Error(`Unknown or disabled rendered channel: ${channelId}`);
  if (channel.game.game !== 'soft-body-slide') throw new Error(`Imported renders are only accepted for 3D channels: ${channelId}`);
  const plan = planForDate(config, channel, date);
  if (Number(manifest.seed) !== plan.seed) throw new Error(`Seed mismatch for imported job ${plan.id}.`);
  const filename = String(manifest.filename || '');
  if (!/^soft-body-[a-z0-9_-]+-\d+\.mp4$/u.test(filename) || !filename.endsWith(`-${plan.seed}.mp4`)) {
    throw new Error('Invalid imported render filename.');
  }
  const render = manifest.render && typeof manifest.render === 'object' ? manifest.render : {};
  assertNative3dQuality(render.raw, { seed: plan.seed, ...plan.renderRequest });
  return { plan, channel, date, filename, render };
}

export async function importRenderedJob(config, manifest, { copyVideo, restorePublishedVideo = false } = {}) {
  const { plan, channel, date, filename, render } = validateRenderedManifest(config, manifest);
  return withStateLock(config.stateDir, async () => {
    const state = pruneState(await loadState(config.stateDir), oldestRetainedDate(config, date));
    const job = ensureJob(state, plan, channel);
    if (job.status === 'published' && !restorePublishedVideo) {
      return { ok: true, skipped: true, reason: 'already-published', jobId: job.id };
    }
    if (publicationStarted(job)) {
      if (!matchesRenderPlan(job, plan)) throw selectionChangedError(job);
      if (restorePublishedVideo && copyVideo) {
        if (job.render?.filename && job.render.filename !== filename) throw selectionChangedError(job);
        await copyVideo();
        return {
          ok: true,
          skipped: true,
          reason: job.status === 'published' ? 'already-published' : 'publication-started',
          restoredVideo: true,
          jobId: job.id,
        };
      }
      return { ok: true, skipped: true, reason: 'publication-started', jobId: job.id };
    }
    // Copy under the same lock as the state check. A re-import may never
    // overwrite a file already uploaded (or possibly accepted) by a platform.
    if (copyVideo) await copyVideo();
    await refreshUnpublishedSelection(config, job, plan, channel);
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

function channelFailure(action, channel, date, error) {
  return { ok: false, action, channel: channel.id, date, error: errorMessage(error) };
}

async function readyToPublish(config, jobId) {
  const job = (await loadState(config.stateDir)).jobs.find((candidate) => candidate.id === jobId);
  return job?.render?.status === 'ready' && Boolean(job.render.filename);
}

export async function generate(config, { date = dateInTimeZone(new Date(), config.timeZone), channelId, dryRun, skipGames = [] } = {}) {
  const results = [];
  for (const channel of selectedChannels(config, channelId, skipGames)) {
    // One account that cannot render never cancels the accounts after it.
    try {
      results.push(await generateChannel(config, channel, date, { dryRun }));
    } catch (error) {
      results.push(channelFailure('generate', channel, date, error));
    }
  }
  return results;
}

export async function publish(config, {
  date = dateInTimeZone(new Date(), config.timeZone),
  channelId,
  dryRun,
  forcePlatforms = [],
  skipGames = [],
} = {}) {
  const results = [];
  const imported = new Set(skipGames);
  for (const channel of selectedChannels(config, channelId)) {
    try {
      // An account enabled after its generation time, or a generation that
      // failed that night, reaches its publication slot with no video at all.
      // Rendering it here is the only way that slot can still publish. A game
      // rendered by its own workflow is imported, never rendered inline.
      if (!(dryRun ?? config.dryRun) && !imported.has(channel.game.game)
        && !(await readyToPublish(config, planForDate(config, channel, date).id))) {
        results.push(await generateChannel(config, channel, date, { dryRun }));
      }
      results.push(await publishChannel(config, channel, date, { dryRun, forcePlatforms }));
    } catch (error) {
      results.push(channelFailure('publish', channel, date, error));
    }
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
        report.push(channelFailure('generate', channel, today, error));
      }
    }
    if (isTimeDue(channel.publishTime, now, config.timeZone)) {
      const dates = (dryRun ?? config.dryRun) ? [today] : await pendingDates(config, channel, today);
      for (const date of dates) {
        try {
          report.push(await publishChannel(config, channel, date, { dryRun }));
        } catch (error) {
          report.push(channelFailure('publish', channel, date, error));
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
      endpoints: channel.enabled ? await doctorEndpoints(config, channel) : {},
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
