#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { renderClipEpisode } from './render.mjs';
import { cuesFromWords, transcribeClip } from './transcribe.mjs';
import { loadStory, saveStory, upsertEpisode } from './state.mjs';

const RECEIPT_PREFIX = 'CLIPMAKER_STORY:';
const CLIP_PATTERN = /\.(mp4|mov|webm|m4v)$/i;

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) continue;
    const key = entry.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    result[key] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return result;
}

async function listClips(directory) {
  const entries = await fs.readdir(directory).catch(() => []);
  return entries
    .filter((entry) => CLIP_PATTERN.test(entry))
    .sort((a, b) => a.localeCompare(b, 'en', { numeric: true }))
    .map((entry) => path.join(directory, entry));
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const planDir = path.resolve(process.cwd(), String(args.plan || ''));
  if (!args.plan) throw new Error('--plan <dossier du plan> est requis.');

  const plan = JSON.parse(await fs.readFile(path.join(planDir, 'episode.json'), 'utf8'));
  const clipsDir = args.clipsDir ? path.resolve(process.cwd(), String(args.clipsDir)) : path.join(planDir, 'clips');
  const files = await listClips(clipsDir);
  if (!files.length) throw new Error(`Aucun clip trouvé dans ${clipsDir}.`);

  // Fewer clips than planned is fine: the narration groups are merged so the
  // captions still cover the whole episode.
  const groups = plan.groups || [];
  const perClip = Math.ceil(groups.length / files.length) || 1;
  const clips = files.map((file, index) => ({
    file,
    narration: groups.slice(index * perClip, (index + 1) * perClip).flat().join(' ')
      || groups.flat().join(' ').slice(0, 200),
  }));

  // The clip speaks its own dialogue, and the model never says the written line
  // word for word, so the subtitles are built from what is actually heard. A
  // failed transcription falls back to spreading the written narration.
  const transcriptions = [];
  if (!args.noTranscribe) {
    for (const clip of clips) {
      const heard = await transcribeClip(clip.file, { lang: plan.series?.lang || 'fr' });
      if (heard.ok && heard.words.length) {
        clip.cues = cuesFromWords(heard.words);
        transcriptions.push({ file: path.basename(clip.file), source: heard.source, cues: clip.cues.length });
      } else {
        transcriptions.push({ file: path.basename(clip.file), ok: false, reason: heard.reason });
        process.stderr.write(`Sous-titres non cales sur la voix pour ${path.basename(clip.file)} : ${heard.reason}\n`);
      }
    }
  }

  const outputDir = path.resolve(process.cwd(), String(args.outputDir || 'renders'));
  await fs.mkdir(outputDir, { recursive: true });
  const filename = `story-${plan.seriesId}-${plan.jobDate}-ep${plan.episodeNumber}.mp4`;
  const outputFile = path.join(outputDir, filename);
  const workDir = path.join(planDir, 'work');

  const rendered = await renderClipEpisode({
    clips,
    title: plan.draft.title,
    credit: plan.draft.chosenComment ? plan.draft.chosenComment.author : null,
    workDir,
    outputFile,
  });
  if (!args.keepAssets) await fs.rm(workDir, { recursive: true, force: true });

  const state = await loadStory(plan.seriesId);
  upsertEpisode(state, {
    number: plan.episodeNumber,
    jobDate: plan.jobDate,
    date: new Date().toISOString(),
    title: plan.draft.title,
    summary: plan.draft.summary,
    script: plan.draft.shots.map((shot) => shot.narration).join(' '),
    chosenComment: plan.draft.chosenComment,
    chosenReason: plan.draft.chosenReason,
    commentSources: plan.commentSources || [],
    commentsSeen: (plan.comments || []).length,
    source: 'clips',
    filename,
    duration: rendered.duration,
    publishedIds: null,
  });
  await saveStory(state);

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    seriesId: plan.seriesId,
    seriesTitle: plan.series.title,
    episode: plan.episodeNumber,
    filename,
    outputFile,
    duration: rendered.duration,
    clips: rendered.clips,
    transcriptions,
    title: plan.draft.title,
    youtubeTitle: plan.draft.youtubeTitle,
    caption: plan.draft.caption,
    tags: plan.draft.tags,
    steeredBy: plan.draft.chosenComment,
  })}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exit(1);
});
