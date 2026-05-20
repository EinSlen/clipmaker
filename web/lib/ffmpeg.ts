import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import type { OverlayBlock } from './types';

export type RenderInput = {
  inputAbs: string;
  outputAbs: string;
  width: number;
  height: number;
  overlays: OverlayBlock[];
  musicAbs?: string;
  musicVolume?: number; // 0..1
  duckOriginal?: number; // 0..1 multiplier on original audio (1 = keep, 0.4 = -8dB-ish)
};

function escapeDrawText(s: string) {
  // Escape for ffmpeg drawtext "text="
  return s
    .replace(/\\/g, '\\\\')
    .replace(/:/g, '\\:')
    .replace(/'/g, "\\'")
    .replace(/%/g, '\\%')
    .replace(/\n/g, '\\n');
}

function fontFileFor(family: 'serif' | 'sans'): string {
  const win = process.platform === 'win32';
  if (family === 'serif') {
    return win ? 'C\\:/Windows/Fonts/times.ttf' : '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf';
  }
  return win ? 'C\\:/Windows/Fonts/arial.ttf' : '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';
}

function wrapText(text: string, maxCharsPerLine: number): string {
  // Respect explicit \n; for each line longer than maxCharsPerLine, soft-wrap on spaces.
  const out: string[] = [];
  for (const raw of text.split('\n')) {
    if (raw.length <= maxCharsPerLine) {
      out.push(raw);
      continue;
    }
    const words = raw.split(/\s+/);
    let cur = '';
    for (const w of words) {
      if ((cur + ' ' + w).trim().length > maxCharsPerLine) {
        if (cur) out.push(cur);
        cur = w;
      } else {
        cur = (cur ? cur + ' ' : '') + w;
      }
    }
    if (cur) out.push(cur);
  }
  return out.join('\n');
}

export async function renderVideo(input: RenderInput): Promise<{ ok: boolean; stderr: string }> {
  const { inputAbs, outputAbs, width, height, overlays, musicAbs, musicVolume = 0.6, duckOriginal = 1 } = input;

  // Build drawtext filter chain
  const drawSegments: string[] = [];
  for (const ov of overlays) {
    const maxW = Math.max(8, Math.floor((ov.widthPct / 100) * width));
    const fontPx = Math.max(14, Math.round(ov.fontSize * (width / 1080)));
    const approxCharW = fontPx * 0.55;
    const maxChars = Math.max(8, Math.floor(maxW / approxCharW));
    const wrapped = wrapText(ov.text, maxChars);
    const escaped = escapeDrawText(wrapped);
    const fontfile = fontFileFor(ov.fontFamily);

    // x/y based on percentage of frame, but anchor to text width via text_w/h
    const xExpr =
      ov.align === 'center'
        ? `(w*${(ov.xPct / 100).toFixed(4)})-text_w/2`
        : ov.align === 'right'
          ? `(w*${(ov.xPct / 100).toFixed(4)})-text_w`
          : `w*${(ov.xPct / 100).toFixed(4)}`;
    const yExpr = `(h*${(ov.yPct / 100).toFixed(4)})-text_h/2`;

    const opts = [
      `text='${escaped}'`,
      `fontfile='${fontfile}'`,
      `fontsize=${fontPx}`,
      `fontcolor=${ov.color.replace('#', '0x')}`,
      `borderw=${Math.max(2, Math.round(fontPx * 0.05))}`,
      `bordercolor=black@0.85`,
      `line_spacing=${Math.round(fontPx * 0.15)}`,
      `x=${xExpr}`,
      `y=${yExpr}`
    ];
    if (typeof ov.startMs === 'number' || typeof ov.endMs === 'number') {
      const start = (ov.startMs ?? 0) / 1000;
      const end = (ov.endMs ?? 9999999) / 1000;
      opts.push(`enable='between(t,${start.toFixed(3)},${end.toFixed(3)})'`);
    }
    drawSegments.push(`drawtext=${opts.join(':')}`);
  }

  const videoFilter = drawSegments.length ? `[0:v]${drawSegments.join(',')}[v]` : '[0:v]null[v]';

  // Audio
  const audioInputs: string[] = [];
  let audioFilter = '';
  if (musicAbs) {
    audioInputs.push('-i', musicAbs);
    // Mix original (ducked) + music, loop music if shorter
    audioFilter = `[0:a]volume=${duckOriginal.toFixed(2)}[a0];[1:a]aloop=loop=-1:size=2e9,volume=${musicVolume.toFixed(2)}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]`;
  } else {
    audioFilter = '[0:a]anull[aout]';
  }

  const filterComplex = drawSegments.length ? `${videoFilter};${audioFilter}` : `${audioFilter};${videoFilter}`;

  const args = [
    '-y',
    '-i', inputAbs,
    ...audioInputs,
    '-filter_complex', filterComplex,
    '-map', '[v]',
    '-map', '[aout]?',
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',
    '-preset', 'medium',
    '-crf', '20',
    '-c:a', 'aac',
    '-b:a', '192k',
    '-shortest',
    '-movflags', '+faststart',
    outputAbs
  ];

  await fs.mkdir(path.dirname(outputAbs), { recursive: true });

  return new Promise((resolve) => {
    const proc = spawn('ffmpeg', args, { windowsHide: true });
    let stderr = '';
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => resolve({ ok: code === 0, stderr: stderr.slice(-4000) }));
    proc.on('error', (e) => resolve({ ok: false, stderr: String(e) }));
  });
}

export async function probeVideo(file: string): Promise<{ width: number; height: number; duration: number } | null> {
  return new Promise((resolve) => {
    const proc = spawn('ffprobe', [
      '-v', 'error',
      '-select_streams', 'v:0',
      '-show_entries', 'stream=width,height',
      '-show_entries', 'format=duration',
      '-of', 'json',
      file
    ], { windowsHide: true });
    let out = '';
    proc.stdout.on('data', (d) => (out += d.toString()));
    proc.on('close', () => {
      try {
        const j = JSON.parse(out);
        const s = j.streams?.[0] ?? {};
        resolve({
          width: Number(s.width ?? 0),
          height: Number(s.height ?? 0),
          duration: Number(j.format?.duration ?? 0)
        });
      } catch {
        resolve(null);
      }
    });
    proc.on('error', () => resolve(null));
  });
}

export function tmpFile(ext: string) {
  return path.join(os.tmpdir(), `clipmaker-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${ext}`);
}
