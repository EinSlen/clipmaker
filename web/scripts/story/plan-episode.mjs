#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { harvestComments } from './comments.mjs';
import { clipPrompt, inventSeries, writeEpisode } from './writer.mjs';
import { loadStory, saveStory, lastEpisode, nextEpisodeNumber, syncPublications } from './state.mjs';

const RECEIPT_PREFIX = 'CLIPMAKER_PLAN:';
// Hailuo renders 5 or 10 second clips, chosen in its interface, so the planned
// length has to match what the agent actually asks for. Same variable on both
// sides keeps the plan and the generation from drifting apart.
const CLIP_SECONDS = Math.max(5, Math.min(15, Number(process.env.MINIMAX_DURATION) || 10));

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

// Each generated clip covers several written shots, so the narration of the
// shots it spans becomes the spoken content of that clip.
function groupShotsIntoClips(shots, targetSeconds, clipSeconds) {
  const clipCount = Math.max(1, Math.min(5, Math.round(targetSeconds / clipSeconds)));
  const perClip = Math.ceil(shots.length / clipCount);
  const clips = [];
  for (let index = 0; index < shots.length; index += perClip) {
    clips.push(shots.slice(index, index + perClip));
  }
  return clips;
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const seriesId = String(args.series || 'story-dvlad');
  const channelId = String(args.channel || seriesId);
  const tiktokUsername = args.tiktokUser ? String(args.tiktokUser) : null;
  const jobDate = String(args.date || new Date().toISOString().slice(0, 10));
  const targetSeconds = Math.max(30, Math.min(120, Number(args.seconds) || 60));
  const outputDir = path.resolve(process.cwd(), String(args.outputDir || 'renders'));

  let state = await loadStory(seriesId);
  state = await syncPublications(state, channelId, tiktokUsername);
  if (!state.series) {
    state.series = await inventSeries(args.theme ? String(args.theme) : null);
    await saveStory(state);
  }

  const previous = lastEpisode(state);
  const harvest = previous ? await harvestComments(previous) : { comments: [], sources: [] };
  const episodeNumber = nextEpisodeNumber(state);
  const draft = await writeEpisode({
    series: state.series,
    state,
    comments: harvest.comments,
    episodeNumber,
    targetSeconds,
  });

  const groups = groupShotsIntoClips(draft.shots, targetSeconds, CLIP_SECONDS);
  const prompts = groups.map((group, index) => clipPrompt(state.series, group, index, groups.length, CLIP_SECONDS));

  const planDir = path.join(outputDir, `story-${seriesId}-${jobDate}-plan`);
  await fs.mkdir(path.join(planDir, 'clips'), { recursive: true });
  await fs.writeFile(path.join(planDir, 'prompts.txt'), `${prompts.join('\n\n---\n\n')}\n`, 'utf8');
  await fs.writeFile(path.join(planDir, 'episode.json'), `${JSON.stringify({
    seriesId,
    channelId,
    jobDate,
    episodeNumber,
    targetSeconds,
    series: state.series,
    draft,
    groups: groups.map((group) => group.map((shot) => shot.narration)),
    comments: harvest.comments.slice(0, 20),
    commentSources: harvest.sources,
  }, null, 2)}\n`, 'utf8');

  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({
    ok: true,
    seriesId,
    seriesTitle: state.series.title,
    episode: episodeNumber,
    title: draft.title,
    clips: groups.length,
    clipSeconds: CLIP_SECONDS,
    planDir,
    promptsFile: path.join(planDir, 'prompts.txt'),
    clipsDir: path.join(planDir, 'clips'),
    steeredBy: draft.chosenComment,
    commentsSeen: harvest.comments.length,
  })}\n`);
}

run().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.stdout.write(`${RECEIPT_PREFIX}${JSON.stringify({ ok: false, error: error.message })}\n`);
  process.exit(1);
});
