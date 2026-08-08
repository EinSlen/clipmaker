'use client';

import * as React from 'react';
import { Download, Gamepad2, Loader2, Music2, RefreshCw, Sparkles, UploadCloud } from 'lucide-react';
import { Button } from './Button';
import { TikTokTargetPicker } from './TikTokTargetPicker';
import { YoutubePublisher } from './YoutubePublisher';
import { GAME_CATALOG, getGameDefinition, type GameId } from '@/lib/game-catalog';
import type { MusicTrack } from '@/lib/types';

type Theme = 'neon' | 'sunset' | 'ice';
type SoundPack = 'auto' | 'meme' | 'funny' | 'arcade' | 'impact';
type MusicMode = 'hit-reveal' | 'continuous';

type GameResult = {
  filename: string;
  size: number;
  duration: number;
  seed: number;
  game: GameId;
  gameName: string;
  difficulty: number;
  metricLabel: string;
  unitsCompleted: number;
  unitsTotal: number;
  rings?: number;
  theme: Theme;
  soundPack: SoundPack;
  musicMode: MusicMode | 'original';
  musicHits: number;
  musicUsed: string | null;
  musicTitle: string | null;
  musicSource: 'jamendo' | 'library' | 'original';
  musicCredit: string | null;
  musicNote: string | null;
  title: string;
  youtubeTitle: string;
  caption: string;
  tags: string[];
};

const themes: { id: Theme; label: string; colors: string }[] = [
  { id: 'neon', label: 'Rainbow', colors: 'from-fuchsia-500 via-cyan-400 to-lime-400' },
  { id: 'sunset', label: 'Sunset', colors: 'from-orange-500 via-pink-500 to-purple-600' },
  { id: 'ice', label: 'Ice', colors: 'from-cyan-300 via-blue-400 to-indigo-600' },
];

