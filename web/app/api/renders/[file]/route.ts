import { NextResponse } from 'next/server';
import fs from 'node:fs';
import path from 'node:path';
import { RENDERS_DIR } from '@/lib/server-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(_req: Request, { params }: { params: { file: string } }) {
  const safe = path.basename(params.file);
  const full = path.join(RENDERS_DIR, safe);
  if (!fs.existsSync(full)) return NextResponse.json({ ok: false }, { status: 404 });
  const stat = fs.statSync(full);
  const stream = fs.createReadStream(full);
  return new Response(stream as unknown as ReadableStream, {
    headers: {
      'Content-Type': 'video/mp4',
      'Content-Length': String(stat.size),
      'Cache-Control': 'no-cache',
      'Content-Disposition': `inline; filename="${safe}"`
    }
  });
}
