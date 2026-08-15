// Fallback set used when ANTHROPIC_API_KEY is not configured.
// Tone is inspired by accounts like @u.s.e.r.0.0.46:
// short, melancholic, contemplative, often in French. Always 1 to 3 lines.

export const FALLBACK_TEXTS: string[] = [
  "Personne ne sait à quel point je suis fatigué de sourire.",
  "Le silence est devenu mon endroit préféré.",
  "On vieillit le jour où on comprend que personne ne viendra.",
  "Il y a des absences qui font plus de bruit que les présences.",
  "Je vais bien.\nEnfin, je crois.",
  "Je me souviens de toi comme on se souvient d'un rêve qu'on n'a pas eu le temps de finir.",
  "Le plus dur, ce n'est pas de partir. C'est de comprendre que personne ne te retient.",
  "On apprend à vivre avec, parce qu'on n'a pas le choix.",
  "Mes meilleures conversations, je les ai eues dans ma tête.",
  "Certains soirs, même la musique fait mal.",
  "J'ai grandi le jour où j'ai arrêté d'attendre une réponse.",
  "On ne perd pas les gens d'un coup.\nOn les perd un message à la fois.",
  "Je crois que j'étais heureux,\nje ne savais juste pas que c'était ça.",
  "Tout le monde te dit « ça va passer ». Personne ne te demande comment tu tiens en attendant.",
  "Le pire ce n'est pas l'absence. C'est l'habitude qu'on prend de l'absence.",
  "Il m'a appris à aimer.\nIl a oublié de m'apprendre à oublier.",
  "Je suis devenu très bon pour faire semblant.",
  "On grandit dans les silences qu'on n'a pas su combler.",
  "Tu me manques, et c'est peut-être tout ce qui me reste de toi.",
  "J'ai compris que parfois, aimer, c'est s'en aller sans claquer la porte."
];

export const STYLE_SYSTEM_PROMPT = `Tu écris des textes courts pour des vidéos TikTok dans le style des comptes mélancoliques/philosophiques comme @u.s.e.r.0.0.46.

Règles strictes :
- En français.
- 1 à 3 lignes maximum (souvent 1 ou 2). Aucune ligne au-dessus de ~70 caractères.
- Ton : contemplatif, doux-amer, intime, jamais grandiloquent.
- Pas d'emojis, pas de hashtags, pas de guillemets autour du texte.
- Pas de morale, pas de "il faut", pas de motivation type LinkedIn.
- Pas de citation d'auteur ni de référence connue.
- Évite les clichés trop usés ("la vie est belle", etc.).
- Phrases simples. Ponctuation minimale. Parfois un retour à la ligne pour rythmer.
- Sujets : la solitude, l'absence, le temps qui passe, les souvenirs, l'amour fini, grandir, le silence, fatigue émotionnelle, mélancolie douce.

Retourne UNIQUEMENT du JSON valide, sans markdown, sans backticks, sous la forme :
{"texts": ["...", "...", ...]}`;

export const HASHTAG_BANK = [
  '#fyp', '#pourtoi', '#foryou', '#foryoupage', '#viralvideo', '#xyzbca',
  '#triste', '#tristesse', '#melancolie', '#solitude', '#nostalgie', '#souvenirs',
  '#philosophie', '#citation', '#citations', '#phrase', '#texte', '#mots', '#poeme',
  '#sad', '#sadvibes', '#sadedit', '#sadtok', '#deeptalks', '#deepquotes',
  '#emotion', '#emotions', '#sentiments', '#coeurbrise', '#rupture', '#manque',
  '#nuit', '#pluie', '#silence', '#reflexion', '#pensee', '#etatdame',
  '#tiktokfrance', '#francetiktok', '#vibe', '#aesthetic', '#dark', '#tristepourtoi'
];
