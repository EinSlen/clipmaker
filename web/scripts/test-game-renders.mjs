import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
const scriptsDirectory = fileURLToPath(new URL('.', import.meta.url));
const webDirectory = fileURLToPath(new URL('..', import.meta.url));

function run(command, args, { includeStderr = false, ...options } = {}) {
  const result = spawnSync(command, args, { cwd: webDirectory, encoding: 'utf8', stdio: 'pipe', ...options });
  if (result.status !== 0) {
    process.stderr.write(result.stdout || '');
    process.stderr.write(result.stderr || '');
    throw new Error(`${command} exited with ${result.status}`);
  }
  return (includeStderr ? `${result.stdout}${result.stderr}` : result.stdout).trim();
}

process.stdout.write('Running deterministic engine tests...\n');
const unitOutput = run(python, ['-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_game_variants.py', '-v'], { includeStderr: true });
process.stdout.write(`${unitOutput}\n`);

if (!process.argv.includes('--smoke')) process.exit(0);

const catalogSource = readFileSync(join(webDirectory, 'lib', 'game-catalog.ts'), 'utf8');
const allGameIds = [...catalogSource.matchAll(/\bid:\s*['"]([a-z-]+)['"]/g)].map((match) => match[1]);
const gameIds = allGameIds.filter((gameId) => gameId !== 'soft-body-slide');
assert.deepEqual(gameIds, ['ball-escape', 'shape-tunnel', 'laser-dodge', 'boss-battle']);
const outputDirectory = mkdtempSync(join(tmpdir(), 'clipmaker-render-smoke-'));
const results = [];

try {
  for (const [index, gameId] of gameIds.entries()) {
    const output = join(outputDirectory, `${gameId}.mp4`);
    process.stdout.write(`[${index + 1}/${gameIds.length}] Rendering ${gameId}...\n`);
    const stdout = run(python, [
      join(scriptsDirectory, 'render-ball-escape.py'),
      '--output', output,
      '--game', gameId,
      '--duration', '5',
      '--difficulty', '48',
      '--seed', String(700000 + index),
      '--theme', ['neon', 'sunset', 'ice'][index % 3],
      '--sound-pack', 'auto',
      '--music-mode', index % 2 ? 'continuous' : 'hit-reveal',
      '--title', 'AUTOMATED QUALITY TEST',
    ], {
      env: { ...process.env, GAME_RENDER_WIDTH: '270', GAME_RENDER_HEIGHT: '480', GAME_RENDER_FPS: '8' },
    });
    const metadata = JSON.parse(stdout.split(/\r?\n/).at(-1));
    const probe = JSON.parse(run('ffprobe', [
      '-v', 'error', '-show_entries', 'stream=codec_type,codec_name,width,height,pix_fmt,sample_rate',
      '-show_entries', 'format=duration,size', '-of', 'json', output,
    ]));
    const video = probe.streams.find((stream) => stream.codec_type === 'video');
    const audio = probe.streams.find((stream) => stream.codec_type === 'audio');
    assert.equal(metadata.ok, true);
    assert.equal(metadata.game, gameId);
    assert.ok(metadata.events > 0);
    assert.ok(metadata.music_hits > 0);
    assert.equal(video.codec_name, 'h264');
    assert.equal(video.width, 1080);
    assert.equal(video.height, 1920);
    assert.equal(video.pix_fmt, 'yuv420p');
    assert.equal(audio.codec_name, 'aac');
    assert.equal(audio.sample_rate, '48000');
    results.push({ game: gameId, duration: Number(probe.format.duration), bytes: Number(probe.format.size), hits: metadata.music_hits });
  }
  process.stdout.write(`${JSON.stringify({ ok: true, games: results }, null, 2)}\n`);
} finally {
  rmSync(outputDirectory, { recursive: true, force: true });
}
