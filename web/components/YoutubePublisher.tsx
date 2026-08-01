'use client';

import * as React from 'react';
import { ExternalLink, Loader2, ShieldCheck, Youtube } from 'lucide-react';
import { Button } from './Button';

type Status = {
  ok: boolean;
  dryRun: boolean;
  readyForLiveUpload: boolean;
  configured: {
    browser: 'configured' | 'missing';
    cookies: 'configured' | 'missing';
    authenticated: 'configured' | 'missing';
    package: 'configured' | 'missing';
  };
  error?: string;
};

export function YoutubePublisher({
  filename,
  defaultTitle,
  description,
  tags
}: {
  filename: string;
  defaultTitle: string;
  description: string;
  tags: string[];
}) {
  const [status, setStatus] = React.useState<Status | null>(null);
  const [title, setTitle] = React.useState(defaultTitle.slice(0, 100));
  const [privacy, setPrivacy] = React.useState<'private' | 'unlisted'>('private');
  const [adminToken, setAdminToken] = React.useState('');
  const [uploading, setUploading] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [releaseUrl, setReleaseUrl] = React.useState<string | null>(null);

  React.useEffect(() => {
    const saved = window.sessionStorage.getItem('clipmaker-upload-token');
    if (saved) setAdminToken(saved);
    fetch('/api/youtube/status')
      .then((response) => response.json())
      .then(setStatus)
      .catch((error) => setStatus({
        ok: false,
        dryRun: true,
        readyForLiveUpload: false,
        configured: {
          browser: 'missing',
          cookies: 'missing',
          authenticated: 'missing',
          package: 'missing'
        },
        error: String(error)
      }));
  }, []);

  function updateAdminToken(value: string) {
    setAdminToken(value);
    if (value) window.sessionStorage.setItem('clipmaker-upload-token', value);
    else window.sessionStorage.removeItem('clipmaker-upload-token');
  }

  async function upload() {
    if (!title.trim()) return;
    setUploading(true);
    setMessage(null);
    setReleaseUrl(null);
    try {
      const response = await fetch('/api/youtube/upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(adminToken ? { 'x-clipmaker-upload-token': adminToken } : {})
        },
        body: JSON.stringify({
          filename,
          title: title.trim(),
          description,
          tags,
          privacy
        })
      });
      const data = await response.json();
      if (!data.ok) {
        setMessage(`❌ ${data.error || 'Échec de l’envoi YouTube'}`);
        return;
      }
      if (data.dryRun) {
        setMessage(`✅ Simulation validée · ${Math.round(data.media.duration)} s · ${data.media.width}×${data.media.height} · aucun upload effectué`);
      } else {
        setMessage(`✅ Short envoyé sur YouTube en mode ${privacy}`);
        if (data.upload?.releaseUrl) setReleaseUrl(data.upload.releaseUrl);
      }
    } catch (error) {
      setMessage(`❌ ${String(error)}`);
    } finally {
      setUploading(false);
    }
  }

  const liveMode = status?.ok && !status.dryRun;
  const disabled = uploading || !title.trim() || !status?.ok || Boolean(liveMode && !status.readyForLiveUpload);

  return (
    <section className="rounded-xl bg-ink-700/40 border border-white/10 p-3 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <Youtube className="size-4 text-red-500" /> YouTube Shorts
        </h3>
        <span className={`text-[11px] rounded-full px-2 py-1 ${liveMode ? 'bg-red-500/15 text-red-200' : 'bg-emerald-500/15 text-emerald-200'}`}>
          {status ? (liveMode ? 'upload réel' : 'simulation') : 'vérification…'}
        </span>
      </div>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Titre</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value.slice(0, 100))}
          className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
          placeholder="Titre du Short"
        />
        <span className="block text-[10px] text-ink-500">{title.length}/100 caractères</span>
      </label>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Visibilité initiale</span>
        <select
          value={privacy}
          onChange={(event) => setPrivacy(event.target.value as 'private' | 'unlisted')}
          className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
        >
          <option value="private">Privée — recommandée pour vérifier</option>
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
            className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
            autoComplete="off"
          />
        </label>
      )}

      {status && !status.ok && <p className="text-xs text-red-300">{status.error || 'Uploader YouTube indisponible'}</p>}
      {liveMode && !status.readyForLiveUpload && (
        <p className="text-xs text-amber-300">Session YouTube absente ou expirée. Lance <code>npm run youtube:auth</code> dans <code>web/</code>, puis connecte-toi dans la fenêtre Chrome.</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={upload} disabled={disabled}>
          {uploading ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
          {liveMode ? 'Envoyer sur YouTube' : 'Tester l’envoi YouTube'}
        </Button>
        {releaseUrl && (
          <a href={releaseUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-ink-200 hover:text-white">
            Voir la vidéo <ExternalLink className="size-3" />
          </a>
        )}
      </div>

      <p className="text-[11px] text-ink-400">
        La simulation valide le fichier sans publier. En mode réel, ClipMaker réutilise uniquement la session Chrome locale; aucun mot de passe Google n’est stocké. Les publications publiques restent désactivées.
      </p>
      {message && <p className="text-sm text-ink-200 whitespace-pre-wrap">{message}</p>}
    </section>
  );
}
