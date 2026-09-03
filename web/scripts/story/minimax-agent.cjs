#!/usr/bin/env node

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const RECEIPT_PREFIX = 'CLIPMAKER_MINIMAX:';
const CREATE_URL = process.env.MINIMAX_CREATE_URL || 'https://hailuoai.video/create/text-to-video';
const GALLERY_URL = process.env.MINIMAX_GALLERY_URL || 'https://hailuoai.video/mine';
const REPO_ROOT = process.env.REPO_ROOT
  ? path.resolve(process.env.REPO_ROOT)
  : path.resolve(__dirname, '..', '..', '..');
const PROFILE_DIR = process.env.MINIMAX_PROFILE_DIR
  || path.join(REPO_ROOT, '.minimax-browser', 'auth-profile');
// A Chromium profile is far too large for a secret, so the pipeline travels
// with the cookies alone, like the TikTok session file does.
const SESSION_FILE = process.env.MINIMAX_SESSION_FILE
  ? path.resolve(process.env.MINIMAX_SESSION_FILE)
  : path.join(REPO_ROOT, 'web', 'data', 'auth', 'minimax-session.json');
const SESSION_DOMAIN = /(^|\.)(hailuoai\.(video|com)|minimaxi?\.(io|com|chat))$/i;
const SECRET_NAME = 'MINIMAX_COOKIES_B64';
const TEMPORARY_PROFILE = Symbol('temporaryProfile');
const PROMO_PATTERN = /public_assets|\/guide|\/blog|\/banner|\/pages\//i;
const CLIP_PATTERN = /^clip-(\d+)\.mp4$/i;
const CREATIONS_API = /\/api\/feed\/creation\/my/;
const EQUITY_API = /\/v1\/api\/user\/equity/;
// The site defaults to a 21:9 cinematic frame, which is useless for a vertical
// short. Ratio, duration and resolution are interface settings kept per model
// in local storage, not something a prompt can ask for.
const SETTINGS_KEY = 'VIDEO_SETTINGS_BY_MODEL_V2';
const SETTINGS_MODELS = ['hailuo3.0-t2v', 'hailuo3.0-i2v'];
const RATIO = process.env.MINIMAX_RATIO || '9:16';
const RESOLUTION = process.env.MINIMAX_RESOLUTION || '1080';
const CLIP_SECONDS = Math.max(5, Math.min(10, Number(process.env.MINIMAX_DURATION) || 10));

