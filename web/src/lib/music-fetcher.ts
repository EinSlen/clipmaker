import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLIC_MUSIC_DIR } from './server-paths';
import { searchYoutube, downloadAudioMp3 } from './youtube-api';

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

  if (refresh) {
    const existing = await fs.readdir(vibeDir).catch(() => [] as string[]);
    for (const f of existing) {
      if (/\.(mp3|m4a|aac|wav|ogg)$/i.test(f)) {
        await fs.unlink(path.join(vibeDir, f)).catch(() => {});
      }
    }
  }

  const result: FetchResult = { vibe, added: [], skipped: [] };

  for (const q of queries) {
    if (result.added.length >= per) break;
    let hits: Awaited<ReturnType<typeof searchYoutube>> = [];
    try {
      hits = await searchYoutube(q, 5);
    } catch (e) {
      console.warn('[music-fetcher] search failed for', q, String(e).slice(0, 120));
      continue;
    }
    for (const h of hits) {
      if (result.added.length >= per) break;
      if (!h.duration || h.duration < min || h.duration > max) {
        result.skipped.push({ reason: 'duration', title: h.title });
        continue;
      }
      const slug = sanitize(h.title) || h.id;
      const outMp3 = path.join(vibeDir, `${vibe}-${slug}-${h.id}.mp3`);
      try {
        await fs.access(outMp3);
        result.added.push({ file: `/music/${vibe}/${path.basename(outMp3)}`, title: h.title, duration: h.duration, url: h.url });
        continue;
      } catch {}
      const ok = await downloadAudioMp3(h.id, outMp3);
      if (ok) {
        result.added.push({
          file: `/music/${vibe}/${path.basename(outMp3)}`,
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
