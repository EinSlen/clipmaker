import { NextResponse } from 'next/server';
import path from 'node:path';
import fs from 'node:fs/promises';
import { RENDERS_DIR, UPLOADS_DIR, PUBLIC_MUSIC_DIR } from '@/lib/server-paths';
import { probeVideo, renderVideo } from '@/lib/ffmpeg';
import type { OverlayBlock } from '@/lib/types';
import { randomId } from '@/lib/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

type Body = {
  filename: string; // file in uploads/
  overlays: OverlayBlock[];
  music?: { file?: string; random?: boolean; volume?: number; vibe?: string };
  duckOriginal?: number;
};

async function pickRandomMusic(vibe?: string): Promise<string | undefined> {
  try {
    // Try declared tracks first (so we can honor `vibe`)
    const dataRaw = await fs.readFile(path.join(process.cwd(), 'data', 'music.json'), 'utf-8').catch(() => '');
    let declared: { file: string; vibe?: string[] }[] = [];
    try {
      declared = JSON.parse(dataRaw)?.tracks ?? [];
    } catch {}

    const entries = await fs.readdir(PUBLIC_MUSIC_DIR);
    const onDisk = new Set(entries);

    let candidates: string[] = [];
    if (declared.length) {
      const matching = declared.filter((d) => {
        const f = path.basename(d.file);
        if (!onDisk.has(f)) return false;
        if (!vibe) return true;
        return (d.vibe ?? []).map((v) => v.toLowerCase()).includes(vibe.toLowerCase());
      });
      candidates = matching.map((d) => path.basename(d.file));
    }
    // Fallback: all on-disk audio files
    if (!candidates.length) {
      candidates = entries.filter((f) => /\.(mp3|m4a|aac|wav|ogg)$/i.test(f));
    }
    if (!candidates.length) return undefined;
    return path.join(PUBLIC_MUSIC_DIR, candidates[Math.floor(Math.random() * candidates.length)]);
  } catch {
    return undefined;
  }
}

export async function POST(req: Request) {
  const body = (await req.json()) as Body;
  const inputAbs = path.join(UPLOADS_DIR, path.basename(body.filename));
  try {
    await fs.access(inputAbs);
  } catch {
    return NextResponse.json({ ok: false, error: 'Source introuvable' }, { status: 400 });
  }

  const meta = await probeVideo(inputAbs);
  const width = meta?.width || 1080;
  const height = meta?.height || 1920;

  let musicAbs: string | undefined;
  if (body.music?.random) {
    musicAbs = await pickRandomMusic(body.music?.vibe);
  } else if (body.music?.file) {
    const f = path.basename(body.music.file);
    const candidate = path.join(PUBLIC_MUSIC_DIR, f);
    try {
      await fs.access(candidate);
      musicAbs = candidate;
    } catch {
      musicAbs = undefined;
    }
  }

  await fs.mkdir(RENDERS_DIR, { recursive: true });
  const outFilename = `render-${randomId()}.mp4`;
  const outputAbs = path.join(RENDERS_DIR, outFilename);

  const result = await renderVideo({
    inputAbs,
    outputAbs,
    width,
    height,
    overlays: body.overlays || [],
    musicAbs,
    musicVolume: body.music?.volume ?? 0.55,
    duckOriginal: body.duckOriginal ?? (musicAbs ? 0.35 : 1)
  });

  if (!result.ok) {
    return NextResponse.json({ ok: false, error: 'ffmpeg failed', stderr: result.stderr }, { status: 500 });
  }
  return NextResponse.json({ ok: true, filename: outFilename, musicUsed: musicAbs ? path.basename(musicAbs) : null });
}
