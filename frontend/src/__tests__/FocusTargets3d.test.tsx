// The focus targets in the 3D view (docs/FOCUS_PRESETS.md, "In the app"): off
// until the operator turns them on, the choice kept per rig; a marker per
// placed target whose look says who can reach it; no ray hits, so a fixture
// drag goes through; and a target added or removed through the panel's hook
// appears on or goes from the view without a reload.
//
// Rendered through react-three-fiber's own reconciler into a real THREE.Scene,
// with a stand-in renderer (jsdom has no WebGL), as StagePlotFloor3d.test does.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MutableRefObject } from 'react';
import * as THREE from 'three';
import { act, createRoot, extend } from '@react-three/fiber';
import type { ReconcilerRoot } from '@react-three/fiber';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const api = vi.hoisted(() => ({ get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() }));
vi.mock('../services/focusPresetsApi', () => ({ focusPresetsApi: api }));
vi.mock('../services/stagePlotApi', () => ({ refusalText: (_error: unknown, fallback: string) => fallback }));

import { FOCUS_MARKER_MIN_Y, FocusTargetMarkers, buildFocusMarkers } from '../components/rig/previs/FocusTargetMarkers';
import FocusTargets3dToggle from '../components/rig/previs/FocusTargets3dToggle';
import useFocusTargets3d from '../components/rig/previs/useFocusTargets3d';
import type { FocusTargets3dState } from '../components/rig/previs/useFocusTargets3d';
import useFocusPresets from '../components/rig/useFocusPresets';
import type { FocusPresetsState } from '../components/rig/useFocusPresets';
import { focusTargets3dKey, parseFocusPresets } from '../utils/focusPresets';
import { focusAnswer } from './focusPresetsFixture';

extend(THREE as never);
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** The answer the server gives now: with or without the custom "Mirror ball" (red: no head reaches it). */
let withMirror = true;
function currentTable() {
  const answer = focusAnswer();
  if (!withMirror) {
    answer.targets = answer.targets.filter((t) => t.key !== 'custom_4');
    answer.custom_targets = [];
  }
  return parseFocusPresets(answer);
}

function fakeRenderer(canvas: HTMLCanvasElement) {
  return {
    render() {}, setPixelRatio() {}, setSize() {}, getPixelRatio: () => 1, dispose() {}, forceContextLoss() {},
    shadowMap: {}, info: { render: {} }, domElement: canvas,
    xr: { addEventListener() {}, removeEventListener() {}, setAnimationLoop() {}, enabled: false, isPresenting: false },
  } as unknown as THREE.WebGLRenderer;
}

/** The 3D page's part in small, and the Focus presets panel standing in through its hook. */
function Harness({ out, panel }: {
  out: MutableRefObject<FocusTargets3dState | null>;
  panel?: MutableRefObject<FocusPresetsState | null>;
}) {
  const state = useFocusTargets3d(7);
  out.current = state;
  return (
    <>
      {state.markers.length > 0 && <FocusTargetMarkers markers={state.markers} />}
      {panel && <Panel out={panel} />}
    </>
  );
}

