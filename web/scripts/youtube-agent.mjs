import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(webDir, '..');
const rootDataDir = process.env.YOUTUBE_BROWSER_DATA_DIR
  ? path.resolve(process.env.YOUTUBE_BROWSER_DATA_DIR)
  : path.join(repoRoot, '.youtube-browser');
const rawArguments = process.argv.slice(2);
const accountArgumentIndex = rawArguments.indexOf('--account');
const requestedAccount = String(process.env.YOUTUBE_ACCOUNT || (accountArgumentIndex >= 0 ? rawArguments[accountArgumentIndex + 1] : '') || 'default').trim().toLowerCase();
if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(requestedAccount)) {
  throw new Error('Invalid YouTube account profile.');
}
const dataDir = requestedAccount === 'default'
  ? rootDataDir
  : path.join(rootDataDir, 'accounts', requestedAccount);
const legacyAuthProfileDir = path.join(dataDir, 'auth-profile');
const platformAuthProfileDir = path.join(dataDir, `auth-profile-${process.platform}`);
const authProfileDir = process.platform === 'win32' && fs.existsSync(legacyAuthProfileDir)
  ? legacyAuthProfileDir
  : platformAuthProfileDir;
const profilePlatformFile = path.join(authProfileDir, '.clipmaker-platform.json');
const cookieDir = path.join(dataDir, 'yt-auth');
const cookieFile = path.join(cookieDir, 'cookies-profile-local_invalid.json');
const invalidSessionFile = path.join(dataDir, '.session-invalid.json');
const uploadUrl = 'https://www.youtube.com/upload?persist_gl=1&gl=US&persist_hl=1&hl=en';
const profileCredentials = { email: 'profile@local.invalid', pass: '' };
const require = createRequire(import.meta.url);

function browserCandidates() {
  const candidates = [process.env.YOUTUBE_BROWSER_PATH];
  if (process.platform === 'win32') {
    candidates.push(
      process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Google', 'Chrome', 'Application', 'chrome.exe'),
      process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe')
    );
  } else if (process.platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
      '/Applications/Chromium.app/Contents/MacOS/Chromium'
    );
  } else {
    candidates.push('/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable');
  }
  return candidates.filter(Boolean);
}

function findBrowser() {
  return browserCandidates().find((candidate) => fs.existsSync(candidate)) || null;
}

function readCookies() {
  try {
    const cookies = JSON.parse(fs.readFileSync(cookieFile, 'utf8'));
    return Array.isArray(cookies) ? cookies : [];
  } catch {
    return [];
  }
}

function hasYouTubeSession() {
  try {
    if (fs.existsSync(invalidSessionFile)
      && fs.statSync(invalidSessionFile).mtimeMs >= fs.statSync(cookieFile).mtimeMs) {
      return false;
    }
  } catch {
    return false;
  }
  const now = Date.now() / 1000;
  const sessionNames = new Set([
    'LOGIN_INFO', 'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
    '__Secure-1PSID', '__Secure-3PSID'
  ]);
  return readCookies().some((cookie) =>
    sessionNames.has(cookie?.name) &&
    String(cookie?.domain || '').includes('youtube.com') &&
    (!Number.isFinite(cookie?.expires) || cookie.expires <= 0 || cookie.expires > now)
  );
}

function isDryRun() {
  return process.env.YOUTUBE_BROWSER_DRY_RUN !== 'false';
}

function doctor() {
  const browserPath = findBrowser();
  const cookiesPresent = fs.existsSync(cookieFile);
  const authenticated = hasYouTubeSession();
  const packagePresent = (() => {
    try {
      require.resolve('youtube-videos-uploader/package.json', { paths: [webDir] });
      return true;
    } catch {
      return false;
    }
  })();
  const ready = Boolean(browserPath && packagePresent && authenticated);
  return {
    ok: Boolean(browserPath && packagePresent),
    account: requestedAccount,
    dry_run: isDryRun(),
    provider: 'browser-session',
    configured: {
      browser: browserPath ? 'configured' : 'missing',
      cookies: cookiesPresent ? 'configured' : 'missing',
      authenticated: authenticated ? 'configured' : 'missing',
      package: packagePresent ? 'configured' : 'missing'
    },
    browser_path: browserPath,
    ready_for_live_upload: ready,
    next_steps: [
      ...(!browserPath ? ['Définis YOUTUBE_BROWSER_PATH vers Chrome, Edge ou Chromium.'] : []),
      ...(!authenticated ? ['Lance `npm run youtube:auth` dans web/ puis connecte-toi à YouTube.'] : []),
      ...(isDryRun() ? ['Définis YOUTUBE_BROWSER_DRY_RUN=false après un premier test en mode privé.'] : [])
    ]
  };
}

function launchArgs() {
  const args = [
    '--disable-dev-shm-usage',
    '--lang=en-US',
    '--window-size=1365,768',
    '--start-maximized'
  ];
  const runningAsRoot = typeof process.getuid === 'function' && process.getuid() === 0;
  if (process.env.YOUTUBE_BROWSER_NO_SANDBOX === 'true' || runningAsRoot) {
    args.push('--no-sandbox', '--disable-setuid-sandbox');
  }
  return args;
}

function loadBrowserAutomation() {
  const manifest = require.resolve('youtube-videos-uploader/package.json', { paths: [webDir] });
  const packageRequire = createRequire(manifest);
  return {
    puppeteer: packageRequire('puppeteer-extra'),
    uploader: packageRequire(path.dirname(manifest))
  };
}

