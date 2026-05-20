import { NextResponse } from 'next/server';
import { searchYoutube, type YtSearchHit } from '@/lib/youtube-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

// Queries target the @insocixble / @u.s.e.r.0.0.46 vibe: one person, dark/low-light space,
// cinematic mood — no Shorts memes, no movie-quote compilations, no music-only clips.
const QUERIES_BY_VIBE: Record<string, string[]> = {
  sad: [
    'lonely person dark room cinematic b roll',
    'sad man dim light window aesthetic b roll',
    'girl alone dark bedroom cinematic shot',
    'silhouette person dark room melancholic',
    'sad figure low light cinematic footage',
    'person crying dark room cinematic'
  ],
  philo: [
    'man staring window dark cinematic b roll',
    'person sitting dark room thinking cinematic',
    'pensive man dim light cinematic shot',
    'lonely figure dark interior cinematic footage',
    'introspective dark cinematic person b roll'
  ],
  rupture: [
    'sad person dark room after breakup cinematic',
    'lonely girl crying dark bedroom aesthetic',
    'man sitting floor dark room sad cinematic',
    'heartbroken person dark room b roll',
    'sad person bed dark night cinematic'
  ],
  solitude: [
    'person alone dark apartment cinematic b roll',
    'lonely man dark bar night cinematic',
    'silhouette walking dark street rain',
    'girl alone dark room window night',
    'alone in dark room aesthetic footage'
  ],
  anime: [
    'sad anime character dark room aesthetic',
    'lonely anime girl night window aesthetic',
    'dark cinematic sad anime edit'
  ]
};

type Candidate = YtSearchHit & { score: number; reason: string };

function scoreCandidate(c: YtSearchHit): { score: number; reason: string } {
  let score = 0;
  const reasons: string[] = [];

  if (c.duration >= 5 && c.duration <= 30) {
    score += 28;
    reasons.push('clip court');
  } else if (c.duration > 30 && c.duration <= 60) {
    score += 18;
  } else if (c.duration > 60 && c.duration <= 120) {
    score += 8;
  } else if (c.duration > 300) {
    score -= 20;
  }

  if (c.width && c.height && c.width / c.height < 0.7) {
    score += 15;
    reasons.push('vertical');
  }

  if (c.views > 100_000) score += 8;

  const t = c.title.toLowerCase();

  // Strong boosts: dark / cinematic / single-person framing
  if (/cinematic|b[\s-]?roll|cinemato|stock footage|film|short film|aesthetic/.test(t)) {
    score += 22;
    reasons.push('cinématique');
  }
  if (/dark|night|dim|low\s?light|shadow|silhouette|moody|noir|black/.test(t)) {
    score += 22;
    reasons.push('sombre');
  }
  if (/alone|lonely|solitude|sitting|standing|window|bedroom|interior|room/.test(t)) {
    score += 14;
    reasons.push('intimiste');
  }
  if (/girl|woman|man|boy|guy|person|figure|face|portrait/.test(t)) {
    score += 10;
    reasons.push('humain');
  }
  if (/sad|triste|melanchol|melanco|crying|breakup|heartbroken|depression/.test(t)) {
    score += 14;
    reasons.push('mood');
  }

  // Heavy penalties: avoid the noise that polluted previous results
  if (/#shorts|tiktok compilation|tik\s?tok\b/.test(t)) score -= 30;
  if (/movie scene|movie clip|crying scene|saddest scene|saddest movie|tearjerker/.test(t)) score -= 25;
  if (/quotes|quote|saying|reaction|compilation|funny|meme|prank|tutorial|how to/.test(t)) score -= 30;
  if (/lyrics|lyric video|cover song|music video|official video/.test(t)) score -= 25;
  if (/asmr|relaxing|sleep|study|10 hours/.test(t)) score -= 25;
  if (/landscape|drone|timelapse|wallpaper|loop animation|nature relaxation/.test(t)) score -= 20;
  if (/gameplay|gaming|minecraft|fortnite|valorant|roblox/.test(t)) score -= 50;

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

  return NextResponse.json({ items: scored, source: scored.length ? 'ok' : 'empty' });
}
