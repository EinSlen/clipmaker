import { normalizePublisherConfig, publicPublisherConfig } from './publisher-config.js';
import { runScheduler } from './scheduler.js';

const API_VERSION = '2026-03-10';
const APP_CONFIG_KEY = 'github-app-config';
const INSTALLATION_KEY = 'github-app-installation';
const PUBLISHER_CONFIG_KEY = 'publisher-config-v1';
const PUBLISHER_SESSIONS_KEY = 'publisher-sessions-v1';
const PUBLISHER_ACCOUNTS_KEY = 'publisher-accounts-v1';
const SCHEDULER_SESSION_KEY = 'github-scheduler-session-v1';
const SESSION_LIFETIME_MS = 150 * 24 * 60 * 60 * 1000;
const MAX_BODY_BYTES = 12_000;
const MAX_SYNC_BODY_BYTES = 96_000;
const SOFT_BODY_OBSTACLES = new Set([
  'peg-grid',
  'moving-slide',
  'stair-cascade',
  'v-stairs',
  'pipe-bend',
  'twin-gears',
  'compression-ring',
]);

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function bytesToBase64Url(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '');
}

function base64UrlToBytes(value) {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function randomToken(size = 32) {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return bytesToBase64Url(bytes);
}

async function encryptionKey(env) {
  const bytes = base64UrlToBytes(env.SESSION_SECRET || '');
  if (bytes.byteLength !== 32) throw new Error('SESSION_SECRET must contain exactly 32 random bytes.');
  return crypto.subtle.importKey('raw', bytes, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
}

export async function sealSession(payload, env) {
  const iv = new Uint8Array(12);
  crypto.getRandomValues(iv);
  const plaintext = new TextEncoder().encode(JSON.stringify(payload));
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await encryptionKey(env), plaintext);
  return `v1.${bytesToBase64Url(iv)}.${bytesToBase64Url(new Uint8Array(encrypted))}`;
}

export async function openSession(value, env) {
  try {
    const [version, ivPart, dataPart] = String(value || '').split('.');
    if (version !== 'v1' || !ivPart || !dataPart) throw new Error('Malformed session');
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: base64UrlToBytes(ivPart) },
      await encryptionKey(env),
      base64UrlToBytes(dataPart),
    );
    const payload = JSON.parse(new TextDecoder().decode(decrypted));
    if (!payload.access_token || !payload.login || Number(payload.session_expires_at) <= Date.now()) {
      throw new Error('Expired session');
    }
    return payload;
  } catch {
    throw new HttpError(401, 'Session GitHub absente ou expirée.');
  }
}

async function safeEqual(left, right) {
  const encoder = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(String(left || ''))),
    crypto.subtle.digest('SHA-256', encoder.encode(String(right || ''))),
  ]);
  const leftBytes = new Uint8Array(a);
  const rightBytes = new Uint8Array(b);
  let difference = 0;
  for (let index = 0; index < leftBytes.byteLength; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }
  return difference === 0 && Boolean(String(left || '')) && Boolean(String(right || ''));
}

