'use client';

import * as React from 'react';
import { Loader2, RefreshCw, Copy, Check } from 'lucide-react';
import { Button } from './Button';

export function HashtagPanel({ sourceText, value, onChange }: { sourceText: string; value: string[]; onChange: (v: string[]) => void }) {
  const [pool, setPool] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/ai/hashtags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sourceText, count: 20 })
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
    const txt = value.join(' ');
    navigator.clipboard.writeText(txt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Hashtags</h3>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={load}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />} régénérer
          </Button>
          <Button size="sm" variant="ghost" onClick={copyAll} disabled={!value.length}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />} {copied ? 'copié' : 'copier'}
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {pool.map((tag) => {
          const active = value.includes(tag);
          return (
            <button
              key={tag}
              onClick={() => toggle(tag)}
              className={`text-xs h-7 px-3 rounded-full border transition ${
                active ? 'bg-accent text-white border-accent' : 'border-white/15 text-ink-200 hover:bg-white/5'
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
