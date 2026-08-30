import { NextResponse } from 'next/server';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { TIKTOK_COOKIES_DIR, TIKTOK_UPLOADER_DIR } from '@/lib/server-paths';
import { hasPublisherWriteAccess } from '@/lib/server-publisher-config';
import { interactiveAuthUrl, requestInteractiveAuth } from '@/lib/server-auth-requests';

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
  studioReady?: boolean;
  provider?: string;
  visiblePostCount?: number;
};

type StudioDoctor = {
  ok: boolean;
  username: string;
  provider: 'tiktok-studio-browser';
  readyForLiveUpload: boolean;
  visiblePostCount: number;
};

const DOCTOR_PREFIX = 'CLIPMAKER_TIKTOK_DOCTOR:';
const STUDIO_AGENT_PATH = path.join(process.cwd(), 'scripts', 'tiktok-studio-agent.cjs');

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

function inspectStudio(username: string): Promise<StudioDoctor> {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.execPath, [STUDIO_AGENT_PATH, 'doctor', '--users', username], {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: true,
    });
    const timeout = setTimeout(() => proc.kill(), 90_000);
    let out = '';
    let err = '';
    proc.stdout.on('data', (data) => (out += data.toString()));
    proc.stderr.on('data', (data) => (err += data.toString()));
    proc.on('close', (code) => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(err.trim() || `TikTok Studio doctor exited with code ${code}.`));
      const line = out.split(/\r?\n/).reverse().find((entry) => entry.startsWith(DOCTOR_PREFIX));
      if (!line) return reject(new Error('TikTok Studio doctor returned no proof.'));
      try {
        const result = JSON.parse(line.slice(DOCTOR_PREFIX.length)) as StudioDoctor;
        if (result.ok !== true
          || result.username !== username
          || result.provider !== 'tiktok-studio-browser'
          || result.readyForLiveUpload !== true) {
          return reject(new Error('TikTok Studio session is not ready for live upload.'));
        }
        resolve(result);
      } catch {
        reject(new Error('TikTok Studio doctor returned invalid JSON.'));
      }
    });
    proc.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
}

export async function GET(req: Request) {
  try {
    let accounts = await inspectAccounts();
    const verify = new URL(req.url).searchParams.get('verify')?.trim() || '';
    if (verify) {
      if (!/^[A-Za-z0-9._]{2,32}$/.test(verify)) {
        return NextResponse.json({ accounts, note: 'Nom TikTok à vérifier invalide.' }, { status: 400 });
      }
      const matching = accounts.find((account) => account.username === verify);
      if (!matching?.ready) {
        return NextResponse.json({ accounts, note: `La session TikTok @${verify} est absente ou expirée.` });
      }
      try {
        const studio = await inspectStudio(verify);
        accounts = accounts.map((account) => account.username === verify ? {
          ...account,
          ready: studio.readyForLiveUpload,
          studioReady: studio.readyForLiveUpload,
          provider: studio.provider,
          visiblePostCount: studio.visiblePostCount,
        } : account);
      } catch (error) {
        accounts = accounts.map((account) => account.username === verify ? {
          ...account,
          ready: false,
          studioReady: false,
          error: error instanceof Error ? error.message : 'TikTok Studio indisponible.',
        } : account);
      }
    }
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
  if (!hasPublisherWriteAccess(req)) {
    return NextResponse.json({ ok: false, error: 'Clé administrateur requise.' }, { status: 401 });
  }
  const body = await req.json().catch(() => ({} as { username?: string }));
  const username = String(body?.username || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) {
    return NextResponse.json({ ok: false, error: 'Nom d’utilisateur TikTok invalide.' }, { status: 400 });
  }

  await requestInteractiveAuth('tiktok', username);
  return NextResponse.json({
    ok: true,
    username,
    authUrl: interactiveAuthUrl(req, 'tiktok'),
    message: 'Le navigateur TikTok est prêt. Connecte-toi ou crée ton compte, puis actualise les sessions.',
  });
}