function escapeAttribute(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function cookie(request, name) {
  const source = request.headers.get('Cookie') || '';
  for (const entry of source.split(';')) {
    const [key, ...parts] = entry.trim().split('=');
    if (key === name) return decodeURIComponent(parts.join('='));
  }
  return '';
}

function temporaryCookie(name, value, path) {
  return `${name}=${encodeURIComponent(value)}; Path=${path}; Max-Age=600; HttpOnly; Secure; SameSite=Lax`;
}

function clearCookie(name, path) {
  return `${name}=; Path=${path}; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;
}

function noStoreHeaders(extra = {}) {
  return { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extra };
}

function redirect(location, headers = {}) {
  return new Response(null, { status: 302, headers: noStoreHeaders({ Location: location, ...headers }) });
}

function dashboardRedirect(env, query = '', fragment = '') {
  return `${env.DASHBOARD_ORIGIN}/clipmaker/${query}${fragment}`;
}

function allowedOrigin(request, env) {
  return request.headers.get('Origin') === env.DASHBOARD_ORIGIN;
}

function corsHeaders(request, env) {
  if (!allowedOrigin(request, env)) return {};
  return {
    'Access-Control-Allow-Origin': env.DASHBOARD_ORIGIN,
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
    'Access-Control-Max-Age': '600',
    Vary: 'Origin',
  };
}

function json(payload, status, request, env, extra = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: noStoreHeaders({ 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(request, env), ...extra }),
  });
}

export function parseBearer(request) {
  const match = (request.headers.get('Authorization') || '').match(/^Bearer\s+(.+)$/iu);
  if (!match) throw new HttpError(401, 'Connexion GitHub requise.');
  return match[1];
}

async function appConfig(env) {
  const stored = await env.CONFIG.get(APP_CONFIG_KEY, 'json');
  if (!stored?.client_id || !stored?.client_secret) throw new HttpError(503, 'La GitHub App doit encore être initialisée.');
  return stored;
}

async function github(path, options = {}) {
  const response = await fetch(path.startsWith('http') ? path : `https://api.github.com${path}`, {
    ...options,
    headers: {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': API_VERSION,
      'User-Agent': 'ClipMaker-Cloud-Control',
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return { response, payload: null };
  const payload = await response.json().catch(() => ({}));
  return { response, payload };
}

function tokenPayload(payload, previous = {}) {
  const now = Date.now();
  if (!payload.access_token) throw new HttpError(502, 'GitHub n’a pas retourné de jeton utilisateur.');
  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token || previous.refresh_token || '',
    access_expires_at: payload.expires_in ? now + Math.max(60, Number(payload.expires_in) - 60) * 1000 : null,
    refresh_expires_at: payload.refresh_token_expires_in
      ? now + Math.max(60, Number(payload.refresh_token_expires_in) - 60) * 1000
      : previous.refresh_expires_at || null,
  };
}

async function exchangeAuthorizationCode(code, config, callbackUrl) {
  const response = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: config.client_id,
      client_secret: config.client_secret,
      code,
      redirect_uri: callbackUrl,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) throw new HttpError(502, payload.error_description || 'Échec de la connexion GitHub.');
  return tokenPayload(payload);
}

async function refreshedSession(session, config) {
  if (!session.access_expires_at || Number(session.access_expires_at) > Date.now() + 90_000) {
    return { session, changed: false };
  }
  if (!session.refresh_token || (session.refresh_expires_at && Number(session.refresh_expires_at) <= Date.now())) {
    throw new HttpError(401, 'La connexion GitHub a expiré.');
  }
  const response = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: config.client_id,
      client_secret: config.client_secret,
      grant_type: 'refresh_token',
      refresh_token: session.refresh_token,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) throw new HttpError(401, 'La connexion GitHub doit être renouvelée.');
  return {
    session: { ...session, ...tokenPayload(payload, session), session_expires_at: Date.now() + SESSION_LIFETIME_MS },
    changed: true,
  };
}

async function authenticatedSession(request, env) {
  if (!allowedOrigin(request, env)) throw new HttpError(403, 'Origine du tableau de bord refusée.');
  const config = await appConfig(env);
  const opened = await openSession(parseBearer(request), env);
  if (opened.login.toLowerCase() !== env.ALLOWED_LOGIN.toLowerCase()) throw new HttpError(403, 'Compte GitHub non autorisé.');
  const refreshed = await refreshedSession(opened, config);
  return { ...refreshed, config };
}

async function workflowRequest(request, env) {
  const expected = env.WORKFLOW_CONFIG_TOKEN || '';
  const provided = parseBearer(request);
  if (!await safeEqual(provided, expected)) throw new HttpError(401, 'Jeton du runner GitHub invalide.');
}

async function boundedJson(request, maximum = MAX_BODY_BYTES) {
  const length = Number(request.headers.get('Content-Length') || 0);
  if (length > maximum) throw new HttpError(413, 'Requête trop volumineuse.');
  return request.json().catch(() => {
    throw new HttpError(400, 'Corps JSON invalide.');
  });
}

