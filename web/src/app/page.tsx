"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  CalendarClock,
  Film,
  Gamepad2,
  Library,
  Loader2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Youtube,
} from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Dropzone } from "@/components/Dropzone";
import { YoutubePanel } from "@/components/YoutubePanel";
import { GameStudio } from "@/components/GameStudio";
import { AutomationPanel } from "@/components/AutomationPanel";
import { Button } from "@/components/Button";
import { listVideos, putVideo, deleteVideo, probeVideo } from "@/lib/db";
import type { LibraryVideo } from "@/lib/types";

type Tab = "game" | "automation" | "upload" | "library" | "youtube";

const tabs = [
  {
    id: "game",
    label: "Jeux",
    longLabel: "Jeux automatiques",
    description: "Créer un format original",
    Icon: Gamepad2,
  },
  {
    id: "automation",
    label: "Planning",
    longLabel: "Planning automatique",
    description: "Un jeu par compte",
    Icon: CalendarClock,
  },
  {
    id: "upload",
    label: "Importer",
    longLabel: "Importer une vidéo",
    description: "Monter un fichier existant",
    Icon: Upload,
  },
  {
    id: "library",
    label: "Vidéos",
    longLabel: "Bibliothèque",
    description: "Retrouver les imports",
    Icon: Library,
  },
  {
    id: "youtube",
    label: "Inspiration",
    longLabel: "Inspiration YouTube",
    description: "Rechercher une source",
    Icon: Youtube,
  },
] as const;

