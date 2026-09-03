import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { readPublisherConfig } from './config.mjs';
import { fetchYoutubeComments } from '../../scripts/story/comments.mjs';
import { lastEpisode, nextEpisodeNumber, storySoFar, upsertEpisode } from '../../scripts/story/state.mjs';
import { clipPrompt } from '../../scripts/story/writer.mjs';
import { cuesFromWords } from '../../scripts/story/transcribe.mjs';

let counter = 0;

async function normalizeConfig(document) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'clipmaker-story-'));
  const file = path.join(directory, `publisher-${counter++}.json`);
  fs.writeFileSync(file, JSON.stringify(document), 'utf8');
  try {
    return await readPublisherConfig(file, {});
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function storyConfig(overrides = {}) {
  return {
    version: 1,
    dryRun: true,
    baseUrl: 'http://127.0.0.1:3000',
    timeZone: 'Europe/Paris',
    stateDir: '../data/publisher',
    channels: [{
      id: 'story-dvlad',
      enabled: true,
      generateTime: '00:07',
      publishTime: '18:00',
      game: { id: 'story-comments', duration: 60, tiktokUser: 'dvlad', ...overrides },
      youtube: { enabled: true, account: 'default', privacy: 'private', confirmPublic: false },
      tiktok: { enabled: true, username: 'dvlad', visibility: 'private', confirmPublic: false },
    }],
  };
}

test('a story channel carries the identifiers the episode builder needs', async () => {
  const config = await normalizeConfig(storyConfig());
  const game = config.channels[0].game;
  assert.equal(game.game, 'story-comments');
  assert.equal(game.channelId, 'story-dvlad');
  assert.equal(game.series, 'story-dvlad');
  assert.equal(game.tiktokUser, 'dvlad');
  assert.equal(game.duration, 60);
});

test('an explicit series id survives a channel rename and the theme is kept', async () => {
  const config = await normalizeConfig(storyConfig({ series: 'nightwatch', storyTheme: 'une villa de téléréalité' }));
  const game = config.channels[0].game;
  assert.equal(game.series, 'nightwatch');
  assert.equal(game.channelId, 'story-dvlad');
  assert.equal(game.storyTheme, 'une villa de téléréalité');
});

test('story episodes stay inside the thirty to one hundred and twenty second window', async () => {
  await assert.rejects(normalizeConfig(storyConfig({ duration: 15 })), /duration must be between 30 and 120/);
  await assert.rejects(normalizeConfig(storyConfig({ duration: 180 })), /duration must be between 30 and 120/);
  const config = await normalizeConfig(storyConfig({ duration: 120 }));
  assert.equal(config.channels[0].game.duration, 120);
});

test('the series memory numbers episodes in order and credits the viewers who steered them', () => {
  const state = { seriesId: 'demo', series: null, episodes: [] };
  assert.equal(nextEpisodeNumber(state), 1);
  assert.equal(lastEpisode(state), null);

  upsertEpisode(state, { number: 2, summary: 'la porte s’est ouverte' });
  upsertEpisode(state, { number: 1, summary: 'le phare a clignoté', chosenComment: { author: '@ada', text: 'entre dans le phare' } });
  assert.deepEqual(state.episodes.map((episode) => episode.number), [1, 2]);
  assert.equal(nextEpisodeNumber(state), 3);
  assert.equal(lastEpisode(state).number, 2);

  upsertEpisode(state, { number: 2, summary: 'la porte s’est refermée' });
  assert.equal(state.episodes.length, 2);

  const memory = storySoFar(state);
  assert.match(memory, /Épisode 1 : le phare a clignoté/);
  assert.match(memory, /le spectateur @ada a orienté cet épisode/);
  assert.match(memory, /Épisode 2 : la porte s’est refermée/);
});

test('an empty series tells the writer it is producing the pilot', () => {
  assert.match(storySoFar({ episodes: [] }), /pilote/i);
});

test('YouTube comments are normalised and a disabled comment section is not a failure', async (t) => {
  const original = globalThis.fetch;
  process.env.YOUTUBE_API_KEY = 'test-key';
  t.after(() => { globalThis.fetch = original; delete process.env.YOUTUBE_API_KEY; });

  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      items: [
        { snippet: { topLevelComment: { snippet: { authorDisplayName: '@ada', textOriginal: '  she should\nopen the door  ', likeCount: 12, publishedAt: '2026-09-02T10:00:00Z' } } } },
        { snippet: { topLevelComment: { snippet: { authorDisplayName: '@bob', textOriginal: '', likeCount: 3 } } } },
      ],
    }),
  });
  const ok = await fetchYoutubeComments('4kg5YD3iG94');
  assert.equal(ok.ok, true);
  assert.equal(ok.comments.length, 1);
  assert.deepEqual(ok.comments[0], {
    platform: 'youtube',
    author: '@ada',
    text: 'she should open the door',
    likes: 12,
    publishedAt: '2026-09-02T10:00:00Z',
  });

  globalThis.fetch = async () => ({ ok: false, status: 403, text: async () => 'commentsDisabled' });
  const denied = await fetchYoutubeComments('4kg5YD3iG94');
  assert.equal(denied.ok, false);
  assert.equal(denied.reason, 'youtube-http-403');
  assert.deepEqual(denied.comments, []);
});

