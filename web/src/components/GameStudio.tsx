"use client";

import * as React from "react";
import Image from "next/image";
import {
  CheckCircle2,
  Download,
  Gamepad2,
  Loader2,
  Music2,
  Palette,
  RefreshCw,
  Settings2,
  Sparkles,
  UploadCloud,
  Video,
  Youtube,
} from "lucide-react";
import { Button } from "./Button";
import { TikTokTargetPicker } from "./TikTokTargetPicker";
import { YoutubePublisher } from "./YoutubePublisher";
import {
  GAME_CATALOG,
  getGameDefinition,
  type GameId,
} from "@/lib/game-catalog";
import type { MusicTrack } from "@/lib/types";

type Theme = "neon" | "sunset" | "ice";
type SoundPack = "auto" | "meme" | "funny" | "arcade" | "impact" | "asmr";
type MusicMode = "hit-reveal" | "continuous";
type SoftBodyObstacle = "auto" | "moving-slide" | "stair-cascade" | "v-stairs" | "pipe-bend" | "peg-grid" | "twin-gears" | "compression-ring";
type RenderedSoundPack = SoundPack | "glass" | "premium-foley";
type RenderedMusicMode = MusicMode | "original" | "foley-only" | "subtle-bed";
type GameOutcome =
  | "escaped"
  | "failed"
  | "incomplete"
  | "survived"
  | "collision"
  | "player"
  | "boss"
  | "draw"
  | "comparison-complete";

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
  soundPack: RenderedSoundPack;
  musicMode: RenderedMusicMode;
  musicHits: number;
  completedAt: number | null;
  outcome: GameOutcome | null;
  musicUsed: string | null;
  musicTitle: string | null;
  musicSource: "jamendo" | "library" | "original";
  musicCredit: string | null;
  musicNote: string | null;
  variantKey: string | null;
  variantLabel: string | null;
  variantShape: string | null;
  variantRamp: string | null;
  variantPalette: string | null;
  variantReceiver: string | null;
  variantObstacle: string | null;
  variantObstacleLabel: string | null;
  variantSourceVideo: string | null;
  stagePreset: string | null;
  softnessStages: number[] | null;
  title: string;
  youtubeTitle: string;
  caption: string;
  tags: string[];
};

const gameOutcomeLabels: Record<GameOutcome, string> = {
  escaped: "Sortie réussie naturellement",
  failed: "Échec : aucune sortie trouvée",
  incomplete: "Temps écoulé avant la sortie",
  survived: "Parcours laser réussi",
  collision: "Collision avec un laser",
  player: "Victoire du joueur",
  boss: "Victoire du boss",
  draw: "Égalité",
  "comparison-complete": "Comparaison des cinq niveaux terminée",
};

const gameOutcomeTones: Record<GameOutcome, string> = {
  escaped: "text-emerald-200/90",
  failed: "text-rose-200/90",
  incomplete: "text-amber-200/90",
  survived: "text-emerald-200/90",
  collision: "text-rose-200/90",
  player: "text-emerald-200/90",
  boss: "text-violet-200/90",
  draw: "text-amber-200/90",
  "comparison-complete": "text-emerald-200/90",
};

const softBodyShapeLabels: Record<string, string> = {
  "classic-pill": "Capsule classique",
  "slender-cylinder": "Cylindre fin",
  "plush-capsule": "Capsule moelleuse",
  "rounded-barrel": "Tonneau arrondi",
  "rolled-gel": "Gel roulé",
};

const softBodyRampLabels: Record<string, string> = {
  "classic-lip": "Rampe classique",
  "double-wave": "Double vague",
  "scoop-launch": "Rampe tremplin",
  "roller-wave": "Vague roulante",
  "long-glide": "Longue glissade",
};

const softBodyPaletteLabels: Record<string, string> = {
  champagne: "studio champagne",
  "rose-gold": "studio or rose",
  platinum: "studio platine",
  copper: "studio cuivre",
  "pale-gold": "studio or pâle",
};

const softBodyObstacles: { id: SoftBodyObstacle; label: string; description: string; image: string }[] = [
  { id: "auto", label: "Rotation automatique", description: "Alterner entre rampe, triple escalier, V et grille. Les trois scènes expérimentales restent manuelles.", image: "/game-previews/soft-body-slide.webp" },
  { id: "moving-slide", label: "Rampe mobile", description: "Glissades, relances et chute dans le tube.", image: "/game-previews/soft-body-obstacles/moving-slide.webp" },
  { id: "stair-cascade", label: "Cascade de marches", description: "Rebonds successifs sur un escalier suspendu.", image: "/game-previews/soft-body-obstacles/stair-cascade.webp" },
  { id: "v-stairs", label: "Double escalier en V", description: "Deux descentes convergent vers le réceptacle.", image: "/game-previews/soft-body-obstacles/v-stairs.webp" },
  { id: "pipe-bend", label: "Coude de tuyau · bêta", description: "Test manuel : la forme boule de la référence reste à reconstruire.", image: "/game-previews/soft-body-obstacles/pipe-bend.webp" },
  { id: "peg-grid", label: "Grille de plots", description: "Compression et déviation entre plusieurs plots.", image: "/game-previews/soft-body-obstacles/peg-grid.webp" },
  { id: "twin-gears", label: "Doubles engrenages · bêta", description: "Test manuel : la forme croix de la référence reste à reconstruire.", image: "/game-previews/soft-body-obstacles/twin-gears.webp" },
  { id: "compression-ring", label: "Anneau · bêta", description: "Test manuel : l’anneau sur sculpture de la référence reste à reconstruire.", image: "/game-previews/soft-body-obstacles/compression-ring.webp" },
];

