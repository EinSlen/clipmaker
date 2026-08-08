import { NextResponse } from 'next/server';
import { listYouTubeAccounts } from '@/lib/youtube-agent';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json({ ok: true, accounts: await listYouTubeAccounts() });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
