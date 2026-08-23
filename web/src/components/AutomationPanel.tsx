"use client";

import * as React from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Gamepad2,
  Loader2,
  Music2,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  Youtube,
} from "lucide-react";
import { Button } from "@/components/Button";
import { GAME_CATALOG, getGameDefinition, type GameId } from "@/lib/game-catalog";
import type {
  PublisherChannelConfig,
  PublisherConfigDocument,
  PublisherRuntimeStatus,
} from "@/lib/publisher-types";
import type { TiktokAccount } from "@/lib/types";

type YoutubeAccount = { id: string; label: string; configured: boolean };
type YoutubeStatus = {
  readyForLiveUpload?: boolean;
  publicUploadAllowed?: boolean;
  dryRun?: boolean;
};

const OBSTACLES = [
  ["auto", "Automatique"],
  ["moving-slide", "Rampe mobile"],
  ["stair-cascade", "Cascade d’escaliers"],
  ["v-stairs", "Barres en V"],
  ["pipe-bend", "Tube courbé"],
  ["peg-grid", "Grille de barres"],
  ["twin-gears", "Double engrenage"],
  ["compression-ring", "Anneau de compression"],
] as const;

function defaultChannel(index: number): PublisherChannelConfig {
  const definition = GAME_CATALOG[index % GAME_CATALOG.length];
  return {
    id: `canal-${Date.now().toString(36).slice(-6)}-${index + 1}`,
    enabled: false,
    generateTime: "00:30",
    publishTime: "18:30",
    game: {
      id: definition.id,
      difficulty: definition.metricDefault,
      duration: definition.id === "soft-body-slide" ? 30 : 15,
      theme: "neon",
      soundPack: "auto",
      musicMode: definition.id === "shape-tunnel" || definition.id === "soft-body-slide"
        ? "continuous"
        : "hit-reveal",
      musicVolume: 0.55,
      title: definition.defaultHook,
      ...(definition.id === "soft-body-slide" ? { obstacle: "auto" } : {}),
    },
    youtube: {
      enabled: false,
      account: "default",
      privacy: "private",
      confirmPublic: false,
    },
    tiktok: {
      enabled: false,
      username: null,
      musicId: null,
      visibility: "private",
      confirmPublic: false,
    },
  };
}

function statusLabel(value: string): string {
  return ({
    planned: "Planifiée",
    rendering: "Génération",
    ready: "Prête",
    publishing: "Publication",
    published: "Publiée",
    partial: "Partielle",
    failed: "Échec",
    pending: "En attente",
    disabled: "Désactivée",
  } as Record<string, string>)[value] || value;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <label className="inline-flex min-h-11 cursor-pointer items-center gap-3 text-sm font-medium">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 accent-[#7c5cff]"
      />
      <span>{label}</span>
    </label>
  );
}

