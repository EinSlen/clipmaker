'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Library, Youtube, Trash2, Loader2, Wand2 } from 'lucide-react';
import { TopBar } from '@/components/TopBar';
import { Dropzone } from '@/components/Dropzone';
import { YoutubePanel } from '@/components/YoutubePanel';
import { Button } from '@/components/Button';
import { listVideos, putVideo, deleteVideo, probeVideo } from '@/lib/db';
import { randomId } from '@/lib/utils';
import type { LibraryVideo } from '@/lib/types';

type Tab = 'upload' | 'library' | 'youtube';

export default function Home() {
  const router = useRouter();
  const [tab, setTab] = React.useState<Tab>('upload');
  const [items, setItems] = React.useState<LibraryVideo[]>([]);
  const [uploading, setUploading] = React.useState(false);

  React.useEffect(() => {
    listVideos().then(setItems);
  }, []);

  async function handleFile(file: File) {
    setUploading(true);
    try {
      // Probe metadata locally
      const meta = await probeVideo(file);
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/upload', { method: 'POST', body: fd });
      const j = await r.json();
      if (!j.ok) {
        alert('Upload échoué');
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
        blob: file
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

  async function onYoutubeImported(info: { id: string; filename: string; size: number; title: string }) {
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
        blob
      };
      await putVideo(rec);
      const next = await listVideos();
      setItems(next);
      router.push(`/editor/${rec.id}?file=${encodeURIComponent(info.filename)}`);
    } catch (e) {
      console.error(e);
      alert('Import YouTube OK côté serveur mais impossible de précharger localement.');
    }
  }

  async function removeItem(id: string) {
    if (!confirm('Supprimer cette vidéo de la bibliothèque ?')) return;
    await deleteVideo(id);
    setItems(await listVideos());
  }

  return (
    <div className="min-h-dvh">
      <TopBar />
      <main className="mx-auto max-w-3xl px-4 pb-32 pt-4 space-y-4">
        <section className="rounded-2xl bg-gradient-to-br from-accent/15 via-accent/5 to-transparent border border-white/10 p-4">
          <div className="flex items-start gap-3">
            <Wand2 className="size-5 text-accent mt-1" />
            <div>
              <h1 className="text-lg font-semibold leading-tight">Studio sad/philo TikTok</h1>
              <p className="text-ink-400 text-sm">
                Importe une vidéo, ajoute du texte mélancolique, choisis ta musique triste, et publie sur TikTok depuis un de tes comptes.
              </p>
            </div>
          </div>
        </section>

        <nav className="grid grid-cols-3 gap-2 sticky top-14 z-20 bg-ink-900/85 backdrop-blur -mx-4 px-4 py-2 border-b border-white/5">
          {([
            { id: 'upload', label: 'Importer', Icon: Wand2 },
            { id: 'library', label: 'Bibliothèque', Icon: Library },
            { id: 'youtube', label: 'YouTube', Icon: Youtube }
          ] as const).map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`h-10 rounded-xl text-sm font-medium flex items-center justify-center gap-2 border transition ${
                tab === id ? 'bg-accent text-white border-accent' : 'border-white/10 text-ink-200 hover:bg-white/5'
              }`}
            >
              <Icon className="size-4" /> {label}
            </button>
          ))}
        </nav>

        {tab === 'upload' && <Dropzone onFile={handleFile} busy={uploading} />}

        {tab === 'library' && (
          <div className="space-y-2">
            {items.length === 0 && <p className="text-ink-400 text-sm">Aucune vidéo enregistrée. Importes-en une pour commencer.</p>}
            <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {items.map((it) => (
                <li key={it.id} className="rounded-xl overflow-hidden border border-white/10 bg-ink-800/70 flex flex-col">
                  {it.thumb ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={it.thumb} alt="" className="aspect-[9/16] object-cover w-full" />
                  ) : (
                    <div className="aspect-[9/16] bg-ink-700" />
                  )}
                  <div className="p-2 space-y-1">
                    <div className="text-xs line-clamp-2">{it.name}</div>
                    <div className="text-[11px] text-ink-400">{Math.round(it.duration)}s · {it.width}×{it.height}</div>
                    <div className="flex gap-2 mt-1">
                      <Button size="sm" className="flex-1" onClick={() => router.push(`/editor/${it.id}?file=${encodeURIComponent(it.serverPath || '')}`)}>
                        Éditer
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => removeItem(it.id)} aria-label="Supprimer">
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === 'youtube' && <YoutubePanel onImported={onYoutubeImported} />}
      </main>

      {uploading && (
        <div className="fixed inset-x-0 bottom-0 z-40 p-3">
          <div className="mx-auto max-w-3xl rounded-xl bg-ink-700/90 border border-white/10 text-sm px-4 py-3 flex items-center gap-2">
            <Loader2 className="size-4 animate-spin" /> Import en cours…
          </div>
        </div>
      )}
    </div>
  );
}
