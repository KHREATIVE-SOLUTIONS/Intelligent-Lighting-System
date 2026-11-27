// The stage plot on the 3D floor across a replace and a recalibration: a new
// image the server keeps uncalibrated takes the plane away and frees the old
// texture and blob URL; the calibration saved in the 2D plan brings it back at
// its new place and opacity without a reload. And the toggle, off then on,
// leaves one texture, not two. docs/STAGE_PLOT.md, "In the 3D view".
//
// The harness and stand-ins are those of StagePlotFloor3d.test.tsx.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MutableRefObject } from 'react';
import * as THREE from 'three';
import { act, createRoot, extend } from '@react-three/fiber';
import type { ReconcilerRoot } from '@react-three/fiber';

const api = vi.hoisted(() => ({
  info: vi.fn(),
  image: vi.fn(),
  upload: vi.fn(),
  remove: vi.fn(),
  calibrate: vi.fn(),
}));

vi.mock('../services/stagePlotApi', () => ({
  stagePlotApi: api,
  refusalText: (_error: unknown, fallback: string) => fallback,
}));

import { StagePlotFloor } from '../components/rig/previs/StagePlotFloor';
import useStagePlot3d from '../components/rig/previs/useStagePlot3d';
import type { StagePlot3dState } from '../components/rig/previs/useStagePlot3d';
import useStagePlot from '../components/rig/useStagePlot';
import type { StagePlotState } from '../components/rig/useStagePlot';
import { STAGE_PLOT_LIFT } from '../utils/stagePlot3d';

extend(THREE as never);
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// docs/STAGE_PLOT.md's example: a 600 x 400 px plot turned 90 degrees, 0.02 m a pixel.
const CALIBRATED = {
  rig_id: 7, present: true, width_px: 600, height_px: 400,
  calibration: {
    point_a: { x: 100, y: 100 }, point_b: { x: 300, y: 100 }, distance_m: 4,
    origin: { x: 200, y: 300 }, rotation_deg: 90, opacity: 0.4,
  },
  transform: { scale_m_per_px: 0.02, rotation_deg: 90, offset_x: 6, offset_z: -4, matrix: [0, 0.02, -0.02, 0, 6, -4] },
};
const UNCALIBRATED = { rig_id: 7, present: true, width_px: 600, height_px: 400, calibration: null, transform: null };

// The new image's calibration: not turned, 0.01 m a pixel, at its saved opacity of 0.7.
const RECALIBRATION = {
  point_a: { x: 0, y: 0 }, point_b: { x: 400, y: 0 }, distance_m: 4,
  origin: { x: 0, y: 0 }, rotation_deg: 0, opacity: 0.7,
};
const RETRANSFORM = { scale_m_per_px: 0.01, rotation_deg: 0, offset_x: 1, offset_z: -2, matrix: [0.01, 0, 0, 0.01, 1, -2] };
const RECALIBRATED = { ...UNCALIBRATED, calibration: RECALIBRATION, transform: RETRANSFORM };

let loads: Array<{ url: string; texture: THREE.Texture; dispose: ReturnType<typeof vi.fn> }> = [];
let urlCount = 0;

function fakeRenderer(canvas: HTMLCanvasElement) {
  return {
    render() {}, setPixelRatio() {}, setSize() {}, getPixelRatio: () => 1, dispose() {}, forceContextLoss() {},
    shadowMap: {}, info: { render: {} }, domElement: canvas,
    xr: { addEventListener() {}, removeEventListener() {}, setAnimationLoop() {}, enabled: false, isPresenting: false },
  } as unknown as THREE.WebGLRenderer;
}

function Harness({ rigId, out, twoD }: {
  rigId: number;
  out: MutableRefObject<StagePlot3dState | null>;
  twoD?: MutableRefObject<StagePlotState | null>;
}) {
  const state = useStagePlot3d(rigId, 10, 8);
  out.current = state;
  return (
    <>
      {state.floor && <StagePlotFloor {...state.floor} />}
      {twoD && <TwoD rigId={rigId} out={twoD} />}
    </>
  );
}

function TwoD({ rigId, out }: { rigId: number; out: MutableRefObject<StagePlotState | null> }) {
  out.current = useStagePlot(rigId, 10, 8);
  return null;
}

let root: ReconcilerRoot<HTMLCanvasElement> | null = null;
let scene: THREE.Scene | null = null;

async function mount(element: JSX.Element) {
  const canvas = document.createElement('canvas');
  root = createRoot(canvas);
  await act(async () => {
    root!.configure({
      gl: fakeRenderer(canvas),
      frameloop: 'never',
      size: { width: 200, height: 200, top: 0, left: 0 },
      onCreated: (state) => { scene = state.scene; },
    });
    root!.render(element);
  });
  await settle();
}

