export const GAME_IDS = [
  'ball-escape',
  'shape-tunnel',
  'boss-battle',
  'melody-drop',
  'color-switch',
  'orbit-merge',
  'laser-dodge',
  'brick-cascade',
  'soft-body-slide',
] as const;

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
  {
    id: 'color-switch',
    name: 'Color Switch',
    shortName: 'Switch',
    description: 'A color-changing ball must cross the matching slice of every gate.',
    defaultHook: 'Can it match every color?',
    metricLabel: 'Gates',
    metricMin: 24,
    metricMax: 180,
    metricStep: 6,
    metricDefault: 96,
    tags: ['#colorswitch', '#perfecttiming'],
    accent: 'from-yellow-400 via-pink-500 to-cyan-400',
  },
  {
    id: 'orbit-merge',
    name: 'Orbit Merge',
    shortName: 'Orbit',
    description: 'Orbiting particles collide and merge into an ever-growing neon planet.',
    defaultHook: 'How big can this planet get?',
    metricLabel: 'Merges',
    metricMin: 30,
    metricMax: 240,
    metricStep: 10,
    metricDefault: 140,
    tags: ['#orbitmerge', '#spacegame'],
    accent: 'from-blue-500 via-violet-500 to-fuchsia-500',
  },
  {
    id: 'laser-dodge',
    name: 'Laser Dodge',
    shortName: 'Dodge',
    description: 'A tiny runner accelerates through a rotating field of closing lasers.',
    defaultHook: 'One touch and it is over!',
    metricLabel: 'Lasers',
    metricMin: 30,
    metricMax: 240,
    metricStep: 10,
    metricDefault: 150,
    tags: ['#laserdodge', '#closecall'],
    accent: 'from-red-500 via-orange-400 to-yellow-300',
  },
  {
    id: 'brick-cascade',
    name: 'Brick Cascade',
    shortName: 'Cascade',
    description: 'One impact triggers a fast, colorful domino chain reaction.',
    defaultHook: 'Do not blink at the last row!',
    metricLabel: 'Bricks',
    metricMin: 40,
    metricMax: 320,
    metricStep: 10,
    metricDefault: 200,
    tags: ['#brickcascade', '#chainreaction'],
    accent: 'from-lime-400 via-emerald-400 to-cyan-400',
  },
  {
    id: 'soft-body-slide',
    name: 'Soft Body Slide 3D',
    shortName: 'Soft Body',
    description: 'Premium Blender scene with studio lighting, metallic materials and procedural deformation.',
    defaultHook: '0% vs 100% softness — what happens?',
    metricLabel: 'Softness',
    metricMin: 0,
    metricMax: 100,
    metricStep: 10,
    metricDefault: 100,
    tags: ['#softbody', '#blender3d', '#3dsimulation'],
    accent: 'from-amber-300 via-yellow-500 to-orange-600',
  },
] as const;

export function isGameId(value: unknown): value is GameId {
  return typeof value === 'string' && (GAME_IDS as readonly string[]).includes(value);
}

export function getGameDefinition(id: GameId): GameDefinition {
  return GAME_CATALOG.find((game) => game.id === id) || GAME_CATALOG[0];
}
