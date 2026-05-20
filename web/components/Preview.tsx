'use client';

import * as React from 'react';
import { Move, Trash2, Pencil, Plus, Type } from 'lucide-react';
import type { OverlayBlock } from '@/lib/types';
import { clamp, randomId } from '@/lib/utils';

type Props = {
  src: string;
  overlays: OverlayBlock[];
  setOverlays: (next: OverlayBlock[]) => void;
  selectedId?: string;
  setSelectedId: (id?: string) => void;
};

export function Preview({ src, overlays, setOverlays, selectedId, setSelectedId }: Props) {
  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const dragRef = React.useRef<{ id: string; startX: number; startY: number; baseX: number; baseY: number } | null>(null);

  function onPointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation();
    setSelectedId(id);
    const ov = overlays.find((o) => o.id === id);
    if (!ov) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { id, startX: e.clientX, startY: e.clientY, baseX: ov.xPct, baseY: ov.yPct };
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!dragRef.current || !wrapperRef.current) return;
    const rect = wrapperRef.current.getBoundingClientRect();
    const dxPct = ((e.clientX - dragRef.current.startX) / rect.width) * 100;
    const dyPct = ((e.clientY - dragRef.current.startY) / rect.height) * 100;
    setOverlays(
      overlays.map((o) =>
        o.id === dragRef.current!.id
          ? { ...o, xPct: clamp(dragRef.current!.baseX + dxPct, 0, 100), yPct: clamp(dragRef.current!.baseY + dyPct, 0, 100) }
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
      text: 'Touche pour écrire…',
      xPct: 50,
      yPct: 50,
      widthPct: 80,
      fontSize: 56,
      color: '#ffffff',
      align: 'center',
      fontFamily: 'serif',
      italic: true
    };
    setOverlays([...overlays, ov]);
    setSelectedId(ov.id);
  }

  return (
    <div className="space-y-2">
      <div
        ref={wrapperRef}
        className="relative mx-auto rounded-2xl overflow-hidden bg-black border border-white/10"
        style={{ aspectRatio: '9 / 16', maxHeight: '70dvh', width: '100%', touchAction: 'none' }}
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
          const fontPx = Math.max(14, Math.round(o.fontSize * (wrapperW / 1080)));
          return (
            <div
              key={o.id}
              onPointerDown={(e) => onPointerDown(e, o.id)}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedId(o.id);
              }}
              className={`absolute select-none cursor-grab active:cursor-grabbing overlay-text px-1 ${
                selectedId === o.id ? 'outline outline-2 outline-accent rounded' : ''
              } ${o.italic ? 'italic' : ''}`}
              style={{
                left: `${o.xPct}%`,
                top: `${o.yPct}%`,
                width: `${o.widthPct}%`,
                transform:
                  o.align === 'center' ? 'translate(-50%, -50%)' : o.align === 'right' ? 'translate(-100%, -50%)' : 'translate(0%, -50%)',
                textAlign: o.align,
                color: o.color,
                fontSize: fontPx,
                fontFamily: o.fontFamily === 'sans' ? 'ui-sans-serif, system-ui' : 'Times New Roman, ui-serif, Georgia, serif'
              }}
            >
              {o.text}
            </div>
          );
        })}

        <button
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
    </div>
  );
}

export function OverlayInspector({
  overlay,
  onChange,
  onDelete
}: {
  overlay: OverlayBlock;
  onChange: (next: OverlayBlock) => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl bg-ink-700/60 border border-white/10 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <Pencil className="size-4 text-accent" />
        <span className="text-sm font-medium">Texte sélectionné</span>
        <button onClick={onDelete} className="ml-auto text-ink-200 hover:text-red-400" aria-label="Supprimer">
          <Trash2 className="size-4" />
        </button>
      </div>
      <textarea
        value={overlay.text}
        onChange={(e) => onChange({ ...overlay, text: e.target.value })}
        rows={3}
        className="w-full bg-ink-800 border border-white/10 rounded-lg px-3 py-2 text-sm resize-y font-serif italic"
      />
      <div className="grid grid-cols-2 gap-3 text-xs">
        <label className="space-y-1">
          <span className="text-ink-400">Taille ({overlay.fontSize}px)</span>
          <input
            type="range"
            min={24}
            max={140}
            value={overlay.fontSize}
            onChange={(e) => onChange({ ...overlay, fontSize: Number(e.target.value) })}
            className="w-full"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Largeur ({overlay.widthPct}%)</span>
          <input
            type="range"
            min={20}
            max={100}
            value={overlay.widthPct}
            onChange={(e) => onChange({ ...overlay, widthPct: Number(e.target.value) })}
            className="w-full"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Couleur</span>
          <input
            type="color"
            value={overlay.color}
            onChange={(e) => onChange({ ...overlay, color: e.target.value })}
            className="w-full h-9 bg-transparent"
          />
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Police</span>
          <select
            value={overlay.fontFamily}
            onChange={(e) => onChange({ ...overlay, fontFamily: e.target.value as 'serif' | 'sans' })}
            className="w-full h-9 bg-ink-800 border border-white/10 rounded-lg px-2"
          >
            <option value="serif">Serif (style philo)</option>
            <option value="sans">Sans-serif</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-ink-400">Alignement</span>
          <select
            value={overlay.align}
            onChange={(e) => onChange({ ...overlay, align: e.target.value as 'left' | 'center' | 'right' })}
            className="w-full h-9 bg-ink-800 border border-white/10 rounded-lg px-2"
          >
            <option value="left">Gauche</option>
            <option value="center">Centré</option>
            <option value="right">Droite</option>
          </select>
        </label>
        <label className="flex items-center gap-2 mt-5">
          <input type="checkbox" checked={!!overlay.italic} onChange={(e) => onChange({ ...overlay, italic: e.target.checked })} />
          <span className="text-ink-200">Italique</span>
        </label>
      </div>
      <p className="text-[11px] text-ink-400">Astuce : déplace le texte en le glissant sur l’aperçu.</p>
    </div>
  );
}
