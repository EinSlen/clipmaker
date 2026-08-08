"use client";

import * as React from "react";
import { Trash2, Pencil, Plus, Type } from "lucide-react";
import type { OverlayBlock } from "@/lib/types";
import { clamp, randomId } from "@/lib/utils";

type Props = {
  src: string;
  overlays: OverlayBlock[];
  setOverlays: (next: OverlayBlock[]) => void;
  selectedId?: string;
  setSelectedId: (id?: string) => void;
};

export function Preview({
  src,
  overlays,
  setOverlays,
  selectedId,
  setSelectedId,
}: Props) {
  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const dragRef = React.useRef<{
    id: string;
    startX: number;
    startY: number;
    baseX: number;
    baseY: number;
  } | null>(null);

  function onPointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation();
    setSelectedId(id);
    const ov = overlays.find((o) => o.id === id);
    if (!ov) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = {
      id,
      startX: e.clientX,
      startY: e.clientY,
      baseX: ov.xPct,
      baseY: ov.yPct,
    };
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!dragRef.current || !wrapperRef.current) return;
    const rect = wrapperRef.current.getBoundingClientRect();
    const dxPct = ((e.clientX - dragRef.current.startX) / rect.width) * 100;
    const dyPct = ((e.clientY - dragRef.current.startY) / rect.height) * 100;
    setOverlays(
      overlays.map((o) =>
        o.id === dragRef.current!.id
          ? {
              ...o,
              xPct: clamp(dragRef.current!.baseX + dxPct, 0, 100),
              yPct: clamp(dragRef.current!.baseY + dyPct, 0, 100),
            }
          : o
      )
    );
  }

  function onPointerUp(e: React.PointerEvent) {
    try {
      (e.target as Element).releasePointerCapture(e.pointerId);
    } catch {}
    dragRef.current = null;
  }

  function addEmptyOverlay() {
    const ov: OverlayBlock = {
      id: randomId(),
      text: "Touche pour écrire…",
      xPct: 50,
      yPct: 50,
      widthPct: 80,
      fontSize: 56,
      color: "#ffffff",
      align: "center",
      fontFamily: "serif",
      italic: true,
    };
    setOverlays([...overlays, ov]);
    setSelectedId(ov.id);
  }

  return (
    <section className="panel space-y-3 p-3 sm:p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-xl bg-accent/10 text-accent">
            <Type className="size-4" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-white">
              Aperçu de la vidéo
            </h2>
            <p className="text-[11px] text-ink-500">
              Déplace les textes directement sur l’image.
            </p>
          </div>
        </div>
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-semibold tracking-wide text-ink-300">
          9:16
        </span>
      </div>
      <div
        ref={wrapperRef}
        className="relative mx-auto overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl shadow-black/40"
        style={{
          aspectRatio: "9 / 16",
          width: "min(100%, 42.75dvh)",
          maxWidth: "32rem",
          touchAction: "none",
        }}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={() => setSelectedId(undefined)}
      >
        <video
          ref={videoRef}
          src={src}
          className="absolute inset-0 w-full h-full object-cover"
          controls
          playsInline
          muted={false}
        />

        {overlays.map((o) => {
          const wrapperW = wrapperRef.current?.clientWidth ?? 360;
          const fontPx = Math.max(
            14,
            Math.round(o.fontSize * (wrapperW / 1080))
          );
          return (
            <div
              key={o.id}
              onPointerDown={(e) => onPointerDown(e, o.id)}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedId(o.id);
              }}
              className={`absolute select-none cursor-grab active:cursor-grabbing overlay-text px-1 ${
                selectedId === o.id
                  ? "outline outline-2 outline-accent rounded"
                  : ""
              } ${o.italic ? "italic" : ""}`}
              style={{
                left: `${o.xPct}%`,
                top: `${o.yPct}%`,
                width: `${o.widthPct}%`,
                transform:
                  o.align === "center"
                    ? "translate(-50%, -50%)"
                    : o.align === "right"
                    ? "translate(-100%, -50%)"
                    : "translate(0%, -50%)",
                textAlign: o.align,
                color: o.color,
                fontSize: fontPx,
                fontFamily:
                  o.fontFamily === "sans"
                    ? "ui-sans-serif, system-ui"
                    : "Times New Roman, ui-serif, Georgia, serif",
              }}
            >
              {o.text}
            </div>
          );
        })}

        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            addEmptyOverlay();
          }}
          className="absolute bottom-3 right-3 size-11 rounded-full bg-accent grid place-items-center shadow-lg shadow-accent/30"
          aria-label="Ajouter un texte"
        >
          <Plus className="size-5 text-white" />
        </button>
      </div>
    </section>
  );
}

