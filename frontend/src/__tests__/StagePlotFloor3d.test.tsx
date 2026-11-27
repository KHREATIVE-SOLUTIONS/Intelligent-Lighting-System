// The stage plot on the 3D floor: drawn only when calibrated and wanted, at
// its saved opacity, from the authenticated fetch's object URL; it takes no
// ray hits; its texture is disposed and the URL revoked when it changes, goes,
// or the view unmounts. docs/STAGE_PLOT.md, "In the 3D view".
//
// Rendered through react-three-fiber's own reconciler into a real THREE.Scene,
// with a stand-in renderer (jsdom has no WebGL): nothing is drawn to a screen.
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
import { STAGE_PLOT_LIFT, stagePlot3dKey } from '../utils/stagePlot3d';

extend(THREE as never);
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// docs/STAGE_PLOT.md's example: a 600 x 400 px plot turned 90 degrees, 0.02 m a pixel.
const CALIBRATION = {
  point_a: { x: 100, y: 100 }, point_b: { x: 300, y: 100 }, distance_m: 4,
  origin: { x: 200, y: 300 }, rotation_deg: 90, opacity: 0.4,
};
const TRANSFORM = {
  scale_m_per_px: 0.02, rotation_deg: 90, offset_x: 6, offset_z: -4, matrix: [0, 0.02, -0.02, 0, 6, -4],
};
const CALIBRATED = {
  rig_id: 7, present: true, width_px: 600, height_px: 400, calibration: CALIBRATION, transform: TRANSFORM,
};
const UNCALIBRATED = { rig_id: 7, present: true, width_px: 600, height_px: 400, calibration: null, transform: null };

/** Every texture the stand-in loader handed out, with the URL it was asked for. */
let loads: Array<{ url: string; texture: THREE.Texture; dispose: ReturnType<typeof vi.fn> }> = [];
let urlCount = 0;

function fakeRenderer(canvas: HTMLCanvasElement) {
  return {
    render() {}, setPixelRatio() {}, setSize() {}, getPixelRatio: () => 1, dispose() {}, forceContextLoss() {},
    shadowMap: {}, info: { render: {} }, domElement: canvas,
    xr: { addEventListener() {}, removeEventListener() {}, setAnimationLoop() {}, enabled: false, isPresenting: false },
  } as unknown as THREE.WebGLRenderer;
}

/** The 3D page's part in small: the hook, and the plane when it says to draw one. */
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

/** The 2D plan's Stage plot control stands in through its hook: remove and replace are its buttons. */
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

/** Lets the mocked requests answer and the stand-in loader call back. */
async function settle() {
  for (let i = 0; i < 6; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  }
}

const plane = () => scene?.getObjectByName('stage-plot-floor-plane') as THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> | undefined;

