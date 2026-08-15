function timeoutSignal(timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error(`Request timed out after ${timeoutMs} ms.`)), timeoutMs);
  timer.unref?.();
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

async function request(baseUrl, pathname, options = {}, timeoutMs = 60_000) {
  const timeout = timeoutSignal(timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${pathname}`, { ...options, signal: timeout.signal });
    const text = await response.text();
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
    const accounts = await request(config.baseUrl, '/api/tiktok/accounts', {}, 30_000);
    results.app = { ok: true };
    const tiktokConfigured = !channel.tiktok.enabled
      || (Array.isArray(accounts.accounts)
        && accounts.accounts.some((account) => account.username === channel.tiktok.username));
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
