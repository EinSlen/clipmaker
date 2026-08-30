#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const RECEIPT_PREFIX = 'CLIPMAKER_RECEIPT:';
const DOCTOR_PREFIX = 'CLIPMAKER_TIKTOK_DOCTOR:';
const STUDIO_CONTENT_URL = 'https://www.tiktok.com/tiktokstudio/content';
const STUDIO_UPLOAD_URL = 'https://www.tiktok.com/tiktokstudio/upload?from=upload&lang=en';

function parseArgs(argv) {
  const result = { command: argv[0] || 'doctor' };
  for (let index = 1; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

function playwright() {
  try {
    return require('playwright-chromium');
  } catch {
    return require(path.join(__dirname, 'tiktok-signature', 'node_modules', 'playwright-chromium'));
  }
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

function cookiePath(username) {
  return path.resolve(process.cwd(), 'CookiesDir', `tiktok_session-${username}.cookie`);
}

function readCookies(username) {
  const filename = cookiePath(username);
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
    ], { encoding: 'utf8', windowsHide: true, maxBuffer: 1024 * 1024 });
    if (decoded.status !== 0) throw new Error(`Unable to read TikTok session for ${username}.`);
    source = JSON.parse(decoded.stdout);
  }
  if (!Array.isArray(source)) throw new Error(`Invalid TikTok session for ${username}.`);
  const now = Date.now() / 1000;
  const cookies = source
    .filter((cookie) => cookie && cookie.name && cookie.value)
    .map((cookie) => {
      const expires = Number(cookie.expires || cookie.expiry || cookie.expirationDate || -1);
      const sameSite = ['Strict', 'Lax', 'None'].includes(cookie.sameSite) ? cookie.sameSite : 'Lax';
      return {
        name: String(cookie.name),
        value: String(cookie.value),
        domain: String(cookie.domain || '.tiktok.com'),
        path: String(cookie.path || '/'),
        expires: Number.isFinite(expires) && expires > now ? expires : -1,
        httpOnly: Boolean(cookie.httpOnly),
        secure: cookie.secure !== false,
        sameSite,
      };
    });
  if (!cookies.some((cookie) => cookie.name === 'sessionid')) {
    throw new Error(`TikTok sessionid missing for ${username}.`);
  }
  return cookies;
}

function numericPostId(value) {
  const candidate = String(value || '').trim();
  return /^\d{12,25}$/.test(candidate) ? candidate : null;
}

function responsePostIds(value, found = new Set()) {
  if (!value || typeof value !== 'object') return found;
  for (const [key, entry] of Object.entries(value)) {
    if (['aweme_id', 'awemeId', 'item_id', 'itemId', 'post_id', 'postId'].includes(key)) {
      const id = numericPostId(entry);
      if (id) found.add(id);
    }
    if (entry && typeof entry === 'object') responsePostIds(entry, found);
  }
  return found;
}

async function pagePostIds(page) {
  const hrefs = await page.locator('a[href*="/video/"]').evaluateAll((anchors) => anchors.map((anchor) => anchor.href));
  const ids = new Set();
  for (const href of hrefs) {
    const match = /\/video\/(\d{12,25})/.exec(href);
    if (match) ids.add(match[1]);
  }
  return ids;
}

async function collectPostIds(page, attempts = 4) {
  const ids = new Set();
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!/tiktokstudio\/content/i.test(page.url())) {
      await goto(page, STUDIO_CONTENT_URL);
    } else if (attempt > 0) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 }).catch(() => {});
    }
    await page.waitForTimeout(3500);
    for (const id of await pagePostIds(page).catch(() => new Set())) ids.add(id);
  }
  return ids;
}

async function goto(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForTimeout(2500);
  if (/login|signup/i.test(page.url())) throw new Error('TikTok session expired; reconnect the account.');
}

async function visible(locator) {
  try {
    return await locator.isVisible();
  } catch {
    return false;
  }
}

