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
    creationId: string;
    statusCode: number;
    uploadVideoId: string;
  };
};

const RECEIPT_PREFIX = 'CLIPMAKER_RECEIPT:';

function parseUploaderReceipt(stdout: string): UploadReceipt | null {
  const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith(RECEIPT_PREFIX));
  if (!line) return null;
  try {
    const source = JSON.parse(line.slice(RECEIPT_PREFIX.length)) as Record<string, unknown>;
    const raw = source.raw && typeof source.raw === 'object' ? source.raw as Record<string, unknown> : {};
    const platformPostId = String(source.platformPostId || '').trim();
    const privacy = raw.privacy === 'public' ? 'public' : 'private';
    if (!platformPostId) return null;
    return {
      provider: String(source.provider || 'tiktok-web-upload').trim() || 'tiktok-web-upload',
      platformPostId,
      releaseUrl: String(source.releaseUrl || '').trim(),
      raw: {
        privacy,
        creationId: String(raw.creationId || '').trim(),
        statusCode: Number(raw.statusCode || 0),
        uploadVideoId: String(raw.uploadVideoId || platformPostId).trim(),
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
  const py = process.env.PYTHON_BIN || 'python';

  const args = [
    'cli.py', 'upload', '--users', username, '-v', videoAbs, '-t', caption,
    '--visibility', visibility === 'public' ? '0' : '1',
  ];
  if (musicId) args.push('--music-id', musicId);

  return new Promise<Response>((resolve) => {
    const proc = spawn(py, args, {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: true
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => (stdout += d.toString()));
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => {
      const upload = code === 0 ? parseUploaderReceipt(stdout) : null;
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
      resolve(NextResponse.json({ ok: false, error: String(e) }, { status: 500 }));
    });
  });
}
