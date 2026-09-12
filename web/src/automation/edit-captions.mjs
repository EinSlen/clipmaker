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
  // The wordless channel had no deck, so publicationCopy returned null
  // for it and the publisher fell back to the one caption baked into the
  // render manifest. Every post carried the same words and the same four
  // tags, which is the shape TikTok calls unoriginal and keeps out of the
  // For You feed. These say nothing about how a drop ends, because the
  // physics decides that fresh on every render.
  gameplay: [
    'guess which one lands before it does.',
    'which softness would you bet on?',
    'five levels of soft, one moving ramp.',
    'softness is the only thing that changes here.',
    'same release, five different bodies.',
    'the ramp never stops moving.',
    'stiff bounces, soft folds.',
    'watch the gold bend.',
    'how soft is too soft?',
    'wait for the hundred.',
    'every level falls differently.',
    'no cuts, no tricks, just softness.',
    'the bounce tells you the softness.',
    'softer does not always mean better.',
    'this is what one hundred percent soft looks like.',
    'physics, but make it soft.',
    'a moving ramp ruins every plan.',
    'the middle levels are the interesting ones.',
    'i could watch the hundred percent all day.',
    'the softest one moves like liquid.',
    'did you call it before the end?',
    'the cup is smaller than it looks.',
    'stiff, firm, soft, softer, gel.',
    'watch what happens at seventy five.',
    'it gets softer every time.',
    'the difference shows up in the last second.',
    'one release, five answers.',
    'the ramp is doing its own thing.',
    'soft body physics never gets old.',
    'which one would you have picked?',
    'the gel level is the best level.',
    'you can see the softness in the bounce.',
    'nothing here is animated by hand.',
    'every drop is simulated, not keyframed.',
    'the whole point is the last one.',
    'guess the landing before it happens.',
  ],
});

// Two tags stay put so the account keeps one address, two move with the
// day so two posts never carry an identical footer.
//
// The fixed pair used to be #softbody, and TikTok's own numbers argued
// against it: #softbodysimulation carries 78.2M views against 12.5M for
// #softbodyphysics, and the search box completes "soft body" into chubby
// body and body trimmer before it reaches anything three dimensional. The
// short form is ambiguous on this platform; the long one is the genre.
const GAMEPLAY_TAGS = Object.freeze([
  ['#softbodysimulation', '#satisfying', '#oddlysatisfying', '#simulation'],
  ['#softbodysimulation', '#satisfying', '#softbodyphysics', '#3danimation'],
  ['#softbodysimulation', '#satisfying', '#simulation', '#blender'],
  ['#softbodysimulation', '#satisfying', '#asmr', '#oddlysatisfying'],
  ['#softbodysimulation', '#satisfying', '#3dart', '#physics'],
  // Public listings for this genre pair #satisfyingvideo with
  // #3danimation. #cinema4d travels with them too and is left out: the
  // renders are Blender, and a tag that lies about the tool is a tag
  // the audience it attracts will bounce off.
  ['#softbodysimulation', '#satisfying', '#satisfyingvideo', '#3danimation'],
]);

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
    tags: resolved === 'gameplay'
      ? GAMEPLAY_TAGS[((index % GAMEPLAY_TAGS.length) + GAMEPLAY_TAGS.length) % GAMEPLAY_TAGS.length]
      : resolved === 'melancholic'
        ? ['#melancholy', '#latenightthoughts', '#softbody', '#shorts']
        : ['#quietcomeback', '#newchapter', '#softbody', '#shorts'],
  };
}
