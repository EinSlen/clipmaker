import { NextResponse } from 'next/server';
import { FALLBACK_TEXTS, STYLE_SYSTEM_PROMPT } from '@/lib/fallback-texts';
import { llmComplete, extractStringArray } from '@/lib/llm';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function pickRandom<T>(arr: T[], n: number): T[] {
  const pool = [...arr];
  const out: T[] = [];
  while (out.length < n && pool.length) {
    out.push(pool.splice(Math.floor(Math.random() * pool.length), 1)[0]);
  }
  return out;
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { mood?: string; count?: number; theme?: string }));
  const count = Math.min(Math.max(Number(body?.count) || 8, 1), 20);
  const mood = (body?.mood as string) || 'mélancolique';
  const theme = (body?.theme as string) || '';

  const userPrompt = [
    `Ambiance : ${mood}.`,
    theme ? `Thème optionnel : ${theme}.` : '',
    `Génère ${count} textes différents.`,
    `Varie les longueurs (de 5 mots à 2 lignes).`,
    `Rappel : réponse JSON {"texts":[...]} uniquement.`
  ]
    .filter(Boolean)
    .join('\n');

  const llm = await llmComplete({
    system: STYLE_SYSTEM_PROMPT,
    user: userPrompt,
    temperature: 1,
    maxTokens: 1024
  });

  if (llm.text) {
    const texts = extractStringArray(llm.text, 'texts').slice(0, count);
    if (texts.length) return NextResponse.json({ texts, source: llm.source });
  }
  return NextResponse.json({ texts: pickRandom(FALLBACK_TEXTS, count), source: 'fallback', note: llm.error });
}
