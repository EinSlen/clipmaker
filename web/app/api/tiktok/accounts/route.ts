import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { TIKTOK_COOKIES_DIR, TIKTOK_UPLOADER_DIR } from '@/lib/server-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function extractUsername(filename: string): string | null {
  // Vendor names files like "tiktok_session-<username>.cookie".
  const base = path.basename(filename).replace(/\.[^.]+$/, '');
  if (/^empty$/i.test(base)) return null;
  const m = base.match(/[_-]([A-Za-z0-9._]+)$/);
  const candidate = m ? m[1] : base;
  if (!candidate || /^(empty|cookie|session|tiktok)$/i.test(candidate)) return null;
  return candidate;
}

export async function GET() {
  try {
    const entries = await fs.readdir(TIKTOK_COOKIES_DIR);
    const accounts = entries
      .map((f) => ({ file: f, username: extractUsername(f) }))
      .filter((a) => a.username)
      .map((a) => ({ username: a.username as string, cookieFile: a.file }));
    return NextResponse.json({ accounts });
  } catch (err) {
    return NextResponse.json({ accounts: [], note: 'CookiesDir introuvable. Lance `python cli.py login -n <username>` une fois pour ajouter un compte.' });
  }
}

export async function POST(req: Request) {
  // Trigger an interactive login (opens a browser on the SERVER). Only works locally.
  const body = await req.json().catch(() => ({} as { username?: string }));
  const username = String(body?.username || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) {
    return NextResponse.json({ ok: false, error: 'username invalide' }, { status: 400 });
  }

  return new Promise<Response>((resolve) => {
    const py = process.env.PYTHON_BIN || 'python';
    const proc = spawn(py, ['cli.py', 'login', '-n', username], {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: false
    });
    let out = '';
    let err = '';
    proc.stdout.on('data', (d) => (out += d.toString()));
    proc.stderr.on('data', (d) => (err += d.toString()));
    proc.on('close', (code) => {
      resolve(
        NextResponse.json({
          ok: code === 0 || /already saved|Unnecessary login/i.test(out),
          stdout: out.slice(-2000),
          stderr: err.slice(-2000),
          code
        })
      );
    });
    proc.on('error', (e) => {
      resolve(NextResponse.json({ ok: false, error: String(e) }, { status: 500 }));
    });
  });
}