function parseArgs(argv) {
  const result = { command: argv[0] && !argv[0].startsWith('--') ? argv[0] : 'doctor' };
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

function receipt(payload) {
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify(payload)}\n`);
}

function log(message) {
  process.stderr.write(`${message}\n`);
}

function playwright() {
  try {
    return require('playwright-chromium');
  } catch {
    return require(path.join(
      REPO_ROOT, 'vendor', 'TiktokAutoUploader', 'tiktok_uploader',
      'tiktok-signature', 'node_modules', 'playwright-chromium',
    ));
  }
}

// A stock Chromium build gets refused by the Google sign-in flow, so the real
// installed browser is preferred and the bundled one is only a last resort.
function chromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

// Mirrors the TikTok agent: whatever the browser or the secret hands over is
// coerced into the shape Playwright accepts, and a dead expiry becomes a
// session cookie instead of a cookie the browser drops on sight.
function normaliseCookies(source) {
  if (!Array.isArray(source)) throw new Error('Session Minimax invalide : un tableau de cookies est attendu.');
  const now = Date.now() / 1000;
  return source
    .filter((cookie) => cookie && cookie.name && cookie.value)
    .map((cookie) => {
      const expires = Number(cookie.expires ?? cookie.expiry ?? cookie.expirationDate ?? -1);
      const sameSite = ['Strict', 'Lax', 'None'].includes(cookie.sameSite) ? cookie.sameSite : 'Lax';
      return {
        name: String(cookie.name),
        value: String(cookie.value),
        domain: String(cookie.domain || '.hailuoai.video'),
        path: String(cookie.path || '/'),
        expires: Number.isFinite(expires) && expires > now ? expires : -1,
        httpOnly: Boolean(cookie.httpOnly),
        secure: cookie.secure !== false,
        sameSite,
      };
    });
}

// Measured by diffing a signed out profile against a signed in one: the whole
// difference is `_token`. Without it the browser opens anonymous and every clip
// burns its full timeout before failing, so a stale session fails loudly here.
const AUTH_COOKIE = process.env.MINIMAX_AUTH_COOKIE || '_token';

function hasAuthCookie(cookies) {
  return cookies.some((cookie) => cookie.name === AUTH_COOKIE);
}

function sessionSource() {
  if (process.env[SECRET_NAME]) return `secret ${SECRET_NAME}`;
  if (fs.existsSync(SESSION_FILE)) return `fichier ${SESSION_FILE}`;
  return `profil ${PROFILE_DIR}`;
}

function storedSession() {
  const encoded = process.env[SECRET_NAME];
  const raw = encoded
    ? JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'))
    : (fs.existsSync(SESSION_FILE) ? JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8')) : null);
  if (!raw) return null;
  const cookies = normaliseCookies(raw);
  if (!hasAuthCookie(cookies)) {
    throw new Error(`Session Minimax sans cookie ${AUTH_COOKIE} (${sessionSource()}). Relance login puis session.`);
  }
  return cookies;
}

async function exportSession(context) {
  const cookies = (await context.cookies())
    .filter((cookie) => SESSION_DOMAIN.test(String(cookie.domain || '').replace(/^\./, '')));
  const normalised = normaliseCookies(cookies);
  if (!hasAuthCookie(normalised)) log(`Attention : aucun cookie ${AUTH_COOKIE} dans cet export, la pipeline le refusera.`);
  await fsp.mkdir(path.dirname(SESSION_FILE), { recursive: true });
  await fsp.writeFile(SESSION_FILE, `${JSON.stringify(normalised, null, 2)}\n`, { mode: 0o600 });
  return cookies;
}

function pushGitHubSecret(cookies, repo) {
  const result = spawnSync('gh', ['secret', 'set', SECRET_NAME, '--repo', repo], {
    input: Buffer.from(JSON.stringify(normaliseCookies(cookies)), 'utf8').toString('base64'),
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(String(result.stderr || result.stdout || 'gh secret set a echoue').trim());
  }
}

async function closeContext(context) {
  const temporary = context[TEMPORARY_PROFILE];
  await context.close().catch(() => {});
  if (temporary) await fsp.rm(temporary, { recursive: true, force: true });
}

// Two ways in. Locally the persistent profile holds the session. In a pipeline
// there is no profile, so a throwaway one is built and the exported cookies are
// injected into it. `profile` forces the local route, which is what the login
// and export commands need.
async function openContext({ mode = 'auto' } = {}) {
  const { chromium } = playwright();
  const cookies = mode === 'profile' ? null : storedSession();
  const profileDir = cookies
    ? await fsp.mkdtemp(path.join(os.tmpdir(), 'minimax-profile-'))
    : PROFILE_DIR;
  await fsp.mkdir(profileDir, { recursive: true });
  const executablePath = chromiumExecutable();
  const context = await chromium.launchPersistentContext(profileDir, {
    // The generation UI never settles in headless mode and the sign-in flow
    // refuses it outright, so the window is always real. Use Xvfb on a runner.
    headless: false,
    ...(executablePath ? { executablePath } : {}),
    viewport: null,
    acceptDownloads: true,
    locale: 'en-US',
    args: [
      '--disable-blink-features=AutomationControlled',
      '--window-size=1500,980',
      '--no-first-run',
      '--no-default-browser-check',
    ],
  });
  context.setDefaultTimeout(45000);
  // Seeded before the app boots, so the create page opens already set to a
  // vertical frame instead of having to be driven through a dropdown.
  await context.addInitScript(({ key, models, settings }) => {
    try {
      const current = JSON.parse(window.localStorage.getItem(key) || '{}');
      for (const model of models) current[model] = { ...(current[model] || {}), ...settings };
      window.localStorage.setItem(key, JSON.stringify(current));
    } catch {}
  }, {
    key: SETTINGS_KEY,
    models: SETTINGS_MODELS,
    settings: { ratio: RATIO, duration: CLIP_SECONDS, resolution: RESOLUTION, quality: '' },
  });
  if (cookies) {
    await context.addCookies(cookies);
    context[TEMPORARY_PROFILE] = profileDir;
  }
  return context;
}

async function currentPage(context) {
  const existing = context.pages().find((page) => !page.isClosed());
  return existing || context.newPage();
}

async function dismissOverlays(page) {
  // The landing page stacks a cookie banner and a welcome dialog, and both
  // swallow real clicks on the composer underneath.
  const labels = [/accept all/i, /accept/i, /agree/i, /got it/i, /^ok$/i, /tout accepter/i];
  for (const label of labels) {
    const button = page.getByRole('button', { name: label }).first();
    if (await button.isVisible().catch(() => false)) {
      await button.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(400);
    }
  }
  for (const selector of ['[aria-label="close-quick-select"]', '[aria-label="Close"]', '[aria-label="close"]', '.ant-modal-close']) {
    const close = page.locator(selector).first();
    if (await close.isVisible().catch(() => false)) {
      await close.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(300);
    }
  }
  await dismissActivityModal(page);
}

// A promotional modal appears on the first signed in load and swallows every
// click on the create button underneath. It only shows up once in a while, so
// each recourse is tried in turn rather than relying on one close control.
async function dismissActivityModal(page) {
  const wrap = page.locator('.ant-modal-wrap, [class*="activity-modal"]').first();
  if (!(await wrap.isVisible().catch(() => false))) return false;
  const inner = wrap.locator('.ant-modal-close, [aria-label*="close" i], [class*="close"]').first();
  if (await inner.isVisible().catch(() => false)) {
    await inner.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(500);
  }
  if (!(await wrap.isVisible().catch(() => false))) return true;
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(500);
  if (!(await wrap.isVisible().catch(() => false))) return true;
  await page.locator('.ant-modal-mask').first().click({ timeout: 3000, force: true }).catch(() => {});
  await page.waitForTimeout(500);
  return !(await wrap.isVisible().catch(() => false));
}

// The composer is a contenteditable div carrying a stable id, checked against
// the live page. The shape heuristic below is the fallback if that id moves.
async function findComposer(page) {
  const pinned = page.locator(process.env.MINIMAX_PROMPT_SELECTOR || '#video-create-textarea').first();
  if (await pinned.isVisible().catch(() => false)) return pinned;
  if (process.env.MINIMAX_PROMPT_SELECTOR) {
    throw new Error(`MINIMAX_PROMPT_SELECTOR ne correspond a rien de visible : ${process.env.MINIMAX_PROMPT_SELECTOR}`);
  }
  const candidates = page.locator('textarea, [contenteditable="true"]');
  const count = await candidates.count();
  let best = null;
  let bestArea = 0;
  for (let index = 0; index < count; index += 1) {
    const candidate = candidates.nth(index);
    if (!(await candidate.isVisible().catch(() => false))) continue;
    const box = await candidate.boundingBox().catch(() => null);
    if (!box) continue;
    const area = box.width * box.height;
    if (area > bestArea) {
      bestArea = area;
      best = candidate;
    }
  }
  if (!best) throw new Error('Zone de prompt introuvable. Lance la commande probe puis fixe MINIMAX_PROMPT_SELECTOR.');
  return best;
}

async function findSubmit(page) {
  if (process.env.MINIMAX_SUBMIT_SELECTOR) {
    return page.locator(process.env.MINIMAX_SUBMIT_SELECTOR).first();
  }
  const names = [/^create$/i, /^generate$/i, /create video/i, /generate video/i];
  for (const name of names) {
    const button = page.getByRole('button', { name }).first();
    if (await button.isVisible().catch(() => false)) return button;
  }
  // The site styles some controls as plain divs, so a text match is the last
  // resort before giving up.
  const labelled = page.getByText(/^create$/i).first();
  if (await labelled.isVisible().catch(() => false)) return labelled;
  throw new Error('Bouton de generation introuvable. Lance la commande probe puis fixe MINIMAX_SUBMIT_SELECTOR.');
}

// The create page renders in full for a signed out visitor, composer included,
// so the only reliable marker is the Sign In control, itself a styled div.
// The account endpoint carries the balance and the base price of one video.
// The price actually charged for the current settings is the badge beside the
// create button, which is the base price doubled for a ten second clip, so the
// badge wins and the computed value is only a fallback.
async function readAccount(page, { navigate = true } = {}) {
  const waiter = page.waitForResponse((response) => EQUITY_API.test(response.url()), { timeout: 45000 });
  await (navigate
    ? page.goto(CREATE_URL, { waitUntil: 'domcontentloaded' })
    : page.reload({ waitUntil: 'domcontentloaded' })).catch(() => {});
  const response = await waiter.catch(() => null);
  const payload = response ? await response.json().catch(() => null) : null;
  const data = (payload && payload.data) || {};
  const balance = Number(data.totalCredits);
  const videoCost = Number(data.videoCost) || 0;
  await page.waitForTimeout(2500);
  const badge = await page.evaluate(() => {
    const button = Array.from(document.querySelectorAll('button')).find((node) => /create/i.test(node.innerText || ''));
    const text = String(button?.parentElement?.innerText || '').replace(/\s+/g, ' ');
    // The price sits immediately before the label, and the settings row above
    // it also holds numbers, so the label anchors the match.
    const anchored = text.match(/(\d{1,4})\s*(?:credits?)?\s*create/i);
    return anchored ? Number(anchored[1]) : null;
  }).catch(() => null);
  const computed = clipPrice(videoCost);
  return {
    balance: Number.isFinite(balance) ? balance : null,
    unitCost: badge || computed || Number(process.env.MINIMAX_CREDITS_PER_CLIP) || null,
    videoCost: videoCost || null,
    plan: String(data.memberName || '') || null,
    queueLength: Number(data.queueLength) || 0,
    trialExpires: Number(data.trialExpireTime)
      ? new Date(Number(data.trialExpireTime)).toISOString().slice(0, 10)
      : null,
  };
}

function affordableClips(account) {
  if (!account || account.balance === null || !account.unitCost) return null;
  return Math.floor(account.balance / account.unitCost);
}

async function readSettings(page) {
  return page.evaluate((key) => {
    try {
      return JSON.parse(window.localStorage.getItem(key) || '{}')['hailuo3.0-t2v'] || null;
    } catch {
      return null;
    }
  }, SETTINGS_KEY).catch(() => null);
}

// The composer is a Slate editor. Typing key by key silently loses everything
// after the first characters, because each keystroke re-renders and resets the
// selection: a full prompt reached the model as two letters. insertText posts
// the whole string as a single input event, and the result is read back because
// a truncated prompt still generates a plausible looking clip.
async function fillComposer(page, composer, prompt) {
  await composer.click();
  await page.keyboard.press('Control+A').catch(() => {});
  await page.keyboard.press('Delete').catch(() => {});
  await page.keyboard.insertText(prompt);
  await page.waitForTimeout(600);
  const written = String(await composer.innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
  const expected = prompt.replace(/\s+/g, ' ').trim();
  if (written.length < Math.floor(expected.length * 0.9)) {
    throw new Error(`Prompt tronque a la saisie : ${written.length} caracteres sur ${expected.length}.`);
  }
  return written;
}

// An overlay that intercepts this one click would otherwise cost the whole
// episode, so the click is retried once overlays are cleared and then, as a
// last resort, dispatched directly on the element.
async function clickSubmit(page, submit) {
  const first = await submit.click({ timeout: 20000 }).then(() => true).catch((error) => error);
  if (first === true) return 'clic direct';
  await dismissOverlays(page);
  const second = await submit.click({ timeout: 20000 }).then(() => true).catch((error) => error);
  if (second === true) return 'clic apres fermeture des overlays';
  const dispatched = await submit.evaluate((node) => {
    node.click();
    return true;
  }).catch(() => false);
  if (!dispatched) throw new Error(`Clic sur le bouton de generation impossible : ${second.message || second}`);
  return 'evenement DOM';
}

async function signedIn(page) {
  await dismissOverlays(page);
  for (const label of [/^sign in$/i, /^log in$/i, /^se connecter$/i]) {
    const control = page.getByText(label).first();
    if (await control.isVisible().catch(() => false)) return false;
  }
  return findComposer(page).then(() => true).catch(() => false);
}

async function download(context, url, outputFile, referer) {
  const response = await context.request.get(url, {
    headers: { referer, accept: 'video/mp4,video/*;q=0.9,*/*;q=0.8' },
    timeout: 180000,
  });
  if (!response.ok()) throw new Error(`Telechargement refuse (HTTP ${response.status()}) : ${url.slice(0, 120)}`);
  const body = await response.body();
  if (body.length < 20000) throw new Error(`Fichier trop petit (${body.length} octets), la generation a probablement echoue.`);
  await fsp.mkdir(path.dirname(outputFile), { recursive: true });
  await fsp.writeFile(outputFile, body);
  return body.length;
}

function probeVideo(file) {
  const result = spawnSync(process.env.FFPROBE_PATH || 'ffprobe', [
    '-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'stream=width,height', '-show_entries', 'format=duration',
    '-of', 'json', file,
  ], { encoding: 'utf8', windowsHide: true });
  if (result.status !== 0) return null;
  try {
    const payload = JSON.parse(result.stdout);
    const stream = (payload.streams || [])[0] || {};
    return {
      width: Number(stream.width) || 0,
      height: Number(stream.height) || 0,
      duration: Number(payload.format && payload.format.duration) || 0,
    };
  } catch {
    return null;
  }
}

// Measured on the live site: the create page lazy loads promotional reels while
// a job runs, and they have the exact shape of a result. A candidate is only
// kept once its path is not one of those and the bytes on disk match what the
// prompt asked for, otherwise the episode gets assembled out of adverts.
async function claimCandidate(context, url, outputFile, referer, wantPortrait) {
  if (PROMO_PATTERN.test(url)) return { ok: false, reason: 'contenu promotionnel du site' };
  const allow = process.env.MINIMAX_RESULT_PATTERN ? new RegExp(process.env.MINIMAX_RESULT_PATTERN, 'i') : null;
  if (allow && !allow.test(url)) return { ok: false, reason: 'hors MINIMAX_RESULT_PATTERN' };
  const temp = `${outputFile}.part`;
  let bytes = 0;
  try {
    bytes = await download(context, url, temp, referer);
  } catch (error) {
    await fsp.rm(temp, { force: true });
    return { ok: false, reason: error.message };
  }
  const info = probeVideo(temp);
  const discard = async (reason) => {
    await fsp.rm(temp, { force: true });
    return { ok: false, reason };
  };
  if (!info) return discard('fichier video illisible');
  if (info.duration < 2 || info.duration > 60) return discard(`duree hors bornes (${info.duration.toFixed(1)} s)`);
  if (wantPortrait && info.width >= info.height) {
    return discard(`format paysage ${info.width}x${info.height} alors que le prompt demande du 9:16`);
  }
  await fsp.rename(temp, outputFile);
  return { ok: true, bytes, info };
}

// Only the account's own creations appear in the feed, so a record id that was
// not there before the submit is unambiguously this generation. The earlier
// approach of watching for any new video on the page kept mistaking the site's
// own promotional reels for the result.
function creationRecords(payload) {
  const feeds = payload && payload.data && payload.data.feeds;
  if (!Array.isArray(feeds)) return [];
  return feeds.map((feed) => {
    const media = feed?.metaInfo?.videoMetaInfo?.mediaInfo || {};
    return {
      id: String(feed?.commonInfo?.id || ''),
      status: Number(feed?.commonInfo?.status),
      createTime: Number(feed?.commonInfo?.createTime) || 0,
      prompt: String(feed?.modelParameter?.videoParameter?.desc || ''),
      ratio: String(feed?.modelParameter?.videoParameter?.aspectRatio || ''),
      url: media.url || media.downloadURL?.watermarkURL || null,
      width: Number(media.width) || 0,
      height: Number(media.height) || 0,
    };
  }).filter((record) => record.id);
}

// The site signs its own API calls, so the list is obtained by letting the
// gallery fetch it and capturing the response, never by rebuilding the request.
async function readCreations(page, { reload = false } = {}) {
  const waiter = page.waitForResponse((response) => CREATIONS_API.test(response.url()), { timeout: 60000 });
  const navigation = reload
    ? page.reload({ waitUntil: 'domcontentloaded' })
    : page.goto(GALLERY_URL, { waitUntil: 'domcontentloaded' });
  await navigation.catch(() => {});
  const response = await waiter.catch(() => null);
  if (!response) return null;
  return creationRecords(await response.json().catch(() => null));
}

async function generateClip(context, prompt, outputFile, { timeoutMs = 600000 } = {}) {
  const page = await currentPage(context);
  const gallery = await context.newPage();
  try {
    const before = await readCreations(gallery);
    if (before === null) throw new Error("La liste des creations n'a pas repondu, session probablement expiree.");
    const known = new Set(before.map((record) => record.id));

    if (!/create/i.test(page.url())) await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded' });
    await dismissOverlays(page);
    const settings = await readSettings(page);
    if (settings && settings.ratio && settings.ratio !== RATIO) {
      log(`Attention : le site annonce le format ${settings.ratio} au lieu de ${RATIO}.`);
    }

    const composer = await findComposer(page);
    const written = await fillComposer(page, composer, prompt);
    const submit = await findSubmit(page);
    const how = await clickSubmit(page, submit);
    log(`Prompt envoye (${written.length} caracteres, ${how}), attente du rendu.`);

    const deadline = Date.now() + timeoutMs;
    let waited = false;
    while (Date.now() < deadline) {
      await page.waitForTimeout(20000);
      const records = await readCreations(gallery, { reload: waited });
      waited = true;
      const fresh = (records || []).filter((record) => !known.has(record.id));
      if (!fresh.length) continue;
      const ready = fresh.find((record) => record.url);
      if (!ready) {
        log(`Generation en cours (${fresh.length} enregistrement), statut ${fresh[0].status}.`);
        continue;
      }
      // Identity is settled by the record id, so orientation is reported rather
      // than used to accept or reject the file.
      if (ready.ratio && ready.ratio !== RATIO) {
        log(`Attention : clip rendu en ${ready.ratio} au lieu de ${RATIO} (${ready.width}x${ready.height}).`);
      }
      const claim = await claimCandidate(context, ready.url, outputFile, gallery.url(), false);
      if (!claim.ok) throw new Error(`Clip refuse (${claim.reason}) : ${ready.url.slice(0, 120)}`);
      return {
        file: outputFile,
        bytes: claim.bytes,
        recordId: ready.id,
        url: ready.url,
        ratio: ready.ratio,
        promptStored: ready.prompt,
        info: claim.info,
      };
    }
    throw new Error(`Aucun clip recupere apres ${Math.round(timeoutMs / 60000)} min.`);
  } finally {
    await gallery.close().catch(() => {});
  }
}
function readPrompts(planDir) {
  const source = fs.readFileSync(path.join(planDir, 'prompts.txt'), 'utf8');
  return source
    .split(/\r?\n\s*---\s*\r?\n/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

async function commandLogin(args) {
  const waitSeconds = Math.max(60, Math.min(1800, Number(args.wait) || 420));
  const context = await openContext({ mode: 'profile' });
  const page = await currentPage(context);
  await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded' }).catch(() => {});
  log('Connecte-toi dans la fenetre qui vient de s ouvrir.');
  log('Si Google refuse la connexion, passe par la connexion e-mail ou SMS du site.');
  log(`Session enregistree dans ${PROFILE_DIR}. Fenetre ouverte ${waitSeconds} s max.`);
  const deadline = Date.now() + waitSeconds * 1000;
  let ok = false;
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    if (await signedIn(page).catch(() => false)) {
      ok = true;
      break;
    }
  }
  // The cookies are exported straight away, so a successful login is usable by
  // the pipeline without a second manual step.
  const cookies = ok ? await exportSession(context) : [];
  await closeContext(context);
  receipt({
    ok,
    profileDir: PROFILE_DIR,
    ...(ok ? { sessionFile: SESSION_FILE, cookies: cookies.length } : { error: 'session-non-detectee' }),
  });
}

// Exports the cookies of an existing profile, and optionally stores them in the
// GitHub secret the workflow reads. Nothing is written while signed out, since
// an anonymous session would silently break every pipeline run.
async function commandSession(args) {
  const context = await openContext({ mode: 'profile' });
  try {
    const page = await currentPage(context);
    await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);
    const authenticated = await signedIn(page).catch(() => false);
    if (!authenticated && !args.force) {
      receipt({ ok: false, authenticated, error: 'profil non connecte, lance login (ou --force)' });
      return;
    }
    const cookies = await exportSession(context);
    const repo = String(args.repo || 'EinSlen/clipmaker').trim();
    if (args.githubSecret) pushGitHubSecret(cookies, repo);
    receipt({
      ok: cookies.length > 0,
      authenticated,
      sessionFile: SESSION_FILE,
      cookies: cookies.length,
      names: cookies.map((cookie) => cookie.name),
      secret: args.githubSecret ? `${SECRET_NAME}@${repo}` : null,
    });
  } finally {
    await closeContext(context);
  }
}

// `videoCost` is half the price of a five second clip, measured twice against
// the figure the interface displays: 30 announced for 60 charged at five
// seconds, and 120 at ten. Guessing low would start a run that cannot be paid
// for, so the price is derived with that factor rather than taken as is.
function clipPrice(videoCost) {
  return videoCost ? Math.round(videoCost * 2 * (CLIP_SECONDS / 5)) : null;
}

// The account endpoint answers to the session cookies alone, with no signature,
// so the balance can be watched without opening a window.
async function commandCredits(args) {
  const cookies = storedSession();
  if (!cookies) throw new Error(`Aucune session Minimax (${sessionSource()}). Lance login.`);
  const url = new URL('https://hailuoai.video/v1/api/user/equity');
  for (const [key, value] of Object.entries({
    device_platform: 'web', app_id: '3001', version_code: '22203', biz_id: '0',
    unix: `${Date.now()}`, lang: 'en',
  })) url.searchParams.set(key, value);
  const response = await fetch(url, {
    headers: {
      cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; '),
      referer: CREATE_URL,
      'user-agent': process.env.MINIMAX_USER_AGENT
        || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    },
  });
  if (!response.ok) throw new Error(`Solde illisible (HTTP ${response.status}).`);
  const data = (await response.json())?.data || {};
  const balance = Number(data.totalCredits);
  const videoCost = Number(data.videoCost) || 0;
  const unitCost = clipPrice(videoCost);
  const clips = Math.max(1, Number(args.clips) || 1);
  receipt({
    ok: Number.isFinite(balance),
    balance: Number.isFinite(balance) ? balance : null,
    unitCost,
    clipSeconds: CLIP_SECONDS,
    plan: String(data.memberName || '') || null,
    affordableClips: unitCost ? Math.floor(balance / unitCost) : null,
    needed: unitCost ? clips * unitCost : null,
    enough: Boolean(unitCost && balance >= clips * unitCost),
  });
}

async function commandDoctor() {
  const context = await openContext();
  try {
    const page = await currentPage(context);
    await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);
    const authenticated = await signedIn(page).catch(() => false);
    const composer = await findComposer(page).catch(() => null);
    const submit = await findSubmit(page).then(() => true).catch(() => false);
    const settings = await readSettings(page);
    // A prompt that arrives truncated still produces a plausible clip, so the
    // preflight writes a full length probe and reads it back. Nothing is
    // submitted, so this costs no credit.
    const probe = `Preflight ${'x'.repeat(240)} fin`;
    let promptOk = false;
    let promptError = null;
    if (composer) {
      promptOk = await fillComposer(page, composer, probe).then(() => true).catch((error) => {
        promptError = error.message;
        return false;
      });
      await composer.click().catch(() => {});
      await page.keyboard.press('Control+A').catch(() => {});
      await page.keyboard.press('Delete').catch(() => {});
    }
    const account = await readAccount(page, { navigate: false }).catch(() => null);
    receipt({
      ok: authenticated && Boolean(composer) && submit && promptOk && settings?.ratio === RATIO,
      url: page.url(),
      authenticated,
      credits: account,
      affordableClips: affordableClips(account),
      composerFound: Boolean(composer),
      submitFound: submit,
      promptAccepted: promptOk,
      ...(promptError ? { promptError } : {}),
      settings: settings || null,
      expected: { ratio: RATIO, duration: CLIP_SECONDS, resolution: RESOLUTION },
      executable: chromiumExecutable(),
      session: sessionSource(),
    });
  } finally {
    await closeContext(context);
  }
}

// Dumps what the live page actually exposes, so the selectors above can be
// pinned to real markup instead of assumptions.
async function commandProbe(args) {
  const outDir = path.resolve(process.cwd(), String(args.out || 'renders/minimax-probe'));
  await fsp.mkdir(outDir, { recursive: true });
  const context = await openContext();
  try {
    const page = await currentPage(context);
    await page.goto(String(args.url || CREATE_URL), { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(Number(args.settle) || 6000);
    await dismissOverlays(page);
    const report = await page.evaluate(() => {
      const visible = (node) => {
        const box = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const describe = (node) => {
        const box = node.getBoundingClientRect();
        return {
          tag: node.tagName.toLowerCase(),
          id: node.id || null,
          className: typeof node.className === 'string' ? node.className.slice(0, 160) : null,
          text: (node.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80) || null,
          ariaLabel: node.getAttribute('aria-label'),
          placeholder: node.getAttribute('placeholder'),
          dataTestId: node.getAttribute('data-testid') || node.getAttribute('data-test-id'),
          box: { x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.width), h: Math.round(box.height) },
        };
      };
      const pick = (selector) => Array.from(document.querySelectorAll(selector)).filter(visible).map(describe);
      return {
        url: location.href,
        title: document.title,
        inputs: pick('textarea, [contenteditable="true"], input[type="text"]'),
        buttons: pick('button, [role="button"]').slice(0, 60),
        videos: Array.from(document.querySelectorAll('video, video source')).map((node) => node.currentSrc || node.src).filter(Boolean),
        creditText: Array.from(document.querySelectorAll('span, div'))
          .filter((node) => node.children.length === 0 && /credit|points?/i.test(node.textContent || ''))
          .filter(visible)
          .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60))
          .slice(0, 12),
      };
    });
    const reportFile = path.join(outDir, 'probe.json');
    await fsp.writeFile(reportFile, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    await fsp.writeFile(path.join(outDir, 'page.html'), await page.content(), 'utf8');
    await page.screenshot({ path: path.join(outDir, 'page.png') }).catch(() => {});
    receipt({ ok: true, reportFile, outDir, url: report.url, inputs: report.inputs.length, buttons: report.buttons.length });
  } finally {
    await closeContext(context);
  }
}

async function commandGenerate(args) {
  const prompt = String(args.prompt || '').trim();
  if (!prompt) throw new Error('--prompt "texte" est requis.');
  const outputFile = path.resolve(process.cwd(), String(args.output || 'renders/minimax-clip.mp4'));
  const timeoutMs = Math.max(60, Number(args.timeout) || 600) * 1000;
  const context = await openContext();
  try {
    receipt({ ok: true, ...(await generateClip(context, prompt, outputFile, { timeoutMs })) });
  } finally {
    await closeContext(context);
  }
}

// Already downloaded clips are kept, so a crash halfway through an episode only
// costs the clips that are actually missing.
async function commandPlan(args) {
  const planDir = path.resolve(process.cwd(), String(args.plan || ''));
  if (!args.plan) throw new Error('--plan <dossier du plan> est requis.');
  const prompts = readPrompts(planDir);
  if (!prompts.length) throw new Error(`Aucun prompt dans ${path.join(planDir, 'prompts.txt')}.`);
  const clipsDir = args.clipsDir ? path.resolve(process.cwd(), String(args.clipsDir)) : path.join(planDir, 'clips');
  await fsp.mkdir(clipsDir, { recursive: true });
  const limit = Math.max(1, Math.min(prompts.length, Number(args.limit) || prompts.length));
  const timeoutMs = Math.max(60, Number(args.timeout) || 600) * 1000;

  const produced = [];
  const skipped = [];
  const failed = [];
  const todo = [];
  for (let index = 0; index < limit; index += 1) {
    const outputFile = path.join(clipsDir, `clip-${String(index + 1).padStart(2, '0')}.mp4`);
    const existing = await fsp.stat(outputFile).catch(() => null);
    if (existing && existing.size > 20000) skipped.push(path.basename(outputFile));
    else todo.push({ index, outputFile });
  }

  // Resuming a finished episode must not open a browser at all.
  const context = todo.length ? await openContext() : null;
  let account = null;
  let budget = todo;
  try {
    if (context) {
      // Checked before the first prompt: a clip that cannot be paid for waits
      // out its whole timeout and reports nothing useful, so the balance is
      // turned into a clip count up front and the shortfall is named.
      account = await readAccount(await currentPage(context));
      const affordable = affordableClips(account);
      // All or nothing on purpose. Half an episode means the whole narration
      // crammed over a third of the runtime, which reads worse than the still
      // image fallback, and that fallback still produces a full length episode.
      if (affordable !== null && affordable < todo.length) {
        throw new Error(`Credits insuffisants : ${account.balance} disponibles, ${account.unitCost} par clip de ${CLIP_SECONDS} s, ${todo.length} clip(s) a produire (offre ${account.plan || 'inconnue'}).`);
      }
    }
    for (const { index, outputFile } of budget) {
      log(`Clip ${index + 1}/${limit}`);
      try {
        const result = await generateClip(context, prompts[index], outputFile, { timeoutMs });
        produced.push({ file: path.basename(result.file), bytes: result.bytes, source: result.source });
      } catch (error) {
        failed.push({ clip: index, error: error.message });
        // A quota wall fails every remaining clip the same way, so the run
        // stops and assemble still gets the clips already downloaded.
        if (/quota|credit|insufficient/i.test(error.message)) break;
      }
    }
  } finally {
    if (context) await closeContext(context);
  }
  // Clips left out by the budget are reported like any other miss, otherwise a
  // short episode looks like an unexplained one.
  for (const { index } of todo.slice(budget.length)) {
    failed.push({ clip: index, error: `non genere : ${account?.balance ?? '?'} credits pour ${account?.unitCost ?? '?'} par clip.` });
  }
  const available = (await fsp.readdir(clipsDir).catch(() => [])).filter((entry) => CLIP_PATTERN.test(entry));
  receipt({
    ok: available.length > 0,
    planDir,
    clipsDir,
    planned: prompts.length,
    budgeted: budget.length,
    produced,
    skipped,
    failed,
    credits: account,
    clipsAvailable: available.length,
  });
}

const COMMANDS = {
  login: commandLogin,
  session: commandSession,
  credits: commandCredits,
  doctor: commandDoctor,
  probe: commandProbe,
  generate: commandGenerate,
  plan: commandPlan,
};

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const handler = COMMANDS[args.command];
  if (!handler) throw new Error(`Commande inconnue : ${args.command}. Attendu : ${Object.keys(COMMANDS).join(', ')}.`);
  await handler(args);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  receipt({ ok: false, error: error.message });
  process.exit(1);
});
