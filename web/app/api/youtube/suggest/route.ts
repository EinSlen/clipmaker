import { NextResponse } from 'next/server';
import { searchYoutube, type YtSearchHit } from '@/lib/youtube-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

// Vibe @klaradagoat / @u.s.e.r.0.0.46 : POV intime, sad-girl/sad-boy vent, plan rapproché
// d'une personne seule la nuit, ambiance handheld/journal — pas du b-roll stock détaché.
const QUERIES_BY_VIBE: Record<string, string[]> = {
  sad: [
    'sad girl pov vent video crying alone bedroom',
    'sad boy alone room night vent diary',
    'pov girl sitting alone dark bedroom sad',
    'lonely girl close up crying night vertical',
    'sad pov drinking alone night bedroom',
    'sad vent tiktok style alone room dark',
    'sad girl looking at camera crying dim light'
  ],
  philo: [
    'pov sitting alone window night thinking',
    'sad guy talking to camera dark room vent',
    'introspective vent vlog alone night bedroom',
    'pov man looking at ceiling dark room',
    'late night vent video alone dark room',
    'sad reflection talking camera dim light'
  ],
  rupture: [
    'sad girl crying breakup pov bedroom',
    'pov sitting floor crying after breakup night',
    'heartbroken vent video alone bedroom dark',
    'sad girl on phone crying dark room',
    'pov man crying breakup dim light bedroom'
  ],
  solitude: [
    'pov alone apartment night sad vlog',
    'sad night vlog alone bedroom vent',
    'pov walking alone street night sad',
    'lonely girl pov bed dark room night',
    'alone in room sad vent video dim light',
    'pov drinking alone late night sad'
  ],
  anime: [
    'sad anime girl close up crying dark room',
    'lonely anime character pov bedroom night',
    'anime sad scene close up dark aesthetic'
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

  // Strong boosts: POV / vent / face-cam intimiste à la klaradagoat
  if (/\bpov\b|first person|vlog|vent|talking to camera|talk to camera|diary|journal/.test(t)) {
    score += 30;
    reasons.push('POV/vent');
  }
  if (/close[\s-]?up|selfie|webcam|phone camera|filming myself/.test(t)) {
    score += 20;
    reasons.push('proche');
  }
  if (/dark|night|dim|low\s?light|shadow|silhouette|moody|noir|bedroom at night/.test(t)) {
    score += 22;
    reasons.push('sombre');
  }
  if (/sad|triste|melanchol|melanco|crying|tears|breakup|heartbroken|depression|venting|alone tonight/.test(t)) {
    score += 22;
    reasons.push('mood');
  }
  if (/alone|lonely|solitude|by myself|empty room|bedroom|interior|my room/.test(t)) {
    score += 18;
    reasons.push('intimiste');
  }
  if (/girl|woman|man|boy|guy|person|her|him|face|portrait/.test(t)) {
    score += 8;
    reasons.push('humain');
  }
  // Léger boost cinématique (moins fort qu'avant: on ne veut PAS du stock footage)
  if (/cinematic|aesthetic|film grain|short film/.test(t)) {
    score += 8;
    reasons.push('ciné');
  }

  // Pénalités: éviter le stock footage / b-roll détaché, et la pollution habituelle
  if (/\bb[\s-]?roll\b|stock footage|free footage|royalty free|no copyright/.test(t)) score -= 25;
  if (/#shorts|tiktok compilation|tik\s?tok\b/.test(t)) score -= 30;
  if (/movie scene|movie clip|crying scene|saddest scene|saddest movie|tearjerker/.test(t)) score -= 25;
  if (/quotes|quote|saying|reaction|compilation|funny|meme|prank|tutorial|how to/.test(t)) score -= 30;
  if (/lyrics|lyric video|cover song|music video|official video/.test(t)) score -= 25;
  if (/asmr|relaxing|sleep|study|10 hours/.test(t)) score -= 25;
  if (/landscape|drone|timelapse|wallpaper|loop animation|nature relaxation/.test(t)) score -= 25;
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
