const GAME_LIMITS = Object.freeze({
  'ball-escape': { difficulty: [10, 20], duration: [15, 60] },
  'shape-tunnel': { difficulty: [30, 300], duration: [15, 60] },
  'laser-dodge': { difficulty: [16, 38], duration: [15, 60] },
  'boss-battle': { difficulty: [100, 500], duration: [15, 60] },
  'soft-body-slide': { difficulty: [40, 100], duration: [30, 30] },
});

const THEMES = new Set(['neon', 'sunset', 'ice']);
const SOUND_PACKS = new Set(['auto', 'meme', 'funny', 'arcade', 'impact', 'asmr']);
const MUSIC_MODES = new Set(['hit-reveal', 'continuous']);
const MUSIC_PROFILES = new Set(['auto', 'revenge', 'sad-english', 'original']);
const OBSTACLES = new Set([
  'auto',
  'moving-slide',
  'stair-cascade',
  'v-stairs',
  'pipe-bend',
  'peg-grid',
  'twin-gears',
  'compression-ring',
]);

function fail(message) {
  throw new Error(message);
}

function text(value, label, maximum = 120) {
  const normalized = String(value ?? '').trim();
  if (!normalized) fail(`${label} est requis.`);
  if (normalized.length > maximum) fail(`${label} est trop long.`);
  return normalized;
}

function number(value, label, minimum, maximum) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized) || normalized < minimum || normalized > maximum) {
    fail(`${label} doit être compris entre ${minimum} et ${maximum}.`);
  }
  return normalized;
}

function time(value, label) {
  const normalized = text(value, label, 5);
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/u.test(normalized)) fail(`${label} doit utiliser le format HH:MM.`);
  return normalized;
}

function normalizeGame(value, channelId) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`Le jeu de ${channelId} est invalide.`);
  const id = text(value.id ?? value.game, `Jeu de ${channelId}`, 40);
  const limits = GAME_LIMITS[id];
  if (!limits) fail(`Jeu inconnu pour ${channelId}.`);
  const game = {
    id,
    difficulty: Math.round(number(value.difficulty ?? limits.difficulty[0], 'Difficulté', ...limits.difficulty)),
    duration: Math.round(number(value.duration ?? limits.duration[0], 'Durée', ...limits.duration)),
    theme: THEMES.has(value.theme) ? value.theme : 'neon',
    soundPack: SOUND_PACKS.has(value.soundPack) ? value.soundPack : 'auto',
    musicMode: MUSIC_MODES.has(value.musicMode) ? value.musicMode : (id === 'shape-tunnel' || id === 'soft-body-slide' ? 'continuous' : 'hit-reveal'),
    musicVolume: number(value.musicVolume ?? 0.55, 'Volume', 0, 1),
    title: text(value.title || 'CAN IT ESCAPE?', 'Accroche', 52),
  };
  if (id === 'soft-body-slide') game.obstacle = OBSTACLES.has(value.obstacle) ? value.obstacle : 'auto';
  // Keep legacy plans structurally unchanged until the user chooses a value.
  if (value.musicProfile !== undefined) {
    if (!MUSIC_PROFILES.has(value.musicProfile)) fail('Playlist vocale invalide.');
    game.musicProfile = value.musicProfile;
  }
  return game;
}

function normalizeYoutube(value, channelId) {
  const source = value && typeof value === 'object' ? value : {};
  const privacy = new Set(['private', 'unlisted', 'public']).has(source.privacy) ? source.privacy : 'private';
  const enabled = Boolean(source.enabled);
  const confirmPublic = Boolean(source.confirmPublic);
  if (enabled && privacy === 'public' && !confirmPublic) fail(`La publication YouTube publique de ${channelId} doit être confirmée.`);
  return {
    enabled,
    account: text(source.account || 'default', `Compte YouTube de ${channelId}`, 64),
    privacy,
    confirmPublic,
  };
}

