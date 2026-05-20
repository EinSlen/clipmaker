// Public-Invidious-based YouTube wrapper.
//
// On Render / cloud datacenter IPs, yt-dlp gets blocked by YouTube ("Sign in to confirm
// you're not a bot"). Public Invidious instances proxy and re-expose YouTube data, so they
// work from anywhere. We round-robin a small list and fall back if one is down.

import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';

const DEFAULT_INSTANCES = [
  'https://iv.melmac.space',
  'https://invidious.nerdvpn.de',
  'https://invidious.protokolla.fi',
  'https://invidious.privacyredirect.com',
  'https://yewtu.be'
];

function instances(): string[] {
  const fromEnv = process.env.INVIDIOUS_INSTANCES;
  if (fromEnv) {
    return fromEnv.split(',').map((s) => s.trim()).filter(Boolean);
  }
  return DEFAULT_INSTANCES;
}

async function invFetch(path: string, timeoutMs = 12000): Promise<unknown> {
  let lastErr: unknown = null;
  for (const base of instances()) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      const r = await fetch(base + path, {
        signal: ctrl.signal,
        headers: { 'User-Agent': 'clipmaker/1.0' }
      });
      clearTimeout(t);
      if (r.ok) return await r.json();
      lastErr = `HTTP ${r.status} from ${base}`;
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(`All Invidious instances failed (last: ${String(lastErr).slice(0, 150)})`);
}

export type YtSearchHit = {
  id: string;
  title: string;
  channel: string;
  url: string;
  duration: number;
  views: number;
  thumbnail?: string;
  width?: number;
  height?: number;
};

type InvSearchItem = {
  type?: string;
  videoId?: string;
  title?: string;
  author?: string;
  authorId?: string;
  lengthSeconds?: number;
  viewCount?: number;
  videoThumbnails?: { url: string; width: number; height: number }[];
};

// Official YouTube Data API v3 — works from any IP (including datacenter).
// Free tier: 10000 quota units/day, search costs 100 units → ~100 searches/day.
async function searchYoutubeOfficial(query: string, max: number, apiKey: string): Promise<YtSearchHit[]> {
  const searchUrl = new URL('https://www.googleapis.com/youtube/v3/search');
  searchUrl.searchParams.set('part', 'snippet');
  searchUrl.searchParams.set('type', 'video');
  searchUrl.searchParams.set('q', query);
  searchUrl.searchParams.set('maxResults', String(Math.min(max, 50)));
  searchUrl.searchParams.set('key', apiKey);

  const r = await fetch(searchUrl, { signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error(`yt-data search HTTP ${r.status}`);
  const j = (await r.json()) as { items?: { id: { videoId: string }; snippet: { title: string; channelTitle: string; thumbnails: Record<string, { url: string; width: number }> } }[] };
  const items = j.items || [];
  if (!items.length) return [];

  // Get durations/views in one batch (videos.list, ~1 quota unit)
  const ids = items.map((it) => it.id.videoId).filter(Boolean);
  const detailsUrl = new URL('https://www.googleapis.com/youtube/v3/videos');
  detailsUrl.searchParams.set('part', 'contentDetails,statistics');
  detailsUrl.searchParams.set('id', ids.join(','));
  detailsUrl.searchParams.set('key', apiKey);
  const dResp = await fetch(detailsUrl, { signal: AbortSignal.timeout(15000) });
  const dJson = (await dResp.json().catch(() => ({}))) as { items?: { id: string; contentDetails?: { duration?: string }; statistics?: { viewCount?: string } }[] };
  const detailsById = new Map<string, { duration: number; views: number }>();
  for (const d of dJson.items || []) {
    detailsById.set(d.id, {
      duration: iso8601ToSeconds(d.contentDetails?.duration || 'PT0S'),
      views: Number(d.statistics?.viewCount || 0)
    });
  }

  return items.slice(0, max).map<YtSearchHit>((it) => {
    const d = detailsById.get(it.id.videoId) || { duration: 0, views: 0 };
    const thumbs = it.snippet.thumbnails || {};
    const pickThumb = thumbs.high?.url || thumbs.medium?.url || thumbs.default?.url;
    return {
      id: it.id.videoId,
      title: it.snippet.title,
      channel: it.snippet.channelTitle,
      url: `https://www.youtube.com/watch?v=${it.id.videoId}`,
      duration: d.duration,
      views: d.views,
      thumbnail: pickThumb
    };
  });
}

function iso8601ToSeconds(iso: string): number {
  const m = iso.match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!m) return 0;
  return (Number(m[1] || 0) * 3600) + (Number(m[2] || 0) * 60) + Number(m[3] || 0);
}

export async function searchYoutube(query: string, max: number): Promise<YtSearchHit[]> {
  // Prefer the official API if the user provided a key (works from any IP).
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (apiKey) {
    try {
      return await searchYoutubeOfficial(query, max, apiKey);
    } catch (e) {
      console.warn('[youtube-api] official search failed, falling back to Invidious:', String(e).slice(0, 150));
    }
  }
  // Fallback: round-robin Invidious instances (may be blocked on datacenter IPs).
  const url = `/api/v1/search?q=${encodeURIComponent(query)}&type=video`;
  const data = (await invFetch(url)) as InvSearchItem[];
  return (Array.isArray(data) ? data : [])
    .filter((it) => it.type === 'video' && it.videoId)
    .slice(0, max)
    .map<YtSearchHit>((it) => ({
      id: it.videoId!,
      title: it.title || '',
      channel: it.author || '',
      url: `https://www.youtube.com/watch?v=${it.videoId}`,
      duration: it.lengthSeconds || 0,
      views: it.viewCount || 0,
      thumbnail: it.videoThumbnails?.find((t) => t.width >= 320)?.url || it.videoThumbnails?.[0]?.url
    }));
}

type AdaptiveFormat = {
  url?: string;
  itag?: string;
  type?: string;
  bitrate?: number | string;
  container?: string;
  encoding?: string;
  audioChannels?: number;
  resolution?: string;
};

type FormatStream = AdaptiveFormat;

type InvVideoMeta = {
  videoId?: string;
  title?: string;
  lengthSeconds?: number;
  adaptiveFormats?: AdaptiveFormat[];
  formatStreams?: FormatStream[];
};

async function videoMeta(videoId: string): Promise<InvVideoMeta> {
  const url = `/api/v1/videos/${encodeURIComponent(videoId)}`;
  return (await invFetch(url, 20000)) as InvVideoMeta;
}

function bestAudio(meta: InvVideoMeta): AdaptiveFormat | null {
  const audios = (meta.adaptiveFormats || []).filter((f) => (f.type || '').startsWith('audio/'));
  if (!audios.length) return null;
  audios.sort((a, b) => Number(b.bitrate || 0) - Number(a.bitrate || 0));
  return audios[0];
}

function bestVideo(meta: InvVideoMeta): AdaptiveFormat | null {
  const vids = (meta.adaptiveFormats || []).filter((f) => (f.type || '').startsWith('video/'));
  if (!vids.length) return null;
  // Prefer 1080p or lower mp4
  vids.sort((a, b) => {
    const aH = Number((a.resolution || '0p').replace('p', '')) || 0;
    const bH = Number((b.resolution || '0p').replace('p', '')) || 0;
    // Penalize anything above 1080
    const aScore = aH > 1080 ? aH - 10000 : aH;
    const bScore = bH > 1080 ? bH - 10000 : bH;
    return bScore - aScore;
  });
  return vids[0];
}

async function downloadToFile(url: string, outPath: string): Promise<boolean> {
  try {
    const r = await fetch(url, { headers: { 'User-Agent': 'clipmaker/1.0' } });
    if (!r.ok) return false;
    const buf = Buffer.from(await r.arrayBuffer());
    await fs.writeFile(outPath, buf);
    return true;
  } catch {
    return false;
  }
}

async function ffmpegMux(args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    const proc = spawn('ffmpeg', args, { windowsHide: true });
    let stderr = '';
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => {
      if (code !== 0) console.warn('[ffmpeg]', stderr.slice(-300));
      resolve(code === 0);
    });
    proc.on('error', () => resolve(false));
  });
}

