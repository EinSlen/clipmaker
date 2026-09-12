#!/usr/bin/env node
/**
 * Read this account's own TikTok Studio analytics once and write them down.
 *
 * It reuses the session and the browser setup the publisher already uses to
 * post, because inventing a second way in would be a second thing to keep
 * working. The footprint is deliberately small: one launch, one navigation
 * per page asked for, no polling loop and no retry storm. Whatever TikTok
 * Studio fetches for its own charts is captured as it arrives and written to
 * disk, so the shape of the payload never has to be guessed in advance.
 *
 *   node web/scripts/tiktok-analytics-agent.cjs --user dvlad [--headed] [--out file.json]
 *   node web/scripts/tiktok-analytics-agent.cjs --user dvlad --search "soft body simulation"
 *
 * The search mode reads the public results page the same way a person does,
 * to see what the genre posts and how it performs. It is bounded on purpose:
 * one query, two scrolls, no crawl. TikTok's terms restrict automated
 * collection, so keep it to the occasional look rather than a routine.
 *
 * Nothing is uploaded and nothing is changed on the account. The session file
 * is read, never printed.
 */

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const VENDOR = path.resolve(__dirname, '..', '..', 'vendor', 'TiktokAutoUploader');
const STUDIO_PAGES = [
  'https://www.tiktok.com/tiktokstudio/analytics/overview',
  'https://www.tiktok.com/tiktokstudio/analytics/content',
  'https://www.tiktok.com/tiktokstudio/content',
];
// Wide on purpose. The first run matched the obvious analytics endpoints and
// brought back the account's top posts, which held no daily at all, so there
// was no way to tell whether the dailies underperform or were simply outside
// what that call returns. Every JSON the pages fetch is kept now: one run
// costs somebody's evening, so it should not have to be repeated to widen a
// regular expression.
const SKIP_URL = /\.(js|css|png|jpe?g|webp|svg|woff2?|mp4)(\?|$)/i;

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    const name = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith('--')) args[name] = true;
    else { args[name] = next; index += 1; }
  }
  return args;
}

function playwright() {
  try {
    return require('playwright-chromium');
  } catch {
    return require(path.join(VENDOR, 'tiktok_uploader', 'tiktok-signature', 'node_modules', 'playwright-chromium'));
  }
}

function chromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || undefined;
}

function readCookies(username) {
  const filename = path.join(VENDOR, 'CookiesDir', `tiktok_session-${username}.cookie`);
  if (!fs.existsSync(filename)) throw new Error(`TikTok session not found for ${username}.`);
  let source;
  try {
    source = JSON.parse(fs.readFileSync(filename, 'utf8'));
  } catch {
    const python = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const decoded = spawnSync(python, [
      '-c', 'import json,pickle,sys; print(json.dumps(pickle.load(open(sys.argv[1], "rb"))))', filename,
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
      domain: String(cookie.domain || '.tiktok.com'),
      path: String(cookie.path || '/'),
      httpOnly: Boolean(cookie.httpOnly),
      secure: cookie.secure !== false,
      sameSite: ['Strict', 'Lax', 'None'].includes(cookie.sameSite) ? cookie.sameSite : 'Lax',
    }));
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const username = String(args.user || args.users || '').trim();
  if (!/^[A-Za-z0-9._]{2,32}$/.test(username)) throw new Error('Pass --user <tiktok account name>.');
  const destination = path.resolve(String(args.out || `tiktok-analytics-${username}.json`));

  const cookies = readCookies(username);
  const { chromium } = playwright();
  const browser = await chromium.launch({
    executablePath: chromiumExecutable(),
    headless: args.headed !== true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    locale: 'en-US', timezoneId: 'Europe/Paris', viewport: { width: 1440, height: 1000 },
  });
  await context.addCookies(cookies);
  const page = await context.newPage();

  const captured = [];
  const seen = new Set();
  page.on('response', async (response) => {
    const url = response.url();
    if (SKIP_URL.test(url) || !/tiktok\.com/i.test(url)) return;
    if (!/json/i.test(response.headers()['content-type'] || '')) return;
    const payload = await response.json().catch(() => null);
    if (!payload) return;
    const key = `${url.split('?')[0]}:${JSON.stringify(payload).length}`;
    if (seen.has(key)) return;
    seen.add(key);
    captured.push({ url: url.split('?')[0], query: url.split('?')[1] || '', payload });
  });

  const query = typeof args.search === 'string' ? args.search.trim() : '';
  try {
    if (query) {
      const url = `https://www.tiktok.com/search/video?q=${encodeURIComponent(query)}`;
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90_000 }).catch(() => {});
      await page.waitForTimeout(8000);
      // Two scrolls, not an endless crawl: enough for a first page of results.
      for (let step = 0; step < 2; step += 1) {
        await page.mouse.wheel(0, 4000).catch(() => {});
        await page.waitForTimeout(4000);
      }
    } else {
      for (const target of STUDIO_PAGES) {
        await page.goto(target, { waitUntil: 'networkidle', timeout: 90_000 }).catch(() => {});
        // One settle, not a polling loop: the charts fetch on load.
        await page.waitForTimeout(6000);
      }
    }
    const signedIn = !/\/login/i.test(page.url());
    fs.writeFileSync(destination, `${JSON.stringify({
      account: username, query, signedIn, capturedAt: new Date().toISOString(), responses: captured,
    }, null, 2)}\n`, 'utf8');
    console.log(`signed in: ${signedIn}`);
    console.log(`captured ${captured.length} JSON response(s)`);
    // Say which ones actually carry a list of posts, so the next step knows
    // where to look without opening a three hundred kilobyte file by hand.
    for (const item of captured) {
      const text = JSON.stringify(item.payload);
      const posts = (text.match(/"aweme_id"/g) || []).length;
      const marker = posts ? `  <- ${posts} post reference(s)` : '';
      console.log(`  ${String(item.url).slice(0, 74)}${marker}`);
    }
    console.log(`written to ${destination}`);
    if (!signedIn) console.log('The session did not open Studio; it has probably expired.');
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
