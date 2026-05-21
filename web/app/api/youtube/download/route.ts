import { NextResponse } from 'next/server';
import path from 'node:path';
import fs from 'node:fs/promises';
import { UPLOADS_DIR } from '@/lib/server-paths';
import { randomId } from '@/lib/utils';
import { downloadVideoMp4 } from '@/lib/youtube-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

function extractVideoId(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1).split('/')[0] || null;
    if (u.hostname.includes('youtube.com')) {
      const v = u.searchParams.get('v');
      if (v) return v;
      // /shorts/<id>
      const m = u.pathname.match(/\/shorts\/([^/?]+)/);
      if (m) return m[1];
    }
  } catch {
    // not a URL — maybe a bare ID
  }
  if (/^[A-Za-z0-9_-]{11}$/.test(url)) return url;
  return null;
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { url?: string }));
  const url = String(body?.url || '').trim();
  const id = extractVideoId(url);
  if (!id) return NextResponse.json({ ok: false, error: 'url/video id invalide' }, { status: 400 });

  await fs.mkdir(UPLOADS_DIR, { recursive: true });
  const filename = `${randomId()}.mp4`;
  const outAbs = path.join(UPLOADS_DIR, filename);

  let ok = false;
  try {
    ok = await downloadVideoMp4(id, outAbs);
  } catch (e) {
    console.error('[youtube/download]', e);
    return NextResponse.json(
      { ok: false, error: `download failed: ${String((e as Error)?.message || e).slice(0, 200)}` },
      { status: 502 }
    );
  }
  if (!ok) return NextResponse.json({ ok: false, error: 'download/mux failed' }, { status: 502 });

  const stat = await fs.stat(outAbs);
  return NextResponse.json({ ok: true, id: filename.replace('.mp4', ''), filename, size: stat.size });
}
