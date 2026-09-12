import assert from 'node:assert/strict';
import test from 'node:test';
import { CAPTIONS, publicationCopy } from './edit-captions.mjs';
import { planForDate } from './orchestrator.mjs';

test('each caption deck is original, unique and fits both platforms with full credits', () => {
  assert.equal(CAPTIONS.melancholic.length, 48);
  assert.equal(CAPTIONS.revenge.length, 24);
  for (const [style, deck] of Object.entries(CAPTIONS)) {
    assert.equal(new Set(deck).size, deck.length);
    const seen = new Set();
    for (let day = 0; day < deck.length; day++) {
      const date = new Date(Date.UTC(2026, 7, 31 + day)).toISOString().slice(0, 10);
      const input = { style, channelId: 'softbody-dvlad', date, raw: { music_credit: 'C'.repeat(1600) } };
      const copy = publicationCopy(input);
      assert.deepEqual(copy, publicationCopy(input));
      assert.ok(copy.youtubeTitle.length <= 100);
      assert.ok([copy.caption, ...copy.tags].join(' ').length <= 2000);
      assert.ok(copy.caption.endsWith('C'.repeat(1600)));
      // The wordless deck asks questions on purpose: a question invites
      // a reply, and replies are what the feed counts.
      assert.match(copy.caption.split('\n')[0], /^[a-z ?.,]+$/u);
      seen.add(copy.captionId);
    }
    assert.equal(seen.size, deck.length, 'no repeated phrase within a full daily cycle');
  }
});

test('auto follows the selected recording mood, and the wordless mix gets its own deck', () => {
  for (const moodKey of ['music_profile', 'musicProfile']) {
    for (const creditKey of ['music_credit', 'musicCredit']) {
      const raw = { [moodKey]: 'edit-sad', [creditKey]: 'Film credit / CC BY 3.0 / excerpt' };
      assert.equal(publicationCopy({ raw }).captionStyle, 'melancholic');
      assert.equal(publicationCopy({ raw }).caption.split('\n\n')[1], raw[creditKey]);
      assert.equal(publicationCopy({ raw: { ...raw, [moodKey]: 'edit-revenge' } }).captionStyle, 'revenge');
      assert.equal(publicationCopy({ style: 'gameplay', raw }).captionStyle, 'gameplay');
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
  assert.notEqual(publicationCopy({ style: 'melancholic', channelId: 'a' }).captionId,
    publicationCopy({ style: 'melancholic', channelId: 'b' }).captionId);
});

test('invalid caption inputs fail safely instead of dropping attribution', () => {
  assert.throws(() => publicationCopy({ style: 'invalid' }), /style/);
  for (const date of ['2026-02-30', '2026-99-01', '2026-1-1', 'today', null]) {
    assert.throws(() => publicationCopy({ style: 'melancholic', date }), /date/);
  }
  assert.throws(() => publicationCopy({ style: 'melancholic', seed: NaN }), /seed/);
  assert.throws(() => publicationCopy({ style: 'melancholic', raw: { music_credit: 'x'.repeat(1601) } }), /attribution/);
});

test('changing publication wording does not invalidate an expensive completed 3D render', () => {
  const channel = { id: 'softbody-dvlad', game: { game: 'soft-body-slide', duration: 30 } };
  assert.deepEqual(planForDate({ seedNamespace: 'test' }, channel, '2026-09-01'),
    planForDate({ seedNamespace: 'test' }, { ...channel, captionStyle: 'melancholic' }, '2026-09-01'));
});
