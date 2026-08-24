import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { YOUTUBE_BROWSER_DATA_DIR } from './server-paths';

export type YouTubeDoctorStatus = {
  ok: boolean;
  dry_run: boolean;
  provider: 'browser-session';
  configured: {
    browser: 'configured' | 'missing';
    cookies: 'configured' | 'missing';
    authenticated: 'configured' | 'missing';
    package: 'configured' | 'missing';
  };
  browser_path: string | null;
  ready_for_live_upload: boolean;
  next_steps: string[];
};

export type YouTubeUploadResult = {
  ok: boolean;
  dry_run: boolean;
  result: {
    provider: string;
    platformPostId: string | null;
    releaseUrl: string;
    raw: Record<string, unknown>;
  };
};

const CLI_PATH = path.join(process.cwd(), 'scripts', 'youtube-agent.mjs');
const MAX_OUTPUT_BYTES = 1024 * 1024;

export type YouTubeAccount = {
  id: string;
  label: string;
  configured: boolean;
};

export function normalizeYouTubeAccount(value: unknown): string {
  const account = String(value || 'default').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(account)) {
    throw new Error('Invalid YouTube account profile.');
  }
  return account;
}

export async function listYouTubeAccounts(): Promise<YouTubeAccount[]> {
  const accounts: YouTubeAccount[] = [];
  const defaultCookies = path.join(YOUTUBE_BROWSER_DATA_DIR, 'yt-auth', 'cookies-profile-local_invalid.json');
  accounts.push({ id: 'default', label: 'Default channel', configured: Boolean(await fs.stat(defaultCookies).catch(() => null)) });
  const accountsDir = path.join(YOUTUBE_BROWSER_DATA_DIR, 'accounts');
  const entries = await fs.readdir(accountsDir, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    if (!entry.isDirectory() || !/^[a-z0-9][a-z0-9_-]{0,31}$/i.test(entry.name)) continue;
    const cookieFile = path.join(accountsDir, entry.name, 'yt-auth', 'cookies-profile-local_invalid.json');
    accounts.push({
      id: entry.name,
      label: entry.name.replace(/[-_]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
      configured: Boolean(await fs.stat(cookieFile).catch(() => null)),
    });
  }
  return accounts.sort((a, b) => a.id === 'default' ? -1 : b.id === 'default' ? 1 : a.label.localeCompare(b.label));
}

async function runAgent<T>(args: string[], timeoutMs = 10 * 60 * 1000, account = 'default'): Promise<T> {
  const accountId = normalizeYouTubeAccount(account);
  await fs.mkdir(YOUTUBE_BROWSER_DATA_DIR, { recursive: true });
  await fs.access(CLI_PATH).catch(() => {
    throw new Error('Le script de session YouTube est introuvable.');
  });

  return new Promise<T>((resolve, reject) => {
    const proc = spawn(process.execPath, [CLI_PATH, ...args], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        YOUTUBE_BROWSER_DATA_DIR,
        YOUTUBE_ACCOUNT: accountId,
      },
      windowsHide: true
    });
    let stdout = '';
    let stderr = '';
    let settled = false;

    const timer = setTimeout(() => {
      proc.kill();
      if (!settled) {
        settled = true;
        const detail = (stderr || stdout).trim().slice(-2000);
        reject(new Error(detail ? `YouTube agent timed out: ${detail}` : 'YouTube agent timed out'));
      }
    }, timeoutMs);

    proc.stdout.on('data', (chunk) => {
      if (stdout.length < MAX_OUTPUT_BYTES) stdout += chunk.toString();
    });
    proc.stderr.on('data', (chunk) => {
      if (stderr.length < MAX_OUTPUT_BYTES) stderr += chunk.toString();
    });
    proc.on('error', (error) => {
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        reject(error);
      }
    });
    proc.on('close', (code) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      if (code !== 0) {
        reject(new Error((stderr || stdout || `YouTube agent exited with code ${code}`).trim().slice(0, 2000)));
        return;
      }
      try {
        resolve(JSON.parse(stdout) as T);
      } catch {
        reject(new Error('YouTube agent returned invalid JSON'));
      }
    });
  });
}

export function getYouTubeDoctorStatus(account = 'default'): Promise<YouTubeDoctorStatus> {
  return runAgent<YouTubeDoctorStatus>(['doctor'], 30_000, account);
}

export function uploadYouTubeShort(input: {
  videoPath: string;
  title: string;
  caption: string;
  tags: string[];
  durationSeconds: number;
  aspectRatio: '9:16' | '1:1';
  privacy: 'private' | 'unlisted' | 'public';
  account?: string;
}): Promise<YouTubeUploadResult> {
  const args = [
    'upload-short',
    '--video', input.videoPath,
    '--title', input.title,
    '--caption', input.caption,
    '--duration', String(input.durationSeconds),
    '--aspect-ratio', input.aspectRatio,
    '--privacy', input.privacy
  ];
  if (input.tags.length) args.push('--tags', input.tags.join(','));
  return runAgent<YouTubeUploadResult>(args, 10 * 60 * 1000, input.account);
}