export function validateDispatch(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new HttpError(400, 'Commande invalide.');
  const workflow = String(payload.workflow || '');
  const supplied = payload.inputs && typeof payload.inputs === 'object' && !Array.isArray(payload.inputs) ? payload.inputs : {};

  if (workflow === 'daily-publisher.yml') {
    const action = String(supplied.action || '');
    if (!new Set(['doctor', 'generate', 'publish', 'run']).has(action)) throw new HttpError(400, 'Action quotidienne invalide.');
    return {
      workflow,
      inputs: { action, dry_run: action === 'doctor' ? 'true' : 'false' },
    };
  }

  if (workflow === 'soft-body-artifact.yml') {
    const obstacle = String(supplied.obstacle || '');
    const seed = String(supplied.seed || '');
    const samples = String(supplied.samples || '');
    const chunkSize = String(supplied.chunk_size || '');
    if (!SOFT_BODY_OBSTACLES.has(obstacle)) throw new HttpError(400, 'Obstacle 3D invalide.');
    if (!/^\d{1,12}$/u.test(seed)) throw new HttpError(400, 'Seed invalide.');
    if (!new Set(['32', '64', '128']).has(samples)) throw new HttpError(400, 'Qualité 3D invalide.');
    if (!new Set(['15', '30', '45']).has(chunkSize)) throw new HttpError(400, 'Taille de lot invalide.');
    return {
      workflow,
      inputs: {
        obstacle,
        seed,
        samples,
        chunk_size: chunkSize,
        title: 'HOW SOFT CAN IT GET?',
      },
    };
  }

  throw new HttpError(400, 'Workflow non autorisé.');
}

async function setupStart(request, env) {
  const url = new URL(request.url);
  if (!await safeEqual(url.searchParams.get('key'), env.SETUP_SECRET)) throw new HttpError(404, 'Configuration introuvable.');
  if (await env.CONFIG.get(APP_CONFIG_KEY)) return redirect(dashboardRedirect(env, '?setup=ready'));

  const state = randomToken();
  const origin = url.origin;
  const manifest = {
    name: 'ClipMaker Cloud Control EinSlen',
    url: `${env.DASHBOARD_ORIGIN}/clipmaker/`,
    description: 'Private controller for the EinSlen ClipMaker GitHub Actions workflows.',
    redirect_url: `${origin}/setup/callback`,
    callback_urls: [`${origin}/auth/callback`],
    setup_url: `${origin}/setup/installed`,
    setup_on_update: true,
    public: false,
    hook_attributes: { url: `${origin}/webhook`, active: false },
    default_permissions: { actions: 'write' },
    default_events: [],
    request_oauth_on_install: false,
  };
  const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action https://github.com"><title>Configuration ClipMaker</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0c12;color:#fff;font:16px system-ui}.card{max-width:560px;padding:36px;border:1px solid #30313d;border-radius:20px;background:#151620}button{padding:14px 18px;border:0;border-radius:12px;background:#8f6bff;color:#fff;font-weight:800;cursor:pointer}p{color:#aaaec0;line-height:1.6}</style></head><body><main class="card"><h1>Activer ClipMaker Cloud</h1><p>GitHub va créer une application privée limitée au lancement des workflows de ce dépôt. Aucun accès au code ou aux secrets n’est demandé.</p><form action="https://github.com/settings/apps/new?state=${encodeURIComponent(state)}" method="post"><input type="hidden" name="manifest" value="${escapeAttribute(JSON.stringify(manifest))}"><button type="submit">Continuer sur GitHub</button></form></main></body></html>`;
  return new Response(html, {
    headers: noStoreHeaders({
      'Content-Type': 'text/html; charset=utf-8',
      'Set-Cookie': temporaryCookie('clipmaker_setup_state', state, '/setup/callback'),
    }),
  });
}

async function setupCallback(request, env) {
  const url = new URL(request.url);
  const state = url.searchParams.get('state') || '';
  const expected = cookie(request, 'clipmaker_setup_state');
  if (!await safeEqual(state, expected)) throw new HttpError(403, 'État de configuration GitHub invalide.');
  const code = url.searchParams.get('code');
  if (!code) throw new HttpError(400, 'Code de configuration GitHub absent.');
  const { response, payload } = await github(`/app-manifests/${encodeURIComponent(code)}/conversions`, { method: 'POST' });
  if (!response.ok || !payload.client_id || !payload.client_secret || !payload.slug) {
    throw new HttpError(502, payload.message || 'Impossible de créer la GitHub App.');
  }
  await env.CONFIG.put(APP_CONFIG_KEY, JSON.stringify({
    id: payload.id,
    slug: payload.slug,
    client_id: payload.client_id,
    client_secret: payload.client_secret,
    created_at: new Date().toISOString(),
  }));
  return redirect(`https://github.com/apps/${encodeURIComponent(payload.slug)}/installations/new`, {
    'Set-Cookie': clearCookie('clipmaker_setup_state', '/setup/callback'),
  });
}

