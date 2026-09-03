#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const OUTPUT_PREFIX = 'CLIPMAKER_COMMENTS:';

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2);
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

function repoRoot() {
  return process.env.REPO_ROOT
    ? path.resolve(process.env.REPO_ROOT)
    : path.resolve(__dirname, '..', '..', '..');
}

function playwright() {
  const candidates = [
    'playwright-chromium',
    path.join(repoRoot(), 'vendor', 'TiktokAutoUploader', 'tiktok_uploader', 'tiktok-signature', 'node_modules', 'playwright-chromium'),
    '/opt/tiktok-signature/node_modules/playwright-chromium',
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {}
  }
  throw new Error('playwright-chromium is not installed.');
}

function chromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fs.existsSync(candidate));
  if (!executable) throw new Error('Chromium executable not found.');
  return executable;
}

function readCookies(username) {
  const filename = path.resolve(process.cwd(), 'CookiesDir', `tiktok_session-${username}.cookie`);
  if (!fs.existsSync(filename)) throw new Error(`TikTok session not found for ${username}.`);
  let source;
  try {
    source = JSON.parse(fs.readFileSync(filename, 'utf8'));
  } catch {
    const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const decoded = spawnSync(python, [
      '-c',
      'import json,pickle,sys; print(json.dumps(pickle.load(open(sys.argv[1], "rb"))))',
      filename,
    ], { encoding: 'utf8', windowsHide: true, maxBuffer: 4 * 1024 * 1024 });
    if (decoded.status !== 0) throw new Error(`Unable to read TikTok session for ${username}.`);
    source = JSON.parse(decoded.stdout);
  }
  if (!Array.isArray(source)) throw new Error(`Invalid TikTok session for ${username}.`);
  return source
    .filter((cookie) => cookie && cookie.name && cookie.value)
    .map((cookie) => ({
      name: String(cookie.name),
      value: String(cookie.value),
      domain: cookie.domain || '.tiktok.com',
      path: cookie.path || '/',
      httpOnly: Boolean(cookie.httpOnly),
      secure: cookie.secure !== false,
    }));
}

function collectFromPayload(payload, sink, cursor) {
  if (payload && typeof payload === 'object') cursor.hasMore = payload.has_more === 1 || payload.has_more === true;
  for (const entry of payload?.comments || []) {
    const text = String(entry?.text || '').trim();
    if (!text) continue;
    sink.set(String(entry.cid || `${entry.user?.unique_id}|${text}`), {
      author: entry.user?.unique_id ? `@${entry.user.unique_id}` : 'someone',
      text,
      likes: Number(entry.digg_count || 0),
      publishedAt: entry.create_time ? new Date(entry.create_time * 1000).toISOString() : null,
    });
  }
}

// The page ships the total in its rehydration payload, which tells the loop
// when every comment has been collected instead of guessing.
function commentCount(page) {
  return page.evaluate(() => {
    const node = document.querySelector('#__UNIVERSAL_DATA_FOR_REHYDRATION__');
    if (!node) return null;
    try {
      const scope = JSON.parse(node.textContent).__DEFAULT_SCOPE__ || {};
      const total = scope['webapp.video-detail']?.itemInfo?.itemStruct?.stats?.commentCount;
      return Number.isFinite(Number(total)) ? Number(total) : null;
    } catch {
      return null;
    }
  }).catch(() => null);
}

// The banner sits over the bottom of the page and swallows clicks and wheel
// events aimed at the comment panel.
async function dismissCookieBanner(page) {
  for (const name of [/decline optional cookies/i, /refuser/i, /allow all/i]) {
    const button = page.getByRole('button', { name }).first();
    try {
      await button.click({ timeout: 4000 });
      await page.waitForTimeout(1000);
      return true;
    } catch {}
  }
  return false;
}

function overlayPresent(page) {
  return page.evaluate(() => Boolean(document.querySelector('.TUXModal-overlay'))).catch(() => false);
}

// TikTok raises a slider puzzle over the video page on its own, before any
// interaction, and its overlay swallows every real click. The dialog is
// dismissable, so closing it is enough; the puzzle never has to be solved.
async function dismissBlockingModal(page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (!await overlayPresent(page)) return true;
    await page.evaluate(() => {
      const overlay = document.querySelector('.TUXModal-overlay');
      if (!overlay) return;
      const portal = overlay.closest('[data-floating-ui-portal]') || overlay.parentElement;
      const card = [...portal.querySelectorAll('div')].find((node) => {
        const box = node.getBoundingClientRect();
        return box.width > 250 && box.width < 560 && box.height > 200;
      });
      if (!card) return;
      const cardBox = card.getBoundingClientRect();
      const corner = [...portal.querySelectorAll('button, [role="button"], svg')].find((node) => {
        const box = node.getBoundingClientRect();
        return box.width < 40 && box.height < 40
          && box.x > cardBox.right - 60
          && box.y > cardBox.top - 10 && box.y < cardBox.top + 60;
      });
      if (corner) (corner.closest('button, [role="button"]') || corner).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }).catch(() => {});
    await page.waitForTimeout(1500);
  }
  return !await overlayPresent(page);
}

