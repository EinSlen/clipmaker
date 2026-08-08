export const GAME_IDS = ['ball-escape', 'shape-tunnel', 'boss-battle', 'melody-drop'] as const;

export type GameId = (typeof GAME_IDS)[number];

export type GameDefinition = {
  id: GameId;
  name: string;
  shortName: string;
  description: string;
  defaultHook: string;
  metricLabel: string;
  metricMin: number;
  metricMax: number;
  metricStep: number;
  metricDefault: number;
  tags: string[];
  accent: string;
};

export const GAME_CATALOG: readonly GameDefinition[] = [
  {
    id: 'ball-escape',
    name: 'Ball Escape',
    shortName: 'Escape',
    description: 'A gravity-driven ball accelerates through rotating neon rings.',
    defaultHook: 'Will the ball escape?',
    metricLabel: 'Rings',
    metricMin: 40,
    metricMax: 300,
    metricStep: 10,
    metricDefault: 240,
    tags: ['#ballescape', '#bouncingball'],
    accent: 'from-fuchsia-500 to-cyan-400',
  },
  {
    id: 'shape-tunnel',
    name: 'Shape Tunnel',
    shortName: 'Tunnel',
    description: 'A glowing comet cuts through collapsing, music-reactive shapes.',
    defaultHook: 'Can it reach the center?',
    metricLabel: 'Layers',
    metricMin: 30,
    metricMax: 240,
    metricStep: 10,
    metricDefault: 160,
    tags: ['#shapetunnel', '#oddlysatisfying'],
    accent: 'from-cyan-400 to-lime-400',
  },
  {
    id: 'boss-battle',
    name: 'Boss Battle',
    shortName: 'Battle',
    description: 'Two procedural fighters trade critical hits in a compact arena.',
    defaultHook: 'Who wins this battle?',
    metricLabel: 'Boss HP',
    metricMin: 100,
    metricMax: 500,
    metricStep: 20,
    metricDefault: 300,
    tags: ['#bossbattle', '#simulationgame'],
    accent: 'from-orange-500 to-red-500',
  },
  {
    id: 'melody-drop',
    name: 'Melody Drop',
    shortName: 'Melody',
    description: 'Every gravity bounce unlocks the next note of an original melody.',
    defaultHook: 'Can you guess the melody?',
    metricLabel: 'Notes',
    metricMin: 24,
    metricMax: 180,
    metricStep: 6,
    metricDefault: 96,
    tags: ['#melodydrop', '#musicgame'],
    accent: 'from-violet-500 to-pink-500',
  },
] as const;

export function isGameId(value: unknown): value is GameId {
  return typeof value === 'string' && (GAME_IDS as readonly string[]).includes(value);
}

export function getGameDefinition(id: GameId): GameDefinition {
  return GAME_CATALOG.find((game) => game.id === id) || GAME_CATALOG[0];
}
