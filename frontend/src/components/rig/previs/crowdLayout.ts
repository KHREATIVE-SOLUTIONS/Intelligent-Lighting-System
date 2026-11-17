/**
 * Who stands where on the dance floor.
 *
 * Seeded, so the same room always gets the same crowd: nobody jumps to a new
 * spot when the view re-renders or the quality mode is switched back.
 */
import { seededRandom } from './geometryKit';
import type { ClubLayout } from './layout';

export type CrowdPerson = {
  x: number;
  z: number;
  /** Facing, as a rotation about Y; 0 faces +Z. */
  yaw: number;
  /** Height in metres. */
  height: number;
  /** Timing offset in beats: nobody is exactly on the beat. */
  phase: number;
  /** 1 moves on every beat, 0.5 on every other. */
  rate: number;
  /** How big this person's movement is, around 1. */
  amp: number;
  /** Arms go up once the room's energy passes this. */
  armsAbove: number;
  /** Jumps in a drop rather than just bouncing. */
  jumper: boolean;
  /** Offset for the slow idle sway. */
  idle: number;
  /** Shoulder width relative to the model, around 1. */
  build: number;
  /** Long sleeves: arms take the shirt colour rather than the skin tone. */
  sleeves: boolean;
  shirt: string;
  skin: string;
  hair: string;
};

const SHIRTS = [
  '#2b2d36', '#3a3f4d', '#4a2b33', '#27384a', '#3d4436', '#55575f',
  '#8c8f97', '#b9bcc4', '#5a3a2a', '#2f4a44', '#6b2f3d', '#33325a',
];
const SKINS = ['#c99776', '#b98566', '#a06e52', '#84573f', '#6a4431', '#d6a888'];
const HAIRS = [
  '#17120f', '#17120f', '#241812', '#3a2618', '#5a3d24', '#8a6a3c',
  '#b99a5c', '#6e2a1c', '#55585f', '#2a3550', '#7a2f5a', '#c9c2b4',
];

/** People per square metre the floor is allowed to hold. */
const MAX_DENSITY = 2.6;
/** Elbow room: closer than this to someone already placed is a miss. */
const SPACING_AT_BOOTH = 0.43;
const SPACING_AT_BACK = 0.88;

/** How many people fit, whatever the quality mode asks for. */
export function crowdCapacity(layout: ClubLayout): number {
  const { xMin, xMax, zMin, zMax } = layout.danceFloor;
  return Math.max(0, Math.floor((xMax - xMin) * (zMax - zMin) * MAX_DENSITY));
}

export function placeCrowd(layout: ClubLayout, requested: number): CrowdPerson[] {
  const { xMin, xMax, zMin, zMax } = layout.danceFloor;
  const width = xMax - xMin;
  const depth = zMax - zMin;
  const target = Math.min(Math.max(0, Math.floor(requested)), crowdCapacity(layout));
  if (target === 0 || width <= 0 || depth <= 0) return [];

  const random = seededRandom(0x5eed + Math.round(width * 100) * 31 + Math.round(depth * 100));
  const camera = layout.floorCamera;
  const people: CrowdPerson[] = [];
  const margin = 0.28;

  for (let attempt = 0; attempt < target * 60 && people.length < target; attempt += 1) {
    // Biased toward the booth: the front of a dance floor is always the
    // tightest and it thins out toward the back.
    const along = Math.pow(random(), 1.9);
    const x = xMin + margin + random() * (width - margin * 2);
    const z = zMin + margin + along * (depth - margin * 2);

    if (Math.hypot(x - camera.x, z - camera.z) < camera.clearRadius) continue;

    const spacing = SPACING_AT_BOOTH + (SPACING_AT_BACK - SPACING_AT_BOOTH) * along;
    let clear = true;
    for (const other of people) {
      if (Math.abs(other.x - x) < spacing && Math.abs(other.z - z) < spacing
        && Math.hypot(other.x - x, other.z - z) < spacing) {
        clear = false;
        break;
      }
    }
    if (!clear) continue;

    // Face the booth, turned in a little toward the DJ, give or take.
    const toBoothX = -x * 0.55;
    const toBoothZ = layout.booth.fasciaZ - z;
    const yaw = Math.atan2(toBoothX, toBoothZ) + (random() - 0.5) * 0.5;

    people.push({
      x,
      z,
      yaw,
      height: 1.56 + random() * 0.34,
      phase: (random() - 0.5) * 0.14,
      rate: random() < 0.14 ? 0.5 : 1,
      amp: 0.6 + random() * 0.8,
      armsAbove: 0.66 + random() * 0.5,
      jumper: random() < 0.45,
      idle: random() * Math.PI * 2,
      build: 0.88 + random() * 0.28,
      sleeves: random() < 0.45,
      shirt: SHIRTS[Math.floor(random() * SHIRTS.length)],
      skin: SKINS[Math.floor(random() * SKINS.length)],
      hair: HAIRS[Math.floor(random() * HAIRS.length)],
    });
  }

  return people;
}
