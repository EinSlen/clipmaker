"use client";

import * as React from "react";
import {
  Music2,
  Loader2,
  Shuffle,
  Play,
  Pause,
  RefreshCw,
  Flame,
  UploadCloud,
} from "lucide-react";
import type { MusicTrack } from "@/lib/types";

type VibeOption = { id: string; label: string };

type Value = { file?: string; random: boolean; volume: number; vibe?: string };

export function MusicPicker({
  value,
  onChange,
}: {
  value: Value;
  onChange: (v: Value) => void;
}) {
  const [tracks, setTracks] = React.useState<MusicTrack[]>([]);
  const [vibes, setVibes] = React.useState<VibeOption[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [fetching, setFetching] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [autoFetchedCount, setAutoFetchedCount] = React.useState<number | null>(
    null
  );
  const [playingId, setPlayingId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const load = React.useCallback(async (v?: string) => {
    setLoading(true);
    setAutoFetchedCount(null);
    try {
      const url = v
        ? `/api/music/list?vibe=${encodeURIComponent(v)}`
        : "/api/music/list";
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
      await fetch("/api/music/fetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vibe: value.vibe, refresh: true }),
      });
      await load(value.vibe);
    } finally {
      setFetching(false);
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("vibe", value.vibe || "tendance");
      const r = await fetch("/api/music/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (j.ok) {
        onChange({
          ...value,
          file: j.file,
          random: false,
          vibe: j.vibe || value.vibe,
        });
        await load(value.vibe);
      } else {
        alert("Échec de l’import audio : " + (j.error || ""));
      }
    } finally {
      setUploading(false);
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <span className="grid size-8 place-items-center rounded-xl bg-fuchsia-500/10 text-fuchsia-200">
            <Music2 className="size-4" />
          </span>
          Musique TikTok triste et tendance
        </h3>
        <label className="flex cursor-pointer select-none items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-ink-200 transition hover:bg-white/10">
          <input
            type="checkbox"
            checked={value.random}
            onChange={(e) =>
              onChange({
                ...value,
                random: e.target.checked,
                file: e.target.checked ? undefined : value.file,
              })
            }
          />
          <Shuffle className="size-3.5" /> Aléatoire
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {vibes.map((v) => (
          <button
            key={v.id}
            onClick={() => onChange({ ...value, vibe: v.id, file: undefined })}
            className={`px-3 h-8 rounded-full text-xs border transition ${
              value.vibe === v.id
                ? "bg-accent text-white border-accent"
                : "border-white/15 text-ink-200 hover:bg-white/5"
            }`}
          >
            {v.label}
          </button>
        ))}
        {value.vibe && (
          <button
            onClick={refreshTrending}
            disabled={fetching}
            title="Actualiser les sons tendance"
            className="ml-auto flex h-8 items-center gap-1.5 rounded-full border border-white/15 px-3 text-xs font-medium text-ink-200 transition hover:border-white/25 hover:bg-white/5 disabled:opacity-50"
          >
            {fetching ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Actualiser
          </button>
        )}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          title="Importer une musique depuis le téléphone"
          className="flex h-8 items-center gap-1.5 rounded-full border border-white/15 px-3 text-xs font-medium text-ink-200 transition hover:border-white/25 hover:bg-white/5 disabled:opacity-50"
        >
          {uploading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <UploadCloud className="size-3.5" />
          )}
          Importer
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg"
          className="hidden"
          onChange={onPickFile}
        />
      </div>

      <div className="subpanel space-y-2 p-3">
        <label className="flex items-center justify-between text-xs text-ink-400">
          <span>Volume de la musique</span>
          <span className="font-medium text-white">
            {Math.round(value.volume * 100)} %
          </span>
        </label>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(value.volume * 100)}
          onChange={(e) =>
            onChange({ ...value, volume: Number(e.target.value) / 100 })
          }
          className="h-7 w-full accent-fuchsia-500"
        />
      </div>

      {loading ? (
        <div className="py-4 flex items-center gap-2 text-ink-400 text-sm">
          <Loader2 className="size-4 animate-spin" />{" "}
          {value.vibe
            ? `Téléchargement des sons « ${value.vibe} » tendance…`
            : "Chargement…"}
        </div>
      ) : tracks.length === 0 ? (
        <div className="space-y-2">
          <p className="text-sm leading-5 text-ink-400">
            Aucun son pour ce thème. Essaie d’actualiser la sélection — cette
            opération peut échouer chez certains hébergeurs — ou importe une
            musique depuis ton téléphone.
          </p>
          <div className="flex flex-wrap gap-2">
            {value.vibe && (
              <button
                onClick={refreshTrending}
                disabled={fetching}
                className="inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-accent text-white text-sm"
              >
                {fetching ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Flame className="size-4" />
                )}{" "}
                Actualiser « {value.vibe} »
              </button>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-white/10 text-ink-50 text-sm"
            >
              {uploading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <UploadCloud className="size-4" />
              )}{" "}
              Importer un MP3
            </button>
          </div>
        </div>
      ) : (
        <>
          {autoFetchedCount !== null && autoFetchedCount > 0 && (
            <p className="text-[11px] text-emerald-300/80">
              ↻ {autoFetchedCount} sons tendance fraîchement téléchargés.
            </p>
          )}
          <ul className="scroll-pretty max-h-56 space-y-1 overflow-auto pr-1">
            {tracks.map((t) => {
              const selected = !value.random && value.file === t.file;
              return (
                <li
                  key={t.id}
                  className={`flex h-11 items-center gap-2 rounded-xl border px-2 transition ${
                    selected
                      ? "border-accent/70 bg-accent/10 shadow-sm shadow-accent/10"
                      : "border-white/10 bg-black/10 hover:border-white/20 hover:bg-white/5"
                  }`}
                >
                  <button
                    onClick={() => togglePlay(t)}
                    className="size-8 grid place-items-center rounded-md bg-white/5 hover:bg-white/10"
                    aria-label={`Écouter un aperçu de ${t.title}`}
                  >
                    {playingId === t.id ? (
                      <Pause className="size-4" />
                    ) : (
                      <Play className="size-4" />
                    )}
                  </button>
                  <button
                    className="flex-1 text-left text-sm truncate"
                    onClick={() =>
                      onChange({ ...value, random: false, file: t.file })
                    }
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
          Mode aléatoire actif {value.vibe ? `parmi « ${value.vibe} »` : ""}.
          Une piste différente sera prise à chaque export.
        </p>
      )}
    </div>
  );
}