test('a missing key or video id never reaches the network', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => { throw new Error('the network must not be used'); };

  delete process.env.YOUTUBE_API_KEY;
  assert.equal((await fetchYoutubeComments('4kg5YD3iG94')).reason, 'no-youtube-api-key');

  process.env.YOUTUBE_API_KEY = 'test-key';
  assert.equal((await fetchYoutubeComments('')).reason, 'no-video-id');
  delete process.env.YOUTUBE_API_KEY;
});

test('every clip prompt repeats the cast description so characters stay recognisable', () => {
  const series = {
    visualStyle: 'rendu 3D lisse, lumière de studio',
    characters: [
      { name: 'Fraisette', look: 'une fraise géante, fines jambes humaines, survêtement rouge', trait: 'la manipulatrice' },
      { name: 'Kiwi', look: 'un kiwi trapu, moustache blanche, chemise hawaïenne', trait: 'le naïf' },
    ],
  };

  const prompt = clipPrompt(series, [
    {
      narration: 'Fraisette surprend Kiwi pres de la piscine.',
      image: 'Fraisette surprend Kiwi près de la piscine, plan large',
      cast: [series.characters[0], series.characters[1]],
    },
  ], 0, 2, 10);
  assert.match(prompt, /Fraisette : une fraise géante, fines jambes humaines, survêtement rouge/);
  assert.match(prompt, /Kiwi : un kiwi trapu, moustache blanche, chemise hawaïenne/);
  assert.match(prompt, /rendu 3D lisse, lumière de studio/);
  assert.match(prompt, /9:16/);
  assert.match(prompt, /aucun texte/);
  // The spoken line travels with the prompt, since the clip says it itself.
  assert.match(prompt, /Fraisette surprend Kiwi pres de la piscine\./);
  assert.match(prompt, /PLAN 1\/2/);

  // A shot the writer left without a cast still gets a described character
  // rather than an unanchored prompt.
  const orphan = clipPrompt(series, [{ narration: 'La villa dort.', image: 'la villa vide au petit matin', cast: [] }], 1, 2, 10);
  assert.match(orphan, /Fraisette : une fraise géante/);
});

test('subtitles follow the spoken words instead of being spread evenly', () => {
  // A burst, a long silence, then a burst. An even split would put a caption
  // in the middle of the silence, which is exactly the mismatch to avoid.
  const words = [
    { text: 'Bienvenue', start: 0.4, end: 1.0 },
    { text: 'dans', start: 1.0, end: 1.2 },
    { text: 'la', start: 1.2, end: 1.35 },
    { text: 'villa', start: 1.35, end: 1.9 },
    { text: 'les', start: 8.0, end: 8.2 },
    { text: 'amis', start: 8.2, end: 8.9 },
  ];
  const cues = cuesFromWords(words);
  assert.equal(cues.length, 2);
  assert.equal(cues[0].text, 'Bienvenue dans la villa');
  assert.equal(cues[0].from, 0.4);
  assert.equal(cues[0].to, 1.9);
  // The per word timings survive the grouping, which is what drives the red
  // highlight on the word being pronounced.
  assert.deepEqual(cues[0].words.map((word) => word.text), ['Bienvenue', 'dans', 'la', 'villa']);
  assert.equal(cues[0].words[1].start, 1);
  assert.equal(cues[1].text, 'les amis');
  assert.equal(cues[1].from, 8);
  // Nothing is displayed during the silence between the two groups.
  assert.ok(cues.every((cue) => cue.to <= 2 || cue.from >= 8));

  // A caption never collapses to an unreadable flash.
  const [flash] = cuesFromWords([{ text: 'oui', start: 3, end: 3.05 }]);
  assert.ok(flash.to - flash.from >= 0.35);

  // Long words break into readable groups rather than one endless line.
  const long = cuesFromWords(Array.from({ length: 9 }, (_, index) => ({
    text: `mot${index}`, start: index * 0.5, end: index * 0.5 + 0.4,
  })));
  assert.ok(long.length >= 3);
  assert.ok(long.every((cue) => cue.text.length <= 26));
});
