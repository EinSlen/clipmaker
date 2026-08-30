#!/usr/bin/env node

const path = require('node:path');
const { spawn } = require('node:child_process');

const RECEIPT_PREFIX = 'CLIPMAKER_RECEIPT:';
const FAILURE_PREFIX = 'CLIPMAKER_FAILURE:';
const PROVIDERS = new Set(['auto', 'tiktok-web-upload', 'tiktok-studio-browser']);

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

function prefixedJson(output, prefix) {
  const line = String(output || '').split(/\r?\n/).reverse().find((entry) => entry.startsWith(prefix));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(prefix.length));
  } catch {
    return null;
  }
}

function parseReceipt(output, username) {
  const source = prefixedJson(output, RECEIPT_PREFIX);
  if (!source || !source.raw || typeof source.raw !== 'object') return null;
  const provider = String(source.provider || '');
  const platformPostId = String(source.platformPostId || '');
  const releaseUrl = String(source.releaseUrl || '');
  const privacy = source.raw.privacy === 'public' ? 'public' : 'private';
  const expectedUrl = `https://www.tiktok.com/@${username}/video/${platformPostId}`;
  if (!['tiktok-web-upload', 'tiktok-studio-browser'].includes(provider)
    || !/^\d{12,25}$/.test(platformPostId)
    || releaseUrl !== expectedUrl
    || Number(source.raw.statusCode) !== 0) return null;
  if (provider === 'tiktok-studio-browser'
    && (source.raw.verifiedInStudio !== true
      || source.raw.account !== username
      || !['post-response', 'studio-content'].includes(source.raw.evidence))) return null;
  if (provider === 'tiktok-web-upload') {
    const directApiProof = Boolean(String(source.raw.creationId || ''))
      && /^\d{12,25}$/.test(String(source.raw.uploadVideoId || ''));
    const recoveredProof = source.raw.verifiedInStudio === true
      && source.raw.account === username
      && source.raw.evidence === 'studio-content';
    if (!directApiProof && !recoveredProof) return null;
  }
  return { ...source, provider, platformPostId, releaseUrl, raw: { ...source.raw, privacy, statusCode: 0 } };
}

function parseFailure(output) {
  const source = prefixedJson(output, FAILURE_PREFIX);
  if (!source || source.provider !== 'tiktok-web-upload') return null;
  return {
    stage: String(source.stage || 'unknown'),
    commitAttempted: source.commitAttempted === true,
    safeToFallback: source.safeToFallback === true,
  };
}

function runProcess(command, args, { cwd, timeoutMs }) {
  return new Promise((resolve) => {
    const child = spawn(command, args, { cwd, windowsHide: true });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const append = (current, chunk) => (current + chunk.toString()).slice(-64 * 1024);
    child.stdout.on('data', (chunk) => { stdout = append(stdout, chunk); });
    child.stderr.on('data', (chunk) => { stderr = append(stderr, chunk); });
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);
    child.on('error', (error) => {
      clearTimeout(timeout);
      resolve({ code: -1, stdout, stderr: `${stderr}\n${error}`, timedOut });
    });
    child.on('close', (code) => {
      clearTimeout(timeout);
      resolve({ code: Number.isInteger(code) ? code : -1, stdout, stderr, timedOut });
    });
  });
}

function diagnostic(label, result) {
  const clean = `${result.stderr}\n${result.stdout}`
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith(RECEIPT_PREFIX) && !line.startsWith(FAILURE_PREFIX))
    .slice(-20)
    .join('\n');
  process.stderr.write(`[${label}] exit=${result.code}${result.timedOut ? ' timeout' : ''}${clean ? `\n${clean}` : ''}\n`);
}

function emitReceipt(receipt) {
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify(receipt)}\n`);
}

async function runStudio(studioScript, vendorRoot, args, command = 'upload') {
  const studioArgs = [studioScript, command, '--users', args.users, '--visibility', args.visibility];
  if (command === 'upload') studioArgs.push('--video', args.video, '--title', args.title);
  if (command === 'verify-recent') studioArgs.push('--since', String(args.since));
  return runProcess(process.execPath, studioArgs, { cwd: vendorRoot, timeoutMs: 9 * 60_000 });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const username = String(args.users || '').trim();
  const video = path.resolve(String(args.video || ''));
  const title = String(args.title || '').trim();
  const visibility = String(args.visibility) === '0' ? '0' : '1';
  const provider = String(args.provider || process.env.TIKTOK_UPLOAD_PROVIDER || 'auto');
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) throw new Error('Invalid TikTok account name.');
  if (!video || !title) throw new Error('TikTok video and caption are required.');
  if (!PROVIDERS.has(provider)) throw new Error(`Unsupported TikTok provider: ${provider}.`);

  const repositoryRoot = process.env.REPO_ROOT
    ? path.resolve(process.env.REPO_ROOT)
    : path.resolve(__dirname, '..', '..');
  const vendorRoot = path.join(repositoryRoot, 'vendor', 'TiktokAutoUploader');
  const studioScript = path.join(vendorRoot, 'tiktok_uploader', 'studio-upload.cjs');
  const startedAt = Date.now();
  const common = { users: username, video, title, visibility };

  if (provider !== 'tiktok-studio-browser') {
    const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const rawArgs = [
      'cli.py', 'upload', '--users', username, '-v', video, '-t', title,
      '--visibility', visibility,
    ];
    if (args.musicId) rawArgs.push('--music-id', String(args.musicId));
    const raw = await runProcess(python, rawArgs, { cwd: vendorRoot, timeoutMs: 5 * 60_000 });
    const rawReceipt = raw.code === 0 ? parseReceipt(raw.stdout, username) : null;
    if (rawReceipt) {
      emitReceipt(rawReceipt);
      return;
    }
    diagnostic('tiktok-web-upload', raw);
    if (provider === 'tiktok-web-upload') throw new Error('The TikTok API uploader did not return a valid receipt.');

    const failure = parseFailure(raw.stdout);
    if (!failure?.safeToFallback) {
      const verification = await runStudio(studioScript, vendorRoot, {
        ...common, since: startedAt,
      }, 'verify-recent');
      const recovered = verification.code === 0 ? parseReceipt(verification.stdout, username) : null;
      if (recovered) {
        emitReceipt(recovered);
        return;
      }
      diagnostic('tiktok-studio-verification', verification);
      throw new Error('TikTok API result is ambiguous; Studio fallback was blocked to prevent a duplicate post.');
    }
    if (args.musicId) {
      throw new Error(`TikTok API failed safely at ${failure.stage}; Studio cannot preserve the requested official sound.`);
    }
    process.stderr.write(`[tiktok-auto] API failed safely at ${failure.stage}; using verified Studio fallback.\n`);
  }

  const studio = await runStudio(studioScript, vendorRoot, common, 'upload');
  const studioReceipt = studio.code === 0 ? parseReceipt(studio.stdout, username) : null;
  if (!studioReceipt) {
    diagnostic('tiktok-studio-browser', studio);
    throw new Error('TikTok Studio fallback did not return a verified receipt.');
  }
  emitReceipt(studioReceipt);
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}

module.exports = { parseArgs, parseReceipt, parseFailure };
