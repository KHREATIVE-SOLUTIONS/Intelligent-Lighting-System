/**
 * Picking up a fixture in the 3D view and putting it down somewhere else.
 *
 * Mounted only while the view is in Move fixtures mode, for a rig stored in
 * the database. Each fixture gets a faint sphere to grab. Pressing one selects
 * it; dragging moves it along the floor plan at the height it hangs at, and
 * with Shift held, straight up and down. Releasing hands the new position to
 * the page, which saves it (docs/3D_PREVIEW.md).
 *
 * The geometry is all in fixtureDrag.ts. This file only turns pointer events
 * into rays and draws where the fixture would go.
 *
 * While a drag is under way nothing in React changes: the marker is moved
 * through refs. The rig is only given the new position on release, because a
 * new rig lays the whole venue out again and re-renders every fixture.
 *
 * Nothing here sends DMX. A stored position changes, and only on release.
 */
import { memo, useCallback, useEffect, useMemo, useRef } from 'react';
import { Html } from '@react-three/drei';
import { useThree } from '@react-three/fiber';
import type { ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import {
  beginDrag, dragStep, isRealMove, pointerTravelled, positionText, settleDrag,
} from './fixtureDrag';
import type { DragState, Point3, PositionLimits, Ray, SnapLine, Snapped } from './fixtureDrag';

/** A fixture as the layer needs it: where the rig stores it and how far above that it is drawn. */
export type DragHandle = {
  id: number;
  x: number;
  y: number;
  z: number;
  /** How far above its stored height it is drawn (a fixture stood on the floor). */
  lift: number;
  unconfirmed: boolean;
};

const HANDLE_RADIUS = 0.34;
const SELECTED_COLOR = '#4fc3f7';
const GUESS_COLOR = '#ffb74d';
const CONFIRMED_COLOR = '#b0bec5';

const handleGeometry = new THREE.SphereGeometry(HANDLE_RADIUS, 16, 12);
const ringGeometry = new THREE.TorusGeometry(0.52, 0.025, 8, 40);
const floorRingGeometry = new THREE.TorusGeometry(0.26, 0.015, 6, 28);
const dropGeometry = new THREE.CylinderGeometry(0.012, 0.012, 1, 6);

function handleMaterial(color: string, opacity: number) {
  return new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false });
}
const guessMaterial = handleMaterial(GUESS_COLOR, 0.22);
const confirmedMaterial = handleMaterial(CONFIRMED_COLOR, 0.14);
const selectedMaterial = handleMaterial(SELECTED_COLOR, 0.3);
const markerMaterial = new THREE.MeshBasicMaterial({ color: SELECTED_COLOR, depthTest: false, transparent: true });

const FLAT: [number, number, number] = [Math.PI / 2, 0, 0];

type ActiveDrag = {
  handle: DragHandle;
  state: DragState;
  settled: Snapped;
  moved: boolean;
};

