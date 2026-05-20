'use client';

import * as React from 'react';
import { Music2, Loader2, Shuffle, Play, Pause, RefreshCw, Flame } from 'lucide-react';
import type { MusicTrack } from '@/lib/types';

type VibeOption = { id: string; label: string };

type Value = { file?: string; random: boolean; volume: number; vibe?: string };

export function MusicPicker({
  value,
  onChange
}: {
  value: Value;
  onChange: (v: Value) => void;
}) {
  const [tracks, setTracks] = React.useState<MusicTrack[]>([]);
  const [vibes, setVibes] = React.useState<VibeOption[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [fetching, setFetching] = React.useState(false);
  const [autoFetchedCount, setAutoFetchedCount] = React.useState<number | null>(null);
  const [playingId, setPlayingId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const load = React.useCallback(async (v?: string) => {
    setLoading(true);
    setAutoFetchedCount(null);
    try {
      const url = v ? `/api/music/list?vibe=${encodeURIComponent(v)}` : '/api/music/list';
      const r = await fetch(url);
      const j = await r.json();
      setTracks(j.tracks || []);
      if (j.autoFetched?.added) setAutoFetchedCount(j.autoFetched.added);
      if (Array.isArray(j.vibes) && j.vibes.length) setVibes(j.vibes);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load(value.vibe);
  }, [value.vibe, load]);

  async function refreshTrending() {
    if (!value.vibe) return;
    setFetching(true);
    try {
      await fetch('/api/music/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vibe: value.vibe, refresh: true })
      });
      await load(value.vibe);
    } finally {
      setFetching(false);
    }
  }

  function togglePlay(track: MusicTrack) {
    if (!audioRef.current) audioRef.current = new Audio();
    if (playingId === track.id) {
      audioRef.current.pause();
      setPlayingId(null);
      return;
    }
    audioRef.current.src = track.file;
    audioRef.current.volume = value.volume;
    audioRef.current.play().catch(() => {});
    setPlayingId(track.id);
    audioRef.current.onended = () => setPlayingId(null);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <Music2 className="size-4" /> Musique triste tendance TikTok
        </h3>
        <label className="flex items-center gap-2 text-xs text-ink-200 select-none">
          <input
            type="checkbox"
            checked={value.random}
            onChange={(e) => onChange({ ...value, random: e.target.checked, file: e.target.checked ? undefined : value.file })}
          />
          <Shuffle className="size-3.5" /> aléatoire
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {vibes.map((v) => (
          <button
            key={v.id}
            onClick={() => onChange({ ...value, vibe: v.id, file: undefined })}
            className={`px-3 h-8 rounded-full text-xs border transition ${
              value.vibe === v.id ? 'bg-accent text-white border-accent' : 'border-white/15 text-ink-200 hover:bg-white/5'
            }`}
          >
            {v.label}
          </button>
        ))}
        {value.vibe && (
          <button
            onClick={refreshTrending}
            disabled={fetching}
            title="Re-télécharger les sons tendance"
            className="ml-auto px-3 h-8 rounded-full text-xs border border-white/15 text-ink-200 hover:bg-white/5 flex items-center gap-1"
          >
            {fetching ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            re-pull
          </button>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs text-ink-400">Volume musique : {Math.round(value.volume * 100)}%</label>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(value.volume * 100)}
          onChange={(e) => onChange({ ...value, volume: Number(e.target.value) / 100 })}
          className="w-full"
        />
      </div>

      {loading ? (
        <div className="py-4 flex items-center gap-2 text-ink-400 text-sm">
          <Loader2 className="size-4 animate-spin" /> {value.vibe ? `Téléchargement des sons « ${value.vibe} » tendance…` : 'Chargement…'}
        </div>
      ) : tracks.length === 0 ? (
        <div className="space-y-2">
          <p className="text-ink-400 text-sm">
            Aucun son pour ce thème. {value.vibe && 'Clique « re-pull » pour télécharger depuis YouTube.'}
          </p>
          {value.vibe && (
            <button
              onClick={refreshTrending}
              disabled={fetching}
              className="inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-accent text-white text-sm"
            >
              {fetching ? <Loader2 className="size-4 animate-spin" /> : <Flame className="size-4" />} Télécharger les tendances « {value.vibe} »
            </button>
          )}
        </div>
      ) : (
        <>
          {autoFetchedCount !== null && autoFetchedCount > 0 && (
            <p className="text-[11px] text-emerald-300/80">↻ {autoFetchedCount} sons tendance fraîchement téléchargés.</p>
          )}
          <ul className="space-y-1 max-h-56 overflow-auto scroll-pretty">
            {tracks.map((t) => {
              const selected = !value.random && value.file === t.file;
              return (
                <li
                  key={t.id}
                  className={`flex items-center gap-2 px-2 h-10 rounded-lg border transition ${
                    selected ? 'border-accent bg-accent/10' : 'border-white/10 hover:bg-white/5'
                  }`}
                >
                  <button
                    onClick={() => togglePlay(t)}
                    className="size-8 grid place-items-center rounded-md bg-white/5 hover:bg-white/10"
                    aria-label="Preview"
                  >
                    {playingId === t.id ? <Pause className="size-4" /> : <Play className="size-4" />}
                  </button>
                  <button
                    className="flex-1 text-left text-sm truncate"
                    onClick={() => onChange({ ...value, random: false, file: t.file })}
                  >
                    <span className="font-medium">{t.title}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {value.random && tracks.length > 0 && (
        <p className="text-[11px] text-ink-400">
          Mode aléatoire actif {value.vibe ? `parmi « ${value.vibe} »` : ''}. Une piste différente sera prise à chaque export.
        </p>
      )}
    </div>
  );
}