describe('StagePlotFloor in the 3D view', () => {
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
      // As an image does: the texture first, the picture a moment later.
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

  it('lays a calibrated plot on the floor at its saved opacity, from the blob URL, placed by the plan matrix', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);

    expect(out.current!.status).toBe('calibrated');
    expect(api.image).toHaveBeenCalledWith(7);
    expect(loads.map((l) => l.url)).toEqual(['blob:plot-1']);
    const mesh = plane()!;
    expect(mesh).toBeDefined();
    expect(mesh.material.map).toBe(loads[0].texture);
    expect(mesh.material.opacity).toBeCloseTo(0.4, 9);
    expect(mesh.material.transparent).toBe(true);
    expect(mesh.material.depthWrite).toBe(false);
    // 600 x 400 px at 0.02 m a pixel: 12 x 8 m, its middle on toPlan(300, 200) = (2, 2), turned a quarter.
    expect(mesh.geometry.parameters.width).toBeCloseTo(12, 9);
    expect(mesh.geometry.parameters.height).toBeCloseTo(8, 9);
    const group = mesh.parent!;
    expect(group.position.x).toBeCloseTo(2, 9);
    expect(group.position.y).toBeCloseTo(STAGE_PLOT_LIFT, 9);
    expect(group.position.z).toBeCloseTo(2, 9);
    expect(group.rotation.y).toBeCloseTo(-Math.PI / 2, 9);
  });

  it('takes no ray hits, so a fixture drag goes through it', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    scene!.updateMatrixWorld(true);
    // Straight down onto the plot's middle.
    const ray = new THREE.Raycaster(new THREE.Vector3(2, 5, 2), new THREE.Vector3(0, -1, 0));
    expect(ray.intersectObject(plane()!, true)).toEqual([]);
    expect(ray.intersectObjects(scene!.children, true)).toEqual([]);
  });

  it('does not draw a plot that is not calibrated', async () => {
    api.info.mockResolvedValue(UNCALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(out.current!.status).toBe('uncalibrated');
    expect(out.current!.floor).toBeNull();
    expect(plane()).toBeUndefined();
    expect(loads).toHaveLength(0);
  });

  it('draws nothing for a rig with no plot', async () => {
    api.info.mockResolvedValue({ rig_id: 7, present: false });
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(out.current!.status).toBe('none');
    expect(plane()).toBeUndefined();
  });

  it('turns off and on with the toggle, remembers the choice per rig, and frees the texture when off', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(plane()).toBeDefined();

    await act(async () => out.current!.setOn(false));
    await settle();
    expect(plane()).toBeUndefined();
    expect(window.localStorage.getItem(stagePlot3dKey(7))).toBe('off');
    expect(loads[0].dispose).toHaveBeenCalled();

    await act(async () => out.current!.setOn(true));
    await settle();
    expect(plane()).toBeDefined();
    expect(window.localStorage.getItem(stagePlot3dKey(7))).toBe('on');
  });

  it('starts off for a rig whose operator turned it off before', async () => {
    window.localStorage.setItem(stagePlot3dKey(7), 'off');
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(out.current!.on).toBe(false);
    expect(plane()).toBeUndefined();
  });

  it('disposes the texture and revokes the blob URL when the view unmounts', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(plane()).toBeDefined();
    await act(async () => root!.unmount());
    root = null;
    expect(loads[0].dispose).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:plot-1');
  });

  it('goes when the 2D plan removes the plot, disposing the texture and revoking the URL', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    api.remove.mockResolvedValue({ removed: true });
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    const twoD = { current: null } as MutableRefObject<StagePlotState | null>;
    await mount(<Harness rigId={7} out={out} twoD={twoD} />);
    expect(plane()).toBeDefined();
    const shown = plane()!.material.map;
    const texture = loads.find((l) => l.texture === shown)!;
    const href = texture.url;

    api.info.mockResolvedValue({ rig_id: 7, present: false });
    await act(async () => { await twoD.current!.remove(); });
    await settle();

    expect(out.current!.status).toBe('none');
    expect(plane()).toBeUndefined();
    expect(texture.dispose).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(href);
  });

  it('shows the new image when the 2D plan replaces the plot, freeing the old one', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    const twoD = { current: null } as MutableRefObject<StagePlotState | null>;
    await mount(<Harness rigId={7} out={out} twoD={twoD} />);
    const old = loads.find((l) => l.texture === plane()!.material.map)!;

    // A replaced image keeps its calibration only if the server says so; here it does, to stay drawn.
    api.upload.mockResolvedValue(CALIBRATED);
    api.image.mockResolvedValue(new Blob(['new png']));
    await act(async () => { await twoD.current!.upload(new File(['x'], 'plot.png', { type: 'image/png' })); });
    await settle();

    const now = plane()!;
    expect(now).toBeDefined();
    expect(now.material.map).not.toBe(old.texture);
    expect(loads.find((l) => l.texture === now.material.map)!.url).not.toBe(old.url);
    expect(old.dispose).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(old.url);
  });

  it('picks up a change announced from another tab', async () => {
    api.info.mockResolvedValue(CALIBRATED);
    const out = { current: null } as MutableRefObject<StagePlot3dState | null>;
    await mount(<Harness rigId={7} out={out} />);
    expect(plane()).toBeDefined();

    api.info.mockResolvedValue({ rig_id: 7, present: false });
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'stagePlotChanged', newValue: JSON.stringify({ rigId: 7, change: 'image', at: 'x' }),
      }));
    });
    await settle();
    expect(plane()).toBeUndefined();
    expect(out.current!.status).toBe('none');
  });
});
