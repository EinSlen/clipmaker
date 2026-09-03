import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

const GROQ_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';
// The proxy caps a request at 96 kB, so the speech track is compressed hard:
// 16 kHz mono at 24 kbps stays legible for a transcriber and leaves room for
// base64 expansion on a ten second clip.
const AUDIO_BITRATE = '24k';
const AUDIO_RATE = '16000';
const MAX_PROXY_BYTES = 64_000;

function binary(name) {
  const override = name === 'ffmpeg' ? process.env.FFMPEG_PATH : process.env.FFPROBE_PATH;
  return override || name;
}

function execute(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-4000); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${path.basename(command)} exited with ${code}: ${stderr.slice(-600)}`));
    });
  });
}

export async function extractSpeechAudio(videoFile, audioFile) {
  await execute(binary('ffmpeg'), [
    '-y', '-hide_banner', '-loglevel', 'error',
    '-i', videoFile,
    '-vn', '-ac', '1', '-ar', AUDIO_RATE, '-b:a', AUDIO_BITRATE,
    audioFile,
  ]);
  return (await fs.stat(audioFile)).size;
}

// Groq and Workers AI both answer in the OpenAI verbose shape, so one reader
// covers them: a flat word list with absolute seconds.
function normaliseWords(payload) {
  const words = Array.isArray(payload?.words) ? payload.words : [];
  const cleaned = words
    .map((entry) => ({
      text: String(entry?.word ?? entry?.text ?? '').trim(),
      start: Number(entry?.start),
      end: Number(entry?.end),
    }))
    .filter((entry) => entry.text && Number.isFinite(entry.start) && Number.isFinite(entry.end) && entry.end > entry.start);
  if (cleaned.length) return cleaned;
  // Some models only return segments; a segment still beats an even split.
  return (Array.isArray(payload?.segments) ? payload.segments : [])
    .map((entry) => ({
      text: String(entry?.text || '').trim(),
      start: Number(entry?.start),
      end: Number(entry?.end),
    }))
    .filter((entry) => entry.text && Number.isFinite(entry.start) && Number.isFinite(entry.end) && entry.end > entry.start);
}

async function groqTranscribe(audioFile, lang) {
  const key = process.env.GROQ_API_KEY;
  if (!key) return null;
  const body = new FormData();
  body.append('file', new Blob([await fs.readFile(audioFile)], { type: 'audio/mpeg' }), path.basename(audioFile));
  body.append('model', process.env.GROQ_TRANSCRIBE_MODEL || 'whisper-large-v3');
  body.append('response_format', 'verbose_json');
  body.append('timestamp_granularities[]', 'word');
  if (lang) body.append('language', lang);
  const response = await fetch(GROQ_URL, { method: 'POST', headers: { authorization: `Bearer ${key}` }, body });
  if (!response.ok) {
    throw new Error(`groq-transcribe-http-${response.status}: ${(await response.text().catch(() => '')).slice(0, 200)}`);
  }
  const payload = await response.json();
  return { words: normaliseWords(payload), text: String(payload?.text || '').trim(), source: 'groq' };
}

async function proxyTranscribe(audioFile, lang) {
  const token = process.env.CLIPMAKER_UPLOAD_TOKEN;
  if (!token) return null;
  const audio = await fs.readFile(audioFile);
  if (audio.length > MAX_PROXY_BYTES) {
    throw new Error(`Audio de ${audio.length} octets, au-dela de la limite du proxy (${MAX_PROXY_BYTES}).`);
  }
  const endpoint = String(process.env.CLOUD_CONTROL_API || 'https://clipmaker-cloud-control.einslen.workers.dev')
    .replace(/\/+$/, '');
  const response = await fetch(`${endpoint}/api/ai/run`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ task: 'transcribe', input: { audio: audio.toString('base64'), language: lang } }),
  });
  if (!response.ok) {
    throw new Error(`proxy-transcribe-http-${response.status}: ${(await response.text().catch(() => '')).slice(0, 200)}`);
  }
  const payload = await response.json();
  if (payload.ok !== true) throw new Error(`proxy-transcribe: ${String(payload.error || 'inconnu').slice(0, 200)}`);
  const result = payload.result || {};
  return { words: normaliseWords(result), text: String(result?.text || '').trim(), source: 'workers-ai' };
}

// Never fatal: a clip without a transcription still gets captions, they are
// just spread evenly instead of following the voice.
export async function transcribeClip(videoFile, { lang = 'fr', workDir = null } = {}) {
  const directory = workDir || path.dirname(videoFile);
  const audioFile = path.join(directory, `${path.basename(videoFile, path.extname(videoFile))}.transcribe.mp3`);
  try {
    await extractSpeechAudio(videoFile, audioFile);
    for (const attempt of [groqTranscribe, proxyTranscribe]) {
      const result = await attempt(audioFile, lang).catch((error) => ({ error: error.message }));
      if (!result) continue;
      if (result.error) return { ok: false, reason: result.error, words: [] };
      if (result.words.length) return { ok: true, ...result };
    }
    return { ok: false, reason: 'aucun transcripteur disponible', words: [] };
  } catch (error) {
    return { ok: false, reason: error.message, words: [] };
  } finally {
    await fs.rm(audioFile, { force: true });
  }
}

// Three or four words at a time is what reads best at arm's length, and the
// timings come from the voice rather than from an even division, so a caption
// appears exactly while its words are spoken.
export function cuesFromWords(words, { maxWords = 4, maxChars = 26 } = {}) {
  const cues = [];
  let current = null;
  for (const word of words) {
    const candidate = current ? `${current.text} ${word.text}` : word.text;
    if (current && (current.count >= maxWords || candidate.length > maxChars)) {
      cues.push(current);
      current = null;
    }
    if (!current) {
      current = { text: word.text, from: word.start, to: word.end, count: 1, members: [word] };
    } else {
      current.text = candidate;
      current.to = word.end;
      current.count += 1;
      current.members.push(word);
    }
  }
  if (current) cues.push(current);
  // The per word timings are kept alongside the group: the caption shows the
  // whole group while the word being pronounced is highlighted.
  return cues.map(({ text, from, to, members }) => ({
    text,
    from,
    to: Math.max(to, from + 0.35),
    words: members,
  }));
}
