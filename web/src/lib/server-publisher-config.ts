import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import type {
  PublisherChannelConfig,
  PublisherConfigDocument,
} from "@/lib/publisher-types";
import { GAME_IDS, type GameId } from "@/lib/game-catalog";

const LIMITS: Record<GameId, { difficulty: [number, number]; duration: [number, number] }> = {
  "ball-escape": { difficulty: [10, 20], duration: [15, 60] },
  "shape-tunnel": { difficulty: [30, 300], duration: [15, 60] },
  "laser-dodge": { difficulty: [16, 38], duration: [15, 60] },
  "boss-battle": { difficulty: [100, 500], duration: [15, 60] },
  "soft-body-slide": { difficulty: [40, 100], duration: [30, 30] },
};

const THEMES = new Set(["neon", "sunset", "ice"]);
const SOUND_PACKS = new Set(["auto", "meme", "funny", "arcade", "impact", "asmr"]);
const MUSIC_MODES = new Set(["hit-reveal", "continuous"]);
const MUSIC_PROFILES = new Set(["edit-auto", "edit-sad", "edit-revenge", "auto", "revenge", "sad-english", "original"]);
const OBSTACLES = new Set([
  "auto",
  "moving-slide",
  "stair-cascade",
  "v-stairs",
  "pipe-bend",
  "peg-grid",
  "twin-gears",
  "compression-ring",
]);

