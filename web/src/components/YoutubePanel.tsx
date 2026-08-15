"use client";

import * as React from "react";
import { Loader2, Sparkles, ArrowDownToLine, Youtube } from "lucide-react";
import { Button } from "./Button";
import type { YoutubeSuggestion } from "@/lib/types";

const VIBES = [
  { id: "sad", label: "Triste et esthétique" },
  { id: "philo", label: "Cinéma et réflexion" },
  { id: "nature", label: "Nature et pluie" },
  { id: "anime", label: "Anime mélancolique" },
];

export function YoutubePanel({
  onImported,
}: {
  onImported: (info: {
    id: string;
    filename: string;
    size: number;
    title: string;
  }) => void;
}) {
  const [vibe, setVibe] = React.useState("sad");
  const [items, setItems] = React.useState<YoutubeSuggestion[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [downloadingId, setDownloadingId] = React.useState<string | null>(null);

  // Lit la réponse comme JSON ; si le serveur a crashé sans body (500 vide),
  // on retourne un objet d'erreur lisible au lieu de planter le composant.
  async function safeJson(
    r: Response
  ): Promise<{ ok: boolean; error?: string; [k: string]: unknown }> {
    const text = await r.text().catch(() => "");
    if (!text)
      return {
        ok: false,
        error: `Serveur a renvoyé ${r.status} sans message (probablement une erreur côté API).`,
      };
    try {
      return JSON.parse(text);
    } catch {
      return {
        ok: false,
        error: `Réponse non-JSON (${r.status}): ${text.slice(0, 200)}`,
      };
    }
  }

  const search = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/youtube/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vibe, limit: 12 }),
      });
      const j = await safeJson(r);
      setItems((j.items as YoutubeSuggestion[]) || []);
      if (!r.ok) {
        console.error("Recherche YouTube impossible", j.error || r.status);
        alert(
          "La recherche YouTube n’a pas abouti. Vérifie la connexion et les journaux du serveur."
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const importVid = async (s: YoutubeSuggestion) => {
    setDownloadingId(s.id);
    try {
      const r = await fetch("/api/youtube/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: s.url }),
      });
      const j = await safeJson(r);
      if (j.ok)
        onImported({
          id: j.id as string,
          filename: j.filename as string,
          size: j.size as number,
          title: s.title,
        });
      else {
        console.error("Import YouTube impossible", j.error || r.status);
        alert(
          "L’import YouTube n’a pas abouti. Vérifie les droits de la vidéo et les journaux du serveur."
        );
      }
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <section
      className="subpanel space-y-5 p-4 sm:p-5"
      aria-labelledby="youtube-import-title"
    >
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-red-500/10 text-red-300">
          <Youtube className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h2 id="youtube-import-title" className="font-semibold">
            Importer depuis YouTube
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-400">
            Recherche une vidéo source, puis ajoute-la à ta bibliothèque pour la
            retravailler.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {VIBES.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setVibe(v.id)}
            aria-pressed={vibe === v.id}
            className={`h-10 rounded-full border px-3 text-sm transition ${
              vibe === v.id
                ? "bg-accent text-white border-accent"
                : "border-white/15 text-ink-200 hover:bg-white/5"
            }`}
          >
            {v.label}
          </button>
        ))}
        <Button type="button" onClick={search} className="ml-auto">
          {loading ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="size-4" aria-hidden="true" />
          )}
          Rechercher
        </Button>
      </div>

      {items.length === 0 && !loading && (
        <div className="subpanel p-5 text-center">
          <p className="text-sm text-ink-300">
            Choisis une ambiance, puis lance la recherche pour afficher des
            vidéos correspondantes.
          </p>
        </div>
      )}

      {loading && (
        <div
          className="subpanel flex items-center justify-center gap-2 p-5 text-sm text-ink-300"
          role="status"
        >
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />{" "}
          Recherche sur YouTube…
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map((it) => (
          <article key={it.id} className="subpanel overflow-hidden">
            {it.thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={it.thumbnail}
                alt={`Aperçu de la vidéo « ${it.title} »`}
                className="aspect-video w-full object-cover"
              />
            ) : (
              <div
                className="grid aspect-video place-items-center bg-ink-700 text-xs text-ink-400"
                role="img"
                aria-label={`Aucun aperçu disponible pour « ${it.title} »`}
              >
                Aucun aperçu
              </div>
            )}
            <div className="space-y-2 p-3">
              <h3 className="line-clamp-2 text-sm font-medium">{it.title}</h3>
              <p className="text-xs text-ink-400">
                {it.channel} · {it.duration} s ·{" "}
                {Intl.NumberFormat("fr-FR").format(it.views)} vues
              </p>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="mt-1 w-full"
                disabled={downloadingId === it.id}
                onClick={() => importVid(it)}
                aria-label={`Importer « ${it.title} »`}
              >
                {downloadingId === it.id ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <ArrowDownToLine className="size-4" aria-hidden="true" />
                )}
                Importer
              </Button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
