import { spawn } from 'node:child_process';

// Deterministic stand-ins so the whole chain can be exercised in CI and on a
// laptop with no keys. Never used when CF_AI_TOKEN is present.
const PALETTE = ['0x1b2a41', '0x3c1642', '0x0b3954', '0x4a1c1c', '0x123f2b', '0x2d2438'];

function hash(text) {
  let value = 0;
  for (const character of String(text)) value = (value * 31 + character.charCodeAt(0)) >>> 0;
  return value;
}

function ffmpeg(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.FFMPEG_PATH || 'ffmpeg', args, { windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-4000); });
    child.on('error', reject);
    child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(stderr.slice(-600)))));
  });
}

export async function offlineImage(prompt, file) {
  const colour = PALETTE[hash(prompt) % PALETTE.length];
  await ffmpeg([
    '-y', '-hide_banner', '-loglevel', 'error',
    '-f', 'lavfi', '-i', `color=c=${colour}:s=1024x1024`,
    '-f', 'lavfi', '-i', 'nullsrc=s=1024x1024',
    '-filter_complex', `[0:v]noise=alls=22:allf=t+u,gblur=sigma=3,vignette[v]`,
    '-map', '[v]', '-frames:v', '1', file,
  ]);
  return file;
}

export async function offlineSpeech(text, file) {
  const words = String(text).split(/\s+/).filter(Boolean).length;
  const seconds = Math.max(1.5, words / 2.6);
  await ffmpeg([
    '-y', '-hide_banner', '-loglevel', 'error',
    '-f', 'lavfi', '-i', `sine=frequency=${180 + (hash(text) % 90)}:duration=${seconds.toFixed(2)}`,
    '-af', 'volume=0.05', '-c:a', 'libmp3lame', file,
  ]);
  return file;
}

export function offlineSeries() {
  return {
    title: 'Test hors ligne',
    premise: 'Une série factice qui sert uniquement à exercer la chaîne de production.',
    format: 'Un huis clos de test.',
    characters: [
      { name: 'Alpha', look: 'silhouette de test bleue', trait: 'personnage factice' },
      { name: 'Beta', look: 'silhouette de test rouge', trait: 'personnage factice' },
    ],
    visualStyle: 'aplat de couleur de test',
    lang: 'fr',
    voice: 'fr-FR-HenriNeural',
  };
}

export function offlineDraft(episodeNumber, targetSeconds) {
  const shots = Math.max(6, Math.min(14, Math.round(targetSeconds / 6)));
  const cast = offlineSeries().characters;
  return {
    title: `EPISODE HORS LIGNE ${episodeNumber}`,
    youtubeTitle: `Episode hors ligne ${episodeNumber} #shorts`,
    caption: 'Test hors ligne. Rien de tout cela n\'est publié.',
    tags: ['#test', '#horsligne', '#clipmaker', '#shorts', '#serie'],
    summary: `Épisode hors ligne ${episodeNumber}.`,
    chosenComment: episodeNumber > 1 ? { platform: 'youtube', author: '@test', text: 'continue comme ça', likes: 3 } : null,
    chosenReason: 'Le mode hors ligne prend une direction figée.',
    shots: Array.from({ length: shots }, (_, index) => ({
      narration: `Plan ${index + 1} de l'épisode hors ligne, assez long pour ressembler à une vraie ligne de narration.`,
      image: `plaque de test numéro ${index + 1}`,
      cast: [cast[index % cast.length]],
    })),
  };
}
