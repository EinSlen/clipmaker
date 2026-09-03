import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLISHER_STATE_FILE, STORY_DIR } from './paths.mjs';

export { STORY_DIR };

function emptyState(seriesId) {
  return {
    version: 1,
    seriesId,
    series: null,
    episodes: [],
  };
}

export function statePath(seriesId) {
  return path.join(STORY_DIR, `${seriesId}.json`);
}

export async function loadStory(seriesId) {
  try {
    const raw = await fs.readFile(statePath(seriesId), 'utf8');
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.episodes)) throw new Error('corrupt');
    return { ...emptyState(seriesId), ...parsed, seriesId };
  } catch {
    return emptyState(seriesId);
  }
}

export async function saveStory(state) {
  await fs.mkdir(STORY_DIR, { recursive: true });
  const target = statePath(state.seriesId);
  const temporary = `${target}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
  await fs.rename(temporary, target);
}

export function lastEpisode(state) {
  return state.episodes.length ? state.episodes[state.episodes.length - 1] : null;
}

export function nextEpisodeNumber(state) {
  return state.episodes.reduce((highest, episode) => Math.max(highest, episode.number || 0), 0) + 1;
}

export function findEpisode(state, number) {
  return state.episodes.find((episode) => episode.number === number) || null;
}

export function upsertEpisode(state, episode) {
  const index = state.episodes.findIndex((candidate) => candidate.number === episode.number);
  if (index >= 0) state.episodes[index] = { ...state.episodes[index], ...episode };
  else state.episodes.push(episode);
  state.episodes.sort((a, b) => a.number - b.number);
  return state;
}

// The writer only needs a compact memory, not every past script.
export function storySoFar(state, limit = 6) {
  const recent = state.episodes.slice(-limit);
  if (!recent.length) return 'Aucun épisode n\'est encore sorti. Celui-ci est le pilote.';
  return recent
    .map((episode) => {
      const credit = episode.chosenComment
        ? ` (le spectateur ${episode.chosenComment.author} a orienté cet épisode : « ${episode.chosenComment.text} »)`
        : '';
      return `Épisode ${episode.number} : ${episode.summary}${credit}`;
    })
    .join('\n');
}

// Back-fill the ids the publisher recorded, so the next episode knows which
// posts to read comments from.
export async function syncPublications(state, channelId, tiktokUsername) {
  const raw = await fs.readFile(PUBLISHER_STATE_FILE, 'utf8').catch(() => '');
  if (!raw) return state;
  let jobs = [];
  try {
    jobs = JSON.parse(raw).jobs || [];
  } catch {
    return state;
  }
  for (const episode of state.episodes) {
    if (!episode.jobDate) continue;
    const job = jobs.find((candidate) => candidate.id === `${episode.jobDate}:${channelId}`);
    if (!job) continue;
    const youtube = job.platforms?.youtube?.receipt?.id || null;
    const tiktok = job.platforms?.tiktok?.receipt?.id || null;
    if (!youtube && !tiktok) continue;
    episode.publishedIds = {
      ...(episode.publishedIds || {}),
      ...(youtube ? { youtube } : {}),
      ...(tiktok ? { tiktok, tiktokUsername } : {}),
    };
  }
  return state;
}
