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
  } else {
    lines.push('- Latest stored job: `none`');
  }
  return `${lines.join('\n')}\n`;
}
