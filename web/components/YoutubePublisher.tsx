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

type YouTubeAccount = {
  id: string;
  label: string;
  configured: boolean;
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
  const [accounts, setAccounts] = React.useState<YouTubeAccount[]>([]);
  const [account, setAccount] = React.useState('default');
  const [title, setTitle] = React.useState(defaultTitle.slice(0, 100));
  const [privacy, setPrivacy] = React.useState<'private' | 'unlisted'>('private');
  const [adminToken, setAdminToken] = React.useState('');
  const [uploading, setUploading] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [releaseUrl, setReleaseUrl] = React.useState<string | null>(null);

  React.useEffect(() => {
    const saved = window.sessionStorage.getItem('clipmaker-upload-token');
    if (saved) setAdminToken(saved);
    fetch('/api/youtube/accounts')
      .then((response) => response.json())
      .then((data) => setAccounts(data.accounts || []))
      .catch(() => setAccounts([{ id: 'default', label: 'Default channel', configured: false }]));
  }, []);

  React.useEffect(() => {
    setStatus(null);
    fetch(`/api/youtube/status?account=${encodeURIComponent(account)}`)
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
  }, [account]);

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
          privacy,
          account
        })
      });
      const data = await response.json();
      if (!data.ok) {
        setMessage(`Upload failed: ${data.error || 'YouTube rejected the upload'}`);
        return;
      }
      if (data.dryRun) {
        setMessage(`Dry run passed · ${Math.round(data.media.duration)} s · ${data.media.width}×${data.media.height} · nothing was uploaded`);
      } else {
        setMessage(`Short uploaded to ${account} as ${privacy}`);
        if (data.upload?.releaseUrl) setReleaseUrl(data.upload.releaseUrl);
      }
    } catch (error) {
      setMessage(`Upload failed: ${String(error)}`);
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
          {status ? (liveMode ? 'live upload' : 'dry run') : 'checking...'}
        </span>
      </div>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>YouTube channel profile</span>
        <select value={account} onChange={(event) => setAccount(event.target.value)} className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm">
          {(accounts.length ? accounts : [{ id: 'default', label: 'Default channel', configured: false }]).map((item) => (
            <option key={item.id} value={item.id}>{item.label}{item.configured ? '' : ' — login required'}</option>
          ))}
        </select>
        <span className="block text-[10px] text-ink-500">Create another profile with <code>node scripts/youtube-agent.mjs auth --account channel-name</code>.</span>
      </label>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Title</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value.slice(0, 100))}
          className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
          placeholder="Short title"
        />
        <span className="block text-[10px] text-ink-500">{title.length}/100 characters</span>
      </label>

      <label className="text-xs text-ink-400 space-y-1 block">
        <span>Initial visibility</span>
        <select
          value={privacy}
          onChange={(event) => setPrivacy(event.target.value as 'private' | 'unlisted')}
          className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
        >
          <option value="private">Private — recommended for review</option>
          <option value="unlisted">Unlisted</option>
        </select>
      </label>

      {liveMode && (
        <label className="text-xs text-ink-400 space-y-1 block">
          <span>ClipMaker admin token</span>
          <input
            type="password"
            value={adminToken}
            onChange={(event) => updateAdminToken(event.target.value)}
            className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm"
            autoComplete="off"
          />
        </label>
      )}

      {status && !status.ok && <p className="text-xs text-red-300">{status.error || 'YouTube uploader unavailable'}</p>}
      {liveMode && !status.readyForLiveUpload && (
        <p className="text-xs text-amber-300">The YouTube session is missing or expired. Run <code>npm run youtube:auth</code> in <code>web/</code>, then sign in through the Chrome window.</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={upload} disabled={disabled}>
          {uploading ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
          {liveMode ? 'Upload to YouTube' : 'Test YouTube upload'}
        </Button>
        {releaseUrl && (
          <a href={releaseUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-ink-200 hover:text-white">
            View video <ExternalLink className="size-3" />
          </a>
        )}
      </div>

      <p className="text-[11px] text-ink-400">
        A dry run validates the file without publishing it. In live mode, ClipMaker only reuses the local Chrome session; it never stores a Google password. Public uploads remain disabled.
      </p>
      {message && <p className="text-sm text-ink-200 whitespace-pre-wrap">{message}</p>}
    </section>
  );
}
