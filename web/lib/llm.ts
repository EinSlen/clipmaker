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
    // Try to find the first {...} blob
    const m = cleaned.match(/\{[\s\S]*\}/);
    if (!m) return null;
    try {
      return JSON.parse(m[0]) as T;
    } catch {
      return null;
    }
  }
}
