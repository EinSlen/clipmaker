import { NextResponse } from 'next/server';
import { HASHTAG_BANK } from '@/lib/fallback-texts';
import { llmComplete, extractStringArray } from '@/lib/llm';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function curated(text: string, count: number): string[] {
  const must = ['#fyp', '#pourtoi', '#triste', '#philosophie'];
  const lower = text.toLowerCase();
  const themed: string[] = [];
  if (/amour|coeur|rupture|toi|elle|lui/.test(lower)) themed.push('#rupture', '#coeurbrise', '#manque');
  if (/seul|solitude|silence|nuit/.test(lower)) themed.push('#solitude', '#silence', '#nuit');
  if (/temps|souvenir|grandir|vieill/.test(lower)) themed.push('#souvenirs', '#nostalgie');
  if (/fatigu|tristes|pleur|mal/.test(lower)) themed.push('#sadvibes', '#sad', '#emotion');
  return Array.from(new Set([...must, ...themed, ...HASHTAG_BANK])).slice(0, count);
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { text?: string; count?: number }));
  const text = (body?.text as string) || '';
  const count = Math.min(Math.max(Number(body?.count) || 18, 6), 30);

  const system = `Tu génères des hashtags TikTok pour des vidéos courtes mélancoliques/philosophiques en français. Retourne uniquement du JSON {"hashtags":["#...", ...]} avec environ ${count} tags. Inclus toujours #fyp #pourtoi. Mix : génériques de portée + thématiques (triste, philo, solitude, rupture, etc.) + 1-2 tags FR (#tiktokfrance). Pas de doublon. Tout en minuscules.`;
  const user = `Texte de la vidéo :\n"""${text || '(texte non fourni — fais des hashtags génériques tristes/philo)'}"""\n\nRetourne ${count} hashtags.`;

  const llm = await llmComplete({ system, user, temperature: 0.7, maxTokens: 500 });
  if (llm.text) {
    let tags = extractStringArray(llm.text, 'hashtags');
    if (!tags.length) tags = llm.text.split(/\s+/).filter((t) => t.startsWith('#'));
    if (tags.length) {
      const normalized = Array.from(new Set(tags.map((h) => (h.startsWith('#') ? h : `#${h}`).toLowerCase()))).slice(0, count);
      return NextResponse.json({ hashtags: normalized, source: llm.source });
    }
  }
  return NextResponse.json({ hashtags: curated(text, count), source: 'fallback', note: llm.error });
}
