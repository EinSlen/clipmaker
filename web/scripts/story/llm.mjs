import { generateText } from './workers-ai.mjs';

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

function extractJson(text) {
  const trimmed = String(text).trim();
  try {
    return JSON.parse(trimmed);
  } catch {}
  // Llama sometimes wraps the object in prose or a fenced block.
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('The writer returned no JSON object.');
  return JSON.parse(trimmed.slice(start, end + 1));
}

async function callGroq({ system, user, temperature, maxTokens }) {
  const key = process.env.GROQ_API_KEY;
  if (!key) throw new Error('no-groq-key');
  const response = await fetch(GROQ_URL, {
    method: 'POST',
    headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' },
    body: JSON.stringify({
      model: process.env.GROQ_STORY_MODEL || process.env.GROQ_MODEL || 'llama-3.3-70b-versatile',
      temperature,
      max_tokens: maxTokens,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    }),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    throw new Error(`groq-http-${response.status}: ${detail.slice(0, 300)}`);
  }
  const payload = await response.json();
  return payload?.choices?.[0]?.message?.content || '';
}

// Workers AI is the default because it needs no key of its own; Groq is only
// used when a key happens to be configured.
// `validate` runs inside the retry loop on purpose: a payload that parses but
// misses required fields is a bad generation, and asking again fixes it.
export async function askJson({ system, user, temperature = 0.9, maxTokens = 2400, attempts = 3, validate }) {
  const messages = [{ role: 'system', content: system }, { role: 'user', content: user }];
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const text = process.env.GROQ_API_KEY
        ? await callGroq({ system, user, temperature, maxTokens })
        : await generateText({ messages, maxTokens, temperature, json: true });
      const parsed = extractJson(text);
      if (!parsed || typeof parsed !== 'object') throw new Error('The writer returned a non-object payload.');
      return validate ? validate(parsed) : parsed;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, attempt * 1500));
    }
  }
  throw lastError;
}
