'use client';

import * as React from 'react';
import { Download, Gamepad2, Loader2, Music2, RefreshCw, Sparkles, UploadCloud } from 'lucide-react';
import { AccountPicker } from './AccountPicker';
import { Button } from './Button';
import { YoutubePublisher } from './YoutubePublisher';
import type { MusicTrack } from '@/lib/types';

type Theme = 'neon' | 'sunset' | 'ice';
type SoundPack = 'auto' | 'funny' | 'arcade' | 'impact';

type GameResult = {
  filename: string;
  size: number;
  duration: number;
  seed: number;
  rings: number;
  theme: Theme;
  soundPack: SoundPack;
  musicUsed: string | null;
  title: string;
  youtubeTitle: string;
  caption: string;
  tags: string[];
};

const themes: { id: Theme; label: string; colors: string }[] = [
  { id: 'neon', label: 'Arc-en-ciel', colors: 'from-fuchsia-500 via-cyan-400 to-lime-400' },
  { id: 'sunset', label: 'Sunset', colors: 'from-orange-500 via-pink-500 to-purple-600' },
  { id: 'ice', label: 'Glace', colors: 'from-cyan-300 via-blue-400 to-indigo-600' },
];

export function GameStudio() {
  const [duration, setDuration] = React.useState(45);
  const [rings, setRings] = React.useState(18);
  const [theme, setTheme] = React.useState<Theme>('neon');
  const [soundPack, setSoundPack] = React.useState<SoundPack>('auto');
  const [musicTracks, setMusicTracks] = React.useState<MusicTrack[]>([]);
  const [musicFile, setMusicFile] = React.useState('');
  const [musicVolume, setMusicVolume] = React.useState(0.24);
  const [uploadingMusic, setUploadingMusic] = React.useState(false);
  const musicInputRef = React.useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = React.useState("La balle va-t-elle s'échapper ?");
  const [seed, setSeed] = React.useState('');
  const [rendering, setRendering] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<GameResult | null>(null);
  const [caption, setCaption] = React.useState('');
  const [account, setAccount] = React.useState<string | undefined>();
  const [uploading, setUploading] = React.useState(false);
  const [uploadMessage, setUploadMessage] = React.useState<string | null>(null);
  const [tiktokSound, setTiktokSound] = React.useState('');

  React.useEffect(() => {
    fetch('/api/music/list')
      .then((response) => response.json())
      .then((data) => setMusicTracks(data.tracks || []))
      .catch(() => setMusicTracks([]));
  }, []);

  React.useEffect(() => {
    if (!rendering) return;
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [rendering]);

  function randomizeSeed() {
    setSeed(String(Math.floor(100_000 + Math.random() * 999_800_000)));
  }

  async function generate() {
    setRendering(true);
    setResult(null);
    setError(null);
    setUploadMessage(null);
    try {
      const response = await fetch('/api/game/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          duration,
          rings,
          theme,
          soundPack,
          musicFile: musicFile || undefined,
          musicVolume,
          title,
          seed: seed.trim() ? Number(seed) : undefined,
        }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'Le rendu a échoué.');
      setResult(data);
      setCaption(`${data.caption} ${data.tags.join(' ')}`);
      setSeed(String(data.seed));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRendering(false);
    }
  }

  async function uploadMusic(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.currentTarget.value = '';
    if (!file) return;
    setUploadingMusic(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('vibe', 'jeu');
      const response = await fetch('/api/music/upload', { method: 'POST', body: form });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "L'import audio a échoué.");
      setMusicFile(data.file);
      setMusicTracks((tracks) => [{ id: data.file, title: file.name, file: data.file, vibe: ['jeu'] }, ...tracks.filter((track) => track.file !== data.file)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUploadingMusic(false);
    }
  }

  async function uploadTikTok() {
    if (!result || !account) return;
    setUploading(true);
    setUploadMessage(null);
    try {
      const response = await fetch('/api/tiktok/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: result.filename,
          username: account,
          caption: caption.slice(0, 2000),
          musicId: tiktokSound.trim() || undefined,
        }),
      });
      const data = await response.json();
      setUploadMessage(data.ok ? `✅ Vidéo envoyée sur @${account}` : `❌ ${data.error || data.stderr || 'Échec TikTok'}`);
    } catch (caught) {
      setUploadMessage(`❌ ${String(caught)}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-white/10 bg-ink-800/70 overflow-hidden">
        <div className="h-1.5 bg-gradient-to-r from-fuchsia-500 via-cyan-400 to-lime-400" />
        <div className="p-4 space-y-4">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-accent/15 p-2.5"><Gamepad2 className="size-5 text-accent" /></div>
            <div>
              <h2 className="font-semibold">Ball Escape automatique</h2>
              <p className="text-xs text-ink-400 mt-1">Chaque graine produit une simulation unique, ses effets sonores et une vidéo 1080×1920 prête à publier.</p>
            </div>
          </div>

          <label className="text-xs text-ink-400 space-y-1 block">
            <span>Question affichée dès la première seconde</span>
            <input
              value={title}
              maxLength={52}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Durée</span>
              <select value={duration} onChange={(event) => setDuration(Number(event.target.value))} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                <option value={15}>15 secondes</option>
                <option value={30}>30 secondes</option>
                <option value={45}>45 secondes</option>
                <option value={60}>60 secondes</option>
              </select>
            </label>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Anneaux : {rings}</span>
              <input type="range" min={8} max={32} value={rings} onChange={(event) => setRings(Number(event.target.value))} className="w-full h-10 accent-fuchsia-500" />
            </label>
          </div>

          <div className="space-y-1.5">
            <span className="text-xs text-ink-400">Palette</span>
            <div className="grid grid-cols-3 gap-2">
              {themes.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTheme(item.id)}
                  className={`rounded-xl border p-2 text-xs transition ${theme === item.id ? 'border-white/50 bg-white/10 text-white' : 'border-white/10 text-ink-400 hover:bg-white/5'}`}
                >
                  <span className={`block h-2 rounded-full bg-gradient-to-r ${item.colors} mb-1.5`} />
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-ink-900/55 p-3 space-y-3">
            <div className="flex items-center gap-2">
              <Music2 className="size-4 text-cyan-300" />
              <div>
                <h3 className="text-sm font-medium">Son de la simulation</h3>
                <p className="text-[11px] text-ink-400">Boucle originale + impacts synchronisés, avec piste de fond optionnelle.</p>
              </div>
            </div>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Effets à chaque rebond</span>
              <select value={soundPack} onChange={(event) => setSoundPack(event.target.value as SoundPack)} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                <option value="auto">Auto Buzz — varie selon la vidéo</option>
                <option value="funny">Drôle — boing et pop</option>
                <option value="arcade">Arcade — notes musicales</option>
                <option value="impact">Impact — rebonds graves</option>
              </select>
            </label>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Vraie piste de fond — optionnelle</span>
              <div className="flex gap-2">
                <select value={musicFile} onChange={(event) => setMusicFile(event.target.value)} className="min-w-0 flex-1 bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                  <option value="">Boucle originale uniquement</option>
                  {musicTracks.length > 0 && <option value="__auto__">Auto — rotation de ma bibliothèque</option>}
                  {musicTracks.map((track) => <option key={track.id} value={track.file}>{track.title}</option>)}
                </select>
                <Button type="button" variant="outline" size="sm" onClick={() => musicInputRef.current?.click()} disabled={uploadingMusic}>
                  {uploadingMusic ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />} Importer
                </Button>
                <input ref={musicInputRef} type="file" accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg" className="hidden" onChange={uploadMusic} />
              </div>
            </label>
            {musicFile && (
              <label className="text-xs text-ink-400 space-y-1 block">
                <span>Volume de la piste : {Math.round(musicVolume * 100)}%</span>
                <input type="range" min={0} max={70} value={Math.round(musicVolume * 100)} onChange={(event) => setMusicVolume(Number(event.target.value) / 100)} className="w-full accent-cyan-400" />
              </label>
            )}
            <p className="text-[10px] text-amber-200/80">Pour YouTube, utilise une piste originale ou licenciée. Les sons TikTok officiels s’ajoutent plus bas par URL/ID.</p>
          </div>

          <label className="text-xs text-ink-400 space-y-1 block">
            <span>Graine — vide = nouvelle variante aléatoire</span>
            <div className="flex gap-2">
              <input
                inputMode="numeric"
                value={seed}
                onChange={(event) => setSeed(event.target.value.replace(/\D/g, '').slice(0, 10))}
                placeholder="Aléatoire"
                className="min-w-0 flex-1 bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white"
              />
              <Button type="button" variant="outline" size="sm" onClick={randomizeSeed} aria-label="Nouvelle graine"><RefreshCw className="size-4" /></Button>
            </div>
          </label>

          <Button onClick={generate} disabled={rendering || !title.trim()} className="w-full" size="lg">
            {rendering ? <Loader2 className="size-5 animate-spin" /> : <Sparkles className="size-5" />}
            {rendering ? `Simulation et encodage… ${elapsed}s` : 'Générer la vidéo'}
          </Button>
          <p className="text-[11px] text-ink-500 text-center">Le rendu reste local sur ton serveur. Aucun contenu tiers n’est utilisé.</p>
          {error && <p className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-200">{error}</p>}
        </div>
      </section>

      {result && (
        <>
          <section className="rounded-2xl border border-white/10 bg-black overflow-hidden">
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video src={`/api/renders/${encodeURIComponent(result.filename)}`} controls playsInline loop className="w-full max-h-[72vh] aspect-[9/16] object-contain" />
          </section>

          <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-medium">Variante #{result.seed}</h3>
                <p className="text-[11px] text-ink-400">{result.duration}s · {result.rings} anneaux · {(result.size / 1024 / 1024).toFixed(1)} Mo{result.musicUsed ? ` · ${result.musicUsed}` : ''}</p>
              </div>
              <a href={`/api/renders/${encodeURIComponent(result.filename)}`} download className="inline-flex h-9 items-center gap-2 rounded-xl bg-white/5 px-3 text-sm hover:bg-white/10">
                <Download className="size-4" /> Télécharger
              </a>
            </div>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Légende TikTok/Short</span>
              <textarea value={caption} onChange={(event) => setCaption(event.target.value)} rows={3} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
            </label>
            <AccountPicker value={account} onChange={setAccount} />
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Son officiel TikTok — URL ou ID, optionnel</span>
              <input
                value={tiktokSound}
                onChange={(event) => setTiktokSound(event.target.value)}
                placeholder="https://www.tiktok.com/music/…"
                className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
              />
              <span className="block text-[10px] text-ink-500">Permet de rattacher la publication à un son drôle ou tendance sans l’intégrer au fichier YouTube.</span>
            </label>
            <Button variant="outline" onClick={uploadTikTok} disabled={uploading || !account}>
              {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
              Publier sur TikTok
            </Button>
            {uploadMessage && <p className="text-sm text-ink-200 whitespace-pre-wrap">{uploadMessage}</p>}
          </section>

          <YoutubePublisher
            key={result.filename}
            filename={result.filename}
            defaultTitle={result.youtubeTitle}
            description={caption}
            tags={result.tags}
          />
        </>
      )}
    </div>
  );
}
