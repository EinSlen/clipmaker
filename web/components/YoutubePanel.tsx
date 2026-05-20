'use client';

import * as React from 'react';
import { Loader2, Sparkles, ArrowDownToLine } from 'lucide-react';
import { Button } from './Button';
import type { YoutubeSuggestion } from '@/lib/types';

const VIBES = [
  { id: 'sad', label: 'Triste / aesthetic' },
  { id: 'philo', label: 'Cinéma / philo' },
  { id: 'nature', label: 'Nature / pluie' },
  { id: 'anime', label: 'Anime sad' }
];

export function YoutubePanel({
  onImported
}: {
  onImported: (info: { id: string; filename: string; size: number; title: string }) => void;
}) {
  const [vibe, setVibe] = React.useState('sad');
  const [items, setItems] = React.useState<YoutubeSuggestion[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [downloadingId, setDownloadingId] = React.useState<string | null>(null);

  const search = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/youtube/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vibe, limit: 12 })
      });
      const j = await r.json();
      setItems(j.items || []);
    } finally {
      setLoading(false);
    }
  };

  const importVid = async (s: YoutubeSuggestion) => {
    setDownloadingId(s.id);
    try {
      const r = await fetch('/api/youtube/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: s.url })
      });
      const j = await r.json();
      if (j.ok) onImported({ id: j.id, filename: j.filename, size: j.size, title: s.title });
      else alert('Téléchargement échoué : ' + (j.error || 'erreur'));
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {VIBES.map((v) => (
          <button
            key={v.id}
            onClick={() => setVibe(v.id)}
            className={`px-3 h-8 rounded-full text-sm border transition ${
              vibe === v.id ? 'bg-accent text-white border-accent' : 'border-white/15 text-ink-200 hover:bg-white/5'
            }`}
          >
            {v.label}
          </button>
        ))}
        <Button onClick={search} size="sm" className="ml-auto">
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          Suggérer
        </Button>
      </div>

      {items.length === 0 && !loading && (
        <p className="text-ink-400 text-sm">Clique sur « Suggérer » pour récupérer des vidéos YouTube collant à la vibe.</p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map((it) => (
          <div key={it.id} className="rounded-xl border border-white/10 overflow-hidden bg-ink-800/70">
            {it.thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={it.thumbnail} alt="" className="aspect-video object-cover w-full" />
            ) : (
              <div className="aspect-video bg-ink-700" />
            )}
            <div className="p-2 space-y-1">
              <div className="text-xs font-medium line-clamp-2">{it.title}</div>
              <div className="text-[11px] text-ink-400">{it.channel} · {it.duration}s · {Intl.NumberFormat('fr').format(it.views)} vues</div>
              <Button size="sm" variant="ghost" className="w-full mt-1" disabled={downloadingId === it.id} onClick={() => importVid(it)}>
                {downloadingId === it.id ? <Loader2 className="size-4 animate-spin" /> : <ArrowDownToLine className="size-4" />}
                Importer
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