async function settle() {
  for (let i = 0; i < 6; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  }
}

const plane = () => scene?.getObjectByName('stage-plot-floor-plane') as THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> | undefined;
const shownLoad = () => loads.find((l) => l.texture === plane()?.material.map);
const liveTextures = () => loads.filter((l) => l.dispose.mock.calls.length === 0);

describe('StagePlotFloor in the 3D view, replaced and recalibrated', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    loads = [];
    urlCount = 0;
    window.localStorage.clear();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true, writable: true, value: vi.fn(() => { urlCount += 1; return `blob:plot-${urlCount}`; }),
    });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
    vi.spyOn(THREE.TextureLoader.prototype, 'load').mockImplementation(function load(url, onLoad) {
      const texture = new THREE.Texture();
      const dispose = vi.fn();
      texture.dispose = dispose;
      loads.push({ url, texture, dispose });
      setTimeout(() => onLoad?.(texture), 0);
      return texture;
    });
    api.image.mockResolvedValue(new Blob(['png']));
  });

  afterEach(async () => {
    if (root) await act(async () => root!.unmount());
    root = null;
    scene = null;
    vi.restoreAllMocks();
  });

  it('goes when a replaced image comes back uncalibrated, and returns at the new calibration once it is saved', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    const twoD = { current: null } as MutableRefObject<StagePlotState | null>;
    await mount(<Harness rigId={7} out={out} twoD={twoD} />);
    const old = shownLoad()!;
    expect(old).toBeDefined();

    // Replace: the server keeps no calibration for the new image.
    api.upload.mockResolvedValue(UNCALIBRATED);
    api.info.mockResolvedValue(UNCALIBRATED);
    api.image.mockResolvedValue(new Blob(['new png']));
    await act(async () => { await twoD.current!.upload(new File(['x'], 'plot.png', { type: 'image/png' })); });
    await settle();

    expect(out.current!.status).toBe('uncalibrated');
    expect(out.current!.floor).toBeNull();
    expect(plane()).toBeUndefined();
    expect(old.dispose).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(old.url);
    expect(liveTextures()).toHaveLength(0);

    // Calibrate in the 2D plan: three points, a distance, the opacity, Save.
    api.calibrate.mockResolvedValue({ calibration: RECALIBRATION, transform: RETRANSFORM });
    api.info.mockResolvedValue(RECALIBRATED);
    await act(async () => twoD.current!.startCalibrate());
    for (const [x, z] of [[-3, -2], [1, -2], [-3, 1]] as const) {
      await act(async () => twoD.current!.onPlanPick!(x, z));
    }
    await act(async () => {
      twoD.current!.setDistance('4');
      twoD.current!.setOpacity(0.7);
    });
    await act(async () => { await twoD.current!.saveCalibration(); });
    await settle();

    expect(api.calibrate).toHaveBeenCalledTimes(1);
    expect(out.current!.status).toBe('calibrated');
    const mesh = plane()!;
    expect(mesh).toBeDefined();
    expect(mesh.material.opacity).toBeCloseTo(0.7, 9);
    // 600 x 400 px at 0.01 m a pixel: 6 x 4 m, its middle on toPlan(300, 200) = (4, 0), not turned.
    expect(mesh.geometry.parameters.width).toBeCloseTo(6, 9);
    expect(mesh.geometry.parameters.height).toBeCloseTo(4, 9);
    const group = mesh.parent!;
    expect(group.position.x).toBeCloseTo(4, 9);
    expect(group.position.y).toBeCloseTo(STAGE_PLOT_LIFT, 9);
    expect(group.position.z).toBeCloseTo(0, 9);
    expect(group.rotation.y).toBeCloseTo(0, 9);
    // From the new image, not the freed one; the only texture alive.
    const now = shownLoad()!;
    expect(now.url).not.toBe(old.url);
    expect(liveTextures()).toEqual([now]);
  });

  it('keeps one texture through the toggle off and on: the old one freed, the image not fetched again', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(loads).toHaveLength(1);

    await act(async () => out.current!.setOn(false));
    await settle();
    expect(plane()).toBeUndefined();
    expect(liveTextures()).toHaveLength(0);

    await act(async () => out.current!.setOn(true));
    await settle();
    expect(plane()).toBeDefined();
    expect(loads).toHaveLength(2);
    expect(liveTextures()).toEqual([loads[1]]);
    expect(plane()!.material.map).toBe(loads[1].texture);
    // The same object URL, kept by the hook that made it: not revoked, not made again.
    expect(loads[1].url).toBe(loads[0].url);
    expect(api.image).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });
});
