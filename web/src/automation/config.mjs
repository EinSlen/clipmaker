import fs from 'node:fs/promises';
import path from 'node:path';
import { assertTime } from './time.mjs';

export const GAME_IDS = Object.freeze([
  'ball-escape',
  'shape-tunnel',
  'laser-dodge',
  'boss-battle',
  'soft-body-slide',
]);

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
const PRIVACY = new Set(['private', 'unlisted', 'public']);
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

function requiredString(value, label) {
  const result = String(value ?? '').trim();
  if (!result) throw new Error(`${label} is required.`);
  return result;
}

function optionalString(value) {
  const result = String(value ?? '').trim();
  return result || null;
}

function booleanFromEnv(value, fallback) {
  if (value === undefined) return fallback;
  if (/^(1|true|yes|on)$/i.test(value)) return true;
  if (/^(0|false|no|off)$/i.test(value)) return false;
  throw new Error(`Invalid boolean environment value: ${value}`);
}

function finiteNumber(value, fallback, min, max, label) {
  const parsed = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
    throw new Error(`${label} must be between ${min} and ${max}.`);
  }
  return parsed;
}

function normalizeGameEntry(entry, channelId, source = 'game') {
  if (!entry || typeof entry !== 'object') {
    throw new Error(`channels.${channelId}.${source} must be an object.`);
  }
  const game = requiredString(entry.id ?? entry.game, `channels.${channelId}.${source}.id`);
  if (!GAME_IDS.includes(game)) throw new Error(`Unknown game in ${channelId}: ${game}`);
  const limits = GAME_LIMITS[game];
  const normalized = { game };
  if (entry.difficulty !== undefined) {
    normalized.difficulty = finiteNumber(
      entry.difficulty,
      limits.difficulty[0],
      limits.difficulty[0],
      limits.difficulty[1],
      `${game} difficulty`,
    );
  }
  if (entry.duration !== undefined) {
    normalized.duration = finiteNumber(
      entry.duration,
      limits.duration[0],
      limits.duration[0],
      limits.duration[1],
      `${game} duration`,
    );
  }
  if (entry.theme !== undefined) {
    if (!THEMES.has(entry.theme)) throw new Error(`Invalid theme: ${entry.theme}`);
    normalized.theme = entry.theme;
  }
  if (entry.soundPack !== undefined) {
    if (!SOUND_PACKS.has(entry.soundPack)) throw new Error(`Invalid soundPack: ${entry.soundPack}`);
    normalized.soundPack = entry.soundPack;
  }
  if (entry.musicMode !== undefined) {
    if (!MUSIC_MODES.has(entry.musicMode)) throw new Error(`Invalid musicMode: ${entry.musicMode}`);
    normalized.musicMode = entry.musicMode;
  }
  if (entry.musicVolume !== undefined) normalized.musicVolume = finiteNumber(entry.musicVolume, 0.55, 0, 1, 'musicVolume');
  if (entry.title !== undefined) normalized.title = requiredString(entry.title, 'title').slice(0, 52);
  if (entry.obstacle !== undefined) {
    if (!OBSTACLES.has(entry.obstacle)) throw new Error(`Invalid obstacle: ${entry.obstacle}`);
    normalized.obstacle = entry.obstacle;
  }
  return normalized;
}

function normalizeYoutube(value = {}, channelId) {
  const enabled = Boolean(value.enabled);
  const privacy = value.privacy || 'private';
  if (!PRIVACY.has(privacy)) throw new Error(`Invalid YouTube privacy for ${channelId}.`);
  const confirmPublic = Boolean(value.confirmPublic);
  if (enabled && privacy === 'public' && !confirmPublic) {
    throw new Error(`YouTube public publishing for ${channelId} requires confirmPublic: true.`);
  }
  return {
    enabled,
    account: requiredString(value.account || 'default', `channels.${channelId}.youtube.account`),
    privacy,
    confirmPublic,
  };
}

function normalizeTiktok(value = {}, channelId) {
  const enabled = Boolean(value.enabled);
  const username = optionalString(value.username);
  const visibility = value.visibility || 'private';
  if (!['private', 'public'].includes(visibility)) {
    throw new Error(`Invalid TikTok visibility for ${channelId}.`);
  }
  const confirmPublic = Boolean(value.confirmPublic);
  if (enabled && !username) throw new Error(`TikTok username is required for ${channelId}.`);
  if (enabled && visibility === 'public' && !confirmPublic) {
    throw new Error(`TikTok public publishing for ${channelId} requires confirmPublic: true.`);
  }
  if (username && !/^[A-Za-z0-9._]{2,32}$/.test(username)) {
    throw new Error(`Invalid TikTok username for ${channelId}.`);
  }
  return {
    enabled,
    username,
    musicId: optionalString(value.musicId),
    visibility,
    confirmPublic,
  };
}

