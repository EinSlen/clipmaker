"use client";

import * as React from "react";
import { ExternalLink, Loader2, ShieldCheck, Youtube } from "lucide-react";
import { Button } from "./Button";

type Status = {
  ok: boolean;
  provider?: "youtube-data-api";
  dryRun: boolean;
  readyForLiveUpload: boolean;
  configured: Record<string, "configured" | "missing">;
  error?: string;
};

type YouTubeAccount = {
  id: string;
  label: string;
  configured: boolean;
};

export function YoutubePublisher({
  gameId = "editor",
  filename,
  defaultTitle,
  description,
  tags,
}: {
  gameId?: string;
  filename: string;
  defaultTitle: string;
  description: string;
  tags: string[];
}) {
  const [status, setStatus] = React.useState<Status | null>(null);
  const [accounts, setAccounts] = React.useState<YouTubeAccount[]>([]);
  const [account, setAccount] = React.useState("default");
  const [title, setTitle] = React.useState(defaultTitle.slice(0, 100));
  const [privacy, setPrivacy] = React.useState<"private" | "unlisted">(
    "private"
  );
  const [adminToken, setAdminToken] = React.useState("");
  const [uploading, setUploading] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [releaseUrl, setReleaseUrl] = React.useState<string | null>(null);
  const [routeHydrated, setRouteHydrated] = React.useState(false);

  React.useEffect(() => {
    const saved = window.sessionStorage.getItem("clipmaker-upload-token");
    if (saved) setAdminToken(saved);
    fetch("/api/youtube/accounts")
      .then((response) => response.json())
      .then((data) => {
        const next = (data.accounts || []) as YouTubeAccount[];
        setAccounts(next);
        try {
          const routes = JSON.parse(
            window.localStorage.getItem("clipmaker-game-youtube-routes") || "{}"
          ) as Record<string, string>;
          if (next.some((item) => item.id === routes[gameId]))
            setAccount(routes[gameId]);
        } catch {}
        setRouteHydrated(true);
      })
      .catch(() => {
        setAccounts([
          { id: "default", label: "Chaîne par défaut", configured: false },
        ]);
        setRouteHydrated(true);
      });
  }, [gameId]);

  React.useEffect(() => {
    if (!routeHydrated) return;
    try {
      const routes = JSON.parse(
        window.localStorage.getItem("clipmaker-game-youtube-routes") || "{}"
      ) as Record<string, string>;
      routes[gameId] = account;
      window.localStorage.setItem(
        "clipmaker-game-youtube-routes",
        JSON.stringify(routes)
      );
    } catch {}
  }, [account, gameId, routeHydrated]);

  React.useEffect(() => {
    setStatus(null);
    fetch(`/api/youtube/status?account=${encodeURIComponent(account)}`)
      .then((response) => response.json())
      .then(setStatus)
      .catch((error) =>
        setStatus({
          ok: false,
          dryRun: true,
          readyForLiveUpload: false,
          configured: {},
          error: String(error),
        })
      );
  }, [account]);

  function updateAdminToken(value: string) {
    setAdminToken(value);
    if (value) window.sessionStorage.setItem("clipmaker-upload-token", value);
    else window.sessionStorage.removeItem("clipmaker-upload-token");
  }

  async function upload() {
    if (!title.trim()) return;
    setUploading(true);
    setMessage(null);
    setReleaseUrl(null);
    try {
      const response = await fetch("/api/youtube/upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(adminToken ? { "x-clipmaker-upload-token": adminToken } : {}),
        },
        body: JSON.stringify({
          filename,
          title: title.trim(),
          description,
          tags,
          privacy,
          account,
        }),
      });
      const data = await response.json();
      if (!data.ok) {
        console.error("Publication YouTube impossible", data.error);
        setMessage(
          "Échec de la publication YouTube. Vérifie la session et les journaux du serveur."
        );
        return;
      }
      if (data.dryRun) {
        setMessage(
          `Test validé · ${Math.round(data.media.duration)} s · ${
            data.media.width
          }×${data.media.height} · aucune vidéo publiée`
        );
      } else {
        setMessage(
          `Short envoyé sur ${account} en mode ${
            privacy === "private" ? "privé" : "non répertorié"
          }.`
        );
        if (data.upload?.releaseUrl) setReleaseUrl(data.upload.releaseUrl);
      }
    } catch (error) {
      console.error("Publication YouTube impossible", error);
      setMessage(
        "Échec de la publication YouTube. Vérifie la connexion au serveur."
      );
    } finally {
      setUploading(false);
    }
  }

  const liveMode = status?.ok && !status.dryRun;
  const disabled =
    uploading ||
    !title.trim() ||
    !status?.ok ||
    Boolean(liveMode && !status.readyForLiveUpload);

  return (
    <section
      className="subpanel space-y-4 p-4 sm:p-5"
      aria-labelledby="youtube-publish-title"
    >
      <div className="flex items-center justify-between gap-3">
        <h3
          id="youtube-publish-title"
          className="flex items-center gap-2 font-semibold"
        >
          <Youtube className="size-5 text-red-400" aria-hidden="true" />{" "}
          Publication YouTube Shorts
        </h3>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            liveMode
              ? "bg-red-500/15 text-red-200"
              : "bg-emerald-500/15 text-emerald-200"
          }`}
          role="status"
        >
          {status
            ? liveMode
              ? "Publication réelle"
              : "Mode test"
            : "Vérification…"}
        </span>
      </div>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Profil de chaîne YouTube</span>
        <select
          value={account}
          onChange={(event) => setAccount(event.target.value)}
          className="field-control h-11"
        >
          {(accounts.length
            ? accounts
            : [{ id: "default", label: "Chaîne par défaut", configured: false }]
          ).map((item) => (
            <option key={item.id} value={item.id}>
              {item.id === "default" && item.label === "Default channel"
                ? "Chaîne par défaut"
                : item.label}
              {item.configured ? "" : " — connexion requise"}
            </option>
          ))}
        </select>
        <span className="block text-xs leading-relaxed text-ink-500">
          Cette destination est mémorisée pour ce format. Pour créer un autre
          profil :{" "}
          <code>npm run youtube:oauth:setup -- --client-json CHEMIN --account nom-chaine</code>.
        </span>
      </label>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>
          Titre du Short{" "}
          <span className="text-ink-500">(contenu vidéo en anglais)</span>
        </span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value.slice(0, 100))}
          className="field-control h-11"
          placeholder="Titre du Short en anglais"
        />
        <span className="block text-xs text-ink-500">
          {title.length}/100 caractères
        </span>
      </label>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Visibilité initiale</span>
        <select
          value={privacy}
          onChange={(event) =>
            setPrivacy(event.target.value as "private" | "unlisted")
          }
          className="field-control h-11"
        >
          <option value="private">
            Privée — recommandée pour vérification
          </option>
          <option value="unlisted">Non répertoriée</option>
        </select>
      </label>

      {liveMode && (
        <label className="text-xs text-ink-400 space-y-1 block">
          <span>Jeton d’administration ClipMaker</span>
          <input
            type="password"
            value={adminToken}
            onChange={(event) => updateAdminToken(event.target.value)}
            className="field-control h-11"
            autoComplete="off"
          />
        </label>
      )}

      {status && !status.ok && (
        <p className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-200">
          Service de publication YouTube indisponible. Vérifie la configuration
          du serveur.
        </p>
      )}
      {liveMode && !status.readyForLiveUpload && (
        <p className="rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-xs leading-relaxed text-amber-200">
          L’autorisation OAuth YouTube manque ou a expiré. Lance <code>npm run youtube:oauth:setup</code> dans <code>web/</code>.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          onClick={upload}
          disabled={disabled}
          className="max-sm:w-full"
        >
          {uploading ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <ShieldCheck className="size-4" aria-hidden="true" />
          )}
          {liveMode ? "Publier sur YouTube" : "Tester la publication YouTube"}
        </Button>
        {releaseUrl && (
          <a
            href={releaseUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-ink-200 hover:text-white"
          >
            Voir la vidéo <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        )}
      </div>

      <p className="text-xs leading-relaxed text-ink-400">
        Le mode test valide le fichier sans le publier. En mode réel, ClipMaker
        utilise OAuth et l’API YouTube depuis GitHub Actions ; aucun navigateur ni ordinateur permanent n’est requis.{" "}
        La publication publique reste désactivée.
      </p>
      {message && (
        <p
          className="whitespace-pre-wrap rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-ink-200"
          role="status"
        >
          {message}
        </p>
      )}
    </section>
  );
}