async function setupInstalled(request, env) {
  const url = new URL(request.url);
  const installationId = url.searchParams.get('installation_id');
  if (installationId && /^\d+$/u.test(installationId)) await env.CONFIG.put(INSTALLATION_KEY, installationId);
  return redirect(`${url.origin}/auth/start`);
}

async function authStart(request, env) {
  const config = await appConfig(env);
  const url = new URL(request.url);
  const state = randomToken();
  const callback = `${url.origin}/auth/callback`;
  const authorize = new URL('https://github.com/login/oauth/authorize');
  authorize.searchParams.set('client_id', config.client_id);
  authorize.searchParams.set('redirect_uri', callback);
  authorize.searchParams.set('state', state);
  authorize.searchParams.set('login', env.ALLOWED_LOGIN);
  if (env.REPOSITORY_ID) authorize.searchParams.set('repository_id', env.REPOSITORY_ID);
  return redirect(authorize.toString(), {
    'Set-Cookie': temporaryCookie('clipmaker_oauth_state', state, '/auth/callback'),
  });
}

async function authCallback(request, env) {
  const url = new URL(request.url);
  const state = url.searchParams.get('state') || '';
  const expected = cookie(request, 'clipmaker_oauth_state');
  if (!await safeEqual(state, expected)) throw new HttpError(403, 'État OAuth GitHub invalide.');
  if (url.searchParams.get('error')) throw new HttpError(401, 'Connexion GitHub annulée.');
  const code = url.searchParams.get('code');
  if (!code) throw new HttpError(400, 'Code OAuth GitHub absent.');
  const config = await appConfig(env);
  const exchanged = await exchangeAuthorizationCode(code, config, `${url.origin}/auth/callback`);
  const { response, payload: user } = await github('/user', {
    headers: { Authorization: `Bearer ${exchanged.access_token}` },
  });
  if (!response.ok || !user.login) throw new HttpError(502, 'Impossible de vérifier le compte GitHub.');
  if (user.login.toLowerCase() !== env.ALLOWED_LOGIN.toLowerCase()) throw new HttpError(403, 'Ce compte GitHub n’est pas autorisé.');
  const session = await sealSession({
    ...exchanged,
    login: user.login,
    session_expires_at: Date.now() + SESSION_LIFETIME_MS,
  }, env);
  return redirect(dashboardRedirect(env, '', `#github-session=${encodeURIComponent(session)}`), {
    'Set-Cookie': clearCookie('clipmaker_oauth_state', '/auth/callback'),
  });
}

async function apiSession(request, env) {
  const authenticated = await authenticatedSession(request, env);
  const { response, payload: user } = await github('/user', {
    headers: { Authorization: `Bearer ${authenticated.session.access_token}` },
  });
  if (!response.ok || user.login?.toLowerCase() !== env.ALLOWED_LOGIN.toLowerCase()) {
    throw new HttpError(401, 'La connexion GitHub doit être renouvelée.');
  }
  const schedulerSession = await sealSession(authenticated.session, env);
  await env.CONFIG.put(SCHEDULER_SESSION_KEY, schedulerSession);
  const renewed = authenticated.changed ? schedulerSession : null;
  return json({
    authenticated: true,
    login: user.login,
    session: renewed,
    scheduler: { enabled: true, source: 'github-app', intervalMinutes: 5 },
  }, 200, request, env);
}