function normalizeTiktok(value, channelId) {
  const source = value && typeof value === 'object' ? value : {};
  const visibility = new Set(['private', 'public']).has(source.visibility) ? source.visibility : 'private';
  const username = String(source.username || '').trim() || null;
  const enabled = Boolean(source.enabled);
  const confirmPublic = Boolean(source.confirmPublic);
  if (username && !/^[A-Za-z0-9._]{2,32}$/u.test(username)) fail(`Compte TikTok invalide pour ${channelId}.`);
  if (enabled && !username) fail(`Choisis un compte TikTok pour ${channelId}.`);
  if (enabled && visibility === 'public' && !confirmPublic) fail(`La publication TikTok publique de ${channelId} doit être confirmée.`);
  return {
    enabled,
    username,
    musicId: String(source.musicId || '').trim() || null,
    visibility,
    confirmPublic,
  };
}

export function normalizePublisherConfig(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) fail('Configuration invalide.');
  if (!Array.isArray(raw.channels) || raw.channels.length < 1 || raw.channels.length > 8) {
    fail('La configuration doit contenir entre 1 et 8 canaux.');
  }
  const ids = new Set();
  const youtubeAccounts = new Set();
  const tiktokAccounts = new Set();
  const channels = raw.channels.map((source, index) => {
    if (!source || typeof source !== 'object' || Array.isArray(source)) fail(`Canal ${index + 1} invalide.`);
    const id = text(source.id, `Identifiant du canal ${index + 1}`, 32).toLowerCase();
    if (!/^[a-z0-9][a-z0-9_-]{1,31}$/u.test(id)) fail(`Identifiant de canal invalide : ${id}.`);
    if (ids.has(id)) fail(`Identifiant utilisé deux fois : ${id}.`);
    ids.add(id);
    const enabled = source.enabled !== false;
    const youtube = normalizeYoutube(source.youtube, id);
    const tiktok = normalizeTiktok(source.tiktok, id);
    if (enabled && !youtube.enabled && !tiktok.enabled) fail(`${id} doit publier sur TikTok ou YouTube.`);
    if (enabled && youtube.enabled) {
      const key = youtube.account.toLowerCase();
      if (youtubeAccounts.has(key)) fail(`Le compte YouTube ${youtube.account} est déjà assigné.`);
      youtubeAccounts.add(key);
    }
    if (enabled && tiktok.enabled) {
      const key = tiktok.username.toLowerCase();
      if (tiktokAccounts.has(key)) fail(`Le compte TikTok @${tiktok.username} est déjà assigné.`);
      tiktokAccounts.add(key);
    }
    return {
      id,
      enabled,
      generateTime: time(source.generateTime || '00:30', `Heure de génération de ${id}`),
      publishTime: time(source.publishTime || '18:00', `Heure de publication de ${id}`),
      game: normalizeGame(source.game, id),
      youtube,
      tiktok,
    };
  });
  return {
    version: 1,
    dryRun: Boolean(raw.dryRun),
    timeZone: text(raw.timeZone || 'Europe/Paris', 'Fuseau horaire', 64),
    pollSeconds: Math.round(number(raw.pollSeconds ?? 300, 'Fréquence', 60, 3600)),
    catchupDays: Math.round(number(raw.catchupDays ?? 2, 'Rattrapage', 0, 14)),
    retentionDays: Math.round(number(raw.retentionDays ?? 120, 'Rétention', 7, 730)),
    requestTimeoutMinutes: Math.round(number(raw.requestTimeoutMinutes ?? 1440, 'Délai de rendu', 5, 2880)),
    seedNamespace: text(raw.seedNamespace || 'clipmaker-daily-v1', 'Espace de seed', 80),
    baseUrl: 'http://127.0.0.1:3000',
    stateDir: '../data/publisher',
    channels,
  };
}

export function publicPublisherConfig(config) {
  const { baseUrl: _baseUrl, stateDir: _stateDir, requestTimeoutMinutes, seedNamespace, ...publicConfig } = config;
  return { ...publicConfig, requestTimeoutMinutes, seedNamespace };
}
