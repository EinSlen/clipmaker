import { NextResponse } from 'next/server';
import { spawnYtdlp } from '@/lib/ytdlp';

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

type Candidate = {
  id: string;
  title: string;
  channel: string;
  url: string;
  duration: number;
  views: number;
  thumbnail?: string;
  width?: number;
  height?: number;
};

function ytdlpSearch(query: string, max: number): Promise<Candidate[]> {
  return new Promise((resolve) => {
    const proc = spawnYtdlp([
      `ytsearch${max}:${query}`,
      '--dump-json',
      '--no-download',
      '--no-warnings',
      '-q'
    ]);

    let out = '';
    let err = '';
    proc.stdout.on('data', (d) => (out += d.toString()));
    proc.stderr.on('data', (d) => (err += d.toString()));
    proc.on('close', () => {
      const items: Candidate[] = [];
      for (const line of out.split('\n')) {
        if (!line.trim()) continue;
        try {
          const j = JSON.parse(line);
          items.push({
            id: String(j.id ?? ''),
            title: String(j.title ?? ''),
            channel: String(j.channel ?? j.uploader ?? ''),
            url: String(j.webpage_url ?? `https://www.youtube.com/watch?v=${j.id}`),
            duration: Number(j.duration ?? 0),
            views: Number(j.view_count ?? 0),
            thumbnail: j.thumbnail,
            width: Number(j.width ?? 0),
            height: Number(j.height ?? 0)
          });
        } catch {
          // skip
        }
      }
      if (!items.length && err) console.warn('[youtube/suggest]', err.slice(0, 200));
      resolve(items);
    });
    proc.on('error', () => resolve([]));
  });
}

function scoreCandidate(c: Candidate): { score: number; reason: string } {
  let score = 0;
  const reasons: string[] = [];

  // Duration window 8-90s for a TikTok-friendly source
  if (c.duration >= 8 && c.duration <= 60) {
    score += 25;
    reasons.push('durée idéale');
  } else if (c.duration <= 120) {
    score += 12;
  }

  // Vertical bonus
  if (c.width && c.height && c.width / c.height < 0.7) {
    score += 20;
    reasons.push('format vertical');
  } else if (c.width && c.height && c.width / c.height < 1) {
    score += 6;
  }

  // Views
  if (c.views > 1_000_000) score += 18;
  else if (c.views > 100_000) score += 12;
  else if (c.views > 10_000) score += 6;

  // Title hints
  const t = c.title.toLowerCase();
  if (/sad|triste|melanchol|melanco|alone|lonely|cry|breakup|rupture/.test(t)) {
    score += 18;
    reasons.push('mots clés');
  }
  // People-centric bonus
  if (/girl|woman|man|boy|guy|person|people|couple|portrait|face|crying/.test(t)) {
    score += 12;
    reasons.push('humain');
  }
  if (/aesthetic|cinematic|edit/.test(t)) score += 8;
  // Penalize landscape-only / non-people content
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

  const lots = await Promise.all(queries.map((q) => ytdlpSearch(q, perQuery)));
  const all = lots.flat();

  const seen = new Set<string>();
  const dedup: Candidate[] = [];
  for (const c of all) {
    if (!c.id || seen.has(c.id)) continue;
    seen.add(c.id);
    dedup.push(c);
  }

  const scored = dedup
    .map((c) => ({ ...c, ...scoreCandidate(c) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return NextResponse.json({ items: scored, source: scored.length ? 'yt-dlp' : 'empty' });
}
