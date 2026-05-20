import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function randomId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}
