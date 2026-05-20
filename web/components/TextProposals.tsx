'use client';

import * as React from 'react';
import { Loader2, RefreshCw, Plus } from 'lucide-react';
import { Button } from './Button';

export function TextProposals({ onPick }: { onPick: (text: string) => void }) {
  const [mood, setMood] = React.useState('mélancolique');
  const [theme, setTheme] = React.useState('');
  const [items, setItems] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/ai/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mood, theme, count: 10 })
      });
      const j = await r.json();
      setItems(j.texts || []);
    } finally {
      setLoading(false);
    }
  }, [mood, theme]);

  React.useEffect(() => {
    load();
  }, []); // initial

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select
          value={mood}
          onChange={(e) => setMood(e.target.value)}
          className="h-9 bg-ink-700/80 border border-white/10 rounded-lg px-2 text-sm"
        >
          <option>mélancolique</option>
          <option>solitude</option>
          <option>rupture</option>
          <option>nostalgie</option>
          <option>fatigue émotionnelle</option>
          <option>philosophique doux</option>
        </select>
        <input
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          placeholder="thème optionnel (ex: pluie, ex copine…)"
          className="flex-1 h-9 bg-ink-700/80 border border-white/10 rounded-lg px-3 text-sm"
        />
        <Button onClick={load} size="sm" variant="ghost" aria-label="Régénérer">
          {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
        </Button>
      </div>
      <ul className="space-y-2">
        {items.map((t, i) => (
          <li key={i} className="rounded-xl bg-ink-700/60 border border-white/10 p-3 flex gap-3 items-start">
            <p className="flex-1 text-sm whitespace-pre-wrap font-serif italic text-ink-50">{t}</p>
            <button
              onClick={() => onPick(t)}
              className="shrink-0 size-9 rounded-lg bg-accent/90 text-white grid place-items-center hover:bg-accent"
              aria-label="Ajouter ce texte"
              title="Ajouter à la vidéo"
            >
              <Plus className="size-5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
