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

// Direct InnerTube HTTP call — uses YouTube's own web-client API key, no Data API quota,
// no Google Cloud setup. Lightweight (no big JS lib loaded), so it doesn't blow Render's
// 512 MB free tier. Works from most IPs.
const INNERTUBE_WEB_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8';
const INNERTUBE_CLIENT_VERSION = '2.20250115.00.00';

type IntRun = { text?: string };
type IntRichRuns = { runs?: IntRun[]; simpleText?: string };
type IntThumbnail = { url: string; width?: number; height?: number };
type IntVideoRenderer = {
  videoId?: string;
  title?: IntRichRuns;
  ownerText?: IntRichRuns;
  longBylineText?: IntRichRuns;
  lengthText?: IntRichRuns;
  viewCountText?: IntRichRuns;
  shortViewCountText?: IntRichRuns;
  thumbnail?: { thumbnails?: IntThumbnail[] };
};
type IntItem = { videoRenderer?: IntVideoRenderer; compactVideoRenderer?: IntVideoRenderer };

function runsToText(r?: IntRichRuns): string {
  if (!r) return '';
  if (r.simpleText) return r.simpleText;
  return (r.runs || []).map((x) => x.text || '').join('');
}

function parseDurationText(s: string): number {
  // "1:23" → 83 ; "1:02:03" → 3723
  const parts = s.split(':').map((n) => Number(n) || 0);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] || 0;
}

function parseViewsText(s: string): number {
  return Number(s.replace(/[^\d]/g, '')) || 0;
}

function collectVideoRenderers(node: unknown, out: IntVideoRenderer[]): void {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const x of node) collectVideoRenderers(x, out);
    return;
  }
  const obj = node as Record<string, unknown>;
  if (obj.videoRenderer && typeof obj.videoRenderer === 'object') {
    out.push(obj.videoRenderer as IntVideoRenderer);
  }
  for (const k of Object.keys(obj)) collectVideoRenderers(obj[k], out);
}

async function searchYoutubeInnertube(query: string, max: number): Promise<YtSearchHit[]> {
  const r = await fetch(`https://www.youtube.com/youtubei/v1/search?key=${INNERTUBE_WEB_KEY}`, {
    method: 'POST',
    signal: AbortSignal.timeout(15000),
    headers: {
      'Content-Type': 'application/json',
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
      'X-YouTube-Client-Name': '1',
      'X-YouTube-Client-Version': INNERTUBE_CLIENT_VERSION,
      Origin: 'https://www.youtube.com',
      Referer: 'https://www.youtube.com/'
    },
    body: JSON.stringify({
      context: {
        client: {
          clientName: 'WEB',
          clientVersion: INNERTUBE_CLIENT_VERSION,
          hl: 'fr',
          gl: 'FR',
          utcOffsetMinutes: 60
        }
      },
      query
    })
  });
  if (!r.ok) throw new Error(`innertube HTTP ${r.status}`);
  const j = (await r.json()) as unknown;
  const renderers: IntVideoRenderer[] = [];
  collectVideoRenderers(j, renderers);

  const hits: YtSearchHit[] = [];
  for (const v of renderers) {
    if (!v.videoId) continue;
    const title = runsToText(v.title);
    if (!title) continue;
    const channel = runsToText(v.ownerText) || runsToText(v.longBylineText);
    const duration = parseDurationText(runsToText(v.lengthText));
    const views = parseViewsText(runsToText(v.viewCountText) || runsToText(v.shortViewCountText));
    const thumbs = v.thumbnail?.thumbnails || [];
    const thumb = thumbs.find((t) => (t.width || 0) >= 320)?.url || thumbs[thumbs.length - 1]?.url;
    hits.push({
      id: v.videoId,
      title,
      channel,
      url: `https://www.youtube.com/watch?v=${v.videoId}`,
      duration,
      views,
      thumbnail: thumb
    });
    if (hits.length >= max) break;
  }
  return hits;
}

