"use client";

import * as React from "react";
import { Loader2, RefreshCw, Copy, Check } from "lucide-react";
import { Button } from "./Button";

export function HashtagPanel({
  sourceText,
  value,
  onChange,
}: {
  sourceText: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const [pool, setPool] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ai/hashtags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sourceText, count: 20 }),
      });
      const j = await r.json();
      setPool(j.hashtags || []);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(tag: string) {
    if (value.includes(tag)) onChange(value.filter((t) => t !== tag));
    else onChange([...value, tag]);
  }

  function copyAll() {
    const txt = value.join(" ");
    navigator.clipboard.writeText(txt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">Hashtags</h3>
          <p className="mt-0.5 text-[11px] text-ink-500">
            Sélectionne ceux à ajouter à la légende.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={load}>
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}{" "}
            Régénérer
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={copyAll}
            disabled={!value.length}
          >
            {copied ? (
              <Check className="size-4" />
            ) : (
              <Copy className="size-4" />
            )}{" "}
            {copied ? "Copié" : "Copier"}
          </Button>
        </div>
      </div>
      <div className="flex min-h-8 flex-wrap gap-2" aria-live="polite">
        {loading && pool.length === 0 && (
          <p className="text-xs text-ink-400">Génération des hashtags…</p>
        )}
        {pool.map((tag) => {
          const active = value.includes(tag);
          return (
            <button
              key={tag}
              onClick={() => toggle(tag)}
              aria-pressed={active}
              className={`h-8 rounded-full border px-3 text-xs font-medium transition ${
                active
                  ? "border-accent bg-accent text-white shadow-sm shadow-accent/20"
                  : "border-white/15 bg-black/10 text-ink-200 hover:border-white/25 hover:bg-white/5"
              }`}
            >
              {tag}
            </button>
          );
        })}
      </div>
    </div>
  );
}
