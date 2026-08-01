import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';
import { discoverLicensedMusic } from '@/lib/licensed-music';
import { PUBLIC_MUSIC_DIR, RENDERS_DIR } from '@/lib/server-paths';
import { randomId } from '@/lib/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

type RenderRequest = {
  duration?: number;
  rings?: number;
  seed?: number;
  theme?: 'neon' | 'sunset' | 'ice';
  soundPack?: 'auto' | 'meme' | 'funny' | 'arcade' | 'impact';
  musicFile?: string;
  musicMode?: 'hit-reveal' | 'continuous';
  musicVolume?: number;
  title?: string;
};

let rendering = false;

function numberInRange(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(min, Math.min(max, Math.round(parsed))) : fallback;
}

function runRenderer(args: string[]): Promise<{ stdout: string; stderr: string }> {
  const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error('The render exceeded the 10-minute limit.'));
    }, 10 * 60 * 1000);
    child.stdout.on('data', (chunk) => (stdout += chunk.toString()));
    child.stderr.on('data', (chunk) => (stderr += chunk.toString()));
    child.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timeout);
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(stderr.trim() || `The game engine stopped with exit code ${code}.`));
    });
  });
}

async function listMusicFiles(directory = PUBLIC_MUSIC_DIR): Promise<string[]> {
  const files: string[] = [];
  const entries = await fs.readdir(directory, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await listMusicFiles(candidate));
    else if (/\.(mp3|m4a|aac|wav|ogg)$/i.test(entry.name)) files.push(candidate);
  }
  return files.sort();
}

async function listSafeFallbackMusic(): Promise<string[]> {
  const groups = await Promise.all([
    listMusicFiles(path.join(PUBLIC_MUSIC_DIR, 'game')),
    listMusicFiles(path.join(PUBLIC_MUSIC_DIR, 'licensed')),
  ]);
  return groups.flat().sort();
}

export async function POST(request: Request) {
  if (rendering) {
    return NextResponse.json({ ok: false, error: 'A game render is already running.' }, { status: 409 });
  }
  rendering = true;
  try {
    const body = (await request.json()) as RenderRequest;
    const duration = numberInRange(body.duration, 45, 15, 60);
    const rings = numberInRange(body.rings, 240, 40, 300);
    const seed = numberInRange(body.seed, crypto.randomInt(100_000, 999_999_999), 1, 2_147_483_647);
    const theme = body.theme && ['neon', 'sunset', 'ice'].includes(body.theme) ? body.theme : 'neon';
    const soundPack = body.soundPack && ['auto', 'meme', 'funny', 'arcade', 'impact'].includes(body.soundPack) ? body.soundPack : 'auto';
    const musicMode = body.musicMode === 'continuous' ? 'continuous' : 'hit-reveal';
    const musicVolume = numberInRange(Number(body.musicVolume) * 100, 55, 0, 100) / 100;
    const title = String(body.title || 'Will the ball escape?').trim().slice(0, 52);
    const filename = `ball-escape-${seed}-${randomId()}.mp4`;
    const output = path.join(RENDERS_DIR, filename);
    const script = path.join(process.cwd(), 'scripts', 'render-ball-escape.py');

    await fs.mkdir(RENDERS_DIR, { recursive: true });
    let musicPath: string | undefined;
    let musicTitle: string | null = null;
    let musicCredit: string | null = null;
    let musicSource: 'jamendo' | 'library' | 'original' = 'original';
    let musicNote: string | null = null;
    const requestedMusic = body.musicFile ?? '__discover__';
    if (requestedMusic === '__discover__') {
      try {
        const discovered = await discoverLicensedMusic(seed);
        if (discovered) {
          musicPath = discovered.path;
          musicTitle = `${discovered.title} — ${discovered.artist}`;
          musicCredit = discovered.credit;
          musicSource = discovered.provider;
        }
      } catch (error) {
        musicNote = error instanceof Error ? error.message : String(error);
      }
      if (!musicPath) {
        const candidates = await listSafeFallbackMusic();
        if (candidates.length) {
          musicPath = candidates[seed % candidates.length];
          musicTitle = path.basename(musicPath);
          musicSource = 'library';
          musicNote ||= 'Licensed discovery was unavailable, so ClipMaker used the safe local library.';
        } else {
          musicNote ||= process.env.JAMENDO_CLIENT_ID
            ? 'No eligible CC BY track was found; the original generated soundtrack was used.'
            : 'Online discovery needs JAMENDO_CLIENT_ID; ClipMaker generated a new original electronic track instead.';
        }
      }
    } else if (requestedMusic === '__auto__') {
      const candidates = await listMusicFiles();
      if (candidates.length) {
        musicPath = candidates[seed % candidates.length];
        musicTitle = path.basename(musicPath);
        musicSource = 'library';
      }
    } else if (requestedMusic) {
      const relativeMusic = String(requestedMusic).replace(/^\/?music\//, '');
      const candidate = path.resolve(PUBLIC_MUSIC_DIR, relativeMusic);
      const relativeCheck = path.relative(PUBLIC_MUSIC_DIR, candidate);
      if (relativeCheck.startsWith('..') || path.isAbsolute(relativeCheck)) {
        return NextResponse.json({ ok: false, error: 'Invalid audio track path.' }, { status: 400 });
      }
      try {
        await fs.access(candidate);
        musicPath = candidate;
        musicTitle = path.basename(candidate);
        musicSource = 'library';
      } catch {
        return NextResponse.json({ ok: false, error: 'The selected audio track could not be found.' }, { status: 400 });
      }
    }

    const rendererArgs = [
      script,
      '--output', output,
      '--duration', String(duration),
      '--rings', String(rings),
      '--seed', String(seed),
      '--theme', theme,
      '--sound-pack', soundPack,
      '--title', title,
      '--music-volume', String(musicVolume),
      '--music-mode', musicMode,
    ];
    if (musicPath) rendererArgs.push('--music', musicPath);
    const renderer = await runRenderer(rendererArgs);
    let rendererMetadata: { sound_pack?: string; duration?: number; music?: string; music_generated?: boolean; music_mode?: string; music_hits?: number } = {};
    try {
      const lastLine = renderer.stdout.trim().split(/\r?\n/).at(-1);
      if (lastLine) rendererMetadata = JSON.parse(lastLine);
    } catch {}
    if (!musicTitle && rendererMetadata.music_generated) musicTitle = rendererMetadata.music || 'Original generated track';
    const stat = await fs.stat(output);
    const captionBase = `${title} Run #${seed}. Did you think it would make it out?`;
    return NextResponse.json({
      ok: true,
      filename,
      size: stat.size,
      duration: rendererMetadata.duration || duration,
      seed,
      rings,
      theme,
      soundPack: rendererMetadata.sound_pack || soundPack,
      musicMode: rendererMetadata.music_mode || musicMode,
      musicHits: rendererMetadata.music_hits || 0,
      musicUsed: musicPath ? path.basename(musicPath) : rendererMetadata.music || null,
      musicTitle,
      musicSource,
      musicCredit,
      musicNote,
      title,
      youtubeTitle: `${title} #shorts`,
      caption: musicCredit ? `${captionBase}\n${musicCredit}` : captionBase,
      tags: ['#satisfying', '#ballescape', '#simulation', '#hypnotic', '#shorts'],
    });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  } finally {
    rendering = false;
  }
}
