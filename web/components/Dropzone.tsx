'use client';

import * as React from 'react';
import { UploadCloud, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Dropzone({
  onFile,
  busy
}: {
  onFile: (file: File) => void;
  busy?: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [drag, setDrag] = React.useState(false);

  return (
    <div
      className={cn(
        'rounded-2xl border-2 border-dashed border-white/15 p-6 text-center transition',
        drag && 'border-accent bg-accent/5',
        busy && 'opacity-70 pointer-events-none'
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.currentTarget.value = '';
        }}
      />
      <div className="flex flex-col items-center gap-2 py-4">
        {busy ? <Loader2 className="size-7 animate-spin text-accent" /> : <UploadCloud className="size-7 text-accent" />}
        <div className="font-medium">{busy ? 'Import en cours…' : 'Dépose une vidéo ou clique'}</div>
        <div className="text-ink-400 text-sm">mp4, mov, webm — depuis ton tel ou ton ordi</div>
      </div>
    </div>
  );
}
