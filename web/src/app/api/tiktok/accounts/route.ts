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

type TikTokAccountStatus = {
  username: string;
  cookieFile: string;
  ready: boolean;
  expired: boolean;
  sessionPresent: boolean;
  datacenterPresent: boolean;
  expiresAt: number | null;
  error?: string;
};

function inspectAccounts(): Promise<TikTokAccountStatus[]> {
  return new Promise((resolve, reject) => {
    const py = process.env.PYTHON_BIN || 'python';
    const script = path.join(process.cwd(), 'scripts', 'tiktok-account-status.py');
    const proc = spawn(py, [script, TIKTOK_COOKIES_DIR], { windowsHide: true });
    let out = '';
    let err = '';
    proc.stdout.on('data', (data) => (out += data.toString()));
    proc.stderr.on('data', (data) => (err += data.toString()));
    proc.on('close', (code) => {
      if (code !== 0) return reject(new Error(err.trim() || `Cookie inspection exited with code ${code}.`));
      try {
        const payload = JSON.parse(out) as { accounts?: TikTokAccountStatus[] };
        resolve(Array.isArray(payload.accounts) ? payload.accounts : []);
      } catch {
        reject(new Error('Cookie inspection returned invalid JSON.'));
      }
    });
    proc.on('error', reject);
  });
}

export async function GET() {
  try {
    const accounts = await inspectAccounts();
    return NextResponse.json({ accounts });
  } catch (err) {
    // Preserve account discovery if Python is unavailable, but never claim
    // those unverified files are ready for unattended publishing.
    const entries = await fs.readdir(TIKTOK_COOKIES_DIR).catch(() => [] as string[]);
    const accounts = entries
      .map((file) => ({ file, username: extractUsername(file) }))
      .filter((account) => account.username)
      .map((account) => ({
        username: account.username as string,
        cookieFile: account.file,
        ready: false,
        expired: false,
        sessionPresent: false,
        datacenterPresent: false,
        expiresAt: null,
      }));
    return NextResponse.json({
      accounts,
      note: err instanceof Error ? err.message : 'Impossible de vérifier les sessions TikTok.',
    });
  }
}

export async function POST(req: Request) {
  // Trigger an interactive login (opens a browser on the SERVER). Only works locally.
  const body = await req.json().catch(() => ({} as { username?: string }));
  const username = String(body?.username || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) {
    return NextResponse.json({ ok: false, error: 'Nom d’utilisateur TikTok invalide.' }, { status: 400 });
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
