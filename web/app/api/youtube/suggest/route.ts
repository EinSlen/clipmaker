import { NextResponse } from 'next/server';
import { searchYoutube, type YtSearchHit } from '@/lib/youtube-api';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

// Vibe @1998greenram / @u.s.e.r.0.0.46 : sad-boy cinématique masculin, atmosphère
// sombre/nocturne, plans contemplatifs (voiture la nuit, fumeur dehors, fenêtre,
// silhouette dans la pluie). Mood Anathema/post-rock — pas du vent face-cam.
const QUERIES_BY_VIBE: Record<string, string[]> = {
  sad: [
    'lonely man driving at night cinematic',
    'sad guy looking out window rain cinematic',
    'man smoking alone night cinematic shot',
    'sad boy walking dark street night cinematic',
    'lonely figure car night rain cinematic',
    'man alone window night melancholic cinematic',
    'silhouette man dark city night cinematic'
  ],
  philo: [
    'man staring window cinematic philosophical',
    'lonely man rooftop city night cinematic',
    'man thinking dark room cinematic shot',
    'introspective man window rain cinematic',
    'man walking bridge fog cinematic mood',
    'silhouette man looking at city night cinematic'
  ],
  rupture: [
    'sad man driving night after breakup cinematic',
    'lonely man cigarette rain cinematic shot',
    'heartbroken man dark street cinematic',
    'man sitting car night sad cinematic',
    'sad man window night rain cinematic'
  ],
  solitude: [
    'lonely man walking dark street night cinematic',
    'man alone bar night cinematic shot',
    'silhouette walking rain night cinematic',
    'man alone apartment window night cinematic',
    'man driving alone highway night cinematic',
    'lonely figure dark city night cinematic'
  ],
  anime: [
    'sad anime boy window night aesthetic',
    'lonely anime character night cinematic dark',
    'anime sad boy walking rain dark aesthetic'
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

  // Strong boosts: sad-boy cinématique masculin (Jaxon/Anathema vibe)
  if (/cinematic|short film|film grain|aesthetic|moody|atmospheric/.test(t)) {
    score += 28;
    reasons.push('cinématique');
  }
  if (/dark|night|dim|low\s?light|shadow|silhouette|noir|rain|fog|smoke|neon|streetlight/.test(t)) {
    score += 26;
    reasons.push('sombre');
  }
  if (/sad|triste|melanchol|melanco|breakup|heartbroken|depression|empty|hopeless|nostalgia|nostalgic/.test(t)) {
    score += 20;
    reasons.push('mood');
  }
  if (/alone|lonely|solitude|by myself|walking alone|driving alone|empty street|empty room|empty city/.test(t)) {
    score += 22;
    reasons.push('seul');
  }
  // Cadrage : voiture / nuit / fenêtre / silhouette — signature Jaxon
  if (/driving|car at night|inside car|window|rooftop|bridge|highway|cigarette|smoking/.test(t)) {
    score += 16;
    reasons.push('cadrage');
  }
  if (/man|boy|guy|him|male|figure|silhouette/.test(t)) {
    score += 10;
    reasons.push('masculin');
  }

  // Pénalités: éviter stock footage évident, vent face-cam, et la pollution habituelle
  if (/\bb[\s-]?roll\b|stock footage|free footage|royalty free|no copyright/.test(t)) score -= 18;
  if (/\bpov\b|vlog|vent|talking to camera|talk to camera|webcam|selfie|filming myself/.test(t)) score -= 20;
  if (/#shorts|tiktok compilation|tik\s?tok\b/.test(t)) score -= 30;
  if (/movie scene|movie clip|crying scene|saddest scene|saddest movie|tearjerker/.test(t)) score -= 25;
  if (/quotes|quote|saying|reaction|compilation|funny|meme|prank|tutorial|how to/.test(t)) score -= 30;
  if (/lyrics|lyric video|cover song|music video|official video/.test(t)) score -= 25;
  if (/asmr|relaxing|sleep|study|10 hours/.test(t)) score -= 25;
  if (/landscape only|drone tour|timelapse|wallpaper|loop animation|nature relaxation/.test(t)) score -= 20;
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
