import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';
import { UPLOADS_DIR } from '@/lib/server-paths';
import { randomId } from '@/lib/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(req: Request) {
  const form = await req.formData();
  const file = form.get('file');
  if (!(file instanceof File)) {
    return NextResponse.json({ ok: false, error: 'No file' }, { status: 400 });
  }
  await fs.mkdir(UPLOADS_DIR, { recursive: true });
  const id = randomId();
  const safeExt = (file.name.match(/\.([a-z0-9]{2,5})$/i)?.[1] || 'mp4').toLowerCase();
  const filename = `${id}.${safeExt}`;
  const dest = path.join(UPLOADS_DIR, filename);
  const buf = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(dest, buf);
  return NextResponse.json({ ok: true, id, filename, serverPath: dest, size: buf.length });
}