export function OverlayInspector({
  overlay,
  onChange,
  onDelete,
}: {
  overlay: OverlayBlock;
  onChange: (next: OverlayBlock) => void;
  onDelete: () => void;
}) {
  return (
    <section className="subpanel space-y-4 p-4">
      <div className="flex items-center gap-2">
        <span className="grid size-8 place-items-center rounded-xl bg-accent/10 text-accent">
          <Pencil className="size-4" />
        </span>
        <div>
          <h3 className="text-sm font-semibold text-white">
            Texte sélectionné
          </h3>
          <p className="text-[11px] text-ink-500">
            Style et position du texte incrusté
          </p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="ml-auto grid size-9 place-items-center rounded-xl border border-transparent text-ink-300 transition hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-300"
          aria-label="Supprimer le texte sélectionné"
        >
          <Trash2 className="size-4" />
        </button>
      </div>
      <textarea
        value={overlay.text}
        onChange={(e) => onChange({ ...overlay, text: e.target.value })}
        rows={3}
        aria-label="Contenu du texte sélectionné"
        className="field-control min-h-24 resize-y py-2.5 font-serif italic"
      />
      <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-ink-400">Taille ({overlay.fontSize}px)</span>
          <input
            type="range"
            min={24}
            max={140}
            value={overlay.fontSize}
            onChange={(e) =>
              onChange({ ...overlay, fontSize: Number(e.target.value) })
            }
            className="h-8 w-full accent-fuchsia-500"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Largeur ({overlay.widthPct}%)</span>
          <input
            type="range"
            min={20}
            max={100}
            value={overlay.widthPct}
            onChange={(e) =>
              onChange({ ...overlay, widthPct: Number(e.target.value) })
            }
            className="h-8 w-full accent-fuchsia-500"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Couleur</span>
          <input
            type="color"
            value={overlay.color}
            onChange={(e) => onChange({ ...overlay, color: e.target.value })}
            className="field-control h-10 cursor-pointer bg-transparent p-1"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Police</span>
          <select
            value={overlay.fontFamily}
            onChange={(e) =>
              onChange({
                ...overlay,
                fontFamily: e.target.value as "serif" | "sans",
              })
            }
            className="field-control h-10"
          >
            <option value="serif">Avec empattements (style philo)</option>
            <option value="sans">Sans empattements</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Alignement</span>
          <select
            value={overlay.align}
            onChange={(e) =>
              onChange({
                ...overlay,
                align: e.target.value as "left" | "center" | "right",
              })
            }
            className="field-control h-10"
          >
            <option value="left">Gauche</option>
            <option value="center">Centré</option>
            <option value="right">Droite</option>
          </select>
        </label>
        <label className="mt-5 flex cursor-pointer items-center gap-2 rounded-xl border border-white/10 bg-black/10 px-3 py-2.5">
          <input
            type="checkbox"
            checked={!!overlay.italic}
            onChange={(e) => onChange({ ...overlay, italic: e.target.checked })}
          />
          <span className="text-ink-200">Italique</span>
        </label>
      </div>
      <p className="text-[11px] text-ink-400">
        Astuce : déplace le texte en le faisant glisser directement sur
        l’aperçu.
      </p>
    </section>
  );
}
