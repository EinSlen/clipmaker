import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const TRANSIENT_STATUS_CODES = new Set([429, 500, 502, 503, 504]);
const API_ROOT = 'https://www.googleapis.com';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const LOCAL_CREDENTIAL_BUNDLE = path.resolve(scriptDir, '..', '..', '.youtube-oauth-accounts.json');

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

function normalizeAccount(value) {
  const account = String(value || 'default').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(account)) {
    throw new Error('Invalid YouTube account profile.');
  }
  return account;
}

function defaultEncodedCredentialBundle() {
  if (process.env.YOUTUBE_OAUTH_ACCOUNTS_B64) return process.env.YOUTUBE_OAUTH_ACCOUNTS_B64;
  if (!fs.existsSync(LOCAL_CREDENTIAL_BUNDLE)) return '';
  return Buffer.from(fs.readFileSync(LOCAL_CREDENTIAL_BUNDLE, 'utf8'), 'utf8').toString('base64');
}

export function readCredentialAccounts(encoded = defaultEncodedCredentialBundle()) {
  if (!encoded) return {};
  try {
    const parsed = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'));
    const source = parsed && typeof parsed === 'object' && parsed.accounts && typeof parsed.accounts === 'object'
      ? parsed.accounts
      : parsed;
    const accounts = {};
    for (const [rawId, rawCredentials] of Object.entries(source || {})) {
      const id = normalizeAccount(rawId);
      const credentials = rawCredentials && typeof rawCredentials === 'object' ? rawCredentials : {};
      accounts[id] = {
        clientId: String(credentials.clientId || credentials.client_id || '').trim(),
        clientSecret: String(credentials.clientSecret || credentials.client_secret || '').trim(),
        refreshToken: String(credentials.refreshToken || credentials.refresh_token || '').trim(),
      };
    }
    return accounts;
  } catch {
    throw new Error('YOUTUBE_OAUTH_ACCOUNTS_B64 is not a valid credential bundle.');
  }
}

function credentialsForAccount(account, env = process.env) {
  const accounts = readCredentialAccounts(env.YOUTUBE_OAUTH_ACCOUNTS_B64 || '');
  if (accounts[account]) return accounts[account];
  if (account !== 'default') return { clientId: '', clientSecret: '', refreshToken: '' };
  return {
    clientId: String(env.YOUTUBE_OAUTH_CLIENT_ID || '').trim(),
    clientSecret: String(env.YOUTUBE_OAUTH_CLIENT_SECRET || '').trim(),
    refreshToken: String(env.YOUTUBE_OAUTH_REFRESH_TOKEN || '').trim(),
  };
}

export function listCredentialAccounts(encoded = defaultEncodedCredentialBundle()) {
  const accounts = readCredentialAccounts(encoded);
  if (!Object.keys(accounts).length && process.env.YOUTUBE_OAUTH_CLIENT_ID) {
    accounts.default = credentialsForAccount('default');
  }
  return Object.entries(accounts)
    .map(([id, credentials]) => ({
      id,
      label: id === 'default'
        ? 'Default channel'
        : id.replace(/[-_]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
      configured: Boolean(credentials.clientId && credentials.clientSecret && credentials.refreshToken),
    }))
    .sort((a, b) => a.id === 'default' ? -1 : b.id === 'default' ? 1 : a.label.localeCompare(b.label));
}

function isDryRun() {
  return process.env.YOUTUBE_API_DRY_RUN !== 'false';
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function responseError(response, fallback) {
  const payload = await response.json().catch(() => null);
  const message = payload?.error?.message || payload?.error_description || fallback || `HTTP ${response.status}`;
  return new Error(String(message).slice(0, 1000));
}

async function refreshAccessToken(credentials) {
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: credentials.clientId,
      client_secret: credentials.clientSecret,
      refresh_token: credentials.refreshToken,
      grant_type: 'refresh_token',
    }),
  });
  if (!response.ok) throw await responseError(response, 'YouTube OAuth token refresh failed.');
  const payload = await response.json();
  if (!payload.access_token) throw new Error('YouTube OAuth did not return an access token.');
  return String(payload.access_token);
}