async function apiDispatch(request, env) {
  const authenticated = await authenticatedSession(request, env);
  const command = validateDispatch(await boundedJson(request));
  const { response, payload } = await github(
    `/repos/${encodeURIComponent(env.REPOSITORY_OWNER)}/${encodeURIComponent(env.REPOSITORY_NAME)}/actions/workflows/${encodeURIComponent(command.workflow)}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authenticated.session.access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs: command.inputs }),
    },
  );
  if (!response.ok) throw new HttpError(response.status === 403 ? 403 : 502, payload?.message || 'GitHub a refusé le lancement du workflow.');
  const renewed = authenticated.changed ? await sealSession(authenticated.session, env) : null;
  return json({ ok: true, workflow: command.workflow, session: renewed }, 202, request, env);
}

function normalizeAccounts(raw) {
  const source = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const tiktok = Array.isArray(source.tiktok) ? source.tiktok.slice(0, 16).map((item) => ({
    username: String(item?.username || '').trim().slice(0, 32),
    ready: Boolean(item?.ready),
  })).filter((item) => /^[A-Za-z0-9._]{2,32}$/u.test(item.username)) : [];
  const youtube = Array.isArray(source.youtube) ? source.youtube.slice(0, 16).map((item) => ({
    id: String(item?.id || '').trim().slice(0, 64),
    label: String(item?.label || item?.id || '').trim().slice(0, 80),
    ready: Boolean(item?.ready),
  })).filter((item) => item.id) : [];
  return { tiktok, youtube };
}

async function apiPublisherConfig(request, env) {
  const authenticated = await authenticatedSession(request, env);
  if (request.method === 'PUT') {
    let normalized;
    try {
      normalized = normalizePublisherConfig(await boundedJson(request, 48_000));
    } catch (error) {
      throw new HttpError(400, error instanceof Error ? error.message : 'Configuration invalide.');
    }
    await env.CONFIG.put(PUBLISHER_CONFIG_KEY, JSON.stringify(normalized));
  }
  const stored = await env.CONFIG.get(PUBLISHER_CONFIG_KEY, 'json');
  if (!stored) throw new HttpError(404, 'Aucune configuration cloud n’a encore été synchronisée.');
  const renewed = authenticated.changed ? await sealSession(authenticated.session, env) : null;
  return json({ ok: true, config: publicPublisherConfig(stored), session: renewed }, 200, request, env);
}

async function apiPublisherAccounts(request, env) {
  const authenticated = await authenticatedSession(request, env);
  const accounts = await env.CONFIG.get(PUBLISHER_ACCOUNTS_KEY, 'json') || { tiktok: [], youtube: [] };
  const sessionsSynced = Boolean(await env.CONFIG.get(PUBLISHER_SESSIONS_KEY));
  const renewed = authenticated.changed ? await sealSession(authenticated.session, env) : null;
  return json({ ok: true, accounts, sessionsSynced, session: renewed }, 200, request, env);
}

async function apiWorkflowBootstrap(request, env) {
  await workflowRequest(request, env);
  if (request.method === 'POST') {
    const body = await boundedJson(request, MAX_SYNC_BODY_BYTES);
    let config;
    try {
      config = normalizePublisherConfig(body?.config);
    } catch (error) {
      throw new HttpError(400, error instanceof Error ? error.message : 'Configuration invalide.');
    }
    const sessionsBundle = String(body?.sessionsBundle || '');
    if (!/^[A-Za-z0-9+/=]+$/u.test(sessionsBundle) || sessionsBundle.length > 64_000) {
      throw new HttpError(400, 'Bundle de sessions invalide.');
    }
    const accounts = normalizeAccounts(body?.accounts);
    const syncedAt = new Date().toISOString();
    await Promise.all([
      env.CONFIG.put(PUBLISHER_CONFIG_KEY, JSON.stringify(config)),
      env.CONFIG.put(PUBLISHER_SESSIONS_KEY, sessionsBundle),
      env.CONFIG.put(PUBLISHER_ACCOUNTS_KEY, JSON.stringify({ ...accounts, syncedAt })),
    ]);
  }
  const [config, sessionsBundle, accounts] = await Promise.all([
    env.CONFIG.get(PUBLISHER_CONFIG_KEY, 'json'),
    env.CONFIG.get(PUBLISHER_SESSIONS_KEY),
    env.CONFIG.get(PUBLISHER_ACCOUNTS_KEY, 'json'),
  ]);
  if (!config || !sessionsBundle) throw new HttpError(503, 'La configuration et les sessions cloud ne sont pas encore prêtes.');
  return json({ ok: true, config, sessionsBundle, accounts: accounts || { tiktok: [], youtube: [] } }, 200, request, env);
}

async function apiLogout(request, env) {
  const config = await appConfig(env);
  const session = await openSession(parseBearer(request), env);
  if (allowedOrigin(request, env)) {
    await github(`/applications/${encodeURIComponent(config.client_id)}/token`, {
      method: 'DELETE',
      headers: {
        Authorization: `Basic ${btoa(`${config.client_id}:${config.client_secret}`)}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ access_token: session.access_token }),
    }).catch(() => null);
  }
  await env.CONFIG.delete(SCHEDULER_SESSION_KEY);
  return json({ ok: true }, 200, request, env);
}

