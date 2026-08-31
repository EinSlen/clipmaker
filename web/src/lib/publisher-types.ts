import type { GameId } from "@/lib/game-catalog";

export type PublisherGameConfig = {
  id: GameId;
  difficulty: number;
  duration: number;
  theme: "neon" | "sunset" | "ice";
  soundPack: "auto" | "meme" | "funny" | "arcade" | "impact" | "asmr";
  musicMode: "hit-reveal" | "continuous";
  musicProfile?: "edit-auto" | "edit-sad" | "edit-revenge" | "auto" | "revenge" | "sad-english" | "original";
  musicVolume: number;
  title: string;
  obstacle?: string;
};

export type PublisherChannelConfig = {
  id: string;
  enabled: boolean;
  generateTime: string;
  publishTime: string;
  game: PublisherGameConfig;
  youtube: {
    enabled: boolean;
    account: string;
    privacy: "private" | "unlisted" | "public";
    confirmPublic: boolean;
  };
  tiktok: {
    enabled: boolean;
    username: string | null;
    musicId: string | null;
    visibility: "private" | "public";
    confirmPublic: boolean;
  };
};

export type PublisherConfigDocument = {
  version: 1;
  dryRun: boolean;
  timeZone: string;
  pollSeconds: number;
  catchupDays: number;
  retentionDays: number;
  channels: PublisherChannelConfig[];
};

export type PublisherJobSummary = {
  id: string;
  date: string;
  channelId: string;
  status: string;
  updatedAt: string | null;
  filename: string | null;
  outcome: string | null;
  youtube: string;
  tiktok: string;
};

export type PublisherRuntimeStatus = {
  configured: boolean;
  daemon: {
    active: boolean;
    state: string;
    lastSeenAt: string | null;
  };
  jobs: PublisherJobSummary[];
};
