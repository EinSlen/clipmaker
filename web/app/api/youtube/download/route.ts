import { NextResponse } from 'next/server';
import path from 'node:path';
import fs from 'node:fs/promises';
import { UPLOADS_DIR } from '@/lib/server-paths';
import { randomId } from '@/lib/utils';
import { spawnYtdlp } from '@/lib/ytdlp';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { url?: string }));
  const url = String(body?.url || '').trim();
  if (!/^https?:\/\//.test(url)) {
    return NextResponse.json({ ok: false, error: 'url invalide' }, { status: 400 });
  }
  await fs.mkdir(UPLOADS_DIR, { recursive: true });
  const id = randomId();
  const out = path.join(UPLOADS_DIR, `${id}.%(ext)s`);

  return new Promise<Response>((resolve) => {
    const proc = spawnYtdlp([
      '-f', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
      '--merge-output-format', 'mp4',
      '-o', out,
      '--no-playlist',
      url
    ]);
    let err = '';
    proc.stderr.on('data', (d) => (err += d.toString()));
    proc.on('close', async (code) => {
      if (code !== 0) {
        resolve(NextResponse.json({ ok: false, error: 'yt-dlp failed', stderr: err.slice(-2000) }, { status: 500 }));
        return;
      }
      const files = await fs.readdir(UPLOADS_DIR);
      const match = files.find((f) => f.startsWith(id + '.'));
      if (!match) {
        resolve(NextResponse.json({ ok: false, error: 'sortie introuvable' }, { status: 500 }));
        return;
      }
      const abs = path.join(UPLOADS_DIR, match);
      const stat = await fs.stat(abs);
      resolve(NextResponse.json({ ok: true, id, filename: match, size: stat.size }));
    });
    proc.on('error', (e) => resolve(NextResponse.json({ ok: false, error: String(e) }, { status: 500 })));
  });
}