export function GameStudio() {
  const [game, setGame] = React.useState<GameId>('ball-escape');
  const [duration, setDuration] = React.useState(45);
  const [difficulty, setDifficulty] = React.useState(240);
  const [theme, setTheme] = React.useState<Theme>('neon');
  const [soundPack, setSoundPack] = React.useState<SoundPack>('auto');
  const [musicTracks, setMusicTracks] = React.useState<MusicTrack[]>([]);
  const [musicFile, setMusicFile] = React.useState('__discover__');
  const [musicMode, setMusicMode] = React.useState<MusicMode>('hit-reveal');
  const [musicVolume, setMusicVolume] = React.useState(0.55);
  const [uploadingMusic, setUploadingMusic] = React.useState(false);
  const musicInputRef = React.useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = React.useState('Will the ball escape?');
  const [seed, setSeed] = React.useState('');
  const [rendering, setRendering] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<GameResult | null>(null);
  const [caption, setCaption] = React.useState('');
  const [accounts, setAccounts] = React.useState<string[]>([]);
  const [publishedAccounts, setPublishedAccounts] = React.useState<string[]>([]);
  const [uploading, setUploading] = React.useState(false);
  const [uploadMessage, setUploadMessage] = React.useState<string | null>(null);
  const [tiktokSound, setTiktokSound] = React.useState('');
  const gameDefinition = getGameDefinition(game);
  const [routesHydrated, setRoutesHydrated] = React.useState(false);

  React.useEffect(() => {
    fetch('/api/music/list')
      .then((response) => response.json())
      .then((data) => setMusicTracks(data.tracks || []))
      .catch(() => setMusicTracks([]));
  }, []);

  React.useEffect(() => {
    try {
      const routes = JSON.parse(window.localStorage.getItem('clipmaker-game-tiktok-routes') || '{}') as Record<string, string[]>;
      setAccounts(Array.isArray(routes['ball-escape']) ? routes['ball-escape'] : []);
    } catch {
      setAccounts([]);
    }
    setRoutesHydrated(true);
  }, []);

  React.useEffect(() => {
    if (!routesHydrated) return;
    try {
      const routes = JSON.parse(window.localStorage.getItem('clipmaker-game-tiktok-routes') || '{}') as Record<string, string[]>;
      routes[game] = accounts;
      window.localStorage.setItem('clipmaker-game-tiktok-routes', JSON.stringify(routes));
    } catch {}
  }, [accounts, game, routesHydrated]);

  React.useEffect(() => {
    if (!rendering) return;
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [rendering]);

  function randomizeSeed() {
    setSeed(String(Math.floor(100_000 + Math.random() * 999_800_000)));
  }

  function selectGame(nextGame: GameId) {
    const definition = getGameDefinition(nextGame);
    try {
      const routes = JSON.parse(window.localStorage.getItem('clipmaker-game-tiktok-routes') || '{}') as Record<string, string[]>;
      setAccounts(Array.isArray(routes[nextGame]) ? routes[nextGame] : []);
    } catch {
      setAccounts([]);
    }
    setGame(nextGame);
    setDifficulty(definition.metricDefault);
    setTitle(definition.defaultHook);
    setResult(null);
    setPublishedAccounts([]);
    setUploadMessage(null);
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
          game,
          duration,
          difficulty,
          theme,
          soundPack,
          musicFile: musicFile || undefined,
          musicMode,
          musicVolume,
          title,
          seed: seed.trim() ? Number(seed) : undefined,
        }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'The render failed.');
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
      form.append('vibe', 'game');
      const response = await fetch('/api/music/upload', { method: 'POST', body: form });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'The audio upload failed.');
      setMusicFile(data.file);
      setMusicTracks((tracks) => [{ id: data.file, title: file.name, file: data.file, vibe: ['game'] }, ...tracks.filter((track) => track.file !== data.file)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUploadingMusic(false);
    }
  }

  async function uploadTikTok() {
    if (!result || !accounts.length) return;
    const pendingAccounts = accounts.filter((username) => !publishedAccounts.includes(username));
    if (!pendingAccounts.length) {
      setUploadMessage('All selected TikTok accounts already received this render.');
      return;
    }
    setUploading(true);
    setUploadMessage(null);
    try {
      const messages: string[] = [];
      const uploaded = new Set(publishedAccounts);
      for (const username of pendingAccounts) {
        const response = await fetch('/api/tiktok/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: result.filename,
            username,
            caption: caption.slice(0, 2000),
            musicId: tiktokSound.trim() || undefined,
          }),
        });
        const data = await response.json();
        if (data.ok) {
          uploaded.add(username);
          messages.push(`✅ @${username} — published`);
        } else {
          messages.push(`❌ @${username} — ${data.error || data.stderr || 'upload failed'}`);
        }
      }
      setPublishedAccounts([...uploaded]);
      setUploadMessage(messages.join('\n'));
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
              <h2 className="font-semibold">Automatic Game Studio</h2>
              <p className="text-xs text-ink-400 mt-1">Choose an original simulation, tune its challenge and generate a deterministic 1080×1920 video with synchronized audio.</p>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-ink-300">Game format</span>
              <span className="text-[10px] text-emerald-300">4 original engines</span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {GAME_CATALOG.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectGame(item.id)}
                  className={`overflow-hidden rounded-xl border text-left transition ${game === item.id ? 'border-white/45 bg-white/10 shadow-lg shadow-black/20' : 'border-white/10 bg-ink-900/45 hover:bg-white/5'}`}
                >
                  <span className={`block h-1.5 bg-gradient-to-r ${item.accent}`} />
                  <span className="block p-3">
                    <span className="block text-sm font-semibold text-white">{item.name}</span>
                    <span className="mt-1 block text-[11px] leading-4 text-ink-400">{item.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <label className="text-xs text-ink-400 space-y-1 block">
            <span>Hook shown from the first frame</span>
            <input
              value={title}
              maxLength={52}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Duration</span>
              <select value={duration} onChange={(event) => setDuration(Number(event.target.value))} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                <option value={15}>15 seconds</option>
                <option value={30}>30 seconds</option>
                <option value={45}>45 seconds</option>
                <option value={60}>60 seconds</option>
              </select>
            </label>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>{gameDefinition.metricLabel}: {difficulty}</span>
              <input type="range" min={gameDefinition.metricMin} max={gameDefinition.metricMax} step={gameDefinition.metricStep} value={difficulty} onChange={(event) => setDifficulty(Number(event.target.value))} className="w-full h-10 accent-fuchsia-500" />
            </label>
          </div>

          <div className="space-y-1.5">
            <span className="text-xs text-ink-400">Color theme</span>
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
                <h3 className="text-sm font-medium">Simulation audio</h3>
                <p className="text-[11px] text-ink-400">Discover a fresh licensed track, then reveal its melody one collision at a time.</p>
              </div>
            </div>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Collision sound pack</span>
              <select value={soundPack} onChange={(event) => setSoundPack(event.target.value as SoundPack)} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                <option value="auto">Auto Viral Mix — meme-heavy rotation</option>
                <option value="meme">Meme Mix — meows, boings and pops</option>
                <option value="funny">Funny — boings and pops</option>
                <option value="arcade">Arcade — musical hits</option>
                <option value="impact">Impact — heavy bounces</option>
              </select>
            </label>
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Music source</span>
              <div className="flex gap-2">
                <select value={musicFile} onChange={(event) => setMusicFile(event.target.value)} className="min-w-0 flex-1 bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                  <option value="__discover__">Auto Discovery — fresh licensed track</option>
                  <option value="">Original generated electronic track</option>
                  {musicTracks.length > 0 && <option value="__auto__">Auto — rotate my audio library</option>}
                  {musicTracks.map((track) => <option key={track.id} value={track.file}>{track.title}</option>)}
                </select>
                <Button type="button" variant="outline" size="sm" onClick={() => musicInputRef.current?.click()} disabled={uploadingMusic}>
                  {uploadingMusic ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />} Upload
                </Button>
                <input ref={musicInputRef} type="file" accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg" className="hidden" onChange={uploadMusic} />
              </div>
            </label>
            {musicFile && (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-ink-400 space-y-1 block">
                  <span>Music behavior</span>
                  <select value={musicMode} onChange={(event) => setMusicMode(event.target.value as MusicMode)} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white">
                    <option value="hit-reveal">Hit Reveal — unlock each beat</option>
                    <option value="continuous">Continuous soundtrack</option>
                  </select>
                </label>
                <label className="text-xs text-ink-400 space-y-1 block">
                  <span>Track volume: {Math.round(musicVolume * 100)}%</span>
                  <input type="range" min={10} max={85} value={Math.round(musicVolume * 100)} onChange={(event) => setMusicVolume(Number(event.target.value) / 100)} className="w-full h-10 accent-cyan-400" />
                </label>
              </div>
            )}
            <p className="text-[10px] text-amber-200/80">Auto Discovery only accepts downloadable CC BY tracks. Without one, ClipMaker composes a new original electronic song and still reveals it one hit at a time.</p>
          </div>

          <label className="text-xs text-ink-400 space-y-1 block">
            <span>Seed — leave empty for a new random run</span>
            <div className="flex gap-2">
              <input
                inputMode="numeric"
                value={seed}
                onChange={(event) => setSeed(event.target.value.replace(/\D/g, '').slice(0, 10))}
                placeholder="Random"
                className="min-w-0 flex-1 bg-ink-900 border border-white/10 rounded-lg px-3 h-10 text-sm text-white"
              />
              <Button type="button" variant="outline" size="sm" onClick={randomizeSeed} aria-label="New seed"><RefreshCw className="size-4" /></Button>
            </div>
          </label>

          <Button onClick={generate} disabled={rendering || !title.trim()} className="w-full" size="lg">
            {rendering ? <Loader2 className="size-5 animate-spin" /> : <Sparkles className="size-5" />}
            {rendering ? `Simulating and encoding… ${elapsed}s` : 'Generate video'}
          </Button>
          <p className="text-[11px] text-ink-500 text-center">Rendering stays on your server. No third-party video is used.</p>
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
                <h3 className="text-sm font-medium">Run #{result.seed}</h3>
                <p className="text-[11px] text-ink-400">{result.gameName} · {result.duration}s · {result.difficulty} {result.metricLabel.toLowerCase()} · {(result.size / 1024 / 1024).toFixed(1)} MB{result.musicTitle ? ` · ${result.musicTitle}` : ''}</p>
                <p className="text-[10px] text-cyan-200/80 mt-0.5">{result.musicMode === 'hit-reveal' ? `${result.musicHits} collision-triggered music slices` : result.musicMode === 'continuous' ? 'Continuous soundtrack' : 'Original generated soundtrack'}</p>
              </div>
              <a href={`/api/renders/${encodeURIComponent(result.filename)}`} download className="inline-flex h-9 items-center gap-2 rounded-xl bg-white/5 px-3 text-sm hover:bg-white/10">
                <Download className="size-4" /> Download
              </a>
            </div>
            {result.musicNote && <p className="text-[11px] text-amber-200/80">{result.musicNote}</p>}
            {result.musicCredit && <p className="text-[10px] text-ink-400 break-words">{result.musicCredit}</p>}
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>TikTok / Shorts caption</span>
              <textarea value={caption} onChange={(event) => setCaption(event.target.value)} rows={3} className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" />
            </label>
            <TikTokTargetPicker value={accounts} onChange={setAccounts} />
            <label className="text-xs text-ink-400 space-y-1 block">
              <span>Official TikTok sound — optional URL or ID</span>
              <input
                value={tiktokSound}
                onChange={(event) => setTiktokSound(event.target.value)}
                placeholder="https://www.tiktok.com/music/…"
                className="w-full bg-ink-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
              />
              <span className="block text-[10px] text-ink-500">Attaches the post to a funny or trending sound without embedding it in the YouTube file.</span>
            </label>
            <Button variant="outline" onClick={uploadTikTok} disabled={uploading || !accounts.length || accounts.every((username) => publishedAccounts.includes(username))}>
              {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
              Publish to {accounts.length || 0} TikTok {accounts.length === 1 ? 'account' : 'accounts'}
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