const softBodyObstacleLabels = Object.fromEntries(
  softBodyObstacles.filter((item) => item.id !== "auto").map((item) => [item.id, item.label])
) as Record<string, string>;

function localizedSoftBodyVariant(result: GameResult): string | null {
  if (!result.variantShape || !result.variantRamp || !result.variantPalette) {
    return result.variantLabel;
  }
  return [
    result.variantObstacle
      ? softBodyObstacleLabels[result.variantObstacle] || result.variantObstacleLabel || result.variantObstacle
      : null,
    softBodyShapeLabels[result.variantShape] || result.variantShape,
    result.variantObstacle === "moving-slide"
      ? softBodyRampLabels[result.variantRamp] || result.variantRamp
      : null,
    softBodyPaletteLabels[result.variantPalette] || result.variantPalette,
  ].filter(Boolean).join(" · ");
}

const themes: { id: Theme; label: string; colors: string }[] = [
  {
    id: "neon",
    label: "Arc-en-ciel",
    colors: "from-fuchsia-500 via-cyan-400 to-lime-400",
  },
  {
    id: "sunset",
    label: "Coucher de soleil",
    colors: "from-orange-500 via-pink-500 to-purple-600",
  },
  {
    id: "ice",
    label: "Glace",
    colors: "from-cyan-300 via-blue-400 to-indigo-600",
  },
];

