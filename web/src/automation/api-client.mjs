import http from 'node:http';
import https from 'node:https';

function timeoutSignal(timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error(`Request timed out after ${timeoutMs} ms.`)), timeoutMs);
  timer.unref?.();
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

function requestText(url, options, signal) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const transport = target.protocol === 'https:' ? https : http;
    const request = transport.request(target, {
      method: options.method || 'GET',
      headers: options.headers,
      signal,
    }, (response) => {
      const chunks = [];
      response.on('data', (chunk) => chunks.push(chunk));
      response.on('end', () => resolve({
        ok: response.statusCode >= 200 && response.statusCode < 300,
        status: response.statusCode || 0,
        text: Buffer.concat(chunks).toString('utf8'),
      }));
      response.on('error', reject);
    });
    request.on('error', reject);
    if (options.body !== undefined) request.write(options.body);
    request.end();
  });
}

async function request(baseUrl, pathname, options = {}, timeoutMs = 60_000) {
  const timeout = timeoutSignal(timeoutMs);
  try {
    // Node's built-in fetch has a fixed five-minute Undici headers timeout.
    // Native HTTP keeps the explicit per-operation timeout authoritative for
    // long CPU/Blender renders that legitimately take longer than five minutes.
    const response = await requestText(`${baseUrl}${pathname}`, options, timeout.signal);
    const text = response.text;
    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { ok: false, error: text.slice(0, 2000) || `HTTP ${response.status}` };
    }
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.error || payload.stderr || `HTTP ${response.status}`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  } finally {
    timeout.clear();
  }
}

function jsonHeaders(token) {
  return {
    'content-type': 'application/json',
    ...(token ? { 'x-clipmaker-upload-token': token } : {}),
  };
}

export function renderVideo(config, payload) {
  return request(
    config.baseUrl,
    '/api/game/render',
    { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(payload) },
    config.requestTimeoutMinutes * 60_000,
  );
}

export function uploadYoutube(config, payload, token) {
  return request(
    config.baseUrl,
    '/api/youtube/upload',
    { method: 'POST', headers: jsonHeaders(token), body: JSON.stringify(payload) },
    20 * 60_000,
  );
}

export function uploadTiktok(config, payload, token) {
  return request(
    config.baseUrl,
    '/api/tiktok/upload',
    { method: 'POST', headers: jsonHeaders(token), body: JSON.stringify(payload) },
    20 * 60_000,
  );
}

export async function doctorEndpoints(config, channel) {
  const results = {};
  try {
    const verify = encodeURIComponent(channel.tiktok.username);
    const accounts = await request(config.baseUrl, `/api/tiktok/accounts?verify=${verify}`, {}, 120_000);
    results.app = { ok: true };
    const tiktokConfigured = !channel.tiktok.enabled
      || (Array.isArray(accounts.accounts)
        && accounts.accounts.some((account) => (
          account.username === channel.tiktok.username
          && account.ready === true
          && account.studioReady === true
        )));
    results.tiktok = {
      ok: config.dryRun || tiktokConfigured,
      enabled: channel.tiktok.enabled,
      configured: tiktokConfigured,
      username: channel.tiktok.username,
    };
  } catch (error) {
    results.app = { ok: false, error: error.message };
    results.tiktok = { ok: false, enabled: channel.tiktok.enabled, error: error.message };
  }
  try {
    const status = await request(
      config.baseUrl,
      `/api/youtube/status?account=${encodeURIComponent(channel.youtube.account)}`,
      {},
      30_000,
    );
    const configured = !channel.youtube.enabled
      || (status.ok && !status.dryRun && status.readyForLiveUpload);
    results.youtube = {
      ...status,
      ok: config.dryRun || configured,
      enabled: channel.youtube.enabled,
      configuredForPublishing: configured,
    };
  } catch (error) {
    results.youtube = { ok: false, error: error.message };
  }
  return results;
}
