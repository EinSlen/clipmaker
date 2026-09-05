function gameId(channel) {
  return channel?.game?.game || channel?.game?.id || channel?.game || 'unknown-game';
}

function jobGameId(job) {
  return job?.renderRequest?.game || job?.renderRequest?.id || job?.renderRequest || 'unknown-game';
}

function endpointReady(doctorChannel, platform) {
  const endpoint = doctorChannel?.endpoints?.[platform];
  if (!endpoint) return 'non vérifié';
  return endpoint.ok === false ? 'indisponible' : 'prêt';
}

function channelTargets(channel, doctorChannel) {
  const targets = [];
  if (channel.youtube?.enabled) {
    targets.push(`YouTube ${channel.youtube.account} (${channel.youtube.privacy}, ${endpointReady(doctorChannel, 'youtube')})`);
  }
  if (channel.tiktok?.enabled) {
    targets.push(`TikTok @${channel.tiktok.username} (${channel.tiktok.visibility}, ${endpointReady(doctorChannel, 'tiktok')})`);
  }
  return targets.length ? targets.join(' · ') : 'aucune plateforme activée';
}

function platformPublication(platform, target) {
  if (!target || target.enabled === false) return null;
  const receipt = target.receipt;
  const releaseUrl = /^https:\/\/[a-z0-9.-]+(?:\/[^\s)]*)?$/iu.test(receipt?.releaseUrl || '')
    ? receipt.releaseUrl
    : null;
  const proof = receipt?.id
    ? `reçu ${receipt.provider || platform}${receipt.privacy ? `, ${receipt.privacy}` : ''}`
    : 'aucun reçu enregistré';
  return `  - ${platform}: \`${target.status || 'unknown'}\` · ${proof}${releaseUrl ? ` · [ouvrir la vidéo](${releaseUrl})` : ''}`;
}

// The comment driven channel publishes generated clips or nothing, so the daily
// ticket says how many clips carried the episode and names any that are missing.
function storyLine(render) {
  const story = render?.story;
  if (!story || !story.episode) return null;
  const label = `\`${story.series || 'histoire'}\` épisode ${story.episode}`;
  const clips = story.clipsRequested ?? '?';
  if (story.clipsFailed) {
    return `  - ⚠️ ${label} : ${story.clipsFailed} clip(s) manquant(s) sur ${clips}`;
  }
  return `  - ${label} : monté sur ${clips} clip(s) généré(s)`;
}

// A video that was never rendered and an upload that was refused are both
// isolated from the other accounts, so neither one reaches the run status.
function failureReason(job) {
  if (job.render?.error) return String(job.render.error);
  const refused = ['youtube', 'tiktok']
    .filter((platform) => job.platforms?.[platform]?.error)
    .map((platform) => `${platform}: ${job.platforms[platform].error}`);
  return refused.length ? refused.join(' | ') : null;
}

export function buildPublisherSummary({ operation, config, doctor = null, status = null, configurationError = null }) {
  const activeChannels = (config?.channels || []).filter((channel) => channel.enabled !== false);
  const doctorChannels = new Map((doctor?.channels || []).map((channel) => [channel.id, channel]));
  const jobs = Array.isArray(status?.jobs) ? status.jobs : [];
  const latest = jobs.at(-1) || null;
  const health = doctor
    ? (doctor.ok ? 'prêt' : 'attention requise')
    : 'non vérifié';
  const lines = [
    '# Daily publisher',
    '',
    `- Operation: \`${operation || 'unknown'}\``,
    `- Channel: \`${activeChannels.map((channel) => channel.id).join(', ') || '-'}\``,
    `- Health: \`${health}\``,
    `- Time zone: \`${config?.timeZone || 'Europe/Paris'}\``,
  ];

  if (configurationError) lines.push(`- Configuration: \`unavailable (${configurationError})\``);

  for (const channel of activeChannels) {
    lines.push(
      `- Configuration \`${channel.id}\`: \`${gameId(channel)}\` · génération \`${channel.generateTime}\` · publication \`${channel.publishTime}\``,
      `  - Destinations: ${channelTargets(channel, doctorChannels.get(channel.id))}`,
    );
  }

  if (latest) {
    lines.push(
      `- Latest stored job: \`${latest.status || 'unknown'}\` · \`${latest.date || '-'}\` · \`${latest.channelId || '-'}\` · \`${jobGameId(latest)}\``,
    );
    const story = storyLine(latest.render);
    if (story) lines.push(story);
    for (const platform of ['youtube', 'tiktok']) {
      const publication = platformPublication(platform, latest.platforms?.[platform]);
      if (publication) lines.push(publication);
    }
  } else {
    lines.push('- Latest stored job: `none`');
  }

  // A channel that fails is isolated from the others, so its reason never
  // reaches the run status and would otherwise be invisible in the ticket. The
  // most recent failures are named with what actually went wrong.
  const failures = jobs.filter((job) => ['failed', 'partial'].includes(job.status) && failureReason(job)).slice(-3);
  for (const job of failures) {
    lines.push(`- ❌ \`${job.channelId || '-'}\` ${job.date || ''} : ${failureReason(job).replace(/\s+/g, ' ').slice(0, 300)}`);
  }
  return `${lines.join('\n')}\n`;
}
