import { NextResponse } from 'next/server';
import crypto from 'node:crypto';
import path from 'node:path';
import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { RENDERS_DIR, TIKTOK_UPLOADER_DIR } from '@/lib/server-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

type Body = {
  filename: string; // file in renders/
  username: string;
  caption: string;
  musicId?: string; // ID ou URL TikTok du son officiel à attacher
  visibility?: 'private' | 'public';
  confirmPublic?: boolean;
};

type UploadReceipt = {
  provider: string;
  platformPostId: string;
  releaseUrl: string;
  raw: {
    privacy: 'private' | 'public';
    statusCode: number;
    evidence: 'post-response' | 'studio-content';
    verifiedInStudio: true;
    account: string;
  };
};

const RECEIPT_PREFIX = 'CLIPMAKER_RECEIPT:';
const STUDIO_AGENT_PATH = path.join(process.cwd(), 'scripts', 'tiktok-studio-agent.cjs');

function parseUploaderReceipt(stdout: string, expectedUsername: string): UploadReceipt | null {
  const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith(RECEIPT_PREFIX));
  if (!line) return null;
  try {
    const source = JSON.parse(line.slice(RECEIPT_PREFIX.length)) as Record<string, unknown>;
    const raw = source.raw && typeof source.raw === 'object' ? source.raw as Record<string, unknown> : {};
    const platformPostId = String(source.platformPostId || '').trim();
    const privacy = raw.privacy === 'public' ? 'public' : 'private';
    const provider = String(source.provider || '').trim();
    const releaseUrl = String(source.releaseUrl || '').trim();
    const evidence = raw.evidence === 'post-response' ? 'post-response' : raw.evidence === 'studio-content' ? 'studio-content' : null;
    const expectedUrl = `https://www.tiktok.com/@${expectedUsername}/video/${platformPostId}`;
    if (!/^\d{12,25}$/.test(platformPostId)
      || provider !== 'tiktok-studio-browser'
      || raw.verifiedInStudio !== true
      || String(raw.account || '') !== expectedUsername
      || releaseUrl !== expectedUrl
      || !evidence) return null;
    return {
      provider,
      platformPostId,
      releaseUrl,
      raw: {
        privacy,
        statusCode: Number(raw.statusCode || 0),
        evidence,
        verifiedInStudio: true,
        account: expectedUsername,
      },
    };
  } catch {
    return null;
  }
}

function extractMusicId(raw: string | undefined): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (/^\d{10,}$/.test(s)) return s;
  const m = s.match(/(\d{10,})/);
  return m ? m[1] : null;
}

function hasValidAdminToken(req: Request): boolean {
  const expected = process.env.CLIPMAKER_UPLOAD_TOKEN || '';
  if (!expected) return true;
  const supplied = req.headers.get('x-clipmaker-upload-token') || '';
  if (!supplied) return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export async function POST(req: Request) {
  if (!hasValidAdminToken(req)) {
    return NextResponse.json({ ok: false, error: "Jeton d'administration requis pour publier sur TikTok" }, { status: 401 });
  }
  const body = (await req.json()) as Body;
  const username = String(body.username || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) {
    return NextResponse.json({ ok: false, error: 'username invalide' }, { status: 400 });
  }
  const filename = path.basename(body.filename || '');
  const videoAbs = path.join(RENDERS_DIR, filename);
  try {
    await fs.access(videoAbs);
  } catch {
    return NextResponse.json({ ok: false, error: 'Rendu introuvable' }, { status: 400 });
  }

  const caption = (body.caption || '').slice(0, 2000);
  const visibility = body.visibility || 'private';
  if (!['private', 'public'].includes(visibility)) {
    return NextResponse.json({ ok: false, error: 'Visibilité TikTok invalide' }, { status: 400 });
  }
  if (visibility === 'public' && !body.confirmPublic) {
    return NextResponse.json({ ok: false, error: 'Confirmation explicite requise pour publier sur TikTok' }, { status: 400 });
  }
  const musicId = extractMusicId(body.musicId);
  if (body.musicId && !musicId) {
    return NextResponse.json({ ok: false, error: 'music ID/URL invalide' }, { status: 400 });
  }
  if (musicId) {
    return NextResponse.json({ ok: false, error: 'Les sons officiels TikTok ne sont pas encore compatibles avec l’envoi Studio vérifié.' }, { status: 400 });
  }
  const args = [
    STUDIO_AGENT_PATH, 'upload', '--users', username, '--video', videoAbs, '--title', caption,
    '--visibility', visibility === 'public' ? '0' : '1',
  ];

  return new Promise<Response>((resolve) => {
    const proc = spawn(process.execPath, args, {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: true
    });
    const timeout = setTimeout(() => proc.kill(), 9 * 60_000);
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => (stdout += d.toString()));
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => {
      clearTimeout(timeout);
      const upload = code === 0 ? parseUploaderReceipt(stdout, username) : null;
      const ok = code === 0 && Boolean(upload);
      resolve(
        NextResponse.json({
          ok,
          code,
          ...(!ok && code === 0 ? { error: 'TikTok a accepté la commande sans retourner de reçu vérifiable.' } : {}),
          ...(upload ? { upload } : {}),
          stdout: stdout.slice(-4000),
          stderr: stderr.slice(-4000)
        })
      );
    });
    proc.on('error', (e) => {
      clearTimeout(timeout);
      resolve(NextResponse.json({ ok: false, error: String(e) }, { status: 500 }));
    });
  });
}
