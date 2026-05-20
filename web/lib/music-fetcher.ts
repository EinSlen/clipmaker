import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLIC_MUSIC_DIR } from './server-paths';
import { spawnYtdlp } from './ytdlp';

type SourcesFile = {
  filters?: { minDuration?: number; maxDuration?: number; perFetch?: number };
  queries: Record<string, string[]>;
};

export async function loadSources(): Promise<SourcesFile> {
  try {
    const raw = await fs.readFile(path.join(process.cwd(), 'data', 'music-sources.json'), 'utf-8');
    return JSON.parse(raw) as SourcesFile;
  } catch {
    return { queries: {} };
  }
}

type SearchHit = { id: string; url: string; duration: number; title: string };

function ytdlpSearch(query: string, max: number): Promise<SearchHit[]> {
  return new Promise((resolve) => {
    const proc = spawnYtdlp([`ytsearch${max}:${query}`, '--dump-json', '--no-download', '--no-warnings', '-q']);
    let out = '';
    proc.stdout.on('data', (d) => (out += d.toString()));
    proc.on('close', () => {
      const items: SearchHit[] = [];
      for (const line of out.split('\n')) {
        if (!line.trim()) continue;
        try {
          const j = JSON.parse(line);
          items.push({
            id: String(j.id ?? ''),
            url: String(j.webpage_url ?? `https://www.youtube.com/watch?v=${j.id}`),
            duration: Number(j.duration ?? 0),
            title: String(j.title ?? '')
          });
        } catch {}
      }
      resolve(items);
    });
    proc.on('error', () => resolve([]));
  });
}

function ytdlpExtractAudio(url: string, outBase: string): Promise<string | null> {
  return new Promise((resolve) => {
    const proc = spawnYtdlp([
      '-x',
      '--audio-format', 'mp3',
      '--audio-quality', '0',
      '--no-playlist',
      '--no-warnings',
      '-q',
      '-o', outBase + '.%(ext)s',
      url
    ]);
    let stderr = '';
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', async (code) => {
      if (code !== 0) {
        console.warn('[music-fetcher] yt-dlp audio failed:', stderr.slice(-300));
        resolve(null);
        return;
      }
      const candidate = outBase + '.mp3';
      try {
        await fs.access(candidate);
        resolve(candidate);
      } catch {
        resolve(null);
      }
    });
    proc.on('error', () => resolve(null));
  });
}

function sanitize(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 60)
    .toLowerCase()
    .replace(/^-|-$/g, '');
}

export type FetchResult = {
  vibe: string;
  added: { file: string; title: string; duration: number; url: string }[];
  skipped: { reason: string; title?: string }[];
};

export async function fetchTrendingForVibe(vibe: string, refresh = false): Promise<FetchResult> {
  const sources = await loadSources();
  const queries = sources.queries[vibe] || [];
  const min = sources.filters?.minDuration ?? 15;
  const max = sources.filters?.maxDuration ?? 240;
  const per = sources.filters?.perFetch ?? 3;

  const vibeDir = path.join(PUBLIC_MUSIC_DIR, vibe);
  await fs.mkdir(vibeDir, { recursive: true });

  // If refresh requested, clear existing tracks for that vibe first
  if (refresh) {
    const existing = await fs.readdir(vibeDir).catch(() => [] as string[]);
    for (const f of existing) {
      if (/\.(mp3|m4a|aac|wav|ogg)$/i.test(f)) {
        await fs.unlink(path.join(vibeDir, f)).catch(() => {});
      }
    }
  }

  const result: FetchResult = { vibe, added: [], skipped: [] };
  const wanted = per;

  for (const q of queries) {
    if (result.added.length >= wanted) break;
    const hits = await ytdlpSearch(q, 5);
    for (const h of hits) {
      if (result.added.length >= wanted) break;
      if (!h.duration || h.duration < min || h.duration > max) {
        result.skipped.push({ reason: 'duration', title: h.title });
        continue;
      }
      const slug = sanitize(h.title) || h.id;
      const outBase = path.join(vibeDir, `${vibe}-${slug}-${h.id}`);
      // Skip if already downloaded for this id
      try {
        await fs.access(outBase + '.mp3');
        result.added.push({ file: `/music/${vibe}/${path.basename(outBase)}.mp3`, title: h.title, duration: h.duration, url: h.url });
        continue;
      } catch {}
      const file = await ytdlpExtractAudio(h.url, outBase);
      if (file) {
        result.added.push({
          file: `/music/${vibe}/${path.basename(file)}`,
          title: h.title,
          duration: h.duration,
          url: h.url
        });
      } else {
        result.skipped.push({ reason: 'extract-failed', title: h.title });
      }
    }
  }

  return result;
}
