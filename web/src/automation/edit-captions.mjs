// Original English copy, not quotes from the recordings. A day's choice is
// deterministic; the publisher persists it before attempting either platform.
export const CAPTION_STYLES = ['auto', 'melancholic', 'revenge', 'gameplay', 'manifest', 'story'];
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
  // The story channel writes its own line per episode, so this deck is only
  // drawn from when that line would repeat one already published. It stays
  // in the language the episodes are written in, and it keeps asking for the
  // next move, because the whole format runs on replies.
  story: [
    'Que va-t-il se passer ensuite ?',
    'Dites-nous la suite en commentaire.',
    'Vous auriez fait quoi, à leur place ?',
    'La suite dépend de vos réponses.',
    'On continue dans quelle direction ?',
    'Le prochain choix vous appartient.',
    'Qui devrait ouvrir la porte ?',
    "On s'arrête là ou on continue ?",
    'Votre commentaire décide du prochain épisode.',
    'Personne ne devine jamais la suite.',
    'Il reste une décision à prendre.',
    "Dites-moi ce qu'ils doivent faire.",
    'Le plus voté passe dans le prochain épisode.',
    'Vous sentez venir la suite ?',
    'Un détail change tout dans cet épisode.',
    'On fait confiance à qui maintenant ?',
    'Cette scène a deux fins possibles.',
    'Choisissez, je tourne la suite.',
    'Il y a un piège quelque part.',
    'Racontez-moi comment ça finit.',
    "Personne n'avait vu venir ce passage.",
    'La suite arrive demain, dites-moi quoi.',
    'Vous garderiez le secret, vous ?',
    'Le prochain épisode part de votre réponse.',
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

// A caption has to describe the video it travels with. TikTok lists
// misleading captions and hashtags among the reasons a post never reaches
// the For You feed, and this pipeline made the case on its own account: the
// physics channel was pinned to the sad-edit deck while the story channel
// fell through to the physics deck, so both advertised something the viewer
// was not about to watch. The deck now follows what the render is, and a
// style that does not describe that genre is refused rather than published.
// The first entry is what `auto` resolves to, and the rest is what the
// channel may be pinned to by hand. The story channel leads with its own
// episode copy and only falls back to a deck when that copy would repeat.
export const GENRE_STYLES = Object.freeze({
  physics: ['gameplay'],
  story: ['manifest', 'story'],
  edit: ['melancholic', 'revenge'],
});

export function channelGenre(game = {}) {
  // The dashboard writes `id` and the normalized config writes `game`, and
  // reading only one of them would quietly call every channel physics.
  if ((game?.game ?? game?.id) === 'story-comments') return 'story';
  // Spoken edits are already restricted to soft-body-slide when the config
  // loads, so the music profile is the only thing separating an edit from a
  // plain physics drop.
  if (String(game?.musicProfile || '').startsWith('edit-')) return 'edit';
  return 'physics';
}

// Only reached when an episode's own line would repeat, so these stay
// generic on purpose: the deck cannot know which series is on screen, and a
// series tag that lies about the episode is worse than no series tag.
const STORY_TAGS = Object.freeze([
  ['#histoire', '#storytime', '#serie', '#suite'],
  ['#histoire', '#storytime', '#mystere', '#episode'],
  ['#histoire', '#storytime', '#choisislasuite', '#serie'],
  ['#histoire', '#storytime', '#episode', '#suspense'],
]);

function hash(value) {
  let result = 2166136261;
  for (const char of value) result = Math.imul(result ^ char.charCodeAt(0), 16777619) >>> 0;
  return result;
}

export function publicationCopy({
  style = 'auto', genre = 'physics', channelId = 'preview', date, seed = 1, offset = 0, raw = {},
} = {}) {
  if (!CAPTION_STYLES.includes(style)) throw new Error('Invalid caption style');
  const allowed = GENRE_STYLES[genre];
  if (!allowed) throw new Error(`Invalid channel genre: ${genre}`);
  const mood = raw?.music_profile ?? raw?.musicProfile;
  const resolved = style === 'auto'
    ? genre === 'edit' ? (mood === 'edit-revenge' ? 'revenge' : 'melancholic') : allowed[0]
    : style;
  if (!allowed.includes(resolved)) {
    throw new Error(`Caption style ${resolved} does not describe a ${genre} video`);
  }
  // The story channel writes the episode's own words into the render
  // manifest. Any deck here would replace the episode with a line about
  // something else, which is the exact mismatch this gate exists to stop.
  if (resolved === 'manifest') return null;
  let index = seed;
  if (date !== undefined) {
    if (!/^\d{4}-\d{2}-\d{2}$/u.test(date) || !Number.isFinite(Date.parse(date))
      || new Date(date).toISOString().slice(0, 10) !== date) throw new Error('Invalid caption date');
    index = Math.floor(Date.parse(date) / 86400000);
  }
  if (!Number.isSafeInteger(index)) throw new Error('Invalid caption seed');
  // The offset is how the publisher walks to the next phrase when the day's
  // own phrase would repeat something already posted. Zero keeps the usual
  // deterministic choice, so a retry of the same day lands on the same words.
  if (!Number.isSafeInteger(offset) || offset < 0) throw new Error('Invalid caption offset');
  const deck = CAPTIONS[resolved].map((text, id) => ({ text, id, order: hash(`${channelId}:${resolved}:${id}`) }))
    .sort((a, b) => a.order - b.order || a.id - b.id);
  const selected = deck[(((index + offset) % deck.length) + deck.length) % deck.length];
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
      : resolved === 'story'
        ? STORY_TAGS[((index % STORY_TAGS.length) + STORY_TAGS.length) % STORY_TAGS.length]
        : resolved === 'melancholic'
          ? ['#melancholy', '#latenightthoughts', '#softbody', '#shorts']
          : ['#quietcomeback', '#newchapter', '#softbody', '#shorts'],
  };
}
