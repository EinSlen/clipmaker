import { NextResponse } from 'next/server';
import { searchYoutube, type YtSearchHit } from '@/lib/youtube-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

// Queries focus on PEOPLE in sad/melancholic moments — not landscapes/nature.
const QUERIES_BY_VIBE: Record<string, string[]> = {
  sad: [
    'sad person crying aesthetic short',
    'lonely man window rain aesthetic',
    'girl crying cinematic short',
    'sad people walking alone city short',
    'man sitting alone night sad',
    'crying scene movie aesthetic short'
  ],
  philo: [
    'lonely man walking thinking cinematic',
    'person staring window melancholic',
    'sad woman portrait cinematic',
    'man alone room thinking aesthetic',
    'cinematic portrait melancholic person'
  ],
  rupture: [
    'breakup sad scene movie aesthetic',
    'couple separation sad cinematic',
    'woman crying after breakup short',
    'man missing her sad scene',
    'last hug breakup sad aesthetic'
  ],
  solitude: [
    'sitting alone bench sad person short',
    'man alone bar night sad cinematic',
    'walking alone street rain person',
    'silhouette person alone sad short',
    'lonely girl bedroom aesthetic sad'
  ],
  anime: [
    'sad anime girl crying edit short',
    'lonely anime character aesthetic',
    'anime breakup scene sad edit'
  ]
};

type Candidate = YtSearchHit & { score: number; reason: string };

function scoreCandidate(c: YtSearchHit): { score: number; reason: string } {
  let score = 0;
  const reasons: string[] = [];

  if (c.duration >= 8 && c.duration <= 60) {
    score += 25;
    reasons.push('durée idéale');
  } else if (c.duration <= 120) {
    score += 12;
  }

  if (c.width && c.height && c.width / c.height < 0.7) {
    score += 20;
    reasons.push('format vertical');
  } else if (c.width && c.height && c.width / c.height < 1) {
    score += 6;
  }

  if (c.views > 1_000_000) score += 18;
  else if (c.views > 100_000) score += 12;
  else if (c.views > 10_000) score += 6;

  const t = c.title.toLowerCase();
  if (/sad|triste|melanchol|melanco|alone|lonely|cry|breakup|rupture/.test(t)) {
    score += 18;
    reasons.push('mots clés');
  }
  if (/girl|woman|man|boy|guy|person|people|couple|portrait|face|crying/.test(t)) {
    score += 12;
    reasons.push('humain');
  }
  if (/aesthetic|cinematic|edit/.test(t)) score += 8;
  if (/landscape|nature only|drone|timelapse|wallpaper|asmr|loop animation|relaxing music/.test(t)) score -= 15;
  if (/funny|meme|gameplay|reaction|tutorial|how to/.test(t)) score -= 30;

  return { score, reason: reasons.join(', ') || 'candidat' };
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({} as { vibe?: string; limit?: number }));
  const vibe = (body?.vibe as string) || 'sad';
  const limit = Math.min(Math.max(Number(body?.limit) || 12, 4), 24);

  const queries = QUERIES_BY_VIBE[vibe] || QUERIES_BY_VIBE.sad;
  const perQuery = Math.ceil(limit / queries.length) + 1;

  const lots: YtSearchHit[][] = await Promise.all(
    queries.map(async (q) => {
      try {
        return await searchYoutube(q, perQuery);
      } catch (e) {
        console.warn('[youtube/suggest]', String(e).slice(0, 150));
        return [];
      }
    })
  );
  const all = lots.flat();

  const seen = new Set<string>();
  const dedup: YtSearchHit[] = [];
  for (const c of all) {
    if (!c.id || seen.has(c.id)) continue;
    seen.add(c.id);
    dedup.push(c);
  }

  const scored: Candidate[] = dedup
    .map((c) => ({ ...c, ...scoreCandidate(c) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return NextResponse.json({ items: scored, source: scored.length ? 'invidious' : 'empty' });
}
