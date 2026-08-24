import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..', '..');
const DEFAULT_BUNDLE_FILE = path.join(repoRoot, '.youtube-oauth-accounts.json');
const AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const SCOPE = 'https://www.googleapis.com/auth/youtube.upload';

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
    throw new Error('Le nom du compte doit contenir 1 à 32 lettres, chiffres, tirets ou underscores.');
  }
  return account;
}

function loadDesktopClient(filename) {
  const parsed = JSON.parse(fs.readFileSync(filename, 'utf8'));
  const client = parsed.installed;
  if (!client?.client_id || !client?.client_secret) {
    throw new Error('Ce fichier ne contient pas un client OAuth Google valide. Choisis un client de type Application de bureau.');
  }
  return { clientId: String(client.client_id), clientSecret: String(client.client_secret) };
}

function base64Url(value) {
  return Buffer.from(value).toString('base64url');
}

function openBrowser(url) {
  let command;
  let args;
  if (process.platform === 'win32') {
    command = 'rundll32.exe';
    args = ['url.dll,FileProtocolHandler', url];
  } else if (process.platform === 'darwin') {
    command = 'open';
    args = [url];
  } else {
    command = 'xdg-open';
    args = [url];
  }
  const child = spawn(command, args, { detached: true, stdio: 'ignore', windowsHide: true });
  child.unref();
}

function successPage(account) {
  return `<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Connexion réussie</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#07110f;color:#f8fafc;font:18px system-ui}.card{max-width:560px;margin:24px;padding:42px;border:1px solid #34d39955;border-radius:24px;background:#0d1d19;text-align:center;box-shadow:0 25px 80px #0008}.ok{font-size:52px;color:#6ee7b7}h1{font-size:36px;margin:8px 0 16px}p{color:#cbd5e1;line-height:1.6}</style><main class="card"><div class="ok">✓</div><h1>Connexion YouTube réussie</h1><p>Le compte <strong>${account}</strong> est prêt pour GitHub Actions. Tu peux fermer cette page.</p></main></html>`;
}

async function authorize(client, account) {
  const verifier = base64Url(crypto.randomBytes(48));
  const challenge = base64Url(crypto.createHash('sha256').update(verifier).digest());
  const state = base64Url(crypto.randomBytes(24));

  let resolveCallback;
  let rejectCallback;
  const callback = new Promise((resolve, reject) => {
    resolveCallback = resolve;
    rejectCallback = reject;
  });

  const server = http.createServer((request, response) => {
    try {
      const url = new URL(request.url || '/', `http://${request.headers.host}`);
      if (url.pathname !== '/oauth2/callback') {
        response.writeHead(404).end('Not found');
        return;
      }
      if (url.searchParams.get('state') !== state) throw new Error('État OAuth invalide. Relance la commande.');
      const error = url.searchParams.get('error');
      if (error) throw new Error(`Google a refusé la connexion : ${error}`);
      const code = url.searchParams.get('code');
      if (!code) throw new Error('Google n’a retourné aucun code OAuth.');
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(successPage(account));
      resolveCallback(code);
    } catch (error) {
      response.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' }).end('Connexion impossible. Tu peux fermer cette page et relancer la commande.');
      rejectCallback(error);
    }
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Impossible de démarrer le retour OAuth local.');
  const redirectUri = `http://127.0.0.1:${address.port}/oauth2/callback`;
  const authorization = new URL(AUTHORIZATION_URL);
  authorization.search = new URLSearchParams({
    client_id: client.clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: SCOPE,
    access_type: 'offline',
    prompt: 'consent',
    include_granted_scopes: 'true',
    code_challenge: challenge,
    code_challenge_method: 'S256',
    state,
  }).toString();

  process.stdout.write('Une page Google va s’ouvrir. Choisis la chaîne YouTube à connecter et accepte l’accès.\n');
  openBrowser(authorization.toString());
  const timer = setTimeout(() => rejectCallback(new Error('La connexion OAuth a expiré après 10 minutes.')), 10 * 60 * 1000);
  timer.unref?.();
  try {
    const code = await callback;
    const response = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: client.clientId,
        client_secret: client.clientSecret,
        code,
        code_verifier: verifier,
        grant_type: 'authorization_code',
        redirect_uri: redirectUri,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error_description || payload.error || `Google OAuth HTTP ${response.status}`);
    if (!payload.refresh_token) {
      throw new Error('Google n’a pas retourné de refresh token. Révoque l’ancien accès ClipMaker puis relance la commande.');
    }
    return String(payload.refresh_token);
  } finally {
    clearTimeout(timer);
    server.close();
  }
}

function readBundle(filename) {
  if (!fs.existsSync(filename)) return { accounts: {} };
  const parsed = JSON.parse(fs.readFileSync(filename, 'utf8'));
  return parsed && typeof parsed === 'object' && parsed.accounts && typeof parsed.accounts === 'object'
    ? parsed
    : { accounts: parsed || {} };
}

function setGitHubSecret(repo, encoded) {
  const result = spawnSync('gh', ['secret', 'set', 'YOUTUBE_OAUTH_ACCOUNTS_B64', '--repo', repo], {
    input: encoded,
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(String(result.stderr || result.stdout || 'gh secret set a échoué').trim());
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const account = normalizeAccount(args.account || 'default');
  const repo = String(args.repo || 'EinSlen/clipmaker').trim();
  const clientFile = path.resolve(String(args['client-json'] || ''));
  const bundleFile = path.resolve(String(args['bundle-file'] || DEFAULT_BUNDLE_FILE));
  if (!args['client-json'] || !fs.existsSync(clientFile)) {
    throw new Error('Ajoute --client-json avec le fichier OAuth téléchargé depuis Google Cloud.');
  }
  const client = loadDesktopClient(clientFile);
  const refreshToken = await authorize(client, account);
  const bundle = readBundle(bundleFile);
  bundle.accounts[account] = {
    clientId: client.clientId,
    clientSecret: client.clientSecret,
    refreshToken,
  };
  fs.writeFileSync(bundleFile, `${JSON.stringify(bundle, null, 2)}\n`, { mode: 0o600 });
  setGitHubSecret(repo, Buffer.from(JSON.stringify(bundle), 'utf8').toString('base64'));
  process.stdout.write(`Compte "${account}" enregistré dans le secret GitHub YOUTUBE_OAUTH_ACCOUNTS_B64.\n`);
  process.stdout.write('Aucun cookie, mot de passe ou jeton OAuth n’a été ajouté au dépôt.\n');
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
