"use client";

import * as React from "react";
import { UploadCloud, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Dropzone({
  onFile,
  busy,
}: {
  onFile: (file: File) => void;
  busy?: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const inputId = React.useId();
  const [drag, setDrag] = React.useState(false);

  function openPicker() {
    if (!busy) inputRef.current?.click();
  }

  return (
    <div
      className={cn(
        "panel border-2 border-dashed border-white/15 p-6 text-center transition sm:p-10",
        drag && "border-accent bg-accent/5",
        busy && "opacity-70 pointer-events-none"
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
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openPicker();
        }
      }}
      role="button"
      tabIndex={busy ? -1 : 0}
      aria-disabled={busy}
      aria-busy={busy}
      aria-label={
        busy ? "Import de la vidéo en cours" : "Choisir une vidéo à importer"
      }
    >
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept="video/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.currentTarget.value = "";
        }}
      />
      <div className="flex flex-col items-center gap-2 py-4">
        {busy ? (
          <Loader2
            className="size-8 animate-spin text-accent"
            aria-hidden="true"
          />
        ) : (
          <UploadCloud className="size-8 text-accent" aria-hidden="true" />
        )}
        <div className="font-semibold">
          {busy ? "Import en cours…" : "Dépose une vidéo ici"}
        </div>
        <div className="text-sm text-ink-300">
          ou appuie pour parcourir tes fichiers
        </div>
        <div className="mt-1 text-xs text-ink-500">
          MP4, MOV ou WebM · téléphone et ordinateur
        </div>
      </div>
    </div>
  );
}
