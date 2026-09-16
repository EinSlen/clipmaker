import assert from 'node:assert/strict';
import test from 'node:test';
import { CAPTIONS, GENRE_STYLES, channelGenre, publicationCopy } from './edit-captions.mjs';
import { planForDate } from './orchestrator.mjs';

// Every deck belongs to exactly one genre, and the gate below refuses any
// other pairing, so the tests have to say which genre they are writing for.
const GENRE_OF_STYLE = { melancholic: 'edit', revenge: 'edit', gameplay: 'physics', story: 'story' };
const ENGLISH_DECKS = new Set(['melancholic', 'revenge', 'gameplay']);

test('each caption deck is original, unique and fits both platforms with full credits', () => {
  assert.deepEqual(Object.keys(CAPTIONS).sort(), ['gameplay', 'melancholic', 'revenge', 'story']);
  assert.equal(CAPTIONS.melancholic.length, 48);
  assert.equal(CAPTIONS.revenge.length, 24);
  assert.equal(CAPTIONS.gameplay.length, 36);
  assert.equal(CAPTIONS.story.length, 24);
  for (const [style, deck] of Object.entries(CAPTIONS)) {
    assert.equal(new Set(deck).size, deck.length);
    const seen = new Set();
    for (let day = 0; day < deck.length; day++) {
      const date = new Date(Date.UTC(2026, 7, 31 + day)).toISOString().slice(0, 10);
      const input = {
        style,
        genre: GENRE_OF_STYLE[style],
        channelId: 'softbody-dvlad',
        date,
        raw: { music_credit: 'C'.repeat(1600) },
      };
      const copy = publicationCopy(input);
      assert.deepEqual(copy, publicationCopy(input));
      assert.ok(copy.youtubeTitle.length <= 100);
      assert.ok([copy.caption, ...copy.tags].join(' ').length <= 2000);
      assert.ok(copy.caption.endsWith('C'.repeat(1600)));
      // The wordless deck asks questions on purpose: a question invites
      // a reply, and replies are what the feed counts.
      const line = copy.caption.split('\n')[0];
      if (ENGLISH_DECKS.has(style)) assert.match(line, /^[a-z ?.,]+$/u);
      else assert.match(line, /^[^\p{Extended_Pictographic}]+[.?]$/u);
      seen.add(copy.captionId);
    }
    assert.equal(seen.size, deck.length, 'no repeated phrase within a full daily cycle');
  }
});

test('auto follows the genre, and the spoken edit still follows its recording mood', () => {
  for (const moodKey of ['music_profile', 'musicProfile']) {
    for (const creditKey of ['music_credit', 'musicCredit']) {
      const raw = { [moodKey]: 'edit-sad', [creditKey]: 'Film credit / CC BY 3.0 / excerpt' };
      const edit = { genre: 'edit', raw };
      assert.equal(publicationCopy(edit).captionStyle, 'melancholic');
      assert.equal(publicationCopy(edit).caption.split('\n\n')[1], raw[creditKey]);
      assert.equal(publicationCopy({ ...edit, raw: { ...raw, [moodKey]: 'edit-revenge' } }).captionStyle, 'revenge');
      // The mood belongs to the recording. It never drags a physics drop
      // into the sad deck, which is the mismatch that cost this pipeline a
      // month of reach on its own account.
      assert.equal(publicationCopy({ genre: 'physics', raw }).captionStyle, 'gameplay');
    }
  }
  // A wordless render used to return null here, so the publisher fell back to
  // the single caption baked into the manifest and every post carried the same
  // words and the same four tags.
  for (const raw of [undefined, null, {}, { music_profile: 'original' }, { music_profile: 'sad-english' }]) {
    const copy = publicationCopy({ raw, date: '2026-09-13' });
    assert.equal(copy.captionStyle, 'gameplay');
    assert.ok(copy.caption.length > 0);
    assert.equal(copy.tags.length, 4);
  }
  const week = new Set();
  const footers = new Set();
  for (let day = 0; day < 14; day += 1) {
    const date = new Date(Date.UTC(2026, 8, 13 + day)).toISOString().slice(0, 10);
    const copy = publicationCopy({ channelId: 'softbody-dvlad', date, raw: { music_profile: 'original' } });
    week.add(copy.caption);
    footers.add(copy.tags.join(' '));
  }
  assert.equal(week.size, 14, 'two days never carry the same caption');
  assert.ok(footers.size >= 5, 'the tag footer moves with the day');
  assert.notEqual(publicationCopy({ genre: 'edit', style: 'melancholic', channelId: 'a' }).captionId,
    publicationCopy({ genre: 'edit', style: 'melancholic', channelId: 'b' }).captionId);
});

