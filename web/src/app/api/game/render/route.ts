import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';
import { getGameDefinition, isGameId, type GameId } from '@/lib/game-catalog';
import { discoverLicensedMusic } from '@/lib/licensed-music';
import { PUBLIC_MUSIC_DIR, RENDERS_DIR } from '@/lib/server-paths';
import { randomId } from '@/lib/utils';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 604_800;

type RenderRequest = {
  game?: GameId;
  channelId?: string;
  series?: string;
  tiktokUser?: string;
  storyTheme?: string;
  difficulty?: number;
  duration?: number;
  rings?: number;
  seed?: number;
  theme?: 'neon' | 'sunset' | 'ice';
  soundPack?: 'auto' | 'meme' | 'funny' | 'arcade' | 'impact' | 'asmr';
  musicFile?: string;
  musicMode?: 'hit-reveal' | 'continuous';
  musicProfile?: 'edit-auto' | 'edit-sad' | 'edit-revenge' | 'auto' | 'revenge' | 'sad-english' | 'original';
  musicVolume?: number;
  title?: string;
  obstacle?: 'auto' | 'moving-slide' | 'stair-cascade' | 'v-stairs' | 'pipe-bend' | 'peg-grid' | 'twin-gears' | 'compression-ring';
};

type StoryReceipt = {
  ok: boolean;
  error?: string;
  seriesTitle?: string;
  episode?: number;
  filename?: string;
  duration?: number;
  shots?: number;
  title?: string;
  youtubeTitle?: string;
  caption?: string;
  tags?: string[];
  steeredBy?: { platform: string; author: string; text: string; likes: number } | null;
  commentsSeen?: number;
  commentSources?: { platform: string; ok: boolean; reason?: string; count?: number }[];
  clipsRequested?: number;
  clipsUsed?: number;
  clipsFailed?: { clip: number; error: string }[];
};

type RenderOutcome =
  | 'escaped'
  | 'failed'
  | 'incomplete'
  | 'survived'
  | 'collision'
  | 'player'
  | 'boss'
  | 'draw'
  | 'comparison-complete';

let rendering = false;

function numberInRange(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(min, Math.min(max, Math.round(parsed))) : fallback;
}

function runRenderer(args: string[]): Promise<{ stdout: string; stderr: string }> {
  const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
  const configuredTimeout = Number(process.env.PREMIUM_RENDER_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(configuredTimeout) && configuredTimeout > 0
    ? configuredTimeout
    : 7 * 24 * 60 * 60 * 1000;
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error(`The render exceeded its ${Math.round(timeoutMs / 3_600_000)}-hour limit.`));
    }, timeoutMs);
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

function runNode(args: string[], timeoutMs: number): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { cwd: process.cwd(), windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error('The episode builder exceeded its time limit.'));
    }, timeoutMs);
    child.stdout.on('data', (chunk) => (stdout += chunk.toString()));
    child.stderr.on('data', (chunk) => (stderr = (stderr + chunk.toString()).slice(-8000)));
    child.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timeout);
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(stderr.trim().slice(-1200) || `The episode builder stopped with exit code ${code}.`));
    });
  });
}

async function runStoryBuilder(body: RenderRequest, series: string, seconds: number) {
  const args = [
    path.join(process.cwd(), 'scripts', 'story', 'make-episode.mjs'),
    '--series', series,
    '--channel', String(body.channelId || series),
    '--seconds', String(seconds),
    '--output-dir', RENDERS_DIR,
  ];
  if (body.tiktokUser) args.push('--tiktok-user', String(body.tiktokUser));
  if (body.storyTheme) args.push('--theme', String(body.storyTheme));
  const { stdout } = await runNode(args, 60 * 60 * 1000);
  const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith('CLIPMAKER_MAKE:'));
  if (!line) throw new Error('The episode builder returned no receipt.');
  const receipt = JSON.parse(line.slice('CLIPMAKER_MAKE:'.length)) as StoryReceipt;
  if (!receipt.ok || !receipt.filename) throw new Error(receipt.error || 'The episode builder failed.');
  return receipt;
}

