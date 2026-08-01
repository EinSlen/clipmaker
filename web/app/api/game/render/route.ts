import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';
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
  soundPack?: 'auto' | 'funny' | 'arcade' | 'impact';
  musicFile?: string;
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
      reject(new Error('Le rendu a dépassé la limite de 10 minutes.'));
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
      else reject(new Error(stderr.trim() || `Le moteur de jeu s'est arrêté avec le code ${code}.`));
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

export async function POST(request: Request) {
  if (rendering) {
    return NextResponse.json({ ok: false, error: 'Un rendu de jeu est déjà en cours.' }, { status: 409 });
  }
  rendering = true;
  try {
    const body = (await request.json()) as RenderRequest;
    const duration = numberInRange(body.duration, 45, 15, 60);
    const rings = numberInRange(body.rings, 18, 8, 32);
    const seed = numberInRange(body.seed, crypto.randomInt(100_000, 999_999_999), 1, 2_147_483_647);
    const theme = body.theme && ['neon', 'sunset', 'ice'].includes(body.theme) ? body.theme : 'neon';
    const soundPack = body.soundPack && ['auto', 'funny', 'arcade', 'impact'].includes(body.soundPack) ? body.soundPack : 'auto';
    const musicVolume = numberInRange(Number(body.musicVolume) * 100, 24, 0, 100) / 100;
    const title = String(body.title || "La balle va-t-elle s'échapper ?").trim().slice(0, 52);
    const filename = `ball-escape-${seed}-${randomId()}.mp4`;
    const output = path.join(RENDERS_DIR, filename);
    const script = path.join(process.cwd(), 'scripts', 'render-ball-escape.py');

    await fs.mkdir(RENDERS_DIR, { recursive: true });
    let musicPath: string | undefined;
    if (body.musicFile === '__auto__') {
      const candidates = await listMusicFiles();
      if (candidates.length) musicPath = candidates[seed % candidates.length];
    } else if (body.musicFile) {
      const relativeMusic = String(body.musicFile).replace(/^\/?music\//, '');
      const candidate = path.resolve(PUBLIC_MUSIC_DIR, relativeMusic);
      const relativeCheck = path.relative(PUBLIC_MUSIC_DIR, candidate);
      if (relativeCheck.startsWith('..') || path.isAbsolute(relativeCheck)) {
        return NextResponse.json({ ok: false, error: 'Chemin de piste audio invalide.' }, { status: 400 });
      }
      try {
        await fs.access(candidate);
        musicPath = candidate;
      } catch {
        return NextResponse.json({ ok: false, error: 'La piste audio sélectionnée est introuvable.' }, { status: 400 });
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
    ];
    if (musicPath) rendererArgs.push('--music', musicPath, '--music-volume', String(musicVolume));
    const renderer = await runRenderer(rendererArgs);
    let rendererMetadata: { sound_pack?: string } = {};
    try {
      const lastLine = renderer.stdout.trim().split(/\r?\n/).at(-1);
      if (lastLine) rendererMetadata = JSON.parse(lastLine);
    } catch {}
    const stat = await fs.stat(output);
    return NextResponse.json({
      ok: true,
      filename,
      size: stat.size,
      duration,
      seed,
      rings,
      theme,
      soundPack: rendererMetadata.sound_pack || soundPack,
      musicUsed: musicPath ? path.basename(musicPath) : null,
      title,
      youtubeTitle: `${title} #shorts`,
      caption: `${title} Niveau généré : ${seed}. Tu pensais qu'elle allait sortir ?`,
      tags: ['#satisfying', '#ballescape', '#simulation', '#hypnotic', '#shorts'],
    });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  } finally {
    rendering = false;
  }
}
