'use client';

import Link from 'next/link';
import { Film } from 'lucide-react';

export function TopBar({ subtitle }: { subtitle?: string }) {
  return (
    <header className="sticky top-0 z-30 bg-ink-900/85 backdrop-blur border-b border-white/5">
      <div className="mx-auto max-w-3xl px-4 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <Film className="size-5 text-accent" />
          <span className="font-semibold tracking-tight">clipMaker</span>
          {subtitle && <span className="text-ink-400 text-sm ml-2">/ {subtitle}</span>}
        </Link>
      </div>
    </header>
  );
}