export function publisherConfigPath(): string {
  const webRoot = process.env.REPO_ROOT
    ? path.join(path.resolve(process.env.REPO_ROOT), "web")
    : process.cwd();
  return path.join(webRoot, "config", "publisher.json");
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} invalide.`);
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string, max = 100): string {
  const result = String(value ?? "").trim();
  if (!result) throw new Error(`${label} est obligatoire.`);
  return result.slice(0, max);
}

function number(value: unknown, label: string, min: number, max: number): number {
  const result = Number(value);
  if (!Number.isFinite(result) || result < min || result > max) {
    throw new Error(`${label} doit être compris entre ${min} et ${max}.`);
  }
  return result;
}

function time(value: unknown, label: string): string {
  const result = String(value ?? "");
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result)) throw new Error(`${label} invalide.`);
  return result;
}

function normalizeChannel(value: unknown, index: number): PublisherChannelConfig {
  const raw = object(value, `Canal ${index + 1}`);
  const id = text(raw.id, `Identifiant du canal ${index + 1}`, 32);
  if (!/^[a-z0-9][a-z0-9_-]{1,31}$/.test(id)) throw new Error(`Identifiant de canal invalide : ${id}.`);
  const gameRaw = object(raw.game, `Jeu du canal ${id}`);
  const gameId = text(gameRaw.id, `Jeu du canal ${id}`) as GameId;
  if (!(GAME_IDS as readonly string[]).includes(gameId)) throw new Error(`Jeu inconnu : ${gameId}.`);
  const limits = LIMITS[gameId];
  const theme = text(gameRaw.theme ?? "neon", "Ambiance") as PublisherChannelConfig["game"]["theme"];
  const soundPack = text(gameRaw.soundPack ?? "auto", "Pack sonore") as PublisherChannelConfig["game"]["soundPack"];
  const musicMode = text(gameRaw.musicMode ?? "hit-reveal", "Mode musical") as PublisherChannelConfig["game"]["musicMode"];
  if (!THEMES.has(theme)) throw new Error(`Ambiance invalide : ${theme}.`);
  if (!SOUND_PACKS.has(soundPack)) throw new Error(`Pack sonore invalide : ${soundPack}.`);
  if (!MUSIC_MODES.has(musicMode)) throw new Error(`Mode musical invalide : ${musicMode}.`);
  const musicProfile = gameRaw.musicProfile as PublisherChannelConfig["game"]["musicProfile"];
  if (musicProfile !== undefined && !MUSIC_PROFILES.has(musicProfile)) throw new Error("Playlist vocale invalide.");
  if (musicProfile?.startsWith("edit-") && (gameId !== "soft-body-slide" || Number(gameRaw.musicVolume ?? .55) <= 0)) throw new Error("Les voix d’edit nécessitent Souplesse 3D et un volume supérieur à zéro.");
  const obstacle = gameRaw.obstacle === undefined ? undefined : text(gameRaw.obstacle, "Obstacle");
  if (obstacle && !OBSTACLES.has(obstacle)) throw new Error(`Obstacle invalide : ${obstacle}.`);

  const youtubeRaw = object(raw.youtube ?? {}, `YouTube du canal ${id}`);
  const youtubePrivacy = text(youtubeRaw.privacy ?? "private", "Visibilité YouTube") as PublisherChannelConfig["youtube"]["privacy"];
  if (!["private", "unlisted", "public"].includes(youtubePrivacy)) throw new Error("Visibilité YouTube invalide.");
  const youtubeEnabled = Boolean(youtubeRaw.enabled);
  const youtubeConfirmPublic = Boolean(youtubeRaw.confirmPublic);
  if (youtubeEnabled && youtubePrivacy === "public" && !youtubeConfirmPublic) {
    throw new Error(`Confirme explicitement la publication YouTube publique pour ${id}.`);
  }

  const tiktokRaw = object(raw.tiktok ?? {}, `TikTok du canal ${id}`);
  const username = String(tiktokRaw.username ?? "").trim() || null;
  const tiktokEnabled = Boolean(tiktokRaw.enabled);
  if (username && !/^[A-Za-z0-9._]{2,32}$/.test(username)) throw new Error(`Compte TikTok invalide : ${username}.`);
  if (tiktokEnabled && !username) throw new Error(`Choisis un compte TikTok pour ${id}.`);
  const visibility = text(tiktokRaw.visibility ?? "private", "Visibilité TikTok") as "private" | "public";
  if (!["private", "public"].includes(visibility)) throw new Error("Visibilité TikTok invalide.");
  const tiktokConfirmPublic = Boolean(tiktokRaw.confirmPublic);
  if (tiktokEnabled && visibility === "public" && !tiktokConfirmPublic) {
    throw new Error(`Confirme explicitement la publication TikTok publique pour ${id}.`);
  }

  return {
    id,
    enabled: raw.enabled !== false,
    generateTime: time(raw.generateTime ?? "00:30", "Heure de génération"),
    publishTime: time(raw.publishTime ?? "18:30", "Heure de publication"),
    game: {
      id: gameId,
      difficulty: number(gameRaw.difficulty ?? limits.difficulty[0], "Difficulté", ...limits.difficulty),
      duration: number(gameRaw.duration ?? limits.duration[0], "Durée", ...limits.duration),
      theme,
      soundPack,
      musicMode,
      ...(musicProfile !== undefined ? { musicProfile } : {}),
      musicVolume: number(gameRaw.musicVolume ?? 0.55, "Volume musical", 0, 1),
      title: text(gameRaw.title, "Accroche en anglais", 52),
      ...(obstacle ? { obstacle } : {}),
    },
    youtube: {
      enabled: youtubeEnabled,
      account: text(youtubeRaw.account ?? "default", "Compte YouTube", 32),
      privacy: youtubePrivacy,
      confirmPublic: youtubeConfirmPublic,
    },
    tiktok: {
      enabled: tiktokEnabled,
      username,
      musicId: String(tiktokRaw.musicId ?? "").trim() || null,
      visibility,
      confirmPublic: tiktokConfirmPublic,
    },
  };
}

export function normalizePublisherConfig(value: unknown): PublisherConfigDocument {
  const raw = object(value, "Configuration");
  const channels = Array.isArray(raw.channels) ? raw.channels.map(normalizeChannel) : [];
  if (!channels.length) throw new Error("Ajoute au moins un canal.");
  const ids = new Set<string>();
  const youtubeAccounts = new Set<string>();
  const tiktokAccounts = new Set<string>();
  for (const channel of channels) {
    if (ids.has(channel.id)) throw new Error(`Identifiant en double : ${channel.id}.`);
    ids.add(channel.id);
    if (!channel.enabled) continue;
    if (channel.youtube.enabled) {
      const account = channel.youtube.account.toLowerCase();
      if (youtubeAccounts.has(account)) throw new Error(`Le compte YouTube ${channel.youtube.account} est déjà affecté.`);
      youtubeAccounts.add(account);
    }
    if (channel.tiktok.enabled && channel.tiktok.username) {
      const account = channel.tiktok.username.toLowerCase();
      if (tiktokAccounts.has(account)) throw new Error(`Le compte TikTok @${channel.tiktok.username} est déjà affecté.`);
      tiktokAccounts.add(account);
    }
  }
  return {
    version: 1,
    dryRun: raw.dryRun !== false,
    timeZone: text(raw.timeZone ?? "Europe/Paris", "Fuseau horaire", 80),
    pollSeconds: Math.round(number(raw.pollSeconds ?? 300, "Fréquence", 60, 3600)),
    catchupDays: Math.round(number(raw.catchupDays ?? 2, "Rattrapage", 0, 14)),
    retentionDays: Math.round(number(raw.retentionDays ?? 120, "Conservation", 7, 730)),
    channels,
  };
}

export async function readPublisherDocument(): Promise<{ raw: Record<string, unknown>; config: PublisherConfigDocument }> {
  const raw = JSON.parse(await fs.readFile(publisherConfigPath(), "utf8")) as Record<string, unknown>;
  return { raw, config: normalizePublisherConfig(raw) };
}

export async function writePublisherDocument(value: unknown): Promise<PublisherConfigDocument> {
  const config = normalizePublisherConfig(value);
  const file = publisherConfigPath();
  const existing = await fs.readFile(file, "utf8").then(JSON.parse).catch(() => ({})) as Record<string, unknown>;
  const persisted = {
    ...existing,
    ...config,
    version: 1,
    baseUrl: existing.baseUrl ?? "http://127.0.0.1:3000",
    requestTimeoutMinutes: existing.requestTimeoutMinutes ?? 1440,
    seedNamespace: existing.seedNamespace ?? "clipmaker-daily-v1",
    stateDir: existing.stateDir ?? "../data/publisher",
  };
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(persisted, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(temporary, file).catch(async () => {
    await fs.copyFile(temporary, file);
    await fs.rm(temporary, { force: true });
  });
  return config;
}

export function hasPublisherWriteAccess(request: Request): boolean {
  const expected = process.env.CLIPMAKER_UPLOAD_TOKEN || "";
  const supplied = request.headers.get("x-clipmaker-upload-token") || "";
  if (expected && supplied) {
    const left = Buffer.from(expected);
    const right = Buffer.from(supplied);
    if (left.length === right.length && crypto.timingSafeEqual(left, right)) return true;
  }
  const hostname = new URL(request.url).hostname.toLowerCase();
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

export function publisherStateDir(raw: Record<string, unknown>): string {
  const configFile = publisherConfigPath();
  return path.resolve(path.dirname(configFile), String(raw.stateDir || "../data/publisher"));
}
