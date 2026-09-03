#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { generateImage } from './workers-ai.mjs';
import { frenchVoice, speak } from './voice.mjs';
import { harvestComments } from './comments.mjs';
import { imagePrompt, inventSeries, writeEpisode } from './writer.mjs';
import { renderEpisode } from './render.mjs';
import { cuesFromWords, transcribeClip } from './transcribe.mjs';
import { offlineDraft, offlineImage, offlineSeries, offlineSpeech } from './offline.mjs';
import { loadStory, saveStory, lastEpisode, nextEpisodeNumber, syncPublications, upsertEpisode } from './state.mjs';

const RECEIPT_PREFIX = 'CLIPMAKER_STORY:';

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

async function mapLimited(items, limit, worker) {
  const results = new Array(items.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await worker(items[index], index);
    }
  }));
  return results;
}

async function pickMusic() {
  const root = path.resolve(process.cwd(), 'public', 'music');
  const preferred = ['triste', 'tendance', 'game'];
  for (const folder of preferred) {
    const directory = path.join(root, folder);
    const entries = await fs.readdir(directory).catch(() => []);
    const tracks = entries.filter((entry) => /\.(mp3|m4a|aac|wav|ogg)$/i.test(entry));
    if (tracks.length) return path.join(directory, tracks[Math.floor(Math.random() * tracks.length)]);
  }
  return null;
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const seriesId = String(args.series || 'story-dvlad');
  const channelId = String(args.channel || seriesId);
  const tiktokUsername = args.tiktokUser ? String(args.tiktokUser) : null;
  const jobDate = String(args.date || new Date().toISOString().slice(0, 10));
  const targetSeconds = Math.max(30, Math.min(120, Number(args.seconds) || 60));
  const outputDir = path.resolve(process.cwd(), String(args.outputDir || 'renders'));
  const offline = args.offline === true;

  let state = await loadStory(seriesId);
  state = await syncPublications(state, channelId, tiktokUsername);

  if (!state.series) {
    state.series = offline ? offlineSeries() : await inventSeries(args.theme ? String(args.theme) : null);
    await saveStory(state);
  }

  const previous = lastEpisode(state);
  const harvest = previous && !offline ? await harvestComments(previous) : { comments: [], sources: [] };
  const episodeNumber = nextEpisodeNumber(state);

  const draft = offline
    ? offlineDraft(episodeNumber, targetSeconds)
    : await writeEpisode({
      series: state.series,
      state,
      comments: harvest.comments,
      episodeNumber,
      targetSeconds,
    });

  const workDir = path.join(outputDir, `story-${seriesId}-${jobDate}`);
  const assetsDir = path.join(workDir, 'assets');
  await fs.mkdir(assetsDir, { recursive: true });

  const shots = await mapLimited(draft.shots, offline ? 4 : 3, async (shot, index) => {
    const stem = String(index).padStart(2, '0');
    const imageFile = path.join(assetsDir, `shot-${stem}.jpg`);
    const audioFile = path.join(assetsDir, `shot-${stem}.mp3`);
    if (offline) {
      await offlineImage(shot.image, imageFile);
      await offlineSpeech(shot.narration, audioFile);
      return { ...shot, imageFile, audioFile };
    }
    await fs.writeFile(imageFile, await generateImage(imagePrompt(state.series, shot)));
    // The voice reports its own word timings, so the highlighted subtitles need
    // no transcriber here. Transcribing the result is only the fallback.
    const spoken = await speak(shot.narration, {
      lang: state.series.lang || 'fr',
      voice: state.series.voice,
      outputFile: audioFile,
    });
    let words = spoken.words || [];
    if (!words.length) {
      const heard = await transcribeClip(audioFile, { lang: state.series.lang || 'fr', workDir: assetsDir });
      words = heard.ok ? heard.words : [];
    }
    return { ...shot, imageFile, audioFile, cues: words.length ? cuesFromWords(words) : null };
  });

  const filename = `story-${seriesId}-${jobDate}-ep${episodeNumber}.mp4`;
  const outputFile = path.join(outputDir, filename);
  const rendered = await renderEpisode({
    shots,
    title: draft.title,
    credit: draft.chosenComment ? draft.chosenComment.author : null,
    musicFile: args.noMusic ? null : await pickMusic(),
    workDir,
    outputFile,
  });

  // The whole renders tree is packed into the encrypted runtime artifact, so
  // the per-shot plates and clips must not survive the run.
  if (!args.keepAssets) await fs.rm(workDir, { recursive: true, force: true });

  upsertEpisode(state, {
    number: episodeNumber,
    jobDate,
    date: new Date().toISOString(),
    title: draft.title,
    summary: draft.summary,
    script: draft.shots.map((shot) => shot.narration).join(' '),
    chosenComment: draft.chosenComment,
    chosenReason: draft.chosenReason,
    commentSources: harvest.sources,
    commentsSeen: harvest.comments.length,
    filename,
    duration: rendered.duration,
    publishedIds: null,
  });
  await saveStory(state);

  const receipt = {
    ok: true,
    seriesId,
    seriesTitle: state.series.title,
    episode: episodeNumber,
    filename,
    outputFile,
    duration: rendered.duration,
    shots: rendered.shots,
    title: draft.title,
    youtubeTitle: draft.youtubeTitle,
    caption: draft.caption,
    tags: draft.tags,
    steeredBy: draft.chosenComment,
    commentsSeen: harvest.comments.length,
    commentSources: harvest.sources,
  };
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify(receipt)}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exit(1);
});
