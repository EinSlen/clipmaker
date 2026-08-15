"use client";

import Link from "next/link";
import { Clapperboard, Sparkles } from "lucide-react";

export function TopBar({ subtitle }: { subtitle?: string }) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-950/80 backdrop-blur-2xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="group flex items-center gap-3 rounded-xl">
          <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-accent via-fuchsia-500 to-cyan-400 shadow-lg shadow-accent/20 transition group-hover:scale-105">
            <Clapperboard className="size-[18px] text-white" />
          </span>
          <span className="leading-none">
            <span className="block text-[15px] font-bold tracking-tight text-white">
              clipMaker
            </span>
            <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
              studio vertical
            </span>
          </span>
          {subtitle && (
            <span className="hidden text-sm text-ink-400 sm:inline">
              / {subtitle}
            </span>
          )}
        </Link>
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-[11px] font-medium text-ink-300">
          <Sparkles className="size-3.5 text-cyan-300" />
          Rendu sur serveur
        </div>
      </div>
    </header>
  );
}
