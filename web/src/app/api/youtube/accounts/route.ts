import { NextResponse } from 'next/server';
import { listYouTubeAccounts } from '@/lib/youtube-agent';
import { hasPublisherWriteAccess } from '@/lib/server-publisher-config';
import { interactiveAuthUrl, requestInteractiveAuth } from '@/lib/server-auth-requests';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json({ ok: true, accounts: await listYouTubeAccounts() });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  if (!hasPublisherWriteAccess(request)) {
    return NextResponse.json({ ok: false, error: 'Clé administrateur requise.' }, { status: 401 });
  }
  const body = await request.json().catch(() => ({} as { account?: string }));
  const account = String(body?.account || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(account)) {
    return NextResponse.json({ ok: false, error: 'Utilise 1 à 32 lettres, chiffres, tirets ou underscores.' }, { status: 400 });
  }
  await requestInteractiveAuth('youtube', account);
  return NextResponse.json({
    ok: true,
    account,
    authUrl: interactiveAuthUrl(request, 'youtube'),
    message: 'Le navigateur YouTube est prêt. Connecte-toi ou crée ton compte Google, puis actualise les sessions.',
  });
}
