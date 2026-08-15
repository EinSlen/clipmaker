import { NextResponse } from 'next/server';
import { fetchTrendingForVibe } from '@/lib/music-fetcher';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { vibe?: string; refresh?: boolean }));
  const vibe = (body.vibe || '').toLowerCase().trim();
  if (!vibe) return NextResponse.json({ ok: false, error: 'vibe requise' }, { status: 400 });
  const result = await fetchTrendingForVibe(vibe, !!body.refresh);
  return NextResponse.json({ ok: true, ...result });
}