async function firstVisible(page, selectors) {
  for (const selector of selectors) {
    const candidates = page.locator(selector);
    const count = await candidates.count();
    for (let index = 0; index < count; index += 1) {
      const candidate = candidates.nth(index);
      if (await visible(candidate)) return candidate;
    }
  }
  return null;
}

async function waitForUploadPage(page) {
  const file = page.locator('input[type="file"]').first();
  await file.waitFor({ state: 'attached', timeout: 60_000 }).catch(() => {});
  if (await file.count()) return file;
  const text = (await page.locator('body').innerText().catch(() => '')).slice(0, 500);
  if (/captcha|verify|security check/i.test(text)) throw new Error('TikTok requires an interactive security check; reconnect the account.');
  throw new Error('TikTok Studio upload form did not load.');
}

async function dismissUploadOverlays(page) {
  for (const label of [/^Decline optional cookies$/i, /^Got it$/i, /^Cancel$/i]) {
    const buttons = page.getByRole('button', { name: label, exact: true });
    for (let index = (await buttons.count()) - 1; index >= 0; index -= 1) {
      const button = buttons.nth(index);
      if (await visible(button)) {
        await button.click({ force: true }).catch(() => {});
        await page.waitForTimeout(250);
      }
    }
  }
  // TikTok's first-use tour and cookie web component can remain mounted after
  // their own dismissal button disappears. They have no upload state, but do
  // intercept every pointer event in a headless browser.
  await page.locator('tiktok-cookie-banner, #react-joyride-portal')
    .evaluateAll((nodes) => nodes.forEach((node) => node.remove()))
    .catch(() => {});
}

async function setCaption(page, caption) {
  const deadline = Date.now() + 90_000;
  let editor = null;
  while (!editor && Date.now() < deadline) {
    editor = await firstVisible(page, [
      '[data-e2e="caption-editor"] [contenteditable="true"]',
      'div.public-DraftEditor-content[contenteditable="true"]',
      'div[contenteditable="true"][role="textbox"]',
      'div[contenteditable="true"][role="combobox"]',
      'textarea[placeholder*="caption" i]',
      'div[contenteditable="true"]',
    ]);
    if (!editor) await page.waitForTimeout(1000);
  }
  if (!editor) throw new Error('TikTok caption editor not found.');
  await dismissUploadOverlays(page);
  await editor.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.insertText(caption.slice(0, 2000));
}

async function setVisibility(page, privacy) {
  const privateLabels = /^(Only you|Only me|Private)$/i;
  const publicLabels = /^(Everyone|Public)$/i;
  const target = privacy === 'private' ? privateLabels : publicLabels;
  const current = page.getByText(target, { exact: true }).last();
  if (await visible(current)) return;
  const opener = await firstVisible(page, [
    '[data-e2e="permission-container"]',
    '[class*="PermissionSetting"]',
    'button[role="combobox"]:has-text("Everyone")',
    'button[role="combobox"]:has-text("Public")',
    'button[role="combobox"]:has-text("Friends")',
    'button[role="combobox"]:has-text("Only you")',
    'button[role="combobox"]:has-text("Only me")',
    'button[role="combobox"]:has-text("Private")',
  ]) || await firstVisible(page, [
    'text=/^(Everyone|Public|Friends|Only you|Only me|Private)$/i',
  ]);
  if (!opener) throw new Error('TikTok visibility control not found.');
  await dismissUploadOverlays(page);
  await opener.click();
  const roleOptions = page.getByRole('option', { name: target, exact: true });
  const option = await roleOptions.count()
    ? roleOptions.last()
    : page.getByText(target, { exact: true }).last();
  await option.waitFor({ state: 'visible', timeout: 10_000 });
  await option.click();
  await page.waitForTimeout(500);
  const selected = page.locator('button[role="combobox"]').filter({ hasText: target }).last();
  if (!await visible(selected)) {
    throw new Error(`TikTok did not confirm ${privacy} visibility.`);
  }
}

async function postButton(page) {
  return firstVisible(page, [
    'button[data-e2e="post_video_button"]',
    'button:has-text("Post")',
    'button:has-text("Publish")',
  ]);
}