function Health({ ready, children }: { ready: boolean; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
      ready ? "bg-emerald-500/15 text-emerald-200" : "bg-amber-500/15 text-amber-200"
    }`}>
      {ready ? <CheckCircle2 className="size-3.5" /> : <AlertTriangle className="size-3.5" />}
      {children}
    </span>
  );
}

export function AutomationPanel() {
  const [config, setConfig] = React.useState<PublisherConfigDocument | null>(null);
  const [runtime, setRuntime] = React.useState<PublisherRuntimeStatus | null>(null);
  const [tiktokAccounts, setTiktokAccounts] = React.useState<TiktokAccount[]>([]);
  const [youtubeAccounts, setYoutubeAccounts] = React.useState<YoutubeAccount[]>([]);
  const [youtubeStatuses, setYoutubeStatuses] = React.useState<Record<string, YoutubeStatus>>({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [adminToken, setAdminToken] = React.useState("");

  const refreshRuntime = React.useCallback(async () => {
    const response = await fetch("/api/publisher/status", { cache: "no-store" });
    setRuntime(await response.json());
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [configResponse, runtimeResponse, tiktokResponse, youtubeResponse] = await Promise.all([
        fetch("/api/publisher/config", { cache: "no-store" }),
        fetch("/api/publisher/status", { cache: "no-store" }),
        fetch("/api/tiktok/accounts", { cache: "no-store" }),
        fetch("/api/youtube/accounts", { cache: "no-store" }),
      ]);
      const configPayload = await configResponse.json();
      if (!configResponse.ok || !configPayload.ok) throw new Error(configPayload.error || "Configuration introuvable.");
      const tiktokPayload = await tiktokResponse.json();
      const youtubePayload = await youtubeResponse.json();
      const accounts = (youtubePayload.accounts || []) as YoutubeAccount[];
      setConfig(configPayload.config);
      setRuntime(await runtimeResponse.json());
      setTiktokAccounts(tiktokPayload.accounts || []);
      setYoutubeAccounts(accounts);
      const statuses = await Promise.all(accounts.map(async (account) => {
        const response = await fetch(`/api/youtube/status?account=${encodeURIComponent(account.id)}`, { cache: "no-store" });
        return [account.id, await response.json()] as const;
      }));
      setYoutubeStatuses(Object.fromEntries(statuses));
      setAdminToken(window.sessionStorage.getItem("clipmaker-upload-token") || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    const timer = window.setInterval(() => { void refreshRuntime(); }, 30_000);
    return () => window.clearInterval(timer);
  }, [refreshRuntime]);

  function updateChannel(index: number, updater: (channel: PublisherChannelConfig) => PublisherChannelConfig) {
    setConfig((current) => current ? {
      ...current,
      channels: current.channels.map((channel, channelIndex) => channelIndex === index ? updater(channel) : channel),
    } : current);
    setMessage(null);
  }

  function changeGame(index: number, id: GameId) {
    const definition = getGameDefinition(id);
    updateChannel(index, (channel) => ({
      ...channel,
      game: {
        ...channel.game,
        id,
        difficulty: definition.metricDefault,
        duration: id === "soft-body-slide" ? 30 : 15,
        title: definition.defaultHook,
        musicMode: id === "shape-tunnel" || id === "soft-body-slide" ? "continuous" : "hit-reveal",
        ...(id === "soft-body-slide" ? { obstacle: "auto" } : { obstacle: undefined }),
      },
    }));
  }

  async function save() {
    if (!config) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/publisher/config", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(adminToken ? { "x-clipmaker-upload-token": adminToken } : {}),
        },
        body: JSON.stringify(config),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Sauvegarde impossible.");
      setConfig(payload.config);
      setMessage("Planning sauvegardé. Le daemon utilisera ces réglages au prochain passage.");
      if (adminToken) window.sessionStorage.setItem("clipmaker-upload-token", adminToken);
      await refreshRuntime();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="panel flex min-h-72 items-center justify-center gap-3 p-8 text-sm text-ink-300" role="status"><Loader2 className="size-5 animate-spin" /> Chargement du planning…</div>;
  }

  if (!config) {
    return (
      <div className="panel p-6 sm:p-8">
        <AlertTriangle className="size-8 text-amber-300" />
        <h2 className="mt-4 text-xl font-semibold">Planning indisponible</h2>
        <p className="mt-2 text-sm text-ink-400">{error || "Crée la configuration serveur avant d’utiliser cet écran."}</p>
        <Button className="mt-5" onClick={() => void load()}><RefreshCw className="size-4" /> Réessayer</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden p-5 sm:p-7" aria-labelledby="automation-title">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-accent-soft"><CalendarClock className="size-4" /> Publication quotidienne</p>
            <h2 id="automation-title" className="mt-2 text-xl font-bold sm:text-2xl">Un jeu fixe pour chacun de tes comptes</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-400">La génération démarre en avance, puis chaque vidéo est envoyée une seule fois à l’heure choisie. Les seeds changent automatiquement chaque jour.</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Health ready={Boolean(runtime?.daemon.active)}>{runtime?.daemon.active ? "Daemon actif" : "Daemon hors ligne"}</Health>
            <Button variant="ghost" size="sm" onClick={() => void load()} aria-label="Actualiser le planning"><RefreshCw className="size-4" /></Button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="subpanel p-4"><p className="text-xs text-ink-500">Canaux actifs</p><p className="mt-1 text-2xl font-semibold">{config.channels.filter((channel) => channel.enabled).length}</p></div>
          <div className="subpanel p-4"><p className="text-xs text-ink-500">Fuseau horaire</p><p className="mt-1 text-sm font-semibold">{config.timeZone}</p></div>
          <div className="subpanel p-4"><p className="text-xs text-ink-500">Dernier signal</p><p className="mt-1 text-sm font-semibold">{runtime?.daemon.lastSeenAt ? new Date(runtime.daemon.lastSeenAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "Aucun"}</p></div>
        </div>
      </section>

      <section className="panel p-5 sm:p-7" aria-labelledby="global-settings-title">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 id="global-settings-title" className="font-semibold">Réglages généraux</h2>
            <p className="mt-1 text-sm text-ink-400">Le mode test calcule le planning sans générer ni publier.</p>
          </div>
          <Toggle checked={config.dryRun} onChange={(dryRun) => setConfig({ ...config, dryRun })} label="Mode test uniquement" />
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <label className="space-y-1.5 text-xs text-ink-400"><span>Fuseau horaire</span><input className="field-control h-11" value={config.timeZone} onChange={(event) => setConfig({ ...config, timeZone: event.target.value })} /></label>
          <label className="space-y-1.5 text-xs text-ink-400"><span>Vérification du planning</span><select className="field-control h-11" value={config.pollSeconds} onChange={(event) => setConfig({ ...config, pollSeconds: Number(event.target.value) })}><option value={60}>Chaque minute</option><option value={300}>Toutes les 5 minutes</option><option value={900}>Toutes les 15 minutes</option></select></label>
          <label className="space-y-1.5 text-xs text-ink-400"><span>Rattrapage après arrêt</span><select className="field-control h-11" value={config.catchupDays} onChange={(event) => setConfig({ ...config, catchupDays: Number(event.target.value) })}><option value={0}>Aucun</option><option value={1}>1 jour</option><option value={2}>2 jours</option><option value={7}>7 jours</option></select></label>
        </div>
      </section>

      <div className="space-y-5">
        {config.channels.map((channel, index) => {
          const definition = getGameDefinition(channel.game.id);
          const tiktok = tiktokAccounts.find((account) => account.username === channel.tiktok.username);
          const youtube = youtubeStatuses[channel.youtube.account];
          return (
            <article key={channel.id} className={`panel overflow-hidden ${channel.enabled ? "" : "opacity-75"}`}>
              <div className="grid lg:grid-cols-[13rem_minmax(0,1fr)]">
                <div className="relative min-h-52 overflow-hidden border-b border-white/10 bg-black/20 lg:min-h-full lg:border-b-0 lg:border-r">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={definition.preview} alt={`Aperçu du jeu ${definition.uiName}`} className="absolute inset-0 size-full object-cover" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/5 to-black/25" />
                  <div className="absolute inset-x-0 bottom-0 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-white/70">{definition.engineLabel}</p><p className="mt-1 font-bold">{definition.uiName}</p></div>
                </div>

                <div className="space-y-6 p-5 sm:p-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3">
                      <span className="grid size-10 place-items-center rounded-xl bg-accent/15 text-accent-soft"><Gamepad2 className="size-5" /></span>
                      <div><h3 className="font-semibold">Canal {index + 1}</h3><p className="text-xs text-ink-500">{channel.id}</p></div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Toggle checked={channel.enabled} onChange={(enabled) => updateChannel(index, (item) => ({ ...item, enabled }))} label={channel.enabled ? "Actif" : "Désactivé"} />
                      <Button variant="ghost" size="sm" disabled={config.channels.length === 1} onClick={() => setConfig({ ...config, channels: config.channels.filter((_, itemIndex) => itemIndex !== index) })} aria-label={`Supprimer le canal ${index + 1}`}><Trash2 className="size-4" /></Button>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <label className="space-y-1.5 text-xs text-ink-400"><span>Jeu de ce compte</span><select className="field-control h-11" value={channel.game.id} onChange={(event) => changeGame(index, event.target.value as GameId)}>{GAME_CATALOG.map((game) => <option key={game.id} value={game.id}>{game.uiName}</option>)}</select></label>
                    <label className="space-y-1.5 text-xs text-ink-400"><span>Générer à</span><input type="time" className="field-control h-11" value={channel.generateTime} onChange={(event) => updateChannel(index, (item) => ({ ...item, generateTime: event.target.value }))} /></label>
                    <label className="space-y-1.5 text-xs text-ink-400"><span>Publier à</span><input type="time" className="field-control h-11" value={channel.publishTime} onChange={(event) => updateChannel(index, (item) => ({ ...item, publishTime: event.target.value }))} /></label>
                    <label className="space-y-1.5 text-xs text-ink-400"><span>Durée</span><select disabled={channel.game.id === "soft-body-slide"} className="field-control h-11" value={channel.game.duration} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, duration: Number(event.target.value) } }))}>{[15, 30, 45, 60].map((duration) => <option key={duration} value={duration}>{duration} secondes</option>)}</select></label>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
                    <label className="space-y-1.5 text-xs text-ink-400"><span>Accroche dans la vidéo <span className="text-ink-500">(anglais)</span></span><input className="field-control h-11" value={channel.game.title} maxLength={52} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, title: event.target.value } }))} /></label>
                    <label className="space-y-1.5 text-xs text-ink-400"><span>{definition.uiMetricLabel}</span><input type="number" min={definition.metricMin} max={definition.metricMax} step={definition.metricStep} disabled={channel.game.id === "soft-body-slide"} className="field-control h-11" value={channel.game.difficulty} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, difficulty: Number(event.target.value) } }))} /></label>
                  </div>

                  {channel.game.id === "soft-body-slide" && (
                    <label className="block space-y-1.5 text-xs text-ink-400"><span>Obstacle 3D</span><select className="field-control h-11" value={channel.game.obstacle || "auto"} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, obstacle: event.target.value } }))}>{OBSTACLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                  )}

                  <fieldset className="subpanel space-y-4 p-4 sm:p-5">
                    <legend className="px-2 text-sm font-semibold">Destinations</legend>
                    <div className="grid gap-5 xl:grid-cols-2">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between gap-3"><Toggle checked={channel.tiktok.enabled} onChange={(enabled) => updateChannel(index, (item) => ({ ...item, tiktok: { ...item.tiktok, enabled } }))} label="Publier sur TikTok" />{channel.tiktok.username && <Health ready={Boolean(tiktok?.ready)}>{tiktok?.ready ? "Session prête" : tiktok?.expired ? "Session expirée" : "Connexion requise"}</Health>}</div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label className="space-y-1.5 text-xs text-ink-400"><span>Compte TikTok</span><select className="field-control h-11" value={channel.tiktok.username || ""} onChange={(event) => updateChannel(index, (item) => ({ ...item, tiktok: { ...item.tiktok, username: event.target.value || null } }))}><option value="">Choisir un compte</option>{tiktokAccounts.map((account) => <option key={account.username} value={account.username}>@{account.username}{account.ready ? "" : " — reconnexion"}</option>)}</select></label>
                          <label className="space-y-1.5 text-xs text-ink-400"><span>Visibilité TikTok</span><select className="field-control h-11" value={channel.tiktok.visibility} onChange={(event) => updateChannel(index, (item) => ({ ...item, tiktok: { ...item.tiktok, visibility: event.target.value as "private" | "public", confirmPublic: false } }))}><option value="private">Privée</option><option value="public">Publique</option></select></label>
                        </div>
                        {channel.tiktok.visibility === "public" && <Toggle checked={channel.tiktok.confirmPublic} onChange={(confirmPublic) => updateChannel(index, (item) => ({ ...item, tiktok: { ...item.tiktok, confirmPublic } }))} label="Je confirme la publication TikTok publique" />}
                        {channel.tiktok.username && !tiktok?.ready && <a className="inline-flex min-h-11 items-center gap-2 text-sm text-accent-soft hover:text-white" href={`http://${typeof window !== "undefined" ? window.location.hostname : "127.0.0.1"}:6081/vnc.html?autoconnect=true&resize=scale`} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /> Reconnecter ce compte</a>}
                      </div>

                      <div className="space-y-3 border-t border-white/10 pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
                        <div className="flex items-center justify-between gap-3"><Toggle checked={channel.youtube.enabled} onChange={(enabled) => updateChannel(index, (item) => ({ ...item, youtube: { ...item.youtube, enabled } }))} label="Publier sur YouTube" />{channel.youtube.account && <Health ready={Boolean(youtube?.readyForLiveUpload)}>{youtube?.readyForLiveUpload ? "Session prête" : "Connexion requise"}</Health>}</div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label className="space-y-1.5 text-xs text-ink-400"><span>Chaîne YouTube</span><select className="field-control h-11" value={channel.youtube.account} onChange={(event) => updateChannel(index, (item) => ({ ...item, youtube: { ...item.youtube, account: event.target.value } }))}>{(youtubeAccounts.length ? youtubeAccounts : [{ id: "default", label: "Chaîne par défaut", configured: false }]).map((account) => <option key={account.id} value={account.id}>{account.id === "default" ? "Chaîne par défaut" : account.label}</option>)}</select></label>
                          <label className="space-y-1.5 text-xs text-ink-400"><span>Visibilité YouTube</span><select className="field-control h-11" value={channel.youtube.privacy} onChange={(event) => updateChannel(index, (item) => ({ ...item, youtube: { ...item.youtube, privacy: event.target.value as "private" | "unlisted" | "public", confirmPublic: false } }))}><option value="private">Privée</option><option value="unlisted">Non répertoriée</option><option value="public" disabled={!youtube?.publicUploadAllowed}>Publique{youtube?.publicUploadAllowed ? "" : " — bloquée serveur"}</option></select></label>
                        </div>
                        {channel.youtube.privacy === "public" && <Toggle checked={channel.youtube.confirmPublic} onChange={(confirmPublic) => updateChannel(index, (item) => ({ ...item, youtube: { ...item.youtube, confirmPublic } }))} label="Je confirme la publication YouTube publique" />}
                        {!youtube?.readyForLiveUpload && <a className="inline-flex min-h-11 items-center gap-2 text-sm text-accent-soft hover:text-white" href={`http://${typeof window !== "undefined" ? window.location.hostname : "127.0.0.1"}:6080/vnc.html?autoconnect=true&resize=scale`} target="_blank" rel="noreferrer"><Youtube className="size-4" /> Connecter YouTube</a>}
                      </div>
                    </div>
                  </fieldset>

                  <details className="subpanel p-4">
                    <summary className="cursor-pointer text-sm font-medium text-ink-200">Style et son avancés</summary>
                    <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                      <label className="space-y-1.5 text-xs text-ink-400"><span>Ambiance</span><select className="field-control h-11" value={channel.game.theme} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, theme: event.target.value as PublisherChannelConfig["game"]["theme"] } }))}><option value="neon">Néon</option><option value="sunset">Coucher de soleil</option><option value="ice">Glace</option></select></label>
                      <label className="space-y-1.5 text-xs text-ink-400"><span>Pack sonore</span><select className="field-control h-11" value={channel.game.soundPack} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, soundPack: event.target.value as PublisherChannelConfig["game"]["soundPack"] } }))}><option value="auto">Automatique</option><option value="funny">Drôle</option><option value="arcade">Arcade</option><option value="impact">Impacts</option><option value="asmr">ASMR</option><option value="meme">Mème</option></select></label>
                      <label className="space-y-1.5 text-xs text-ink-400"><span>Musique</span><select className="field-control h-11" value={channel.game.musicMode} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, musicMode: event.target.value as PublisherChannelConfig["game"]["musicMode"] } }))}><option value="hit-reveal">Révélée aux impacts</option><option value="continuous">Continue</option></select></label>
                      <label className="space-y-1.5 text-xs text-ink-400"><span>Volume · {Math.round(channel.game.musicVolume * 100)} %</span><input type="range" min={0} max={1} step={0.05} className="h-11 w-full accent-[#7c5cff]" value={channel.game.musicVolume} onChange={(event) => updateChannel(index, (item) => ({ ...item, game: { ...item.game, musicVolume: Number(event.target.value) } }))} /></label>
                    </div>
                  </details>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <Button variant="outline" className="w-full sm:w-auto" onClick={() => setConfig({ ...config, channels: [...config.channels, defaultChannel(config.channels.length)] })}><Plus className="size-4" /> Ajouter un compte et son jeu</Button>

      {runtime?.jobs.length ? (
        <section className="panel p-5 sm:p-7" aria-labelledby="recent-jobs-title">
          <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-white/5"><Clock3 className="size-5" /></span><div><h2 id="recent-jobs-title" className="font-semibold">Historique récent</h2><p className="text-xs text-ink-500">Derniers rendus enregistrés par le daemon</p></div></div>
          <div className="mt-5 overflow-x-auto scroll-pretty">
            <table className="w-full min-w-[42rem] text-left text-sm"><thead className="text-xs uppercase tracking-wider text-ink-500"><tr><th className="pb-3 pr-4">Date</th><th className="pb-3 pr-4">Canal</th><th className="pb-3 pr-4">Rendu</th><th className="pb-3 pr-4">YouTube</th><th className="pb-3">TikTok</th></tr></thead><tbody className="divide-y divide-white/5">{runtime.jobs.slice(0, 8).map((job) => <tr key={job.id}><td className="py-3 pr-4">{job.date}</td><td className="py-3 pr-4 text-ink-300">{job.channelId}</td><td className="py-3 pr-4">{statusLabel(job.status)}</td><td className="py-3 pr-4 text-ink-400">{statusLabel(job.youtube)}</td><td className="py-3 text-ink-400">{statusLabel(job.tiktok)}</td></tr>)}</tbody></table>
          </div>
        </section>
      ) : null}

      <section className="sticky bottom-3 z-30 rounded-2xl border border-white/10 bg-ink-950/90 p-3 shadow-2xl backdrop-blur-xl" aria-label="Sauvegarde du planning">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0" aria-live="polite">{message ? <p className="flex items-center gap-2 text-sm text-emerald-200"><ShieldCheck className="size-4" /> {message}</p> : error ? <p className="flex items-center gap-2 text-sm text-red-200"><AlertTriangle className="size-4" /> {error}</p> : <p className="flex items-center gap-2 text-sm text-ink-400"><Music2 className="size-4" /> Vérifie les comptes, puis sauvegarde.</p>}</div>
          <div className="flex gap-2">
            <details className="relative"><summary className="flex h-11 cursor-pointer items-center rounded-xl border border-white/10 px-3 text-xs text-ink-300">Clé admin</summary><div className="absolute bottom-14 right-0 w-72 rounded-2xl border border-white/10 bg-ink-900 p-3 shadow-2xl"><label className="space-y-1.5 text-xs text-ink-400"><span>Requise hors de localhost</span><input type="password" className="field-control h-11" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" /></label></div></details>
            <Button onClick={() => void save()} disabled={saving}>{saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} Sauvegarder</Button>
          </div>
        </div>
      </section>
    </div>
  );
}
