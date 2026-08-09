export const GAME_IDS = [
  "ball-escape",
  "shape-tunnel",
  "laser-dodge",
  "boss-battle",
  "soft-body-slide",
] as const;

export type GameId = (typeof GAME_IDS)[number];

export type GameDefinition = {
  id: GameId;
  name: string;
  uiName: string;
  shortName: string;
  description: string;
  objective: string;
  defaultHook: string;
  metricLabel: string;
  uiMetricLabel: string;
  metricMin: number;
  metricMax: number;
  metricStep: number;
  metricDefault: number;
  tags: string[];
  accent: string;
  preview: string;
  engineLabel: string;
};

export const GAME_CATALOG: readonly GameDefinition[] = [
  {
    id: "ball-escape",
    name: "Ball Escape",
    uiName: "Évasion circulaire",
    shortName: "Escape",
    description:
      "Une balle accélère dans un vortex hypnotique dont les anneaux éclatent à chaque passage.",
    objective: "Détruire toute la spirale avant le dernier rebond.",
    defaultHook: "Will the ball escape?",
    metricLabel: "Rings",
    uiMetricLabel: "Anneaux",
    metricMin: 10,
    metricMax: 20,
    metricStep: 1,
    metricDefault: 14,
    tags: ["#ballescape", "#bouncingball"],
    accent: "from-fuchsia-500 to-cyan-400",
    preview: "/game-previews/ball-escape.webp",
    engineLabel: "PHYSIQUE 2D",
  },
  {
    id: "shape-tunnel",
    name: "Organic Escape",
    uiName: "Évasion organique",
    shortName: "Organic",
    description:
      "Une comète rebondit et brise des centaines de couches organiques au rythme des impacts.",
    objective: "Détruire chaque couche pour atteindre l’extérieur.",
    defaultHook: "Will the bouncing ball escape?",
    metricLabel: "Layers",
    uiMetricLabel: "Couches",
    metricMin: 30,
    metricMax: 300,
    metricStep: 10,
    metricDefault: 200,
    tags: ["#bouncingball", "#asmr", "#satisfyingvideo"],
    accent: "from-cyan-400 to-lime-400",
    preview: "/game-previews/organic-escape.webp",
    engineLabel: "ORGANIQUE 2D",
  },
  {
    id: "laser-dodge",
    name: "Laser Dodge",
    uiName: "Esquive laser",
    shortName: "Laser",
    description:
      "Un pilote néon traverse un champ de lasers mobiles avec de véritables détections de collision.",
    objective: "Enchaîner les esquives et survivre au dernier passage.",
    defaultHook: "Can it dodge every laser?",
    metricLabel: "Lasers",
    uiMetricLabel: "Lasers",
    metricMin: 30,
    metricMax: 240,
    metricStep: 10,
    metricDefault: 150,
    tags: ["#laserdodge", "#nearmiss", "#perfecttiming"],
    accent: "from-red-500 via-orange-400 to-cyan-300",
    preview: "/game-previews/laser-dodge.webp",
    engineLabel: "COLLISIONS 2D",
  },
  {
    id: "boss-battle",
    name: "Boss Battle",
    uiName: "Combat de boss",
    shortName: "Boss",
    description:
      "Une arme articulée affronte un Warden blindé dans une arène aux collisions physiques.",
    objective: "Suivre chaque impact et prédire qui survivra au coup critique.",
    defaultHook: "Who wins this physics battle?",
    metricLabel: "Boss HP",
    uiMetricLabel: "PV du boss",
    metricMin: 100,
    metricMax: 500,
    metricStep: 20,
    metricDefault: 300,
    tags: ["#bossbattle", "#battlesimulation", "#whowins"],
    accent: "from-cyan-400 via-violet-500 to-red-500",
    preview: "/game-previews/boss-battle.webp",
    engineLabel: "ARÈNE PHYSIQUE",
  },
  {
    id: "soft-body-slide",
    name: "Soft Body Slide 3D",
    uiName: "Test de souplesse 3D",
    shortName: "Soft Body",
    description:
      "Chaque graine combine une nouvelle forme, rampe, palette, physique et progression de souplesse.",
    objective: "Comparer cinq atterrissages de 0 % à 100 % de souplesse.",
    defaultHook: "0% to 100% softness — which landing is best?",
    metricLabel: "Max softness",
    uiMetricLabel: "Souplesse maximale",
    metricMin: 40,
    metricMax: 100,
    metricStep: 10,
    metricDefault: 100,
    tags: ["#softbody", "#blender3d", "#satisfying"],
    accent: "from-amber-300 via-yellow-500 to-orange-600",
    preview: "/game-previews/soft-body-slide.webp",
    engineLabel: "BLENDER CINÉMA",
  },
] as const;

export function isGameId(value: unknown): value is GameId {
  return (
    typeof value === "string" && (GAME_IDS as readonly string[]).includes(value)
  );
}

export function getGameDefinition(id: GameId): GameDefinition {
  return GAME_CATALOG.find((game) => game.id === id) || GAME_CATALOG[0];
}
