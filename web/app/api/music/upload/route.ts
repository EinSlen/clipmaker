import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLIC_MUSIC_DIR } from '@/lib/server-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

function sanitize(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60)
    .toLowerCase() || 'track';
}

export async function POST(req: Request) {
  const form = await req.formData();
  const file = form.get('file');
  const vibe = String(form.get('vibe') || 'tendance').toLowerCase().replace(/[^a-z]/g, '') || 'tendance';
  if (!(file instanceof File)) {
    return NextResponse.json({ ok: false, error: 'No file' }, { status: 400 });
  }
  const ext = (file.name.match(/\.(mp3|m4a|aac|wav|ogg)$/i)?.[1] || 'mp3').toLowerCase();
  const base = sanitize(file.name.replace(/\.[^.]+$/, ''));
  const filename = `${base}-${Date.now().toString(36)}.${ext}`;
  const dir = path.join(PUBLIC_MUSIC_DIR, vibe);
  await fs.mkdir(dir, { recursive: true });
  const dest = path.join(dir, filename);
  const buf = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(dest, buf);
  return NextResponse.json({ ok: true, file: `/music/${vibe}/${filename}`, vibe, size: buf.length });
}