async function schedulerCredential(env) {
  const stored = await env.CONFIG.get(SCHEDULER_SESSION_KEY);
  if (stored) {
    try {
      const opened = await openSession(stored, env);
      const config = await appConfig(env);
      const refreshed = await refreshedSession(opened, config);
      if (refreshed.changed) {
        await env.CONFIG.put(SCHEDULER_SESSION_KEY, await sealSession(refreshed.session, env));
      }
      return { token: refreshed.session.access_token, source: 'github-app' };
    } catch (error) {
      console.warn(JSON.stringify({
        message: 'stored GitHub App scheduler session is unavailable',
        error: error instanceof Error ? error.message : String(error),
      }));
    }
  }
  if (env.GITHUB_AUTOMATION_TOKEN) return { token: env.GITHUB_AUTOMATION_TOKEN, source: 'automation-secret' };
  throw new Error('No GitHub scheduler credential is configured.');
}

async function scheduledTick(controller, env) {
  const credential = await schedulerCredential(env);
  const results = await runScheduler({
    env: {
      CONFIG: env.CONFIG,
      REPOSITORY_OWNER: env.REPOSITORY_OWNER,
      REPOSITORY_NAME: env.REPOSITORY_NAME,
      github,
    },
    token: credential.token,
    now: new Date(controller.scheduledTime),
  });
  console.log(JSON.stringify({
    message: 'clipmaker scheduler tick',
    credential: credential.source,
    scheduledTime: new Date(controller.scheduledTime).toISOString(),
    results,
  }));
}

async function route(request, env) {
  const url = new URL(request.url);
  if (request.method === 'OPTIONS' && url.pathname.startsWith('/api/')) {
    if (!allowedOrigin(request, env)) throw new HttpError(403, 'Origine refusée.');
    return new Response(null, { status: 204, headers: noStoreHeaders(corsHeaders(request, env)) });
  }
  if (request.method === 'GET' && url.pathname === '/health') {
    const [configured, schedulerSession] = await Promise.all([
      env.CONFIG.get(APP_CONFIG_KEY),
      env.CONFIG.get(SCHEDULER_SESSION_KEY),
    ]);
    return json({
      ok: true,
      configured: Boolean(configured),
      scheduler: Boolean(schedulerSession || env.GITHUB_AUTOMATION_TOKEN),
    }, 200, request, env);
  }
  if (request.method === 'GET' && url.pathname === '/setup/start') return setupStart(request, env);
  if (request.method === 'GET' && url.pathname === '/setup/callback') return setupCallback(request, env);
  if (request.method === 'GET' && url.pathname === '/setup/installed') return setupInstalled(request, env);
  if (request.method === 'GET' && url.pathname === '/auth/start') return authStart(request, env);
  if (request.method === 'GET' && url.pathname === '/auth/callback') return authCallback(request, env);
  if (request.method === 'GET' && url.pathname === '/api/session') return apiSession(request, env);
  if ((request.method === 'GET' || request.method === 'PUT') && url.pathname === '/api/config') return apiPublisherConfig(request, env);
  if (request.method === 'GET' && url.pathname === '/api/accounts') return apiPublisherAccounts(request, env);
  if ((request.method === 'GET' || request.method === 'POST') && url.pathname === '/api/workflow/bootstrap') return apiWorkflowBootstrap(request, env);
  if (request.method === 'POST' && url.pathname === '/api/dispatch') return apiDispatch(request, env);
  if (request.method === 'POST' && url.pathname === '/api/logout') return apiLogout(request, env);
  if (request.method === 'POST' && url.pathname === '/webhook') return new Response(null, { status: 204 });
  if (request.method === 'GET' && url.pathname === '/') return redirect(`${env.DASHBOARD_ORIGIN}/clipmaker/`);
  throw new HttpError(404, 'Route introuvable.');
}

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      const message = error instanceof HttpError ? error.message : 'Erreur interne du contrôle Cloud.';
      if (!(error instanceof HttpError)) {
        console.error(JSON.stringify({ message: 'cloud-control request failed', error: error instanceof Error ? error.message : String(error), path: new URL(request.url).pathname }));
      }
      return json({ error: message }, status, request, env);
    }
  },
  async scheduled(controller, env) {
    try {
      await scheduledTick(controller, env);
    } catch (error) {
      console.error(JSON.stringify({
        message: 'clipmaker scheduler failed',
        error: error instanceof Error ? error.message : String(error),
        scheduledTime: new Date(controller.scheduledTime).toISOString(),
      }));
      throw error;
    }
  },
};
