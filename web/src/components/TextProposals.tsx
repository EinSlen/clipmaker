"use client";

import * as React from "react";
import { Loader2, RefreshCw, Plus } from "lucide-react";
import { Button } from "./Button";

export function TextProposals({ onPick }: { onPick: (text: string) => void }) {
  const [mood, setMood] = React.useState("mélancolique");
  const [theme, setTheme] = React.useState("");
  const [items, setItems] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ai/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood, theme, count: 10 }),
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
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
        <select
          value={mood}
          onChange={(e) => setMood(e.target.value)}
          aria-label="Ambiance du texte"
          className="field-control h-10"
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
          placeholder="Thème facultatif : pluie, rupture…"
          aria-label="Thème facultatif"
          className="field-control h-10"
        />
        <Button
          onClick={load}
          size="sm"
          variant="ghost"
          className="h-10"
          aria-label="Régénérer les propositions"
        >
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
        </Button>
      </div>
      {loading && items.length === 0 && (
        <p
          className="flex items-center gap-2 py-3 text-sm text-ink-400"
          aria-live="polite"
        >
          <Loader2 className="size-4 animate-spin" /> Préparation des
          propositions…
        </p>
      )}
      <ul className="space-y-2" aria-live="polite">
        {items.map((t, i) => (
          <li
            key={i}
            className="subpanel flex items-start gap-3 p-3 transition hover:border-white/20 hover:bg-white/[0.04]"
          >
            <p className="flex-1 whitespace-pre-wrap font-serif text-sm italic leading-5 text-ink-50">
              {t}
            </p>
            <button
              onClick={() => onPick(t)}
              className="grid size-9 shrink-0 place-items-center rounded-xl border border-accent/50 bg-accent/90 text-white shadow-lg shadow-accent/15 transition hover:-translate-y-0.5 hover:bg-accent"
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