// A scripted element.click() is an untrusted event and is what makes TikTok
// raise the slider captcha. Playwright's click sends real input.
async function openCommentPanel(page) {
  const icon = page.locator('[data-e2e="comment-icon"]').first();
  try {
    await icon.click({ timeout: 8000 });
    return true;
  } catch {}
  return page.evaluate(() => {
    const node = document.querySelector('[data-e2e="comment-icon"]');
    const target = node?.closest('button, a, [role="button"], div');
    if (!target) return false;
    target.click();
    return true;
  }).catch(() => false);
}

function scrollCommentPanel(page) {
  return page.evaluate(() => {
    const panel = [...document.querySelectorAll('div')]
      .filter((node) => node.scrollHeight > node.clientHeight + 80 && node.clientHeight > 200)
      .pop();
    if (panel) panel.scrollTop = panel.scrollHeight;
    else window.scrollBy(0, 1200);
  }).catch(() => {});
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const username = String(args.user || '').trim();
  // The signed-in identity and the author in the URL are normally the same
  // account, but they can be given separately.
  const account = String(args.account || username).trim();
  const videoId = String(args.video || '').trim();
  const max = Math.min(200, Number(args.max) || 60);
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) throw new Error('Invalid TikTok account name.');
  if (!/^[A-Za-z0-9._]{2,32}$/.test(account)) throw new Error('Invalid TikTok session account.');
  if (!/^\d{12,25}$/.test(videoId)) throw new Error('Invalid TikTok video id.');

  const { chromium } = playwright();
  const browser = await chromium.launch({
    executablePath: chromiumExecutable(),
    // TikTok answers /api/comment/list with an empty body in headless mode.
    // A real window, under Xvfb on Linux, is the only way to read comments.
    headless: args.headless === true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    locale: 'en-US',
    timezoneId: 'Europe/Paris',
    viewport: { width: 1440, height: 1000 },
  });
  await context.addCookies(readCookies(account));
  const page = await context.newPage();
  const found = new Map();
  const cursor = { hasMore: true };
  page.on('response', async (response) => {
    if (!/\/api\/comment\/list/i.test(response.url())) return;
    const payload = await response.json().catch(() => null);
    if (payload) collectFromPayload(payload, found, cursor);
  });
  let expected = null;
  let blocked = false;
  try {
    await page.goto(`https://www.tiktok.com/@${username}/video/${videoId}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60_000,
    });
    await page.waitForTimeout(6000);
    await dismissCookieBanner(page);
    blocked = !await dismissBlockingModal(page);
    expected = await commentCount(page);

    // TikTok never requests the comment list until the panel is opened, so
    // scrolling alone returns nothing.
    if (!await openCommentPanel(page)) throw new Error('The comment panel could not be opened.');
    await page.waitForTimeout(5000);
    await dismissBlockingModal(page);

    // Stop on whichever comes first: the cap, the total the page declared,
    // TikTok saying there is no next page, or two idle scrolls in a row.
    const deadline = Date.now() + 75_000;
    let previous = -1;
    let idle = 0;
    while (Date.now() < deadline
      && found.size < max
      && cursor.hasMore
      && (expected === null || found.size < expected)
      && idle < 2) {
      idle = found.size === previous ? idle + 1 : 0;
      previous = found.size;
      await dismissBlockingModal(page);
      await scrollCommentPanel(page);
      await page.waitForTimeout(3000);
    }
    if (!found.size) blocked = blocked || await overlayPresent(page);
  } finally {
    await browser.close().catch(() => {});
  }

  const comments = [...found.values()].sort((a, b) => b.likes - a.likes).slice(0, max);
  // An empty list because a captcha stood in the way is not the same fact as a
  // post that genuinely has no comments, and the writer must not confuse them.
  if (!comments.length && blocked) {
    process.stdout.write(`${OUTPUT_PREFIX}${JSON.stringify({ ok: false, error: 'tiktok-captcha', videoId, comments: [] })}\n`);
    return;
  }
  process.stdout.write(`${OUTPUT_PREFIX}${JSON.stringify({ ok: true, videoId, expected, captcha: blocked, comments })}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.stdout.write(`${OUTPUT_PREFIX}${JSON.stringify({ ok: false, error: error.message, comments: [] })}\n`);
  process.exit(1);
});