/** Downloads the best audio stream as mp3 (transcode via ffmpeg). */
export async function downloadAudioMp3(videoId: string, outMp3: string): Promise<boolean> {
  const meta = await videoMeta(videoId);
  const audio = bestAudio(meta);
  if (!audio?.url) return false;
  // Temp file for raw audio (likely m4a or webm/opus)
  const ext = audio.container || (audio.type?.includes('webm') ? 'webm' : 'm4a');
  const tmp = outMp3 + '.src.' + ext;
  const got = await downloadToFile(audio.url, tmp);
  if (!got) return false;
  const ok = await ffmpegMux([
    '-y', '-i', tmp,
    '-vn', '-c:a', 'libmp3lame', '-b:a', '192k',
    outMp3
  ]);
  await fs.unlink(tmp).catch(() => {});
  return ok;
}

/** Downloads best video+audio and muxes to mp4. */
export async function downloadVideoMp4(videoId: string, outMp4: string): Promise<boolean> {
  const meta = await videoMeta(videoId);
  const audio = bestAudio(meta);
  const video = bestVideo(meta);
  if (!audio?.url || !video?.url) return false;

  const aTmp = outMp4 + '.audio.src';
  const vTmp = outMp4 + '.video.src';
  const [aOk, vOk] = await Promise.all([
    downloadToFile(audio.url, aTmp),
    downloadToFile(video.url, vTmp)
  ]);
  if (!aOk || !vOk) {
    await fs.unlink(aTmp).catch(() => {});
    await fs.unlink(vTmp).catch(() => {});
    return false;
  }
  const ok = await ffmpegMux([
    '-y', '-i', vTmp, '-i', aTmp,
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
    '-movflags', '+faststart',
    outMp4
  ]);
  await fs.unlink(aTmp).catch(() => {});
  await fs.unlink(vTmp).catch(() => {});
  return ok;
}