export async function searchYoutube(query: string, max: number): Promise<YtSearchHit[]> {
  // 1) Try Innertube (no key, no setup, works from most IPs)
  try {
    const r = await searchYoutubeInnertube(query, max);
    if (r.length) return r;
  } catch (e) {
    console.warn('[youtube-api] innertube search failed:', String(e).slice(0, 150));
  }
  // 2) Try the official Data API if the user gave a key
  const apiKey = process.env.YOUTUBE_API_KEY;
  if (apiKey) {
    try {
      return await searchYoutubeOfficial(query, max, apiKey);
    } catch (e) {
      console.warn('[youtube-api] official search failed:', String(e).slice(0, 150));
    }
  }
  // 3) Fallback: round-robin Invidious instances (often blocked on datacenter IPs).
  const url = `/api/v1/search?q=${encodeURIComponent(query)}&type=video`;
  const data = (await invFetch(url).catch(() => [])) as InvSearchItem[];
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

// Innertube /player — ANDROID client renvoie des URLs non cipherées dans la plupart des cas.
type IntFormat = {
  url?: string;
  itag?: number;
  mimeType?: string;
  bitrate?: number;
  width?: number;
  height?: number;
  qualityLabel?: string;
  audioQuality?: string;
  signatureCipher?: string;
};
type IntPlayerResponse = {
  playabilityStatus?: { status?: string; reason?: string };
  videoDetails?: { videoId?: string; title?: string; lengthSeconds?: string };
  streamingData?: {
    formats?: IntFormat[];
    adaptiveFormats?: IntFormat[];
  };
};

type IntClient = {
  name: string;
  key: string;
  clientName: string;
  clientVersion: string;
  ua: string;
  cn: string;
  extra?: Record<string, unknown>;
};

// Plusieurs clients Innertube — YouTube applique différentes restrictions selon
// l'IP source, certains clients passent là où d'autres se font 403.
const INTERTUBE_CLIENTS: IntClient[] = [
  {
    name: 'IOS',
    key: 'AIzaSyB-63vPrdThhKuerbB2N_l7Kwwcxj6yUAc',
    clientName: 'IOS',
    clientVersion: '19.45.4',
    ua: 'com.google.ios.youtube/19.45.4 (iPhone16,2; U; CPU iOS 18_1 like Mac OS X;)',
    cn: '5',
    extra: { deviceMake: 'Apple', deviceModel: 'iPhone16,2', osName: 'iPhone', osVersion: '18.1.0.22B83' }
  },
  {
    name: 'ANDROID',
    key: 'AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w',
    clientName: 'ANDROID',
    clientVersion: '19.09.37',
    ua: 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip',
    cn: '3',
    extra: { androidSdkVersion: 34, osName: 'Android', osVersion: '14' }
  },
  {
    name: 'TVHTML5_EMBED',
    key: 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8',
    clientName: 'TVHTML5_SIMPLY_EMBEDDED_PLAYER',
    clientVersion: '2.0',
    ua: 'Mozilla/5.0 (PlayStation 4 5.55) AppleWebKit/601.2 (KHTML, like Gecko)',
    cn: '85'
  }
];

async function innertubePlayerOne(videoId: string, client: IntClient): Promise<IntPlayerResponse> {
  const r = await fetch(`https://www.youtube.com/youtubei/v1/player?key=${client.key}`, {
    method: 'POST',
    signal: AbortSignal.timeout(15000),
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': client.ua,
      'X-YouTube-Client-Name': client.cn,
      'X-YouTube-Client-Version': client.clientVersion
    },
    body: JSON.stringify({
      context: {
        client: {
          clientName: client.clientName,
          clientVersion: client.clientVersion,
          hl: 'en',
          gl: 'US',
          utcOffsetMinutes: 0,
          ...(client.extra || {})
        }
      },
      videoId,
      contentCheckOk: true,
      racyCheckOk: true
    })
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as IntPlayerResponse;
}

async function innertubePlayer(videoId: string): Promise<IntPlayerResponse> {
  const errors: string[] = [];
  for (const c of INTERTUBE_CLIENTS) {
    try {
      const p = await innertubePlayerOne(videoId, c);
      const sd = p.streamingData;
      if (sd && ((sd.formats?.length ?? 0) + (sd.adaptiveFormats?.length ?? 0)) > 0) {
        return p;
      }
      // Pas de stream → client n'a pas accès (souvent age/region). Essaie le suivant.
      const status = p.playabilityStatus?.status || 'NO_STREAMS';
      errors.push(`${c.name}=${status}`);
    } catch (e) {
      errors.push(`${c.name}=${String((e as Error).message || e).slice(0, 60)}`);
    }
  }
  throw new Error(`innertube all clients failed: ${errors.join(' | ')}`);
}

function intToAdaptive(f: IntFormat): AdaptiveFormat {
  // mimeType ex: 'video/mp4; codecs="avc1.64001F"' ou 'audio/mp4; codecs="mp4a.40.2"'
  const mt = f.mimeType || '';
  const type = mt.split(';')[0] || '';
  const container = mt.startsWith('video/') ? mt.split('/')[1]?.split(';')[0] : mt.split('/')[1]?.split(';')[0];
  return {
    url: f.url,
    itag: String(f.itag ?? ''),
    type,
    bitrate: f.bitrate,
    container,
    resolution: f.qualityLabel
  };
}

async function videoMetaInnertube(videoId: string): Promise<InvVideoMeta> {
  const p = await innertubePlayer(videoId);
  if (p.playabilityStatus?.status && p.playabilityStatus.status !== 'OK') {
    throw new Error(`playability ${p.playabilityStatus.status}: ${p.playabilityStatus.reason || ''}`);
  }
  const sd = p.streamingData || {};
  const formats = (sd.formats || []).filter((f) => f.url).map(intToAdaptive);
  const adaptiveFormats = (sd.adaptiveFormats || []).filter((f) => f.url).map(intToAdaptive);
  return {
    videoId: p.videoDetails?.videoId,
    title: p.videoDetails?.title,
    lengthSeconds: Number(p.videoDetails?.lengthSeconds || 0),
    formatStreams: formats,
    adaptiveFormats: [...adaptiveFormats, ...formats]
  };
}

async function videoMeta(videoId: string): Promise<InvVideoMeta> {
  // 1) Innertube multi-client (rapide, pas de signature cipher)
  let innertubeErr = '';
  try {
    return await videoMetaInnertube(videoId);
  } catch (e) {
    innertubeErr = String((e as Error).message || e).slice(0, 300);
    console.warn('[youtube-api] innertube failed:', innertubeErr);
  }
  // 2) Fallback Invidious (souvent down sur datacenter)
  try {
    const url = `/api/v1/videos/${encodeURIComponent(videoId)}`;
    return (await invFetch(url, 20000)) as InvVideoMeta;
  } catch (e) {
    const invErr = String((e as Error).message || e).slice(0, 200);
    // Agrège les deux pour que le client puisse voir où ça coince réellement
    throw new Error(`innertube: ${innertubeErr} || invidious: ${invErr}`);
  }
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

function bestCombined(meta: InvVideoMeta): AdaptiveFormat | null {
  // formatStreams = streams combinés audio+vidéo (généralement 360p mp4).
  const list = (meta.formatStreams || []).filter((f) => f.url && (f.type || '').startsWith('video/'));
  if (!list.length) return null;
  list.sort((a, b) => {
    const aH = Number((a.resolution || '0p').replace('p', '')) || 0;
    const bH = Number((b.resolution || '0p').replace('p', '')) || 0;
    return bH - aH;
  });
  return list[0];
}

async function ytdlpDownload(videoId: string, outMp4: string): Promise<{ ok: boolean; err?: string }> {
  return new Promise((resolve) => {
    // player_client multi-fallback : web_safari/mweb/tv_embedded bypassent la
    // plupart des restrictions IP cloud actuelles.
    const args = [
      '-f', 'bv*[ext=mp4]+ba[ext=m4a]/best[ext=mp4]/best',
      '--merge-output-format', 'mp4',
      '-o', outMp4,
      '--no-playlist',
      '--no-progress',
      '--extractor-args', 'youtube:player_client=web_safari,mweb,tv_embedded,android',
      `https://www.youtube.com/watch?v=${videoId}`
    ];
    const proc = spawn('yt-dlp', args, { windowsHide: true });
    let out = '';
    let err = '';
    proc.stdout.on('data', (d) => (out += d.toString()));
    proc.stderr.on('data', (d) => (err += d.toString()));
    proc.on('close', (code) => {
      const combined = (err + '\n' + out).trim();
      if (code !== 0) console.warn('[yt-dlp] exit', code, '\n', combined.slice(-1200));
      const errLine = combined.split('\n').find((l) => /ERROR:|sign in|forbidden|unavailable|HTTP Error|429/i.test(l));
      const summary = errLine ? errLine.slice(0, 350) : (combined.slice(-350) || '<aucun output capturé>');
      resolve({ ok: code === 0, err: code === 0 ? undefined : `exit=${code ?? 'null'} ${summary}` });
    });
    proc.on('error', (e) => resolve({ ok: false, err: `spawn: ${String(e).slice(0, 200)}` }));
  });
}

async function downloadFromMeta(meta: InvVideoMeta, outMp4: string): Promise<boolean> {
  // 1) Stream combiné (un seul fichier, simple remux — le plus fiable quand dispo)
  const combined = bestCombined(meta);
  if (combined?.url) {
    const tmp = outMp4 + '.combined.src';
    const got = await downloadToFile(combined.url, tmp);
    if (got) {
      const ok = await ffmpegMux([
        '-y', '-i', tmp,
        '-c', 'copy', '-movflags', '+faststart',
        outMp4
      ]);
      await fs.unlink(tmp).catch(() => {});
      if (ok) return true;
      console.warn('[youtube-api] combined remux failed, fallback adaptive');
    }
  }

  // 2) Streams séparés audio/vidéo (qualité plus haute)
  const audio = bestAudio(meta);
  const video = bestVideo(meta);
  if (!audio?.url || !video?.url) {
    console.warn('[youtube-api] no playable formats', { hasAudio: !!audio?.url, hasVideo: !!video?.url });
    return false;
  }

  const aTmp = outMp4 + '.audio.src';
  const vTmp = outMp4 + '.video.src';
  const [aOk, vOk] = await Promise.all([
    downloadToFile(audio.url, aTmp),
    downloadToFile(video.url, vTmp)
  ]);
  if (!aOk || !vOk) {
    console.warn('[youtube-api] stream download failed', { aOk, vOk });
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

/** Downloads best video+audio and muxes to mp4. */
export async function downloadVideoMp4(videoId: string, outMp4: string): Promise<boolean> {
  let metaErr = '';
  // 1) Path metadata (Innertube → Invidious → mux manuel)
  try {
    const meta = await videoMeta(videoId);
    if (await downloadFromMeta(meta, outMp4)) return true;
  } catch (e) {
    metaErr = String((e as Error).message || e).slice(0, 400);
    console.warn('[youtube-api] meta path failed, fallback yt-dlp:', metaErr);
  }

  // 2) Fallback final: yt-dlp (installé dans le Docker) avec player_clients à jour
  const yt = await ytdlpDownload(videoId, outMp4);
  if (yt.ok) return true;

  // Tout a échoué — propage les deux erreurs pour diagnostic
  throw new Error(`meta: ${metaErr || 'no playable formats'} || yt-dlp: ${yt.err || 'failed'}`);
}