export const FixtureDragLayer = memo(function FixtureDragLayer({
  handles,
  selectedId,
  limits,
  snapLines,
  onSelect,
  onMove,
}: {
  handles: DragHandle[];
  selectedId: number | null;
  limits: PositionLimits;
  /** The lines to snap to, or null with snapping off. */
  snapLines: SnapLine[] | null;
  onSelect: (id: number) => void;
  /** A drag ended somewhere new: the position to store, in the rig's own terms. */
  onMove: (id: number, to: Point3) => void;
}) {
  const camera = useThree((state) => state.camera);
  const gl = useThree((state) => state.gl);
  const controls = useThree((state) => state.controls) as { enabled: boolean } | null;

  const markerRef = useRef<THREE.Group>(null);
  const dropRef = useRef<THREE.Mesh>(null);
  const floorRef = useRef<THREE.Mesh>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const drag = useRef<ActiveDrag | null>(null);
  const stopListening = useRef<(() => void) | null>(null);
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const pointer = useMemo(() => new THREE.Vector2(), []);

  // Read through refs by the window listeners, which outlive a render.
  const latest = useRef({ limits, snapLines, onMove, controls });
  latest.current = { limits, snapLines, onMove, controls };

  const selected = handles.find((handle) => handle.id === selectedId) ?? null;

  /** Put the marker where the fixture would be drawn at `at` (a stored position). */
  const showMarker = useCallback((at: Snapped | Point3, lift: number, text: string | null) => {
    const drawnY = at.y + lift;
    markerRef.current?.position.set(at.x, drawnY, at.z);
    if (dropRef.current) {
      // A line from the fixture down to the floor, so its place on the plan can be read.
      dropRef.current.position.set(at.x, drawnY / 2, at.z);
      dropRef.current.scale.set(1, Math.max(0.01, drawnY), 1);
    }
    floorRef.current?.position.set(at.x, 0.03, at.z);
    if (labelRef.current) {
      labelRef.current.textContent = text ?? '';
      labelRef.current.style.display = text ? 'block' : 'none';
    }
  }, []);

  // The marker rests on the selected fixture whenever no drag is under way.
  useEffect(() => {
    if (drag.current || !selected) return;
    showMarker(selected, selected.lift, null);
  }, [selected, showMarker]);

  const rayFrom = useCallback((event: { clientX: number; clientY: number }): Ray => {
    const rect = gl.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1,
      -((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    return { origin: raycaster.ray.origin, direction: raycaster.ray.direction };
  }, [camera, gl, pointer, raycaster]);

  const endDrag = useCallback((commit: boolean) => {
    stopListening.current?.();
    stopListening.current = null;
    const active = drag.current;
    drag.current = null;
    if (latest.current.controls) latest.current.controls.enabled = true;
    if (!active) return;
    if (commit && active.moved) {
      // The marker stays where the fixture was put until the rig catches up.
      showMarker(active.settled, active.handle.lift, null);
      latest.current.onMove(active.handle.id, { x: active.settled.x, y: active.settled.y, z: active.settled.z });
    } else {
      showMarker(active.handle, active.handle.lift, null);
    }
  }, [showMarker]);

  // A drag cut short by the layer going away (the mode switched off, the rig
  // changed) saves nothing and hands the camera back.
  useEffect(() => () => {
    endDrag(false);
    gl.domElement.style.cursor = '';
  }, [endDrag, gl]);

  const handlePointerDown = useCallback((handle: DragHandle, event: ThreeEvent<PointerEvent>) => {
    if (event.button !== 0) return;
    // The camera must not turn with the fixture, and a fixture behind this one
    // must not be picked up as well.
    event.stopPropagation();
    onSelect(handle.id);
    endDrag(false);

    const start: Point3 = { x: handle.x, y: handle.y + handle.lift, z: handle.z };
    const pressedAt = { x: event.nativeEvent.clientX, y: event.nativeEvent.clientY };
    let armed = false;
    const active: ActiveDrag = {
      handle,
      state: dragStep(beginDrag(start), rayFrom(event.nativeEvent), event.nativeEvent.shiftKey),
      settled: { x: handle.x, y: handle.y, z: handle.z, snappedTo: null },
      moved: false,
    };
    drag.current = active;
    if (latest.current.controls) latest.current.controls.enabled = false;
    showMarker(handle, handle.lift, null);

    const move = (ev: PointerEvent) => {
      const now = drag.current;
      if (!now) return;
      now.state = dragStep(now.state, rayFrom(ev), ev.shiftKey);
      // Alt lets go of the snap for one drag without turning it off.
      const lines = ev.altKey ? null : latest.current.snapLines;
      now.settled = settleDrag(now.state, now.handle.lift, latest.current.limits, lines);
      // A press is a click until the pointer has really travelled on screen;
      // once it has, it stays a drag even if carried back near where it began.
      armed = armed || pointerTravelled(pressedAt, { x: ev.clientX, y: ev.clientY });
      now.moved = armed && isRealMove(now.state, start, now.settled, now.handle);
      showMarker(now.settled, now.handle.lift, now.moved ? positionText(now.settled, now.settled.snappedTo) : null);
    };
    const up = () => endDrag(true);
    const cancel = () => endDrag(false);
    const key = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') endDrag(false);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', cancel);
    window.addEventListener('keydown', key);
    stopListening.current = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      window.removeEventListener('keydown', key);
    };
  }, [endDrag, onSelect, rayFrom, showMarker]);

  return (
    <group>
      {handles.map((handle) => (
        <mesh
          key={handle.id}
          geometry={handleGeometry}
          material={handle.id === selectedId ? selectedMaterial : handle.unconfirmed ? guessMaterial : confirmedMaterial}
          position={[handle.x, handle.y + handle.lift, handle.z]}
          onPointerDown={(event) => handlePointerDown(handle, event)}
          onPointerOver={() => { gl.domElement.style.cursor = 'grab'; }}
          onPointerOut={() => { gl.domElement.style.cursor = ''; }}
          renderOrder={5}
          dispose={null}
        />
      ))}

      {/* Where the selected fixture is, or while it is dragged, where it would go. */}
      {selected && (
        <>
          <group ref={markerRef} position={[selected.x, selected.y + selected.lift, selected.z]}>
            <mesh geometry={ringGeometry} material={markerMaterial} rotation={FLAT} renderOrder={6} dispose={null} />
            <Html center position={[0, 0.8, 0]} style={{ pointerEvents: 'none' }} zIndexRange={[10, 0]}>
              <div
                ref={labelRef}
                data-testid="drag-readout"
                style={{
                  display: 'none',
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: 'rgba(0,0,0,0.78)',
                  border: `1px solid ${SELECTED_COLOR}`,
                  color: '#e1f5fe',
                  fontSize: 12,
                  fontFamily: 'Consolas, monospace',
                  whiteSpace: 'nowrap',
                }}
              />
            </Html>
          </group>
          <mesh ref={dropRef} geometry={dropGeometry} material={markerMaterial} renderOrder={6} dispose={null} />
          <mesh
            ref={floorRef}
            geometry={floorRingGeometry}
            material={markerMaterial}
            rotation={FLAT}
            renderOrder={6}
            dispose={null}
          />
        </>
      )}
    </group>
  );
});
