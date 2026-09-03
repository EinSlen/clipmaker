import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { synthesizeEnglishSpeech } from './workers-ai.mjs';

// Workers AI has no French text-to-speech: MeloTTS rejects every language code
// but "en", and both Aura models are English or Spanish only. edge-tts needs no
// key and no quota, and ships five French neural voices.
export const FRENCH_VOICES = [
  'fr-FR-HenriNeural',
  'fr-FR-DeniseNeural',
  'fr-FR-EloiseNeural',
  'fr-FR-RemyMultilingualNeural',
  'fr-FR-VivienneMultilingualNeural',
];

function pythonBinary() {
  return process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
}

function runEdgeTts(args, timeoutMs = 90_000) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBinary(), ['-m', 'edge_tts', ...args], { windowsHide: true });
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('edge-tts timed out.'));
    }, timeoutMs);
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-4000); });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else reject(new Error(`edge-tts exited with ${code}: ${stderr.slice(-600)}`));
    });
  });
}

export function frenchVoice(seed = 0) {
  return FRENCH_VOICES[Math.abs(Math.trunc(seed)) % FRENCH_VOICES.length];
}

// The service reports where each word lands while it speaks, so the timings the
// captions need come for free here. Falling back to the command line keeps the
// voice working even if that stream cannot be read.
function speakWithWords(payload) {
  const script = path.join(path.dirname(fileURLToPath(import.meta.url)), 'speak_words.py');
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBinary(), [script], { windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('speak_words timed out.'));
    }, 90_000);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-2000); });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`speak_words exited with ${code}: ${stderr.slice(-400)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout).words || []);
      } catch (error) {
        reject(new Error(`speak_words returned invalid JSON: ${error.message}`));
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

export async function speak(text, { lang = 'fr', voice, rate = '+8%', outputFile }) {
  const clean = String(text || '').trim();
  if (!clean) throw new Error('Empty narration line.');
  if (!outputFile) throw new Error('speak needs an output file.');

  if (lang === 'en') {
    await fs.writeFile(outputFile, await synthesizeEnglishSpeech(clean));
    return { file: outputFile, words: [] };
  }

  const selected = voice || frenchVoice();
  const words = await speakWithWords({ text: clean, voice: selected, rate, output: outputFile })
    .catch(async (error) => {
      process.stderr.write(`Timings de mots indisponibles (${error.message}), repli sur edge-tts simple.\n`);
      await runEdgeTts(['--voice', selected, '--rate', rate, '--text', clean, '--write-media', outputFile]);
      return [];
    });
  const stat = await fs.stat(outputFile).catch(() => null);
  if (!stat || stat.size < 512) throw new Error('edge-tts produced no audio.');
  return { file: outputFile, words };
}