export function buildVideoResource({ title, description, tags, privacy }) {
  const cleanTags = [...new Set((tags || [])
    .map((tag) => String(tag).trim().replace(/^#/, ''))
    .filter(Boolean))].slice(0, 15);
  return {
    snippet: {
      title: String(title).trim(),
      description: String(description || title).trim().slice(0, 5000),
      tags: cleanTags,
      categoryId: '24',
      defaultLanguage: 'en',
    },
    status: {
      privacyStatus: privacy,
      selfDeclaredMadeForKids: false,
    },
  };
}

async function initiateUpload({ accessToken, resource, size }) {
  const endpoint = new URL('/upload/youtube/v3/videos', API_ROOT);
  endpoint.searchParams.set('uploadType', 'resumable');
  endpoint.searchParams.set('part', 'snippet,status');
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${accessToken}`,
      'content-type': 'application/json; charset=UTF-8',
      'x-upload-content-length': String(size),
      'x-upload-content-type': 'video/mp4',
    },
    body: JSON.stringify(resource),
  });
  if (!response.ok) throw await responseError(response, 'YouTube upload initialization failed.');
  const location = response.headers.get('location');
  if (!location) throw new Error('YouTube did not return a resumable upload URL.');
  return location;
}

function nextOffset(response) {
  const range = response.headers.get('range') || '';
  const match = /bytes=0-(\d+)/i.exec(range);
  return match ? Number(match[1]) + 1 : 0;
}

async function queryUploadOffset(location, total) {
  const response = await fetch(location, {
    method: 'PUT',
    redirect: 'manual',
    headers: {
      'content-length': '0',
      'content-range': `bytes */${total}`,
    },
  });
  if (response.status === 308) return { completed: false, offset: nextOffset(response) };
  if (response.ok) return { completed: true, payload: await response.json() };
  throw await responseError(response, 'Unable to resume the YouTube upload.');
}

async function uploadBytes(location, bytes) {
  let offset = 0;
  let lastError = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    let response;
    try {
      const body = bytes.subarray(offset);
      response = await fetch(location, {
        method: 'PUT',
        redirect: 'manual',
        headers: {
          'content-type': 'video/mp4',
          'content-length': String(body.length),
          'content-range': `bytes ${offset}-${bytes.length - 1}/${bytes.length}`,
        },
        body,
      });
    } catch (error) {
      lastError = error;
    }

    if (response?.ok) return await response.json();
    if (response?.status === 308) {
      offset = nextOffset(response);
      if (offset < bytes.length) continue;
    } else if (response && !TRANSIENT_STATUS_CODES.has(response.status)) {
      throw await responseError(response, 'YouTube video upload failed.');
    } else if (response) {
      lastError = await responseError(response, 'Transient YouTube upload failure.');
    }

    await sleep(Math.min(30_000, 1000 * (2 ** attempt)) + Math.floor(Math.random() * 500));
    try {
      const state = await queryUploadOffset(location, bytes.length);
      if (state.completed) return state.payload;
      offset = state.offset;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('YouTube upload failed after retries.');
}

async function doctor(account) {
  const credentials = credentialsForAccount(account);
  const clientConfigured = Boolean(credentials.clientId && credentials.clientSecret);
  const tokenConfigured = Boolean(credentials.refreshToken);
  let authenticated = false;
  let authenticationError = '';
  if (clientConfigured && tokenConfigured) {
    try {
      await refreshAccessToken(credentials);
      authenticated = true;
    } catch (error) {
      authenticationError = error instanceof Error ? error.message : String(error);
    }
  }
  return {
    ok: true,
    account,
    dry_run: isDryRun(),
    provider: 'youtube-data-api',
    configured: {
      oauth_client: clientConfigured ? 'configured' : 'missing',
      refresh_token: tokenConfigured ? 'configured' : 'missing',
      authenticated: authenticated ? 'configured' : 'missing',
    },
    browser_path: null,
    ready_for_live_upload: authenticated,
    next_steps: [
      ...(!clientConfigured || !tokenConfigured
        ? [`Configure OAuth for the YouTube account "${account}" with npm run youtube:oauth:setup.`]
        : []),
      ...(authenticationError ? [`YouTube OAuth validation failed: ${authenticationError}`] : []),
      ...(isDryRun() ? ['Set YOUTUBE_API_DRY_RUN=false after a private upload test.'] : []),
    ],
  };
}

async function uploadShort(account, args) {
  const input = parseArgs(args);
  const videoPath = path.resolve(String(input.video || ''));
  const title = String(input.title || '').trim();
  const description = String(input.caption || '').trim();
  const privacy = String(input.privacy || 'private').toLowerCase();
  const tags = String(input.tags || '').split(',').map((tag) => tag.trim()).filter(Boolean);
  if (!fs.existsSync(videoPath) || !fs.statSync(videoPath).isFile()) throw new Error('Video file not found.');
  if (!title || title.length > 100 || /[<>]/.test(title)) throw new Error('Invalid YouTube title.');
  if (!['private', 'unlisted', 'public'].includes(privacy)) throw new Error('Invalid YouTube privacy.');

  if (isDryRun()) {
    return {
      ok: true,
      dry_run: true,
      result: { provider: 'youtube-data-api', platformPostId: null, releaseUrl: '', raw: { simulated: true } },
    };
  }

  const credentials = credentialsForAccount(account);
  if (!credentials.clientId || !credentials.clientSecret || !credentials.refreshToken) {
    throw new Error(`YouTube OAuth is not configured for account "${account}".`);
  }
  const accessToken = await refreshAccessToken(credentials);
  const bytes = fs.readFileSync(videoPath);
  const resource = buildVideoResource({ title, description, tags, privacy });
  const location = await initiateUpload({ accessToken, resource, size: bytes.length });
  const uploaded = await uploadBytes(location, bytes);
  const id = String(uploaded?.id || '').trim();
  if (!id) throw new Error('YouTube accepted the upload but did not return a video id.');
  return {
    ok: true,
    dry_run: false,
    result: {
      provider: 'youtube-data-api',
      platformPostId: id,
      releaseUrl: `https://youtube.com/shorts/${id}`,
      raw: { privacy },
    },
  };
}

async function main() {
  const [command = 'doctor', ...args] = process.argv.slice(2);
  const accountArgumentIndex = args.indexOf('--account');
  const account = normalizeAccount(process.env.YOUTUBE_ACCOUNT
    || (accountArgumentIndex >= 0 ? args[accountArgumentIndex + 1] : '')
    || 'default');
  if (command === 'accounts') {
    process.stdout.write(`${JSON.stringify(listCredentialAccounts())}\n`);
  } else if (command === 'doctor') {
    process.stdout.write(`${JSON.stringify(await doctor(account))}\n`);
  } else if (command === 'upload-short') {
    process.stdout.write(`${JSON.stringify(await uploadShort(account, args))}\n`);
  } else {
    throw new Error(`Unknown command: ${command}`);
  }
}

const entrypoint = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (entrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