function Panel({ out }: { out: MutableRefObject<FocusPresetsState | null> }) {
  out.current = useFocusPresets(7);
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

const mesh = (style: string) => scene?.getObjectByName(`focus-targets-${style}`) as THREE.Mesh | undefined;

describe('focus targets in the 3D view', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    window.localStorage.clear();
    withMirror = true;
    api.get.mockImplementation(async () => currentTable());
  });

  afterEach(async () => {
    if (root) await act(async () => root!.unmount());
    root = null;
    scene = null;
  });

  it('is off until the operator turns it on, and reads nothing while off', async () => {
    const out = { current: null } as MutableRefObject<FocusTargets3dState | null>;
    await mount(<Harness out={out} />);
    expect(out.current!.available).toBe(true);
    expect(out.current!.on).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
    expect(scene!.getObjectByName('focus-targets')).toBeUndefined();
  });

  it('marks the targets by who can reach them once turned on, and remembers it for the rig', async () => {
    const out = { current: null } as MutableRefObject<FocusTargets3dState | null>;
    await mount(<Harness out={out} />);
    await act(async () => out.current!.setOn(true));
    await settle();

    expect(window.localStorage.getItem(focusTargets3dKey(7))).toBe('on');
    expect(api.get).toHaveBeenCalledWith(7);
    // Dance floor and audience: all reach. DJ booth: some cannot. Mirror ball: none can.
    expect(out.current!.markers.map((m) => [m.key, m.style])).toEqual([
      ['dj_booth', 'some'], ['dance_floor', 'all'], ['audience', 'all'], ['custom_4', 'none'],
    ]);
    expect(mesh('all')).toBeDefined();
    expect(mesh('some')).toBeDefined();
    expect(mesh('none')).toBeDefined();
    expect(mesh('idle')).toBeUndefined();
    // A different look each: shape as well as colour.
    const colour = (style: string) => {
      const attr = (mesh(style)!.geometry as THREE.BufferGeometry).getAttribute('color');
      return [attr.getX(0), attr.getY(0), attr.getZ(0)].map((v) => v.toFixed(3)).join(',');
    };
    expect(new Set([colour('all'), colour('some'), colour('none')]).size).toBe(3);

    await act(async () => out.current!.setOn(false));
    await settle();
    expect(window.localStorage.getItem(focusTargets3dKey(7))).toBe('off');
    expect(scene!.getObjectByName('focus-targets')).toBeUndefined();
  });

  it('starts on for a rig whose operator turned it on before', async () => {
    window.localStorage.setItem(focusTargets3dKey(7), 'on');
    const out = { current: null } as MutableRefObject<FocusTargets3dState | null>;
    await mount(<Harness out={out} />);
    expect(out.current!.on).toBe(true);
    expect(mesh('all')).toBeDefined();
  });

  it('takes no ray hits, so a fixture drag goes through the markers', async () => {
    window.localStorage.setItem(focusTargets3dKey(7), 'on');
    const out = { current: null } as MutableRefObject<FocusTargets3dState | null>;
    await mount(<Harness out={out} />);
    scene!.updateMatrixWorld(true);
    // Straight down onto the dance floor centre's marker, and onto the DJ booth's.
    for (const [x, z] of [[0, 1.5], [0, -3.5]]) {
      const ray = new THREE.Raycaster(new THREE.Vector3(x, 8, z), new THREE.Vector3(0, -1, 0));
      expect(ray.intersectObjects(scene!.children, true)).toEqual([]);
    }
  });

  it('follows a target added and removed in the panel, without a reload', async () => {
    window.localStorage.setItem(focusTargets3dKey(7), 'on');
    withMirror = false;
    api.addTarget.mockResolvedValue({ target: { id: 4 } });
    api.removeTarget.mockResolvedValue({ removed: 4 });
    const out = { current: null } as MutableRefObject<FocusTargets3dState | null>;
    const panel = { current: null } as MutableRefObject<FocusPresetsState | null>;
    await mount(<Harness out={out} panel={panel} />);
    expect(mesh('none')).toBeUndefined();

    withMirror = true;
    await act(async () => { await panel.current!.add({ name: 'Mirror ball', x: 1, y: 4.5, z: 0 }); });
    await settle();
    expect(out.current!.markers.some((m) => m.key === 'custom_4')).toBe(true);
    expect(mesh('none')).toBeDefined();

    withMirror = false;
    await act(async () => { await panel.current!.remove(4); });
    await settle();
    expect(out.current!.markers.some((m) => m.key === 'custom_4')).toBe(false);
    expect(mesh('none')).toBeUndefined();
  });
});

describe('buildFocusMarkers', () => {
  it('lifts a target on the floor a little, and draws nothing for no markers', () => {
    const built = buildFocusMarkers([{ key: 'k', name: 'Floor', style: 'all', at: [2, 0, 1], line: null }]);
    expect(built.some).toBeNull();
    const box = built.all!.boundingBox!;
    expect(box.min.y).toBeGreaterThan(0);
    expect((box.min.y + box.max.y) / 2).toBeCloseTo(FOCUS_MARKER_MIN_Y, 6);
    expect(Object.values(buildFocusMarkers([])).every((g) => g === null)).toBe(true);
  });

  it('draws the audience line between its ends', () => {
    const built = buildFocusMarkers([
      { key: 'audience', name: 'Audience', style: 'all', at: [0, 1.7, 1.5], line: [[-3, 1.7, 1.5], [3, 1.7, 1.5]] },
    ]);
    const box = built.all!.boundingBox!;
    expect(box.min.x).toBeCloseTo(-3, 1);
    expect(box.max.x).toBeCloseTo(3, 1);
  });
});

describe('FocusTargets3dToggle', () => {
  afterEach(cleanup);

  it('says what it does and calls back when switched', () => {
    const onChange = vi.fn();
    render(<FocusTargets3dToggle available on={false} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Show focus targets in 3D'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('is not shown for a demo rig', () => {
    const { container } = render(<FocusTargets3dToggle available={false} on={false} onChange={() => {}} />);
    expect(container.textContent).toBe('');
  });
});