async function waitUntilReady(page) {
  const deadline = Date.now() + 240_000;
  while (Date.now() < deadline) {
    await dismissUploadOverlays(page);
    const button = await postButton(page);
    if (button && await button.isEnabled().catch(() => false)) return button;
    const body = await page.locator('body').innerText().catch(() => '');
    if (/upload failed|couldn.?t upload|copyright issues detected/i.test(body)) {
      throw new Error('TikTok rejected the uploaded file before publication.');
    }
    await page.waitForTimeout(2000);
  }
  throw new Error('TikTok video upload did not become ready in time.');
}

async function confirmPost(page, baseline, responseIds) {
  const direct = [...responseIds][0];
  if (direct) return { id: direct, evidence: 'post-response' };
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    if (!/tiktokstudio\/content/i.test(page.url())) {
      await goto(page, STUDIO_CONTENT_URL).catch(() => {});
    } else {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 }).catch(() => {});
      await page.waitForTimeout(3000);
    }
    const ids = await collectPostIds(page, 2);
    const added = [...ids].find((id) => !baseline.has(id));
    if (added) return { id: added, evidence: 'studio-content' };
    await page.waitForTimeout(7000);
  }
  throw new Error('TikTok accepted the upload form but no real post appeared in TikTok Studio.');
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const username = String(args.users || args.user || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) throw new Error('Invalid TikTok account name.');
  const cookies = readCookies(username);
  const { chromium } = playwright();
  const browser = await chromium.launch({
    executablePath: chromiumExecutable(),
    headless: args.headed !== true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    locale: 'en-US',
    timezoneId: 'Europe/Paris',
    viewport: { width: 1440, height: 1000 },
  });
  await context.addCookies(cookies);
  const page = await context.newPage();
  const responseIds = new Set();
  page.on('response', async (response) => {
    if (!/project\/post|\/publish|post\/v1/i.test(response.url())) return;
    const payload = await response.json().catch(() => null);
    responsePostIds(payload, responseIds);
  });
  try {
    await goto(page, STUDIO_CONTENT_URL);
    const baseline = await collectPostIds(page);
    await goto(page, STUDIO_UPLOAD_URL);
    const fileInput = await waitForUploadPage(page);
    if (args.command === 'doctor') {
      process.stdout.write(`${DOCTOR_PREFIX}${JSON.stringify({
        ok: true,
        username,
        provider: 'tiktok-studio-browser',
        readyForLiveUpload: true,
        visiblePostCount: baseline.size,
      })}\n`);
      return;
    }
    const video = path.resolve(String(args.video || ''));
    if (!fs.existsSync(video) || !fs.statSync(video).isFile()) throw new Error('TikTok video file not found.');
    const title = String(args.title || '').trim();
    if (!title) throw new Error('TikTok caption is empty.');
    const privacy = String(args.visibility) === '0' ? 'public' : 'private';
    await fileInput.setInputFiles(video);
    await setCaption(page, title);
    await setVisibility(page, privacy);
    const button = await waitUntilReady(page);
    if (args.dryRun === true) {
      process.stdout.write(`${DOCTOR_PREFIX}${JSON.stringify({
        ok: true,
        username,
        provider: 'tiktok-studio-browser',
        readyForLiveUpload: true,
        uploadFormReady: true,
        privacy,
        visiblePostCount: baseline.size,
      })}\n`);
      return;
    }
    await button.click();
    const postNow = page.getByRole('button', { name: /^(Post now|Publish now)$/i }).last();
    if (await postNow.isVisible({ timeout: 5000 }).catch(() => false)) await postNow.click();
    const confirmation = await confirmPost(page, baseline, responseIds);
    const receipt = {
      provider: 'tiktok-studio-browser',
      platformPostId: confirmation.id,
      releaseUrl: `https://www.tiktok.com/@${username}/video/${confirmation.id}`,
      raw: {
        privacy,
        statusCode: 0,
        evidence: confirmation.evidence,
        verifiedInStudio: true,
        account: username,
      },
    };
    process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify(receipt)}\n`);
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

run().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
