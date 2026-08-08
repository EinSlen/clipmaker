import fs from 'node:fs';
import path from 'node:path';
import { UPLOADS_DIR } from '@/lib/server-paths';
import { videoFileResponse } from '@/lib/video-response';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request, { params }: { params: Promise<{ file: string }> }) {
  const { file } = await params;
  const safe = path.basename(file);
  const full = path.join(UPLOADS_DIR, safe);
  if (!fs.existsSync(full)) return new Response('Not found', { status: 404 });
  return videoFileResponse(request, full, safe);
}
