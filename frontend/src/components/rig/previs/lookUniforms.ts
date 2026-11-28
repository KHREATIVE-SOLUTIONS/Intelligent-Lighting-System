/**
 * The look controls as shader uniforms, shared by every material they affect
 * (docs/PREVIZ_LOOK.md).
 *
 * One object per view, made once. The beam, pool and haze materials hold these
 * very uniform objects, so moving the Haze slider writes one number and every
 * material sees it on the next frame, with nothing re-rendered through React.
 */
import * as THREE from 'three';
import { DEFAULT_HAZE } from './beamLook';

export type LookUniforms = {
  /** 0 clean air to 1 thick haze. */
  haze: { value: number };
  /** 1 for soft beams, 0 for the flat beam. */
  softBeams: { value: number };
  /** 1 to draw gobos in the pools, 0 for open pools. */
  gobos: { value: number };
  /** Seconds, for the drifting haze. */
  time: { value: number };
  /** The rig's light this frame, averaged: what the drifting haze is lit by. */
  rigGlow: { value: THREE.Color };
};

export function createLookUniforms(): LookUniforms {
  return {
    haze: { value: DEFAULT_HAZE },
    softBeams: { value: 1 },
    gobos: { value: 1 },
    time: { value: 0 },
    rigGlow: { value: new THREE.Color(0, 0, 0) },
  };
}
