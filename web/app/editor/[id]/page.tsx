'use client';

import * as React from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import { Loader2, Save, UploadCloud, Download, ChevronLeft, Sparkles, Share2 } from 'lucide-react';
import { TopBar } from '@/components/TopBar';
import { Button } from '@/components/Button';
import { Preview, OverlayInspector } from '@/components/Preview';
import { TextProposals } from '@/components/TextProposals';
import { HashtagPanel } from '@/components/HashtagPanel';
import { MusicPicker } from '@/components/MusicPicker';
import { AccountPicker } from '@/components/AccountPicker';
import { getVideo } from '@/lib/db';
import type { OverlayBlock } from '@/lib/types';
import { randomId } from '@/lib/utils';

type Step = 'edit' | 'export';

export default function EditorPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const fileFromQuery = search.get('file') || '';

  const [src, setSrc] = React.useState<string | null>(null);
  const [serverFile, setServerFile] = React.useState<string>(fileFromQuery);
  const [overlays, setOverlays] = React.useState<OverlayBlock[]>([]);
  const [selectedId, setSelectedId] = React.useState<string | undefined>();
  const [hashtags, setHashtags] = React.useState<string[]>([]);
  const [music, setMusic] = React.useState<{ file?: string; random: boolean; volume: number; vibe?: string }>({
    file: undefined,
    random: true,
    volume: 0.55,
    vibe: 'triste'
  });
  const [account, setAccount] = React.useState<string | undefined>();
  const [extraCaption, setExtraCaption] = React.useState('');
  const [tiktokSound, setTiktokSound] = React.useState('');

  const [rendering, setRendering] = React.useState(false);
  const [renderResult, setRenderResult] = React.useState<{ filename: string; musicUsed: string | null } | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [uploadLog, setUploadLog] = React.useState<string | null>(null);
  const [step, setStep] = React.useState<Step>('edit');

  // Load video src from IndexedDB blob, fallback to server-served file
  React.useEffect(() => {
    let revoked = false;
    let url: string | null = null;
    (async () => {
      try {
        const rec = await getVideo(params.id);
        if (rec?.blob) {
          url = URL.createObjectURL(rec.blob);
          if (!revoked) setSrc(url);
          if (!serverFile && rec.serverPath) setServerFile(rec.serverPath);
        } else if (fileFromQuery) {
          setSrc(`/api/uploads/${encodeURIComponent(fileFromQuery)}`);
        }
      } catch (e) {
        console.error(e);
      }
    })();
    return () => {
      revoked = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [params.id, fileFromQuery, serverFile]);

  const selectedOverlay = overlays.find((o) => o.id === selectedId);

  function addOverlayFromProposal(text: string) {
    const ov: OverlayBlock = {
      id: randomId(),
      text,
      xPct: 50,
      yPct: 50,
      widthPct: 78,
      fontSize: 56,
      color: '#ffffff',
      align: 'center',
      fontFamily: 'serif',
      italic: true
    };
    setOverlays((prev) => [...prev, ov]);
    setSelectedId(ov.id);
  }

  async function doRender() {
    if (!serverFile) {
      alert('Fichier source manquant côté serveur — réimporte la vidéo.');
      return;
    }
    setRendering(true);
    setRenderResult(null);
    try {
      const r = await fetch('/api/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: serverFile,
          overlays,
          music: { file: music.file, random: music.random, volume: music.volume, vibe: music.vibe },
          duckOriginal: 0.35
        })
      });
      const j = await r.json();
      if (!j.ok) {
        alert('Rendu échoué : ' + (j.error || ''));
        console.error(j.stderr);
        return;
      }
      setRenderResult({ filename: j.filename, musicUsed: j.musicUsed });
      setStep('export');
    } finally {
      setRendering(false);
    }
  }

  function buildCaption() {
    const overlayTexts = overlays.map((o) => o.text).join(' / ');
    return [overlayTexts, extraCaption, hashtags.join(' ')].filter(Boolean).join(' ').slice(0, 2000);
  }

  async function doUpload() {
    if (!renderResult) return;
    if (!account) {
      alert('Choisis un compte TikTok.');
      return;
    }
    setUploading(true);
    setUploadLog(null);
    try {
      const r = await fetch('/api/tiktok/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: renderResult.filename,
          username: account,
          caption: buildCaption(),
          musicId: tiktokSound.trim() || undefined
        })
      });
      const j = await r.json();
      setUploadLog(j.ok ? '✅ Uploadé sur @' + account : '❌ ' + (j.error || j.stderr || 'échec'));
    } finally {
      setUploading(false);
    }
  }

  async function doShare() {
    if (!renderResult) return;
    setUploading(true);
    setUploadLog(null);
    try {
      const resp = await fetch(`/api/renders/${renderResult.filename}`);
      const blob = await resp.blob();
      const file = new File([blob], renderResult.filename, { type: 'video/mp4' });
      const caption = buildCaption();
      const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean; share?: (d: ShareData) => Promise<void> };
      if (nav.canShare?.({ files: [file] })) {
        await nav.share!({ files: [file], text: caption });
        setUploadLog('✅ Partage ouvert — choisis TikTok dans la share sheet, ajoute le texte et publie.');
      } else if (nav.share) {
        await nav.share({ text: caption, url: window.location.origin + `/api/renders/${renderResult.filename}` });
        setUploadLog('⚠️ Ce navigateur ne sait pas partager un fichier vidéo directement — j’ai partagé le lien. Sinon utilise « Télécharger ».');
      } else {
        // Fallback: just trigger a download so user can pick TikTok from the camera roll
        const a = document.createElement('a');
        a.href = `/api/renders/${renderResult.filename}`;
        a.download = renderResult.filename;
        a.click();
        setUploadLog('Pas de Web Share API ici — la vidéo est téléchargée. Ouvre TikTok et choisis-la depuis ta galerie.');
      }
    } catch (e) {
      setUploadLog('❌ Partage annulé ou échoué : ' + String(e));
    } finally {
      setUploading(false);
    }
  }

  const sourceTextForHashtags = overlays.map((o) => o.text).join('\n');

  return (
    <div className="min-h-dvh pb-32">
      <TopBar subtitle={step === 'edit' ? 'éditeur' : 'export'} />
      <main className="mx-auto max-w-3xl px-4 pt-4 space-y-4">
        <button onClick={() => router.push('/')} className="text-ink-200 text-sm inline-flex items-center gap-1 hover:text-white">
          <ChevronLeft className="size-4" /> Bibliothèque
        </button>

        {!src && (
          <div className="rounded-2xl border border-white/10 p-6 text-center text-ink-400 text-sm">
            <Loader2 className="size-5 animate-spin inline mr-2" /> Chargement de la vidéo…
          </div>
        )}

        {src && step === 'edit' && (
          <div className="grid grid-cols-1 md:grid-cols-[1fr_22rem] gap-4">
            <div className="space-y-3">
              <Preview src={src} overlays={overlays} setOverlays={setOverlays} selectedId={selectedId} setSelectedId={setSelectedId} />
              {selectedOverlay && (
                <OverlayInspector
                  overlay={selectedOverlay}
                  onChange={(next) => setOverlays(overlays.map((o) => (o.id === next.id ? next : o)))}
                  onDelete={() => {
                    setOverlays(overlays.filter((o) => o.id !== selectedOverlay.id));
                    setSelectedId(undefined);
                  }}
                />
              )}
            </div>

            <aside className="space-y-4">
              <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3 space-y-2">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  <Sparkles className="size-4 text-accent" /> Propositions de texte
                </h3>
                <TextProposals onPick={addOverlayFromProposal} />
              </section>

              <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3">
                <MusicPicker value={music} onChange={setMusic} />
              </section>

              <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3">
                <HashtagPanel sourceText={sourceTextForHashtags} value={hashtags} onChange={setHashtags} />
              </section>
            </aside>
          </div>
        )}

        {src && step === 'export' && renderResult && (
          <div className="space-y-4">
            <div className="rounded-2xl overflow-hidden border border-white/10 bg-black">
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                src={`/api/renders/${renderResult.filename}`}
                controls
                playsInline
                className="w-full aspect-[9/16] object-contain bg-black"
              />
            </div>
            {renderResult.musicUsed && <p className="text-xs text-ink-400">Musique : {renderResult.musicUsed}</p>}

            <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3 space-y-3">
              <AccountPicker value={account} onChange={setAccount} />
              <label className="text-xs text-ink-400 space-y-1 block">
                <span>Légende additionnelle (optionnel)</span>
                <textarea
                  value={extraCaption}
                  onChange={(e) => setExtraCaption(e.target.value)}
                  rows={2}
                  className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
                  placeholder="ex: pense à liker si tu te reconnais 🤍"
                />
              </label>
              <label className="text-xs text-ink-400 space-y-1 block">
                <span>Son TikTok (optionnel — ID ou URL .../music/Foo-1234)</span>
                <input
                  value={tiktokSound}
                  onChange={(e) => setTiktokSound(e.target.value)}
                  className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
                  placeholder="https://www.tiktok.com/music/…  ou  7641581184534711600"
                />
                <span className="block text-[10px] text-ink-500">
                  Ajoute la vidéo au compteur du son (icône disque tournant). Best-effort — TikTok peut refuser un son non-autorisé.
                </span>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button onClick={doShare} disabled={uploading}>
                  {uploading ? <Loader2 className="size-4 animate-spin" /> : <Share2 className="size-4" />}
                  Partager → TikTok
                </Button>
                <Button variant="outline" onClick={doUpload} disabled={uploading || !account}>
                  {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                  Publier auto (cookies)
                </Button>
                <a
                  className="inline-flex items-center gap-2 px-4 h-11 rounded-xl bg-white/5 hover:bg-white/10 text-sm"
                  href={`/api/renders/${renderResult.filename}`}
                  download
                >
                  <Download className="size-4" /> Télécharger
                </a>
                <Button variant="ghost" onClick={() => setStep('edit')}>Retour à l’édition</Button>
              </div>
              <p className="text-[11px] text-ink-400">
                « Partager → TikTok » ouvre la share sheet de ton téléphone et envoie la vidéo dans l’app TikTok (recommandé). « Publier auto » utilise les cookies enregistrés côté serveur (compte sélectionné).
              </p>
              {uploadLog && <p className="text-sm text-ink-200 whitespace-pre-wrap">{uploadLog}</p>}
            </section>
          </div>
        )}
      </main>

      {/* Sticky action bar */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-ink-900/95 backdrop-blur">
        <div className="mx-auto max-w-3xl px-4 py-3 flex items-center gap-3">
          {step === 'edit' ? (
            <>
              <div className="text-xs text-ink-400 flex-1">
                {overlays.length} texte(s) · musique : {music.random ? `aléatoire ${music.vibe ? `(${music.vibe})` : ''}` : 'choisie'}
              </div>
              <Button onClick={doRender} disabled={rendering || !serverFile}>
                {rendering ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} Générer
              </Button>
            </>
          ) : (
            <>
              <div className="text-xs text-ink-400 flex-1">Prêt à publier</div>
              <Button variant="ghost" onClick={() => setStep('edit')}>Retour</Button>
              <Button onClick={doShare} disabled={uploading}>
                {uploading ? <Loader2 className="size-4 animate-spin" /> : <Share2 className="size-4" />} Partager
              </Button>
              <Button variant="outline" onClick={doUpload} disabled={uploading || !account}>
                {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />} Publier
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
