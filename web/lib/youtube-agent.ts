import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { YOUTUBE_AGENT_CONFIG_DIR } from './server-paths';

export type YouTubeDoctorStatus = {
  ok: boolean;
  dry_run: boolean;
  configured: {
    client_credentials: 'configured' | 'missing';
    access_token: 'configured' | 'missing';
    refresh_token: 'configured' | 'missing';
  };
  missing_count: number;
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

const AGENT_PACKAGE_DIR = path.join(process.cwd(), 'node_modules', 'youtube-shorts-agent');
const CLI_PATH = path.join(AGENT_PACKAGE_DIR, 'src', 'cli.js');
const MAX_OUTPUT_BYTES = 1024 * 1024;

async function runAgent<T>(args: string[], timeoutMs = 10 * 60 * 1000): Promise<T> {
  await fs.mkdir(YOUTUBE_AGENT_CONFIG_DIR, { recursive: true });
  await fs.access(CLI_PATH).catch(() => {
    throw new Error('youtube-shorts-agent is not installed; run npm install in web/');
  });

  return new Promise<T>((resolve, reject) => {
    const proc = spawn(process.execPath, [CLI_PATH, ...args], {
      cwd: YOUTUBE_AGENT_CONFIG_DIR,
      env: {
        ...process.env,
        YOUTUBE_AGENT_DATA_DIR: path.join(YOUTUBE_AGENT_CONFIG_DIR, '.agent-data')
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
        reject(new Error('YouTube agent timed out'));
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

export function getYouTubeDoctorStatus(): Promise<YouTubeDoctorStatus> {
  return runAgent<YouTubeDoctorStatus>(['doctor'], 30_000);
}

export function uploadYouTubeShort(input: {
  videoPath: string;
  title: string;
  caption: string;
  tags: string[];
  durationSeconds: number;
  aspectRatio: '9:16' | '1:1';
  privacy: 'private' | 'unlisted' | 'public';
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
  return runAgent<YouTubeUploadResult>(args);
}
