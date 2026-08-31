// Original English copy, not quotes from the recordings. A day's choice is
// deterministic; the publisher persists it before attempting either platform.
export const CAPTION_STYLES = ['auto', 'melancholic', 'revenge', 'gameplay'];
export const CAPTIONS = Object.freeze({
  melancholic: [
    'some feelings outlive the goodbye.',
    'the quiet part is always the loudest.',
    'a familiar song. a different life.',
    'some places still feel like someone.',
    'nothing happened today. i still thought of you.',
    'we stopped talking. the memories did not.',
    'missing the ordinary days we never took pictures of.',
    'the hardest part was getting used to the silence.',
    'sometimes a small thing brings everything back.',
    'not every goodbye happens out loud.',
    'the room stayed the same. everything else changed.',
    'some nights are just old memories in a new order.',
    'you can move on and still miss a moment.',
    'a little less hurt. a little more distance.',
    'it was ordinary then. it means everything now.',
    'there are people you remember in the smallest things.',
    'the days moved forward. the feeling took its time.',
    'sometimes healing looks like a quiet evening.',
    'one day, remembering will feel softer.',
    'old conversations have a way of finding quiet nights.',
    'some chapters stay with you after they end.',
    'no grand ending. just two lives growing apart.',
    'a thousand little reminders. not one good reason to call.',
    'the almosts have a sound of their own.',
    'i miss how simple it felt before i knew it would end.',
    'some memories arrive before you are ready.',
    'the distance was easy to measure. the missing was not.',
    'a different street. the same feeling.',
    'learning to leave a little room for the present.',
    'some things fade slowly, and that is okay.',
    'the moment passed. the warmth stayed.',
    'i hope the next memory hurts a little less.',
    'there is a strange kindness in letting time pass.',
    'sometimes you miss the person you were back then.',
    'a memory can feel close even when a person is far away.',
    'the words came later, when there was nobody to tell.',
    'some evenings feel like the end of a long summer.',
    'the things we never said found a home in the silence.',
    'it is strange how much a small moment can hold.',
    'i am not waiting. i am just still remembering.',
    'a gentle reminder that not everything lasts forever.',
    'we never knew which ordinary day would be the last.',
    'some feelings take the long way home.',
    'the goodbye was a moment. letting go took longer.',
    'making peace with a story that ended differently.',
    'i still remember the way that day felt.',
    'a little nostalgia for a life that used to be yours.',
    'maybe tomorrow the silence will feel like peace.',
  ],
  revenge: [
    'let the next chapter speak for itself.',
    'quiet progress still counts.',
    'not everything deserves a reaction.',
    'some endings make room for a better beginning.',
    'a little less explaining. a little more becoming.',
    'the energy went back into building a life.',
    'no announcement. just a different direction.',
    'the comeback can be quiet.',
    'turning that feeling into one more step forward.',
    'there is strength in choosing what comes next.',
    'outgrowing the need to prove a point.',
    'some answers take the shape of a better life.',
    'the next move does not need an audience.',
    'a closed door is not the whole story.',
    'you can start again without asking permission.',
    'keeping the lesson. leaving the rest.',
    'less noise. more purpose.',
    'the old version does not get the final word.',
    'choosing progress over another explanation.',
    'some things are better answered by moving forward.',
    'making something good out of a difficult chapter.',
    'one quiet decision can change the direction.',
    'the strongest reply might be a peaceful life.',
    'new boundaries. new beginnings.',
  ],
});

function hash(value) {
  let result = 2166136261;
  for (const char of value) result = Math.imul(result ^ char.charCodeAt(0), 16777619) >>> 0;
  return result;
}

export function publicationCopy({ style = 'auto', channelId = 'preview', date, seed = 1, raw = {} } = {}) {
  if (!CAPTION_STYLES.includes(style)) throw new Error('Invalid caption style');
  const mood = raw?.music_profile ?? raw?.musicProfile;
  const resolved = style === 'auto'
    ? mood === 'edit-revenge' ? 'revenge' : mood === 'edit-sad' ? 'melancholic' : 'gameplay'
    : style;
  if (resolved === 'gameplay') return null;
  let index = seed;
  if (date !== undefined) {
    if (!/^\d{4}-\d{2}-\d{2}$/u.test(date) || !Number.isFinite(Date.parse(date))
      || new Date(date).toISOString().slice(0, 10) !== date) throw new Error('Invalid caption date');
    index = Math.floor(Date.parse(date) / 86400000);
  }
  if (!Number.isSafeInteger(index)) throw new Error('Invalid caption seed');
  const deck = CAPTIONS[resolved].map((text, id) => ({ text, id, order: hash(`${channelId}:${resolved}:${id}`) }))
    .sort((a, b) => a.order - b.order || a.id - b.id);
  const selected = deck[((index % deck.length) + deck.length) % deck.length];
  const attribution = raw?.music_credit ?? raw?.musicCredit;
  const credit = typeof attribution === 'string' ? attribution.trim() : '';
  // Credits are never dropped or truncated by the platform adapters.
  if (credit.length > 1600) throw new Error('Audio attribution exceeds caption budget');
  return {
    captionStyle: resolved, captionId: `${resolved}-v1-${selected.id}`,
    youtubeTitle: `${selected.text} #shorts`,
    caption: [selected.text, credit].filter(Boolean).join('\n\n'),
    tags: resolved === 'melancholic'
      ? ['#melancholy', '#latenightthoughts', '#softbody', '#shorts']
      : ['#quietcomeback', '#newchapter', '#softbody', '#shorts'],
  };
}
