import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLIC_MUSIC_DIR } from '@/lib/server-paths';
import { fetchTrendingForVibe, loadSources } from '@/lib/music-fetcher';
import type { MusicTrack } from '@/lib/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

type DeclaredFile = MusicTrack & { credit?: string };

async function loadDeclared(): Promise<{ tracks: DeclaredFile[]; vibes: { id: string; label: string }[] }> {
  try {
    const raw = await fs.readFile(path.join(process.cwd(), 'data', 'music.json'), 'utf-8');
    const j = JSON.parse(raw);
    return { tracks: (j?.tracks ?? []) as DeclaredFile[], vibes: (j?.vibes ?? []) as { id: string; label: string }[] };
  } catch {
    return { tracks: [], vibes: [] };
  }
}

const AUDIO_RE = /\.(mp3|m4a|aac|wav|ogg)$/i;

function prettyTitle(name: string): string {
  return name
    .replace(/\.[^.]+$/, '')
    .replace(/^[a-z]+-/, '') // strip vibe prefix
    .replace(/-[A-Za-z0-9_-]{6,15}$/, '') // strip yt-dlp id suffix
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function listOnDisk(): Promise<MusicTrack[]> {
  const out: MusicTrack[] = [];
  // Top-level files (declared by user)
  try {
    const top = await fs.readdir(PUBLIC_MUSIC_DIR);
    for (const f of top) {
      if (AUDIO_RE.test(f)) {
        out.push({
          id: f.replace(/\.[^.]+$/, ''),
          title: prettyTitle(f) || f,
          vibe: ['triste'],
          file: `/music/${f}`
        });
      }
    }
  } catch {}
  // Sub-directories named after a vibe (auto-fetched)
  try {
    const entries = await fs.readdir(PUBLIC_MUSIC_DIR, { withFileTypes: true });
    for (const ent of entries) {
      if (!ent.isDirectory()) continue;
      const vibeId = ent.name;
      const dir = path.join(PUBLIC_MUSIC_DIR, ent.name);
      const files = await fs.readdir(dir).catch(() => [] as string[]);
      for (const f of files) {
        if (!AUDIO_RE.test(f)) continue;
        out.push({
          id: `${vibeId}/${f.replace(/\.[^.]+$/, '')}`,
          title: prettyTitle(f) || f,
          vibe: [vibeId],
          file: `/music/${vibeId}/${f}`
        });
      }
    }
  } catch {}
  return out;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const vibe = (url.searchParams.get('vibe') || '').toLowerCase();
  const autoFetch = url.searchParams.get('autoFetch') !== '0';

  const [declared, found] = await Promise.all([loadDeclared(), listOnDisk()]);

  const declaredFiles = new Set(declared.tracks.map((t) => path.basename(t.file)));
  const onDiskFiles = new Set(found.map((t) => path.basename(t.file)));
  const merged: MusicTrack[] = [];
  for (const d of declared.tracks) {
    if (onDiskFiles.has(path.basename(d.file))) merged.push(d);
  }
  for (const f of found) {
    if (!declaredFiles.has(path.basename(f.file))) merged.push(f);
  }

  let filtered = vibe ? merged.filter((t) => t.vibe?.map((v) => v.toLowerCase()).includes(vibe)) : merged;

  // Auto-fetch trending tracks when requesting a specific vibe with empty results
  let autoFetched: { added: number } | null = null;
  if (vibe && !filtered.length && autoFetch) {
    const sources = await loadSources();
    if (sources.queries[vibe]) {
      const res = await fetchTrendingForVibe(vibe, false);
      autoFetched = { added: res.added.length };
      if (res.added.length) {
        const refreshed = await listOnDisk();
        filtered = refreshed.filter((t) => t.vibe?.map((v) => v.toLowerCase()).includes(vibe));
      }
    }
  }

  return NextResponse.json({
    tracks: filtered,
    all: merged,
    vibes: declared.vibes,
    autoFetched,
    note: merged.length ? null : 'Aucune musique. Choisis un thème pour que l’app en télécharge automatiquement.'
  });
}