function normalizeChannel(value, index) {
  if (!value || typeof value !== 'object') throw new Error(`channels[${index}] must be an object.`);
  const id = requiredString(value.id, `channels[${index}].id`);
  if (!/^[a-z0-9][a-z0-9_-]{1,31}$/.test(id)) throw new Error(`Invalid channel id: ${id}`);
  if (value.game !== undefined && value.rotation !== undefined) {
    throw new Error(`Channel ${id} cannot define both game and rotation.`);
  }
  let gameEntry = value.game;
  let gameSource = 'game';
  if (gameEntry === undefined && value.rotation !== undefined) {
    if (!Array.isArray(value.rotation) || value.rotation.length !== 1) {
      throw new Error(
        `Channel ${id} must have exactly one fixed game. Replace rotation with a single game object.`,
      );
    }
    [gameEntry] = value.rotation;
    gameSource = 'rotation[0]';
  }
  if (typeof gameEntry === 'string') gameEntry = { id: gameEntry };
  if (gameEntry === undefined) throw new Error(`Channel ${id} needs one fixed game.`);
  return {
    id,
    enabled: value.enabled !== false,
    generateTime: assertTime(value.generateTime || '00:30'),
    publishTime: assertTime(value.publishTime || '18:30'),
    game: normalizeGameEntry(gameEntry, id, gameSource),
    youtube: normalizeYoutube(value.youtube, id),
    tiktok: normalizeTiktok(value.tiktok, id),
  };
}

export async function readPublisherConfig(filePath, env = process.env) {
  const absolutePath = path.resolve(filePath);
  const raw = JSON.parse(await fs.readFile(absolutePath, 'utf8'));
  if (!raw || typeof raw !== 'object') throw new Error('Publisher config must be an object.');
  const channels = (Array.isArray(raw.channels) ? raw.channels : []).map(normalizeChannel);
  if (!channels.length) throw new Error('Publisher config needs at least one channel.');
  const ids = new Set();
  const youtubeAccounts = new Map();
  const tiktokAccounts = new Map();
  for (const channel of channels) {
    if (ids.has(channel.id)) throw new Error(`Duplicate channel id: ${channel.id}`);
    ids.add(channel.id);
    if (channel.enabled && channel.youtube.enabled) {
      const account = channel.youtube.account.toLocaleLowerCase('en-US');
      if (youtubeAccounts.has(account)) {
        throw new Error(
          `YouTube account "${channel.youtube.account}" is assigned to both ${youtubeAccounts.get(account)} and ${channel.id}.`,
        );
      }
      youtubeAccounts.set(account, channel.id);
    }
    if (channel.enabled && channel.tiktok.enabled) {
      const account = channel.tiktok.username.toLocaleLowerCase('en-US');
      if (tiktokAccounts.has(account)) {
        throw new Error(
          `TikTok account "${channel.tiktok.username}" is assigned to both ${tiktokAccounts.get(account)} and ${channel.id}.`,
        );
      }
      tiktokAccounts.set(account, channel.id);
    }
  }
  const configDir = path.dirname(absolutePath);
  return {
    version: 1,
    configPath: absolutePath,
    baseUrl: String(env.PUBLISHER_BASE_URL || raw.baseUrl || 'http://127.0.0.1:3000').replace(/\/$/, ''),
    dryRun: booleanFromEnv(env.PUBLISHER_DRY_RUN, raw.dryRun !== false),
    timeZone: requiredString(raw.timeZone || 'Europe/Paris', 'timeZone'),
    pollSeconds: Math.round(finiteNumber(raw.pollSeconds, 300, 60, 3600, 'pollSeconds')),
    catchupDays: Math.round(finiteNumber(raw.catchupDays, 2, 0, 14, 'catchupDays')),
    retentionDays: Math.round(finiteNumber(raw.retentionDays, 120, 7, 730, 'retentionDays')),
    requestTimeoutMinutes: Math.round(finiteNumber(raw.requestTimeoutMinutes, 1440, 5, 2880, 'requestTimeoutMinutes')),
    seedNamespace: requiredString(raw.seedNamespace || 'clipmaker-daily-v1', 'seedNamespace'),
    stateDir: path.resolve(configDir, raw.stateDir || '../data/publisher'),
    channels,
  };
}