async function authenticate() {
  const executablePath = findBrowser();
  if (!executablePath) throw new Error('Chrome, Edge ou Chromium introuvable. Définis YOUTUBE_BROWSER_PATH.');
  const { puppeteer } = loadBrowserAutomation();
  fs.mkdirSync(authProfileDir, { recursive: true });
  fs.mkdirSync(cookieDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath,
    userDataDir: authProfileDir,
    headless: false,
    defaultViewport: null,
    args: launchArgs()
  });
  try {
    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();
    console.log('Connecte-toi à YouTube dans la fenêtre ouverte. Aucun mot de passe ne sera lu ni enregistré par ClipMaker.');
    await page.goto(uploadUrl, { waitUntil: 'domcontentloaded', timeout: 120_000 });
    // Interactive authentication can legitimately take a while (2FA, channel
    // creation, consent screens). Keeping the visible browser alive for thirty
    // minutes prevents noVNC from falling back to a confusing black desktop.
    await page.waitForFunction(() => window.location.hostname === 'studio.youtube.com', { timeout: 30 * 60 * 1000 });
    await page.goto(uploadUrl, { waitUntil: 'domcontentloaded', timeout: 120_000 });
    const cookies = await page.cookies('https://www.youtube.com', 'https://studio.youtube.com', 'https://accounts.google.com');
    const unique = [...new Map(cookies.map((cookie) => [`${cookie.name}|${cookie.domain}|${cookie.path}`, cookie])).values()];
    fs.writeFileSync(cookieFile, JSON.stringify(unique, null, 2), { mode: 0o600 });
    fs.writeFileSync(profilePlatformFile, JSON.stringify({ platform: process.platform }), { mode: 0o600 });
    fs.rmSync(invalidSessionFile, { force: true });
    if (!hasYouTubeSession()) throw new Error('La fenêtre est ouverte, mais aucune session YouTube valide n’a été détectée.');
    console.log(`Session enregistrée localement dans ${cookieFile}`);
  } finally {
    await browser.close();
  }
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!key.startsWith('--')) continue;
    values[key.slice(2)] = args[index + 1] || '';
    index += 1;
  }
  return values;
}

async function uploadShort(args) {
  const input = parseArgs(args);
  const videoPath = path.resolve(String(input.video || ''));
  const title = String(input.title || '').trim();
  const description = String(input.caption || '').trim();
  const privacy = String(input.privacy || 'private').toLowerCase();
  const tags = String(input.tags || '').split(',').map((tag) => tag.trim().replace(/^#/, '')).filter(Boolean).slice(0, 15);
  if (!fs.existsSync(videoPath) || !fs.statSync(videoPath).isFile()) throw new Error('Vidéo introuvable.');
  if (!title || title.length > 100 || /[<>]/.test(title)) throw new Error('Titre YouTube invalide.');
  if (!['private', 'unlisted', 'public'].includes(privacy)) throw new Error('Visibilité YouTube invalide.');

  if (isDryRun()) {
    return {
      ok: true,
      dry_run: true,
      result: { provider: 'browser-session', platformPostId: null, releaseUrl: '', raw: { simulated: true } }
    };
  }

  const state = doctor();
  if (!state.ready_for_live_upload) throw new Error(state.next_steps.join(' '));
  const executablePath = state.browser_path;
  const { uploader } = loadBrowserAutomation();
  fs.mkdirSync(dataDir, { recursive: true });

  const originalLog = console.log;
  const toStderr = (...parts) => process.stderr.write(`${parts.map(String).join(' ')}\n`);
  console.log = toStderr;
  try {
    const links = await uploader.upload(
      profileCredentials,
      [{
        path: videoPath,
        title,
        description: description.slice(0, 5000),
        tags,
        publishType: privacy.toUpperCase(),
        isNotForKid: true,
        skipProcessingWait: true
      }],
      {
        executablePath,
        // The uploader's cookie store is the portable session source. Passing
        // userDataDir disables it and a fresh Linux profile asks for login.
        headless: process.env.YOUTUBE_BROWSER_HEADLESS !== 'false',
        args: launchArgs()
      },
      { log: toStderr, debug: toStderr, warn: toStderr, error: toStderr, userAction: toStderr }
    );
    const releaseUrl = links?.[0] || '';
    return {
      ok: true,
      dry_run: false,
      result: {
        provider: 'browser-session',
        platformPostId: releaseUrl.split('/').filter(Boolean).at(-1) || null,
        releaseUrl,
        raw: { privacy }
      }
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/session is expired|authenticate again|input\[type=["']?email/i.test(message)) {
      fs.writeFileSync(invalidSessionFile, JSON.stringify({ invalidatedAt: new Date().toISOString() }), { mode: 0o600 });
    }
    throw error;
  } finally {
    console.log = originalLog;
  }
}

const [command = 'doctor', ...args] = process.argv.slice(2);
try {
  if (command === 'auth') {
    await authenticate();
  } else if (command === 'doctor') {
    process.stdout.write(`${JSON.stringify(doctor())}\n`);
  } else if (command === 'upload-short') {
    fs.mkdirSync(dataDir, { recursive: true });
    process.chdir(dataDir);
    process.stdout.write(`${JSON.stringify(await uploadShort(args))}\n`);
  } else {
    throw new Error(`Commande inconnue : ${command}`);
  }
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
