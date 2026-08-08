'use client';

import * as React from 'react';
import { Check, Loader2, Plus, Users } from 'lucide-react';
import { Button } from './Button';
import type { TiktokAccount } from '@/lib/types';

export function TikTokTargetPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (usernames: string[]) => void;
}) {
  const [accounts, setAccounts] = React.useState<TiktokAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [adding, setAdding] = React.useState(false);
  const [newName, setNewName] = React.useState('');
  const [note, setNote] = React.useState<string | null>(null);

  async function load(selection = value) {
    setLoading(true);
    try {
      const response = await fetch('/api/tiktok/accounts');
      const data = await response.json();
      const next = (data.accounts || []) as TiktokAccount[];
      setAccounts(next);
      setNote(data.note || null);
      onChange(selection.filter((username) => next.some((account) => account.username === username)));
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    fetch('/api/tiktok/accounts')
      .then((response) => response.json())
      .then((data) => {
        const next = (data.accounts || []) as TiktokAccount[];
        setAccounts(next);
        setNote(data.note || null);
      })
      .finally(() => setLoading(false));
    // Initial account discovery only; later refreshes are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(username: string) {
    onChange(value.includes(username) ? value.filter((item) => item !== username) : [...value, username]);
  }

  async function add() {
    const username = newName.trim();
    if (!username) return;
    setAdding(true);
    try {
      const response = await fetch('/api/tiktok/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username }),
      });
      const data = await response.json();
      if (!data.ok) {
        setNote(data.error || data.stderr || 'The TikTok login could not be started.');
        return;
      }
      setNewName('');
      const selection = [...new Set([...value, username])];
      onChange(selection);
      await load(selection);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium"><Users className="size-4" /> TikTok targets</h3>
        {accounts.length > 1 && (
          <button type="button" onClick={() => onChange(value.length === accounts.length ? [] : accounts.map((account) => account.username))} className="text-[11px] text-cyan-300 hover:text-cyan-200">
            {value.length === accounts.length ? 'Clear all' : 'Select all'}
          </button>
        )}
      </div>

      {loading ? (
        <p className="flex items-center gap-2 py-2 text-sm text-ink-400"><Loader2 className="size-4 animate-spin" /> Loading accounts…</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {accounts.map((account) => {
            const selected = value.includes(account.username);
            return (
              <button
                key={account.username}
                type="button"
                onClick={() => toggle(account.username)}
                className={`inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-sm transition ${selected ? 'border-accent bg-accent text-white' : 'border-white/15 text-ink-200 hover:bg-white/5'}`}
              >
                {selected && <Check className="size-3.5" />} @{account.username}
              </button>
            );
          })}
          {!accounts.length && <p className="text-xs text-ink-400">No connected TikTok account.</p>}
        </div>
      )}

      <details className="rounded-lg border border-white/10 bg-ink-700/40 p-2 open:bg-ink-700/60">
        <summary className="cursor-pointer text-sm text-ink-200">Connect another account</summary>
        <div className="flex gap-2 pt-2">
          <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="TikTok username" className="h-9 min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-800 px-3 text-sm" />
          <Button size="sm" onClick={add} disabled={adding || !newName.trim()}>
            {adding ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Connect
          </Button>
        </div>
        <p className="mt-2 text-[11px] text-ink-400">Targets are saved per game. Uploads run one account at a time and report a separate result for every target.</p>
        {note && <p className="mt-1 text-[11px] text-amber-300">{note}</p>}
      </details>
    </div>
  );
}
