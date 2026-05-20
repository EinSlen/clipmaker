// Resolves a working yt-dlp invocation across PATH and a `python -m yt_dlp` fallback.
import { spawn, spawnSync } from 'node:child_process';

let cached: { cmd: string; args: string[] } | null = null;

function check(cmd: string, args: string[]): boolean {
  try {
    const r = spawnSync(cmd, [...args, '--version'], { windowsHide: true, stdio: 'pipe' });
    return r.status === 0;
  } catch {
    return false;
  }
}

export function resolveYtdlp(): { cmd: string; args: string[] } {
  if (cached) return cached;
  const fromEnv = process.env.YTDLP_BIN;
  if (fromEnv && check(fromEnv, [])) {
    cached = { cmd: fromEnv, args: [] };
    return cached;
  }
  if (check('yt-dlp', [])) {
    cached = { cmd: 'yt-dlp', args: [] };
    return cached;
  }
  const py = process.env.PYTHON_BIN || 'python';
  if (check(py, ['-m', 'yt_dlp'])) {
    cached = { cmd: py, args: ['-m', 'yt_dlp'] };
    return cached;
  }
  // Last resort: assume yt-dlp will work via PATH at runtime (will fail visibly otherwise)
  cached = { cmd: 'yt-dlp', args: [] };
  return cached;
}

export function spawnYtdlp(args: string[]) {
  const r = resolveYtdlp();
  return spawn(r.cmd, [...r.args, ...args], { windowsHide: true });
}