test('a caption that does not describe the video is refused, whatever asked for it', () => {
  assert.equal(channelGenre({ game: 'story-comments' }), 'story');
  assert.equal(channelGenre({ id: 'story-comments' }), 'story');
  assert.equal(channelGenre({ game: 'soft-body-slide' }), 'physics');
  assert.equal(channelGenre({ game: 'soft-body-slide', musicProfile: 'original' }), 'physics');
  assert.equal(channelGenre({ game: 'soft-body-slide', musicProfile: 'edit-sad' }), 'edit');
  assert.equal(channelGenre(), 'physics');
  // The two mismatches that actually shipped: the physics channel pinned to
  // the sad deck, and the story channel falling through to the physics deck.
  assert.throws(() => publicationCopy({ genre: 'physics', style: 'melancholic' }),
    /melancholic does not describe a physics video/);
  assert.throws(() => publicationCopy({ genre: 'story', style: 'gameplay' }),
    /gameplay does not describe a story video/);
  assert.throws(() => publicationCopy({ genre: 'edit', style: 'gameplay' }), /does not describe/);
  assert.throws(() => publicationCopy({ genre: 'wildlife' }), /Invalid channel genre/);
  for (const [genre, styles] of Object.entries(GENRE_STYLES)) {
    for (const style of styles) assert.doesNotThrow(() => publicationCopy({ genre, style }));
  }
});

test('the story channel keeps the words of its own episode', () => {
  assert.equal(publicationCopy({ genre: 'story' }), null);
  assert.equal(publicationCopy({ genre: 'story', style: 'manifest' }), null);
  // The deck exists only for the day an episode line would repeat one
  // already published, so it stays in the language the episodes are in and
  // it never claims a series it cannot know about.
  const copy = publicationCopy({ genre: 'story', style: 'story', date: '2026-09-16' });
  assert.ok(CAPTIONS.story.includes(copy.caption));
  assert.deepEqual(copy.tags.filter((tag) => /masque|tentafruit/iu.test(tag)), []);
  assert.equal(copy.tags.length, 4);
});

test('the offset walks the deck so a repeat can be answered with other words', () => {
  const request = { genre: 'physics', channelId: 'softbody-dvlad', date: '2026-09-16' };
  const day = publicationCopy(request);
  assert.deepEqual(publicationCopy({ ...request, offset: 0 }), day);
  const walked = new Set();
  for (let offset = 0; offset < CAPTIONS.gameplay.length; offset += 1) {
    walked.add(publicationCopy({ ...request, offset }).caption);
  }
  assert.equal(walked.size, CAPTIONS.gameplay.length, 'the walk reaches every phrase in the deck');
  assert.throws(() => publicationCopy({ ...request, offset: -1 }), /offset/);
  assert.throws(() => publicationCopy({ ...request, offset: 1.5 }), /offset/);
});

test('invalid caption inputs fail safely instead of dropping attribution', () => {
  assert.throws(() => publicationCopy({ style: 'invalid' }), /style/);
  for (const date of ['2026-02-30', '2026-99-01', '2026-1-1', 'today', null]) {
    assert.throws(() => publicationCopy({ genre: 'edit', style: 'melancholic', date }), /date/);
  }
  assert.throws(() => publicationCopy({ genre: 'edit', style: 'melancholic', seed: NaN }), /seed/);
  assert.throws(() => publicationCopy({
    genre: 'edit', style: 'melancholic', raw: { music_credit: 'x'.repeat(1601) },
  }), /attribution/);
});

test('changing publication wording does not invalidate an expensive completed 3D render', () => {
  const channel = { id: 'softbody-dvlad', game: { game: 'soft-body-slide', duration: 30 } };
  assert.deepEqual(planForDate({ seedNamespace: 'test' }, channel, '2026-09-01'),
    planForDate({ seedNamespace: 'test' }, { ...channel, captionStyle: 'gameplay' }, '2026-09-01'));
});
