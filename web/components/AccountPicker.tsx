'use client';

import * as React from 'react';
import { Loader2, Plus, User } from 'lucide-react';
import { Button } from './Button';
import type { TiktokAccount } from '@/lib/types';

export function AccountPicker({
  value,
  onChange
}: {
  value?: string;
  onChange: (username: string | undefined) => void;
}) {
  const [accounts, setAccounts] = React.useState<TiktokAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [adding, setAdding] = React.useState(false);
  const [newName, setNewName] = React.useState('');
  const [note, setNote] = React.useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch('/api/tiktok/accounts');
      const j = await r.json();
      setAccounts(j.accounts || []);
      setNote(j.note || null);
      if (!value && j.accounts?.[0]) onChange(j.accounts[0].username);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function add() {
    const username = newName.trim();
    if (!username) return;
    setAdding(true);
    try {
      const r = await fetch('/api/tiktok/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username })
      });
      const j = await r.json();
      if (!j.ok) alert("Échec de l'ajout : " + (j.error || j.stderr || ''));
      else {
        setNewName('');
        onChange(username);
        await load();
      }
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <User className="size-4" /> Compte TikTok
        </h3>
      </div>

      {loading ? (
        <div className="py-2 flex items-center gap-2 text-ink-400 text-sm">
          <Loader2 className="size-4 animate-spin" /> Chargement…
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {accounts.map((a) => (
              <button
                key={a.username}
                onClick={() => onChange(a.username)}
                className={`px-3 h-9 rounded-full text-sm border transition ${
                  value === a.username ? 'bg-accent text-white border-accent' : 'border-white/15 text-ink-200 hover:bg-white/5'
                }`}
              >
                @{a.username}
              </button>
            ))}
            {accounts.length === 0 && <p className="text-ink-400 text-xs">Aucun compte connecté.</p>}
          </div>

          <details className="rounded-lg border border-white/10 bg-ink-700/40 p-2 open:bg-ink-700/60">
            <summary className="text-sm cursor-pointer text-ink-200">Ajouter un compte</summary>
            <div className="pt-2 flex gap-2">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="username TikTok"
                className="flex-1 h-9 bg-ink-800 border border-white/10 rounded-lg px-3 text-sm"
              />
              <Button size="sm" onClick={add} disabled={adding || !newName.trim()}>
                {adding ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                connecter
              </Button>
            </div>
            <p className="text-[11px] text-ink-400 mt-2">
              Lance la commande côté serveur : une fenêtre Chrome s’ouvre, tu te connectes à TikTok manuellement, le cookie est sauvegardé.
              Sur téléphone, fais-le une fois depuis l’ordi puis utilise l’app librement.
            </p>
            {note && <p className="text-[11px] text-amber-300 mt-1">{note}</p>}
          </details>
        </>
      )}
    </div>
  );
}