// Generated clips are the only accepted format for this channel. A run that
// cannot produce them fails and says why, rather than publishing something the
// series is not meant to look like.
async function renderStoryEpisode(body: RenderRequest, seconds: number) {
  const series = String(body.series || body.channelId || 'story').replace(/[^A-Za-z0-9._-]/g, '').slice(0, 60);
  if (!series) throw new Error('A story channel needs a series id.');
  const receipt = await runStoryBuilder(body, series, seconds);
  const stat = await fs.stat(path.join(RENDERS_DIR, receipt.filename as string));
  return NextResponse.json({
    ok: true,
    game: 'story-comments',
    gameName: 'Comment-Driven Story',
    filename: receipt.filename,
    size: stat.size,
    duration: receipt.duration,
    title: receipt.title,
    youtubeTitle: receipt.youtubeTitle,
    caption: receipt.caption,
    tags: receipt.tags,
    outcome: null,
    story: {
      series: receipt.seriesTitle,
      episode: receipt.episode,
      shots: receipt.clipsUsed ?? null,
      clipsRequested: receipt.clipsRequested ?? null,
      clipsFailed: receipt.clipsFailed ?? [],
      steeredBy: receipt.steeredBy ?? null,
      commentsSeen: receipt.commentsSeen ?? 0,
      commentSources: receipt.commentSources ?? [],
    },
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
    if (body.game !== undefined && !isGameId(body.game)) {
      return NextResponse.json({ ok: false, error: 'Unknown game format.' }, { status: 400 });
    }
    const game = isGameId(body.game) ? body.game : 'ball-escape';
    if (game === 'story-comments') {
      await fs.mkdir(RENDERS_DIR, { recursive: true });
      return await renderStoryEpisode(body, numberInRange(body.duration, 60, 30, 120));
    }
    const definition = getGameDefinition(game);
    const requestedDuration = numberInRange(body.duration, 15, 15, 60);
    const duration = game === 'soft-body-slide' ? 30 : requestedDuration;
    const requestedDifficulty = numberInRange(body.difficulty ?? body.rings, definition.metricDefault, definition.metricMin, definition.metricMax);
    const difficulty = game === 'soft-body-slide' ? 100 : requestedDifficulty;
    const seed = numberInRange(body.seed, crypto.randomInt(100_000, 999_999_999), 1, 2_147_483_647);
    const theme = body.theme && ['neon', 'sunset', 'ice'].includes(body.theme) ? body.theme : 'neon';
    const soundPack = body.soundPack && ['auto', 'meme', 'funny', 'arcade', 'impact', 'asmr'].includes(body.soundPack) ? body.soundPack : 'auto';
    const defaultMusicMode = game === 'shape-tunnel' || game === 'soft-body-slide'
      ? 'continuous'
      : 'hit-reveal';
    const musicMode = body.musicMode === 'hit-reveal' || body.musicMode === 'continuous'
      ? body.musicMode
      : defaultMusicMode;
    const musicVolume = numberInRange(Number(body.musicVolume) * 100, 55, 0, 100) / 100;
    const musicProfile = body.musicProfile ?? 'original';
    if (!['edit-auto', 'edit-sad', 'edit-revenge', 'auto', 'revenge', 'sad-english', 'original'].includes(musicProfile)) {
      return NextResponse.json({ ok: false, error: 'Playlist vocale invalide.' }, { status: 400 });
    }
    if (musicProfile.startsWith('edit-') && (game !== 'soft-body-slide' || musicVolume <= 0)) {
      return NextResponse.json({ ok: false, error: 'Les voix d’edit nécessitent Souplesse 3D et un volume supérieur à zéro.' }, { status: 400 });
    }
    if (musicProfile.startsWith('edit-') && body.musicFile) {
      return NextResponse.json({ ok: false, error: 'Choisis la bibliothèque de voix ou un fichier musical, pas les deux.' }, { status: 400 });
    }
    const title = String(body.title || definition.defaultHook).trim().slice(0, 52) || definition.defaultHook;
    const obstacleKeys = ['auto', 'moving-slide', 'stair-cascade', 'v-stairs', 'pipe-bend', 'peg-grid', 'twin-gears', 'compression-ring'] as const;
    const obstacle = body.obstacle && obstacleKeys.includes(body.obstacle) ? body.obstacle : 'auto';
    const filename = `${game}-${seed}-${randomId()}.mp4`;
    const output = path.join(RENDERS_DIR, filename);
    const script = path.join(process.cwd(), 'scripts', game === 'soft-body-slide' ? 'render-premium-3d.py' : 'render-ball-escape.py');

    await fs.mkdir(RENDERS_DIR, { recursive: true });
    let musicPath: string | undefined;
    let musicTitle: string | null = null;
    let musicCredit: string | null = null;
    let musicSource: 'jamendo' | 'library' | 'original' = 'original';
    let musicNote: string | null = null;
    const requestedMusic = body.musicFile ?? (game === 'soft-body-slide' ? '' : '__discover__');
    if (requestedMusic === '__discover__') {
      try {
        const discovered = await discoverLicensedMusic(seed, game === 'shape-tunnel' || game === 'soft-body-slide' ? 'peaceful' : 'energetic');
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
      '--game', game,
      '--duration', String(duration),
      '--difficulty', String(difficulty),
      '--seed', String(seed),
      '--theme', theme,
      '--sound-pack', soundPack,
      '--title', title,
      '--music-volume', String(musicVolume),
      '--music-mode', musicMode,
    ];
    if (game === 'soft-body-slide') rendererArgs.push('--obstacle', obstacle, '--music-profile', musicProfile);
    if (musicPath) rendererArgs.push('--music', musicPath);
    const renderer = await runRenderer(rendererArgs);
    let rendererMetadata: {
      sound_pack?: string;
      duration?: number;
      music?: string;
      music_generated?: boolean;
      music_profile?: string;
      music_provider?: string;
      music_credit?: string;
      music_source_url?: string;
      music_mode?: string;
      music_hits?: number;
      completed_at?: number | null;
      outcome?: RenderOutcome;
      units_completed?: number;
      units_total?: number;
      variation_version?: number;
      variation_fingerprint?: string;
      variant_key?: string;
      variant_label?: string;
      variant_shape?: string;
      variant_ramp?: string;
      variant_palette?: string;
      variant_receiver?: string;
      variant_obstacle?: string;
      variant_obstacle_label?: string;
      variant_source_video?: string;
      stage_preset?: string;
      softness_stages?: number[];
    } = {};
    try {
      const lastLine = renderer.stdout.trim().split(/\r?\n/).at(-1);
      if (lastLine) rendererMetadata = JSON.parse(lastLine);
    } catch {}
    if (!musicTitle && rendererMetadata.music_generated) musicTitle = rendererMetadata.music || 'Original generated track';
    const stat = await fs.stat(output);
    const captionBase = `${title} Run #${seed}. Did you predict the ending?`;
    return NextResponse.json({
      ok: true,
      filename,
      size: stat.size,
      duration: rendererMetadata.duration || duration,
      seed,
      game,
      gameName: definition.name,
      difficulty,
      metricLabel: definition.metricLabel,
      unitsCompleted: rendererMetadata.units_completed || 0,
      unitsTotal: rendererMetadata.units_total || difficulty,
      rings: game === 'ball-escape' ? difficulty : undefined,
      theme,
      soundPack: rendererMetadata.sound_pack || soundPack,
      musicMode: rendererMetadata.music_mode || musicMode,
      musicHits: rendererMetadata.music_hits || 0,
      completedAt: rendererMetadata.completed_at ?? null,
      outcome: rendererMetadata.outcome ?? null,
      musicUsed: musicPath ? path.basename(musicPath) : rendererMetadata.music || null,
      musicTitle: musicTitle || rendererMetadata.music || null,
      musicSource: rendererMetadata.music_provider || musicSource,
      musicCredit: musicCredit || rendererMetadata.music_credit || null,
      musicProfile: rendererMetadata.music_profile || null,
      musicSourceUrl: rendererMetadata.music_source_url || null,
      musicNote,
      variationVersion: rendererMetadata.variation_version || null,
      variationFingerprint: rendererMetadata.variation_fingerprint || null,
      variantKey: rendererMetadata.variant_key || null,
      variantLabel: rendererMetadata.variant_label || null,
      variantShape: rendererMetadata.variant_shape || null,
      variantRamp: rendererMetadata.variant_ramp || null,
      variantPalette: rendererMetadata.variant_palette || null,
      variantReceiver: rendererMetadata.variant_receiver || null,
      variantObstacle: rendererMetadata.variant_obstacle || null,
      variantObstacleLabel: rendererMetadata.variant_obstacle_label || null,
      variantSourceVideo: rendererMetadata.variant_source_video || null,
      stagePreset: rendererMetadata.stage_preset || null,
      softnessStages: rendererMetadata.softness_stages || null,
      native3d: game === 'soft-body-slide' ? rendererMetadata : undefined,
      title,
      youtubeTitle: `${title} #shorts`,
      caption: (musicCredit || rendererMetadata.music_credit) ? `${captionBase}\n${musicCredit || rendererMetadata.music_credit}` : captionBase,
      tags: ['#satisfying', '#simulation', '#hypnotic', ...definition.tags, '#shorts'],
    });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  } finally {
    rendering = false;
  }
}
