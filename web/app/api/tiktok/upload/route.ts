import { NextResponse } from 'next/server';
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
};

export async function POST(req: Request) {
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
  const py = process.env.PYTHON_BIN || 'python';

  return new Promise<Response>((resolve) => {
    const proc = spawn(py, ['cli.py', 'upload', '--user', username, '-v', videoAbs, '-t', caption], {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: true
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => (stdout += d.toString()));
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => {
      resolve(
        NextResponse.json({
          ok: code === 0,
          code,
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
