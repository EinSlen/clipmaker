const DEFAULT_ENDPOINT = 'https://clipmaker-cloud-control.einslen.workers.dev';

// Inference goes through the ClipMaker Worker, which holds the Workers AI
// binding. No Cloudflare API token is needed anywhere outside the account, and
// the runner authenticates with the token it already carries.
function endpoint() {
  return String(process.env.CLOUD_CONTROL_API || DEFAULT_ENDPOINT).replace(/\/+$/, '');
}

function token() {
  const value = process.env.CLIPMAKER_UPLOAD_TOKEN || '';
  if (!value) throw new Error('CLIPMAKER_UPLOAD_TOKEN is required to reach the ClipMaker AI proxy.');
  return value;
}

async function runTask(task, input, { attempts = 3 } = {}) {
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(`${endpoint()}/api/ai/run`, {
        method: 'POST',
        headers: { authorization: `Bearer ${token()}`, 'content-type': 'application/json' },
        body: JSON.stringify({ task, input }),
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(`ai-${task}-http-${response.status}: ${detail.slice(0, 300)}`);
      }
      const payload = await response.json();
      if (payload.ok !== true) throw new Error(`ai-${task}: ${String(payload.error || 'unknown').slice(0, 200)}`);
      return payload.result;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, attempt * 2000));
    }
  }
  throw lastError;
}

export async function generateImage(prompt, seed) {
  const result = await runTask('image', { prompt: String(prompt).slice(0, 8000), steps: 4, seed });
  const encoded = result?.image;
  if (typeof encoded !== 'string' || encoded.length < 512) throw new Error('Workers AI returned no image.');
  return Buffer.from(encoded, 'base64');
}

// The proxy pins the vertical frame and bounds the length, so the caller only
// chooses what the shot shows and which seed makes it reproducible. The model
// answers with a URL rather than bytes, and the caller downloads it.
export async function generateVideo(prompt, { duration, seed, resolution } = {}) {
  const outcome = await runTask('video', {
    prompt: String(prompt).slice(0, 2500),
    ...(Number.isFinite(duration) ? { duration } : {}),
    ...(Number.isFinite(seed) ? { seed } : {}),
    ...(resolution ? { resolution } : {}),
  });
  const state = String(outcome?.state || '');
  if (state && state.toLowerCase() !== 'completed') throw new Error(`Workers AI video state: ${state}.`);
  const url = String(outcome?.result?.video || '');
  // The proxy is trusted, but a plaintext URL would still carry the clip in the
  // clear, so only a loopback host may be http and only the local harness ever
  // is one.
  const safe = /^https:\/\//u.test(url) || /^http:\/\/127\.0\.0\.1(:\d+)?\//u.test(url);
  if (!safe) throw new Error('Workers AI returned no video URL.');
  return url;
}

export async function generateText({ messages, maxTokens = 2048, temperature, json = true }) {
  const result = await runTask('text', { messages, max_tokens: maxTokens, temperature, json });
  // In JSON mode Workers AI hands back an already parsed object rather than a
  // string, so both shapes have to be accepted.
  const response = typeof result === 'string' ? result : result?.response;
  if (response && typeof response === 'object') return JSON.stringify(response);
  if (typeof response !== 'string' || !response.trim()) throw new Error('Workers AI returned no text.');
  return response;
}