export default function Home() {
  const router = useRouter();
  const [tab, setTab] = React.useState<Tab>("game");
  const [items, setItems] = React.useState<LibraryVideo[]>([]);
  const [uploading, setUploading] = React.useState(false);

  React.useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab");
    if (tabs.some((item) => item.id === requested)) setTab(requested as Tab);
  }, []);

  function selectTab(next: Tab) {
    setTab(next);
    const url = new URL(window.location.href);
    if (next === "game") url.searchParams.delete("tab");
    else url.searchParams.set("tab", next);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  React.useEffect(() => {
    listVideos().then(setItems);
  }, []);

  async function handleFile(file: File) {
    setUploading(true);
    try {
      // Probe metadata locally
      const meta = await probeVideo(file);
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!j.ok) {
        alert("Échec de l’import");
        return;
      }
      const rec: LibraryVideo & { blob: Blob } = {
        id: j.id,
        name: file.name,
        size: file.size,
        duration: meta.duration,
        width: meta.width,
        height: meta.height,
        createdAt: Date.now(),
        serverPath: j.filename,
        thumb: meta.thumb,
        blob: file,
      };
      await putVideo(rec);
      const next = await listVideos();
      setItems(next);
      router.push(`/editor/${rec.id}?file=${encodeURIComponent(j.filename)}`);
    } catch (e) {
      console.error(e);
      alert("Impossible d'importer cette vidéo");
    } finally {
      setUploading(false);
    }
  }

  async function onYoutubeImported(info: {
    id: string;
    filename: string;
    size: number;
    title: string;
  }) {
    // Fetch the file we just downloaded so we can probe & cache it client-side
    try {
      const r = await fetch(`/api/uploads/${info.filename}`);
      const blob = await r.blob();
      const meta = await probeVideo(blob);
      const rec: LibraryVideo & { blob: Blob } = {
        id: info.id,
        name: info.title.slice(0, 80) || info.filename,
        size: info.size,
        duration: meta.duration,
        width: meta.width,
        height: meta.height,
        createdAt: Date.now(),
        serverPath: info.filename,
        thumb: meta.thumb,
        blob,
      };
      await putVideo(rec);
      const next = await listVideos();
      setItems(next);
      router.push(
        `/editor/${rec.id}?file=${encodeURIComponent(info.filename)}`
      );
    } catch (e) {
      console.error(e);
      alert(
        "Import YouTube réussi côté serveur, mais impossible de précharger la vidéo localement."
      );
    }
  }

  async function removeItem(id: string) {
    if (!confirm("Supprimer cette vidéo de la bibliothèque ?")) return;
    await deleteVideo(id);
    setItems(await listVideos());
  }

  return (
    <div className="min-h-dvh">
      <TopBar />
      <div className="mx-auto grid max-w-7xl gap-8 px-4 pb-24 pt-0 sm:px-6 lg:grid-cols-[14rem_minmax(0,1fr)] lg:px-8 lg:pt-8">
        <aside className="hidden lg:block">
          <div className="sticky top-24 space-y-5">
            <div className="px-3">
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-ink-500">
                Espace de travail
              </p>
              <p className="mt-2 text-sm leading-5 text-ink-400">
                De l’idée à la publication, sans quitter le studio.
              </p>
            </div>
            <nav className="space-y-1.5" aria-label="Navigation principale">
              {tabs.map(({ id, longLabel, description, Icon }) => (
                <button
                  key={id}
                  type="button"
                  aria-current={tab === id ? "page" : undefined}
                  onClick={() => selectTab(id)}
                  className={`group flex w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition ${
                    tab === id
                      ? "border-white/15 bg-white/[0.08] text-white shadow-lg shadow-black/10"
                      : "border-transparent text-ink-400 hover:border-white/5 hover:bg-white/[0.035] hover:text-ink-200"
                  }`}
                >
                  <span
                    className={`grid size-9 shrink-0 place-items-center rounded-xl ${
                      tab === id
                        ? "bg-accent text-white"
                        : "bg-white/5 text-ink-400 group-hover:text-white"
                    }`}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">
                      {longLabel}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-ink-500">
                      {description}
                    </span>
                  </span>
                </button>
              ))}
            </nav>
            <div className="subpanel p-3.5">
              <p className="flex items-center gap-2 text-xs font-semibold text-ink-200">
                <ShieldCheck className="size-4 text-emerald-300" /> Rendu privé
              </p>
              <p className="mt-1.5 text-[11px] leading-4 text-ink-500">
                Les vidéos sont calculées et conservées sur ton propre serveur.
              </p>
            </div>
          </div>
        </aside>

        <main className="min-w-0 space-y-6">
          <nav
            className="sticky top-16 z-30 -mx-4 grid grid-cols-5 gap-1 border-b border-white/5 bg-ink-950/90 px-2 py-2 backdrop-blur-xl sm:-mx-6 sm:px-5 lg:hidden"
            aria-label="Navigation principale"
          >
            {tabs.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                aria-current={tab === id ? "page" : undefined}
                onClick={() => selectTab(id)}
                className={`flex min-w-0 flex-col items-center justify-center gap-1 rounded-xl border px-1 py-2 text-[10px] font-semibold transition ${
                  tab === id
                    ? "border-accent/60 bg-accent/15 text-white"
                    : "border-transparent text-ink-400"
                }`}
              >
                <Icon className="size-4" />
                <span className="truncate">{label}</span>
              </button>
            ))}
          </nav>

          <header className="panel relative overflow-hidden p-5 sm:p-7">
            <div className="absolute -right-20 -top-24 size-72 rounded-full bg-accent/10 blur-3xl" />
            <div className="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
              <div className="max-w-2xl">
                <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-accent-soft">
                  <Sparkles className="size-3.5" /> Atelier automatisé
                </p>
                <h1 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-3xl">
                  Des vidéos verticales originales, prêtes à publier.
                </h1>
                <p className="mt-2 max-w-xl text-sm leading-6 text-ink-400">
                  Choisis une simulation, règle son rythme et son audio, puis
                  génère des Shorts cohérents pour chacun de tes comptes.
                </p>
              </div>
              <dl className="grid grid-cols-3 gap-2 sm:min-w-[25rem]">
                <div className="rounded-2xl border border-white/[0.08] bg-black/15 p-3">
                  <dt className="text-[10px] uppercase tracking-wider text-ink-500">
                    Moteurs
                  </dt>
                  <dd className="mt-1 text-lg font-semibold">5</dd>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-black/15 p-3">
                  <dt className="text-[10px] uppercase tracking-wider text-ink-500">
                    Format
                  </dt>
                  <dd className="mt-1 text-lg font-semibold">9:16</dd>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-black/15 p-3">
                  <dt className="text-[10px] uppercase tracking-wider text-ink-500">
                    Sortie
                  </dt>
                  <dd className="mt-1 text-lg font-semibold">1080p</dd>
                </div>
              </dl>
            </div>
          </header>

          <section className={tab === "game" ? "block" : "hidden"}>
            <GameStudio />
          </section>

          <section className={tab === "automation" ? "block" : "hidden"}>
            <AutomationPanel />
          </section>

          <section className={tab === "upload" ? "block" : "hidden"}>
            <div className="panel p-5 sm:p-7">
              <div className="mb-5 flex items-start gap-3">
                <span className="grid size-10 place-items-center rounded-xl bg-accent/15 text-accent-soft">
                  <Upload className="size-5" />
                </span>
                <div>
                  <h3 className="font-semibold">Importer une vidéo</h3>
                  <p className="mt-1 text-sm text-ink-400">
                    Ajoute un fichier vertical ou horizontal, puis ouvre-le dans
                    l’éditeur.
                  </p>
                </div>
              </div>
              <Dropzone onFile={handleFile} busy={uploading} />
            </div>
          </section>

          <section className={tab === "library" ? "block" : "hidden"}>
            <div className="panel p-5 sm:p-7">
              <div className="mb-5 flex items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold">Bibliothèque locale</h3>
                  <p className="mt-1 text-sm text-ink-400">
                    Tes imports disponibles dans ce navigateur.
                  </p>
                </div>
                <span className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-ink-300">
                  {items.length} vidéo{items.length === 1 ? "" : "s"}
                </span>
              </div>
              {items.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 px-5 py-14 text-center">
                  <Film className="mx-auto size-7 text-ink-500" />
                  <p className="mt-3 text-sm font-medium">
                    Aucune vidéo enregistrée
                  </p>
                  <p className="mt-1 text-xs text-ink-500">
                    Importe un fichier pour commencer ton premier montage.
                  </p>
                  <Button
                    className="mt-5"
                    size="sm"
                    onClick={() => selectTab("upload")}
                  >
                    <Upload className="size-4" /> Importer une vidéo
                  </Button>
                </div>
              ) : (
                <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
                  {items.map((it) => (
                    <li
                      key={it.id}
                      className="group overflow-hidden rounded-2xl border border-white/10 bg-ink-900/55 transition hover:-translate-y-0.5 hover:border-white/20"
                    >
                      {it.thumb ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={it.thumb}
                          alt={`Aperçu de ${it.name}`}
                          className="aspect-[9/16] w-full object-cover"
                        />
                      ) : (
                        <div className="aspect-[9/16] bg-ink-700" />
                      )}
                      <div className="space-y-2 p-3">
                        <div className="line-clamp-2 text-xs font-medium">
                          {it.name}
                        </div>
                        <div className="text-[11px] text-ink-500">
                          {Math.round(it.duration)} s · {it.width}×{it.height}
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            className="flex-1"
                            onClick={() =>
                              router.push(
                                `/editor/${it.id}?file=${encodeURIComponent(
                                  it.serverPath || ""
                                )}`
                              )
                            }
                          >
                            Éditer
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => removeItem(it.id)}
                            aria-label={`Supprimer ${it.name}`}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className={tab === "youtube" ? "block" : "hidden"}>
            <div className="panel p-5 sm:p-7">
              <div className="mb-5 flex items-start gap-3">
                <span className="grid size-10 place-items-center rounded-xl bg-red-500/10 text-red-400">
                  <Youtube className="size-5" />
                </span>
                <div>
                  <h3 className="font-semibold">
                    Inspiration et import YouTube
                  </h3>
                  <p className="mt-1 text-sm text-ink-400">
                    Recherche des références par ambiance, puis importe une
                    source autorisée dans l’éditeur.
                  </p>
                </div>
              </div>
              <YoutubePanel onImported={onYoutubeImported} />
            </div>
          </section>
        </main>
      </div>

      {uploading && (
        <div className="fixed inset-x-0 bottom-0 z-50 p-3">
          <div className="mx-auto flex max-w-md items-center gap-2 rounded-2xl border border-white/10 bg-ink-700/95 px-4 py-3 text-sm shadow-2xl backdrop-blur">
            <Loader2 className="size-4 animate-spin" /> Import en cours…
          </div>
        </div>
      )}
    </div>
  );
}