export function GameStudio() {
  const [game, setGame] = React.useState<GameId>("ball-escape");
  const [duration, setDuration] = React.useState(15);
  const [difficulty, setDifficulty] = React.useState(
    GAME_CATALOG[0].metricDefault
  );
  const [theme, setTheme] = React.useState<Theme>("neon");
  const [soundPack, setSoundPack] = React.useState<SoundPack>("auto");
  const [musicTracks, setMusicTracks] = React.useState<MusicTrack[]>([]);
  const [musicFile, setMusicFile] = React.useState("__discover__");
  const [musicMode, setMusicMode] = React.useState<MusicMode>("hit-reveal");
  const [musicVolume, setMusicVolume] = React.useState(0.55);
  const [uploadingMusic, setUploadingMusic] = React.useState(false);
  const musicInputRef = React.useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = React.useState("Will the ball escape?");
  const [seed, setSeed] = React.useState("");
  const [softBodyObstacle, setSoftBodyObstacle] = React.useState<SoftBodyObstacle>("auto");
  const [rendering, setRendering] = React.useState(false);
  const [elapsed, setElapsed] = React.useState(0);
  const [batchSize, setBatchSize] = React.useState(1);
  const [batchProgress, setBatchProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<GameResult | null>(null);
  const [batchResults, setBatchResults] = React.useState<GameResult[]>([]);
  const [caption, setCaption] = React.useState("");
  const [accounts, setAccounts] = React.useState<string[]>([]);
  const [publishedAccounts, setPublishedAccounts] = React.useState<string[]>(
    []
  );
  const [uploading, setUploading] = React.useState(false);
  const [uploadMessage, setUploadMessage] = React.useState<string | null>(null);
  const [tiktokSound, setTiktokSound] = React.useState("");
  const [tiktokVisibility, setTiktokVisibility] = React.useState<"private" | "public">("private");
  const [tiktokConfirmPublic, setTiktokConfirmPublic] = React.useState(false);
  const [adminToken, setAdminToken] = React.useState("");
  const [publishTab, setPublishTab] = React.useState<"tiktok" | "youtube">(
    "tiktok"
  );
  const gameDefinition = getGameDefinition(game);
  const [routesHydrated, setRoutesHydrated] = React.useState(false);

  React.useEffect(() => {
    fetch("/api/music/list")
      .then((response) => response.json())
      .then((data) => setMusicTracks(data.tracks || []))
      .catch(() => setMusicTracks([]));
  }, []);

  React.useEffect(() => {
    const savedToken = window.sessionStorage.getItem("clipmaker-upload-token");
    if (savedToken) setAdminToken(savedToken);
    try {
      const routes = JSON.parse(
        window.localStorage.getItem("clipmaker-game-tiktok-routes") || "{}"
      ) as Record<string, string[]>;
      setAccounts(
        Array.isArray(routes["ball-escape"]) ? routes["ball-escape"] : []
      );
    } catch {
      setAccounts([]);
    }
    setRoutesHydrated(true);
  }, []);

  function updateAdminToken(value: string) {
    setAdminToken(value);
    if (value) window.sessionStorage.setItem("clipmaker-upload-token", value);
    else window.sessionStorage.removeItem("clipmaker-upload-token");
  }

  React.useEffect(() => {
    if (!routesHydrated) return;
    try {
      const routes = JSON.parse(
        window.localStorage.getItem("clipmaker-game-tiktok-routes") || "{}"
      ) as Record<string, string[]>;
      routes[game] = accounts;
      window.localStorage.setItem(
        "clipmaker-game-tiktok-routes",
        JSON.stringify(routes)
      );
    } catch {}
  }, [accounts, game, routesHydrated]);

  React.useEffect(() => {
    if (!rendering) return;
    setElapsed(0);
    const timer = window.setInterval(
      () => setElapsed((value) => value + 1),
      1000
    );
    return () => window.clearInterval(timer);
  }, [rendering]);

  function randomizeSeed() {
    setSeed(String(Math.floor(100_000 + Math.random() * 999_800_000)));
  }

  function selectGame(nextGame: GameId) {
    const definition = getGameDefinition(nextGame);
    try {
      const routes = JSON.parse(
        window.localStorage.getItem("clipmaker-game-tiktok-routes") || "{}"
      ) as Record<string, string[]>;
      setAccounts(Array.isArray(routes[nextGame]) ? routes[nextGame] : []);
    } catch {
      setAccounts([]);
    }
    setGame(nextGame);
    setDifficulty(definition.metricDefault);
    setMusicMode(
      nextGame === "shape-tunnel" || nextGame === "soft-body-slide"
        ? "continuous"
        : "hit-reveal"
    );
    if (nextGame === "soft-body-slide") {
      setDuration(30);
      setMusicFile("");
    } else {
      setDuration(15);
      if (!musicFile) setMusicFile("__discover__");
    }
    setTitle(definition.defaultHook);
    setResult(null);
    setBatchResults([]);
    setPublishedAccounts([]);
    setUploadMessage(null);
  }

  async function generate() {
    setRendering(true);
    setResult(null);
    setBatchResults([]);
    setBatchProgress(0);
    setError(null);
    setUploadMessage(null);
    try {
      const generated: GameResult[] = [];
      const requestedSeed = seed.trim() ? Number(seed) : undefined;
      for (let index = 0; index < batchSize; index += 1) {
        const response = await fetch("/api/game/render", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
            obstacle: game === "soft-body-slide" ? softBodyObstacle : undefined,
            seed: requestedSeed
              ? ((requestedSeed + index - 1) % 2_147_483_647) + 1
              : undefined,
          }),
        });
        const data = await response.json();
        if (!data.ok)
          throw new Error(
            `Vidéo ${index + 1} : ${data.error || "échec du rendu."}`
          );
        generated.push(data);
        setBatchResults([...generated]);
        setResult(data);
        setCaption(`${data.caption} ${data.tags.join(" ")}`);
        setSeed(String(data.seed));
        setBatchProgress(index + 1);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRendering(false);
    }
  }

  function selectResult(next: GameResult) {
    setResult(next);
    setCaption(`${next.caption} ${next.tags.join(" ")}`);
    setPublishedAccounts([]);
    setUploadMessage(null);
  }

  async function uploadMusic(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    setUploadingMusic(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("vibe", "game");
      const response = await fetch("/api/music/upload", {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Échec de l’import audio.");
      setMusicFile(data.file);
      setMusicTracks((tracks) => [
        { id: data.file, title: file.name, file: data.file, vibe: ["game"] },
        ...tracks.filter((track) => track.file !== data.file),
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setUploadingMusic(false);
    }
  }

  async function uploadTikTok() {
    if (!result || !accounts.length) return;
    const pendingAccounts = accounts.filter(
      (username) => !publishedAccounts.includes(username)
    );
    if (!pendingAccounts.length) {
      setUploadMessage(
        "Ce rendu a déjà été publié sur tous les comptes TikTok sélectionnés."
      );
      return;
    }
    setUploading(true);
    setUploadMessage(null);
    try {
      const messages: string[] = [];
      const uploaded = new Set(publishedAccounts);
      for (const username of pendingAccounts) {
        const response = await fetch("/api/tiktok/upload", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(window.sessionStorage.getItem("clipmaker-upload-token")
              ? {
                  "x-clipmaker-upload-token":
                    window.sessionStorage.getItem("clipmaker-upload-token") || "",
                }
              : {}),
          },
          body: JSON.stringify({
            filename: result.filename,
            username,
            caption: caption.slice(0, 2000),
            musicId: tiktokSound.trim() || undefined,
            visibility: tiktokVisibility,
            confirmPublic: tiktokVisibility === "public" && tiktokConfirmPublic,
          }),
        });
        const data = await response.json();
        if (data.ok) {
          uploaded.add(username);
          messages.push(`✅ @${username} — publié`);
        } else {
          console.error(
            `Publication TikTok impossible pour @${username}`,
            data.error || data.stderr
          );
          messages.push(`❌ @${username} — échec de la publication`);
        }
      }
      setPublishedAccounts([...uploaded]);
      setUploadMessage(messages.join("\n"));
    } catch (caught) {
      setUploadMessage(`❌ ${String(caught)}`);
    } finally {
      setUploading(false);
    }
  }

  const musicSummary =
    musicFile === "__discover__"
      ? "découverte automatique"
      : musicFile === "__auto__"
      ? "rotation de la bibliothèque"
      : musicFile
      ? "piste choisie"
      : game === "soft-body-slide"
      ? "Foley ASMR original"
      : "piste générée";

  return (
    <div className="space-y-6">
      <section className="panel p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent/15 text-accent-soft">
              <Gamepad2 className="size-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold">
                Studio de jeux automatiques
              </h2>
              <p className="mt-1 max-w-2xl text-sm leading-5 text-ink-400">
                Choisis une simulation originale, règle son rythme et génère une
                vidéo 1080×1920 avec un son parfaitement synchronisé.
              </p>
            </div>
          </div>
          <span className="w-fit rounded-full border border-emerald-400/15 bg-emerald-400/10 px-3 py-1.5 text-[11px] font-semibold text-emerald-200">
            {GAME_CATALOG.length} moteurs originaux
          </span>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <span className="grid size-7 place-items-center rounded-full bg-accent text-xs font-bold">
            1
          </span>
          <div>
            <h3 className="text-sm font-semibold">Choisir la simulation</h3>
            <p className="text-xs text-ink-500">
              Chaque carte montre une image issue du vrai moteur de rendu.
            </p>
          </div>
        </div>
        <div className="scroll-pretty mt-4 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-3 md:grid md:grid-cols-3 md:overflow-visible md:pb-0 xl:grid-cols-5">
          {GAME_CATALOG.map((item) => {
            const selected = game === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => selectGame(item.id)}
                aria-pressed={selected}
                aria-labelledby={`game-${item.id}-title`}
                aria-describedby={`game-${item.id}-objective game-${item.id}-description`}
                className={`group min-w-[78vw] snap-center overflow-hidden rounded-2xl border text-left transition duration-200 sm:min-w-[20rem] md:min-w-0 ${
                  selected
                    ? "border-accent/80 bg-accent/[0.08] shadow-xl shadow-accent/10 ring-1 ring-accent/30"
                    : "border-white/10 bg-ink-900/55 hover:-translate-y-1 hover:border-white/25"
                }`}
              >
                <span className="relative block aspect-[4/5] overflow-hidden bg-black">
                  <Image
                    src={item.preview}
                    alt=""
                    aria-hidden
                    fill
                    sizes="(max-width: 768px) 78vw, 340px"
                    className="scale-125 object-cover opacity-35 blur-2xl"
                  />
                  <span className="absolute inset-0 bg-black/25" />
                  <Image
                    src={item.preview}
                    alt={`Aperçu du jeu ${item.uiName}`}
                    fill
                    sizes="(max-width: 768px) 78vw, 340px"
                    className="object-contain transition duration-500 group-hover:scale-[1.02]"
                  />
                  <span className="absolute left-3 top-3 rounded-full border border-white/15 bg-black/65 px-2.5 py-1 text-[9px] font-bold tracking-[0.14em] text-white backdrop-blur">
                    {item.engineLabel}
                  </span>
                  <span className="absolute bottom-3 left-3 rounded-full border border-white/10 bg-black/55 px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-white/80 backdrop-blur">
                    Aperçu réel
                  </span>
                  {item.id === "soft-body-slide" && (
                    <span className="absolute bottom-3 right-3 rounded-full border border-amber-200/20 bg-black/60 px-2.5 py-1 text-[9px] font-semibold text-amber-100 backdrop-blur">
                      7 parcours physiques
                    </span>
                  )}
                  {(item.id === "laser-dodge" || item.id === "boss-battle") && (
                    <span className="absolute bottom-3 right-3 rounded-full border border-cyan-200/20 bg-black/60 px-2.5 py-1 text-[9px] font-semibold text-cyan-100 backdrop-blur">
                      Issues variables
                    </span>
                  )}
                  {selected && (
                    <span className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-ink-950 shadow-lg">
                      <CheckCircle2 className="size-3.5" /> Sélectionné
                    </span>
                  )}
                </span>
                <span className="block space-y-2 p-4">
                  <span
                    id={`game-${item.id}-title`}
                    className="block text-base font-semibold text-white"
                  >
                    {item.uiName}
                  </span>
                  <span
                    id={`game-${item.id}-objective`}
                    className="block text-xs font-medium leading-5 text-accent-soft"
                  >
                    {item.objective}
                  </span>
                  <span
                    id={`game-${item.id}-description`}
                    className="block text-xs leading-5 text-ink-400"
                  >
                    {item.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <section className="panel p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <span className="grid size-7 place-items-center rounded-full bg-white/10 text-xs font-bold">
              2
            </span>
            <div>
              <h3 className="text-sm font-semibold">Régler la vidéo</h3>
              <p className="text-xs text-ink-500">
                Contenu, apparence et identité sonore.
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="subpanel space-y-4 p-4">
              <div className="flex items-center gap-2">
                <Video className="size-4 text-accent-soft" />
                <h4 className="text-sm font-semibold">Contenu</h4>
              </div>
              <label className="block space-y-1.5 text-xs text-ink-400">
                <span>
                  {game === "soft-body-slide"
                    ? "Titre de publication"
                    : "Accroche dans la vidéo"}{" "}
                  <span className="text-ink-500">(anglais)</span>
                </span>
                <input
                  value={title}
                  maxLength={52}
                  onChange={(event) => setTitle(event.target.value)}
                  className="field-control h-11"
                />
                <span className="block text-[10px] text-ink-500">
                  {game === "soft-body-slide"
                    ? "Utilisé pour TikTok et YouTube ; la vidéo conserve uniquement le niveau de souplesse, comme la référence."
                    : "Ce texte est intégré à la première image du Short."}
                </span>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block space-y-1.5 text-xs text-ink-400">
                  <span>Durée</span>
                  <select
                    value={duration}
                    disabled={game === "soft-body-slide"}
                    onChange={(event) =>
                      setDuration(Number(event.target.value))
                    }
                    className="field-control h-11 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    <option value={15}>15 s</option>
                    <option value={30}>30 s</option>
                    <option value={45}>45 s</option>
                    <option value={60}>60 s</option>
                  </select>
                </label>
                {game === "soft-body-slide" ? (
                  <div className="space-y-1.5 text-xs text-ink-400">
                    <span>Niveaux de souplesse</span>
                    <div className="field-control flex h-11 items-center justify-center font-semibold text-white">
                      5 niveaux générés · 0 → 100 %
                    </div>
                  </div>
                ) : (
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>
                      {gameDefinition.uiMetricLabel} :{" "}
                      <strong className="text-white">{difficulty}</strong>
                    </span>
                    <input
                      type="range"
                      min={gameDefinition.metricMin}
                      max={gameDefinition.metricMax}
                      step={gameDefinition.metricStep}
                      value={difficulty}
                      onChange={(event) =>
                        setDifficulty(Number(event.target.value))
                      }
                      className="h-11 w-full accent-accent"
                    />
                  </label>
                )}
              </div>
            </div>

            <div className="subpanel space-y-4 p-4">
              <div className="flex items-center gap-2">
                <Palette className="size-4 text-accent-soft" />
                <h4 className="text-sm font-semibold">Style visuel</h4>
              </div>
              {game === "soft-body-slide" ? (
                <>
                  <p className="text-xs leading-5 text-ink-500">
                    Chaque graine compose un studio premium différent tout en
                    gardant le rendu marbre et métal de la référence.
                  </p>
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>Famille d’obstacles</span>
                    <select
                      value={softBodyObstacle}
                      onChange={(event) => setSoftBodyObstacle(event.target.value as SoftBodyObstacle)}
                      className="field-control h-11"
                    >
                      {softBodyObstacles.map((item) => (
                        <option key={item.id} value={item.id}>{item.label}</option>
                      ))}
                    </select>
                    <span className="block text-[10px] leading-4 text-ink-500">
                      {softBodyObstacles.find((item) => item.id === softBodyObstacle)?.description}
                    </span>
                    <span className="relative mx-auto block aspect-[9/16] w-40 overflow-hidden rounded-xl border border-white/10 bg-black/30">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={softBodyObstacles.find((item) => item.id === softBodyObstacle)?.image}
                        alt={`Aperçu gameplay : ${softBodyObstacles.find((item) => item.id === softBodyObstacle)?.label}`}
                        className="h-full w-full object-contain"
                      />
                    </span>
                  </label>
                  <div className="flex h-11 items-center gap-3 rounded-xl border border-amber-200/20 bg-amber-200/5 px-3 text-xs font-medium text-white">
                    <span className="h-3 w-16 rounded-full bg-gradient-to-r from-slate-300 via-amber-200 to-yellow-600" />
                    <span>Variation studio automatique</span>
                    <CheckCircle2 className="ml-auto size-4 text-amber-200" />
                  </div>
                </>
              ) : (
                <>
                  <p className="text-xs leading-5 text-ink-500">
                    Le thème recolore le décor, les anneaux et les effets sans
                    modifier la simulation.
                  </p>
                  <div className="grid gap-2">
                    {themes.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setTheme(item.id)}
                        aria-pressed={theme === item.id}
                        className={`flex h-11 items-center gap-3 rounded-xl border px-3 text-xs font-medium transition ${
                          theme === item.id
                            ? "border-white/35 bg-white/10 text-white"
                            : "border-white/10 text-ink-400 hover:border-white/20 hover:bg-white/5"
                        }`}
                      >
                        <span
                          className={`h-3 w-16 rounded-full bg-gradient-to-r ${item.colors}`}
                        />
                        <span>{item.label}</span>
                        {theme === item.id && (
                          <CheckCircle2 className="ml-auto size-4" />
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="subpanel mt-4 space-y-4 p-4">
            <div className="flex items-start gap-2">
              <Music2 className="mt-0.5 size-4 text-cyan-300" />
              <div>
                <h4 className="text-sm font-semibold">
                  Audio de la simulation
                </h4>
                <p className="mt-1 text-xs text-ink-500">
                  {game === "soft-body-slide"
                    ? "Foley ASMR dynamique calé sur chaque obstacle et le réceptacle. La musique reste facultative."
                    : "Associe une musique sous licence et des effets de collision adaptés au jeu."}
                </p>
              </div>
            </div>
            <div className="grid gap-4">
              <label className="block space-y-1.5 text-xs text-ink-400">
                <span>Jeu de sons de collision</span>
                <select
                  value={soundPack}
                  disabled={game === "soft-body-slide"}
                  onChange={(event) =>
                    setSoundPack(event.target.value as SoundPack)
                  }
                  className="field-control h-11 disabled:cursor-not-allowed disabled:opacity-55"
                >
                  <option value="auto">
                    {game === "soft-body-slide"
                      ? "Bruitage premium — glissade et impact"
                      : "Automatique — adapté au jeu"}
                  </option>
                  <option value="meme">
                    Mix mème — miaulements, boings et pops
                  </option>
                  <option value="funny">Drôle — boings et pops</option>
                  <option value="arcade">Arcade — impacts musicaux</option>
                  <option value="impact">Impact — rebonds lourds</option>
                  <option value="asmr">ASMR paisible — tapotements doux</option>
                </select>
              </label>
              <label className="block space-y-1.5 text-xs text-ink-400">
                <span>
                  Source musicale
                </span>
                <div className="flex gap-2">
                  <select
                    value={musicFile}
                    onChange={(event) => setMusicFile(event.target.value)}
                    className="field-control h-11 min-w-0 flex-1"
                  >
                    <option value="__discover__">
                      Découverte automatique — piste sous licence
                    </option>
                    <option value="">
                      {game === "soft-body-slide"
                        ? "Foley ASMR + ambiance originale — recommandé"
                        : "Piste électronique originale générée"}
                    </option>
                    {musicTracks.length > 0 && (
                      <option value="__auto__">
                        Rotation automatique de ma bibliothèque
                      </option>
                    )}
                    {musicTracks.map((track) => (
                      <option key={track.id} value={track.file}>
                        {track.title}
                      </option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => musicInputRef.current?.click()}
                    disabled={uploadingMusic}
                    aria-label="Importer une musique"
                  >
                    {uploadingMusic ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <UploadCloud className="size-4" />
                    )}
                    <span className="hidden sm:inline">Importer</span>
                  </Button>
                  <input
                    ref={musicInputRef}
                    type="file"
                    accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg"
                    className="hidden"
                    onChange={uploadMusic}
                  />
                </div>
              </label>
            </div>
            {(musicFile || game === "soft-body-slide") && (
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="block space-y-1.5 text-xs text-ink-400">
                  <span>Comportement de la musique</span>
                  <select
                    value={musicMode}
                    disabled={game === "soft-body-slide"}
                    onChange={(event) =>
                      setMusicMode(event.target.value as MusicMode)
                    }
                    className="field-control h-11 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    <option value="hit-reveal">
                      Révélation à l’impact — un fragment par collision
                    </option>
                    <option value="continuous">Bande-son continue</option>
                  </select>
                </label>
                <label className="block space-y-1.5 text-xs text-ink-400">
                  <span>
                    Volume de la piste :{" "}
                    <strong className="text-white">
                      {Math.round(musicVolume * 100)} %
                    </strong>
                  </span>
                  <input
                    type="range"
                    min={10}
                    max={85}
                    value={Math.round(musicVolume * 100)}
                    onChange={(event) =>
                      setMusicVolume(Number(event.target.value) / 100)
                    }
                    className="h-11 w-full accent-cyan-400"
                  />
                </label>
              </div>
            )}
            <p className="text-[11px] leading-4 text-amber-200/75">
              La découverte automatique utilise uniquement des pistes CC BY
              téléchargeables. Le mode continu est recommandé pour retenir
              l’attention.
            </p>
          </div>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-24">
          <section className="panel p-5">
            <div className="flex items-center gap-3">
              <span className="grid size-7 place-items-center rounded-full bg-white/10 text-xs font-bold">
                3
              </span>
              <div>
                <h3 className="text-sm font-semibold">Lancer la production</h3>
                <p className="text-xs text-ink-500">
                  Vérifie le résumé avant le rendu.
                </p>
              </div>
            </div>
            <div className="mt-5 rounded-2xl border border-white/10 bg-black/15 p-4">
              <p className="text-sm font-semibold text-white">
                {gameDefinition.uiName}
              </p>
              <p className="mt-1 text-xs leading-5 text-ink-400">
                {gameDefinition.objective}
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <dt className="text-ink-500">Durée</dt>
                  <dd className="mt-1 font-semibold text-white">
                    {duration} s
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-500">
                    {game === "soft-body-slide"
                      ? "Variation"
                      : gameDefinition.uiMetricLabel}
                  </dt>
                  <dd className="mt-1 font-semibold text-white">
                    {game === "soft-body-slide" ? "Automatique" : difficulty}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-ink-500">Audio</dt>
                  <dd className="mt-1 font-semibold text-white">
                    {musicSummary}
                  </dd>
                </div>
              </dl>
            </div>
            <details className="mt-4 rounded-2xl border border-white/10 bg-ink-900/45 p-3 open:bg-ink-900/70">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold text-ink-300">
                <Settings2 className="size-4" /> Options avancées
              </summary>
              <div className="mt-4 space-y-4">
                <label className="block space-y-1.5 text-xs text-ink-400">
                  <span>Graine aléatoire</span>
                  <div className="flex gap-2">
                    <input
                      inputMode="numeric"
                      value={seed}
                      onChange={(event) =>
                        setSeed(
                          event.target.value.replace(/\D/g, "").slice(0, 10)
                        )
                      }
                      placeholder="Aléatoire"
                      className="field-control h-11 min-w-0 flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={randomizeSeed}
                      aria-label="Créer une nouvelle graine"
                    >
                      <RefreshCw className="size-4" />
                    </Button>
                  </div>
                  {game === "soft-body-slide" && (
                    <span className="block text-[10px] leading-4 text-ink-500">
                        La graine change la famille d’obstacles, la forme, le métal,
                        le réceptacle, la physique et les niveaux.
                    </span>
                  )}
                  {game === "laser-dodge" && (
                    <span className="block text-[10px] leading-4 text-ink-500">
                      La graine change le parcours, les angles, les marges
                      d’esquive et la réussite du dernier passage.
                    </span>
                  )}
                  {game === "boss-battle" && (
                    <span className="block text-[10px] leading-4 text-ink-500">
                      La graine change l’arme, le Warden, les trajectoires,
                      les impacts et le vainqueur.
                    </span>
                  )}
                </label>
                <label className="block space-y-1.5 text-xs text-ink-400">
                  <span>Nombre de vidéos</span>
                  <select
                    value={batchSize}
                    onChange={(event) =>
                      setBatchSize(Number(event.target.value))
                    }
                    className="field-control h-11"
                  >
                    <option value={1}>1 vidéo</option>
                    <option value={2}>2 vidéos uniques</option>
                    <option value={3}>3 vidéos uniques</option>
                  </select>
                  <span className="block text-[10px] leading-4 text-ink-500">
                    {game === "soft-body-slide"
                      ? "Chaque vidéo reçoit une combinaison visuelle et physique différente."
                      : "Chaque vidéo reçoit une graine et une sélection musicale différentes."}
                  </span>
                </label>
              </div>
            </details>
            <Button
              onClick={generate}
              disabled={rendering || !title.trim()}
              className="mt-5 w-full"
              size="lg"
            >
              {rendering ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <Sparkles className="size-5" />
              )}
              {rendering
                ? `Encodage ${Math.min(
                    batchProgress + 1,
                    batchSize
                  )}/${batchSize}… ${elapsed} s`
                : `Générer ${
                    batchSize === 1 ? "la vidéo" : `${batchSize} vidéos`
                  }`}
            </Button>
            <p className="mt-3 text-center text-[11px] leading-4 text-ink-500">
              Le rendu reste sur ton serveur. Aucune vidéo tierce n’est
              utilisée.
            </p>
            {error && (
              <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-200">
                <p>La génération n’a pas abouti.</p>
                <details className="mt-2 text-xs text-red-100/75">
                  <summary className="cursor-pointer font-medium">
                    Détails techniques
                  </summary>
                  <p className="mt-1 break-words">{error}</p>
                </details>
              </div>
            )}
          </section>
        </aside>
      </div>

      {result && (
        <section className="panel p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="grid size-7 place-items-center rounded-full bg-emerald-400 text-xs font-bold text-ink-950">
                4
              </span>
              <div>
                <h3 className="text-sm font-semibold">
                  Prévisualiser et publier
                </h3>
                <p className="text-xs text-ink-500">
                  Le rendu est prêt pour TikTok et YouTube Shorts.
                </p>
              </div>
            </div>
            <a
              href={`/api/renders/${encodeURIComponent(result.filename)}`}
              download
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 text-sm font-semibold transition hover:bg-white/10"
            >
              <Download className="size-4" /> Télécharger
            </a>
          </div>

          {batchResults.length > 1 && (
            <div className="mt-5 rounded-2xl border border-white/10 bg-ink-900/45 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="text-xs font-semibold">Lot généré</h4>
                <span className="text-[11px] text-emerald-300">
                  {batchResults.length}/{batchSize} prêtes
                </span>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                {batchResults.map((item, index) => (
                  <button
                    key={item.filename}
                    type="button"
                    onClick={() => selectResult(item)}
                    className={`rounded-xl border p-2.5 text-left text-xs transition ${
                      result.filename === item.filename
                        ? "border-accent/60 bg-accent/10"
                        : "border-white/10 bg-black/20 hover:bg-white/5"
                    }`}
                  >
                    <span className="block font-semibold text-white">
                      Vidéo {index + 1}
                    </span>
                    <span className="text-ink-500">
                      Graine {item.seed} ·{" "}
                      {(item.size / 1024 / 1024).toFixed(1)} Mo
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5 grid items-start gap-6 lg:grid-cols-[minmax(280px,25rem)_minmax(0,1fr)]">
            <div className="space-y-3 lg:sticky lg:top-24">
              <div className="overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl shadow-black/30">
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video
                  src={`/api/renders/${encodeURIComponent(result.filename)}`}
                  controls
                  playsInline
                  loop
                  className="aspect-[9/16] w-full object-contain"
                />
              </div>
              <div className="subpanel p-3.5">
                <p className="text-sm font-semibold">Rendu #{result.seed}</p>
                <p className="mt-1 text-xs leading-5 text-ink-400">
                  {getGameDefinition(result.game).uiName} · {result.duration} s
                  ·{" "}
                  {result.game === "soft-body-slide"
                    ? `5 niveaux · ${(result.softnessStages || [0, 25, 50, 75, 100]).join(
                        " / "
                      )} %`
                    : `${result.difficulty} ${getGameDefinition(
                        result.game
                      ).uiMetricLabel.toLowerCase()}`} ·{" "}
                  {(result.size / 1024 / 1024).toFixed(1)} Mo
                </p>
                {localizedSoftBodyVariant(result) && (
                  <p className="mt-1 text-[11px] text-amber-200/85">
                    Variante : {localizedSoftBodyVariant(result)}
                  </p>
                )}
                {result.outcome && (
                  <p
                    className={`mt-2 text-[11px] font-semibold ${gameOutcomeTones[result.outcome]}`}
                  >
                    Issue : {gameOutcomeLabels[result.outcome]}
                    {result.completedAt !== null
                      ? ` à ${result.completedAt.toFixed(2)} s`
                      : ""}
                  </p>
                )}
                <p className="mt-1 text-[11px] text-cyan-200/80">
                  {result.musicMode === "hit-reveal"
                    ? `${result.musicHits} séquences déclenchées par collision`
                    : result.musicMode === "continuous"
                    ? "Bande-son continue"
                    : result.musicMode === "foley-only"
                    ? "Foley ASMR original, sans musique"
                    : result.musicMode === "subtle-bed"
                    ? "Foley ASMR avec musique discrète"
                    : "Bande-son originale générée"}
                </p>
                {result.musicTitle && (
                  <p className="mt-2 text-[11px] text-ink-500">
                    Musique :{" "}
                    {result.musicSource === "original"
                      ? "Piste originale générée"
                      : result.musicTitle}
                  </p>
                )}
                {result.musicNote && (
                  <p className="mt-2 text-[11px] text-amber-200/80">
                    {result.musicNote}
                  </p>
                )}
                {result.musicCredit && (
                  <p className="mt-2 break-words text-[10px] text-ink-500">
                    {result.musicCredit}
                  </p>
                )}
              </div>
            </div>

            <div className="min-w-0 space-y-4">
              <div className="grid grid-cols-2 rounded-2xl border border-white/10 bg-ink-900/55 p-1">
                <button
                  type="button"
                  onClick={() => setPublishTab("tiktok")}
                  className={`flex h-11 items-center justify-center gap-2 rounded-xl text-sm font-semibold transition ${
                    publishTab === "tiktok"
                      ? "bg-white/10 text-white shadow"
                      : "text-ink-400 hover:text-white"
                  }`}
                >
                  <UploadCloud className="size-4" /> TikTok
                </button>
                <button
                  type="button"
                  onClick={() => setPublishTab("youtube")}
                  className={`flex h-11 items-center justify-center gap-2 rounded-xl text-sm font-semibold transition ${
                    publishTab === "youtube"
                      ? "bg-red-500/15 text-white shadow"
                      : "text-ink-400 hover:text-white"
                  }`}
                >
                  <Youtube className="size-4" /> YouTube
                </button>
              </div>

              {publishTab === "tiktok" ? (
                <section className="subpanel space-y-4 p-4 sm:p-5">
                  <div>
                    <h4 className="text-sm font-semibold">
                      Publication TikTok
                    </h4>
                    <p className="mt-1 text-xs text-ink-500">
                      Choisis les comptes cibles et vérifie la légende avant
                      l’envoi.
                    </p>
                  </div>
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>
                      Légende TikTok / Shorts{" "}
                      <span className="text-ink-500">(contenu en anglais)</span>
                    </span>
                    <textarea
                      value={caption}
                      onChange={(event) => setCaption(event.target.value)}
                      rows={4}
                      className="field-control min-h-28 py-3"
                    />
                  </label>
                  <TikTokTargetPicker value={accounts} onChange={setAccounts} />
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>Visibilité</span>
                    <select
                      value={tiktokVisibility}
                      onChange={(event) => {
                        const value = event.target.value as "private" | "public";
                        setTiktokVisibility(value);
                        if (value === "private") setTiktokConfirmPublic(false);
                      }}
                      className="field-control h-11"
                    >
                      <option value="private">Privée — test recommandé</option>
                      <option value="public">Publique</option>
                    </select>
                  </label>
                  {tiktokVisibility === "public" && (
                    <label className="flex items-start gap-3 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-amber-100">
                      <input
                        type="checkbox"
                        checked={tiktokConfirmPublic}
                        onChange={(event) => setTiktokConfirmPublic(event.target.checked)}
                        className="mt-0.5 size-4"
                      />
                      Je confirme que cette vidéo doit être publiée publiquement sur les comptes sélectionnés.
                    </label>
                  )}
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>Jeton de publication</span>
                    <input
                      type="password"
                      autoComplete="off"
                      value={adminToken}
                      onChange={(event) => updateAdminToken(event.target.value)}
                      placeholder="CLIPMAKER_UPLOAD_TOKEN"
                      className="field-control h-11"
                    />
                    <span className="block text-[10px] leading-4 text-ink-500">
                      Conservé uniquement dans cette session du navigateur.
                    </span>
                  </label>
                  <label className="block space-y-1.5 text-xs text-ink-400">
                    <span>
                      Son TikTok officiel — URL ou identifiant facultatif
                    </span>
                    <input
                      value={tiktokSound}
                      onChange={(event) => setTiktokSound(event.target.value)}
                      placeholder="https://www.tiktok.com/music/…"
                      className="field-control h-11"
                    />
                    <span className="block text-[10px] leading-4 text-ink-500">
                      Associe la publication à un son drôle ou tendance sans
                      l’intégrer au fichier YouTube.
                    </span>
                  </label>
                  <Button
                    onClick={uploadTikTok}
                    disabled={
                      uploading ||
                      !accounts.length ||
                      (tiktokVisibility === "public" && !tiktokConfirmPublic) ||
                      accounts.every((username) =>
                        publishedAccounts.includes(username)
                      )
                    }
                  >
                    {uploading ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <UploadCloud className="size-4" />
                    )}
                    Publier sur {accounts.length || 0} compte
                    {accounts.length === 1 ? "" : "s"} TikTok
                  </Button>
                  {uploadMessage && (
                    <p className="whitespace-pre-wrap text-sm text-ink-200">
                      {uploadMessage}
                    </p>
                  )}
                </section>
              ) : (
                <YoutubePublisher
                  key={result.filename}
                  gameId={result.game}
                  filename={result.filename}
                  defaultTitle={result.youtubeTitle}
                  description={caption}
                  tags={result.tags}
                />
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
