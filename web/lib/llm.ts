// Lightweight LLM client. Free by default via Groq (llama-3.3-70b).
// Optional override: ANTHROPIC_API_KEY → Claude Haiku (premium quality).

type ChatMessage = { role: 'system' | 'user' | 'assistant'; content: string };

type CallOpts = {
  system: string;
  user: string;
  temperature?: number;
  maxTokens?: number;
};

export type LlmResult = { text: string; source: 'groq' | 'anthropic' | 'fallback'; error?: string };

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODEL = process.env.GROQ_MODEL || 'llama-3.3-70b-versatile';

async function callGroq({ system, user, temperature = 1, maxTokens = 1024 }: CallOpts): Promise<string> {
  const key = process.env.GROQ_API_KEY;
  if (!key) throw new Error('no-groq-key');
  const messages: ChatMessage[] = [
    { role: 'system', content: system },
    { role: 'user', content: user }
  ];
  const resp = await fetch(GROQ_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${key}`
    },
    body: JSON.stringify({
      model: GROQ_MODEL,
      messages,
      temperature,
      max_tokens: maxTokens
    })
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    throw new Error(`groq-http-${resp.status}: ${detail.slice(0, 200)}`);
  }
  const j = (await resp.json()) as { choices?: { message?: { content?: string } }[] };
  return j.choices?.[0]?.message?.content ?? '';
}

async function callAnthropic({ system, user, temperature = 1, maxTokens = 1024 }: CallOpts): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error('no-anthropic-key');
  const Anthropic = (await import('@anthropic-ai/sdk')).default;
  const client = new Anthropic({ apiKey: key });
  const resp = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: maxTokens,
    temperature,
    system,
    messages: [{ role: 'user', content: user }]
  });
  return resp.content.map((c) => (c.type === 'text' ? c.text : '')).join('');
}

export async function llmComplete(opts: CallOpts): Promise<LlmResult> {
  // Anthropic override if explicitly configured
  if (process.env.ANTHROPIC_API_KEY) {
    try {
      const text = await callAnthropic(opts);
      return { text, source: 'anthropic' };
    } catch (err) {
      console.warn('[llm] anthropic failed, falling back to Groq:', String(err).slice(0, 200));
    }
  }
  if (process.env.GROQ_API_KEY) {
    try {
      const text = await callGroq(opts);
      return { text, source: 'groq' };
    } catch (err) {
      return { text: '', source: 'fallback', error: String(err).slice(0, 200) };
    }
  }
  return { text: '', source: 'fallback', error: 'no-api-key' };
}

export function parseJsonLoose<T = unknown>(raw: string): T | null {
  const cleaned = raw
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/```$/i, '')
    .trim();
  try {
    return JSON.parse(cleaned) as T;
  } catch {
    // Try the largest balanced {...} substring
    const start = cleaned.indexOf('{');
    if (start >= 0) {
      let depth = 0;
      let inStr = false;
      let esc = false;
      for (let i = start; i < cleaned.length; i++) {
        const c = cleaned[i];
        if (inStr) {
          if (esc) esc = false;
          else if (c === '\\') esc = true;
          else if (c === '"') inStr = false;
          continue;
        }
        if (c === '"') inStr = true;
        else if (c === '{') depth++;
        else if (c === '}') {
          depth--;
          if (depth === 0) {
            try {
              return JSON.parse(cleaned.slice(start, i + 1)) as T;
            } catch {
              break;
            }
          }
        }
      }
    }
    return null;
  }
}

/** Extracts a string array from any text — handles models that wrap JSON in prose,
 *  emit malformed JSON, or just spit a numbered list. */
export function extractStringArray(raw: string, key = 'texts'): string[] {
  if (!raw) return [];
  const cleaned = raw.replace(/^```(?:json)?\s*/i, '').replace(/```$/i, '').trim();

  // 1) Strict JSON
  const parsed = parseJsonLoose<Record<string, unknown>>(cleaned);
  if (parsed && Array.isArray(parsed[key])) {
    return (parsed[key] as unknown[]).filter((t): t is string => typeof t === 'string');
  }

  // 2) Find the first array literal `[ "a", "b", ... ]` after the key (or anywhere)
  //    Walk the string with awareness of strings to extract balanced [...]
  const keyIdx = cleaned.indexOf('"' + key + '"');
  const startSearchFrom = keyIdx >= 0 ? keyIdx : 0;
  const arrStart = cleaned.indexOf('[', startSearchFrom);
  if (arrStart >= 0) {
    let depth = 0;
    let inStr = false;
    let esc = false;
    for (let i = arrStart; i < cleaned.length; i++) {
      const c = cleaned[i];
      if (inStr) {
        if (esc) esc = false;
        else if (c === '\\') esc = true;
        else if (c === '"') inStr = false;
        continue;
      }
      if (c === '"') inStr = true;
      else if (c === '[') depth++;
      else if (c === ']') {
        depth--;
        if (depth === 0) {
          try {
            const arr = JSON.parse(cleaned.slice(arrStart, i + 1));
            if (Array.isArray(arr)) return arr.filter((t): t is string => typeof t === 'string');
          } catch {}
          break;
        }
      }
    }
  }

  // 3) Numbered/bulleted lines fallback
  const lines = cleaned
    .split('\n')
    .map((l) => l.trim())
    .map((l) => l.replace(/^\d+[\).\s]+/, '').replace(/^[-*•"]\s*/, '').replace(/^"|"$/g, '').trim())
    .filter(Boolean);
  if (lines.length >= 2) return lines;

  return [];
}
