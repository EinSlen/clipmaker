export type LibraryVideo = {
  id: string;
  name: string;
  size: number;
  duration: number;
  width: number;
  height: number;
  createdAt: number;
  // For server-stored uploads (also kept in IndexedDB for offline preview)
  serverPath?: string;
  // Optional thumbnail data URL
  thumb?: string;
};

export type OverlayBlock = {
  id: string;
  text: string;
  /** % of video width [0..100] */
  xPct: number;
  /** % of video height [0..100] */
  yPct: number;
  /** % of video width [0..100] (max width) */
  widthPct: number;
  fontSize: number; // px @ 1080p reference
  color: string;
  align: 'left' | 'center' | 'right';
  fontFamily: 'serif' | 'sans';
  italic?: boolean;
  startMs?: number;
  endMs?: number;
};

export type MusicTrack = {
  id: string;
  title: string;
  artist?: string;
  file: string; // url under /music/
  vibe: string[];
  durationSec?: number;
  credit?: string;
};

export type YoutubeSuggestion = {
  id: string;
  title: string;
  channel: string;
  url: string;
  duration: number;
  views: number;
  thumbnail?: string;
  score: number;
  reason: string;
};

export type TiktokAccount = {
  username: string;
  cookieFile: string;
  lastUsedAt?: number;
};

export type RenderJob = {
  videoFile: string; // server path under /uploads
  overlays: OverlayBlock[];
  music?: { file: string; volume: number };
  duckOriginal?: number; // 0..1, lower the original audio
};
