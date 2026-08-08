export const GAME_IDS = [
  'ball-escape',
  'shape-tunnel',
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
    name: 'Organic Escape',
    shortName: 'Organic',
    description: 'A gravity-curved comet breaks hundreds of nested organic layers with tuned ASMR hits.',
    defaultHook: 'Will the bouncing ball escape?',
    metricLabel: 'Layers',
    metricMin: 30,
    metricMax: 300,
    metricStep: 10,
    metricDefault: 200,
    tags: ['#bouncingball', '#asmr', '#satisfyingvideo'],
    accent: 'from-cyan-400 to-lime-400',
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
