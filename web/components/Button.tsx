'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

type Variant = 'primary' | 'ghost' | 'outline' | 'danger';
type Size = 'sm' | 'md' | 'lg';

const baseClass =
  'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition active:scale-[.98] disabled:opacity-50 disabled:cursor-not-allowed select-none';

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent/90 shadow-lg shadow-accent/20',
  ghost: 'bg-white/5 text-ink-50 hover:bg-white/10',
  outline: 'border border-white/15 text-ink-50 hover:bg-white/5',
  danger: 'bg-red-600/90 text-white hover:bg-red-600'
};

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-11 px-4 text-sm',
  lg: 'h-12 px-5 text-base'
};

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => (
    <button ref={ref} className={cn(baseClass, variants[variant], sizes[size], className)} {...props} />
  )
);
Button.displayName = 'Button';
