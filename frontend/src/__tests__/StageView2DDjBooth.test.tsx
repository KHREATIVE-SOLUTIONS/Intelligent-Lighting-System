// The 2D layout view's tag on the DJ booth (docs/ROOM_SCAN.md, slice 28): "DJ"
// on the raised area the 3D view puts the decks on, an amber "DJ?" where that
// is only a guess, and nothing where there is no booth.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { RigFixture, RoomShell } from '../types';

const fixture = {
  id: 1, name: 'Spot 1', dmx_address: 1, position_x: 0, position_y: 4, position_z: 0, rotation_y: 0,
} as unknown as RigFixture;

// A stage, the bar (which the scan called a booth) and the DJ's own booth.
const shell = (booth: number | null = null): RoomShell => {
  const room: RoomShell = {
    source: 'scan',
    room: { width: 12, depth: 10, height: 6 },
    risers: [
      { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage' },
      { center_x: 4, center_z: 3, width: 2, depth: 1, height: 1.1, base_height: 0, name: 'Bar', kind: 'booth' },
      { center_x: -4, center_z: 0, width: 1, depth: 2, height: 1, base_height: 0, name: 'Decks', kind: 'booth' },
    ],
    truss_lines: [],
    truss_rings: [],
  };
  if (booth !== null) room.risers![booth] = { ...room.risers![booth], is_dj_booth: true };
  return room;
};

function view(roomShell?: RoomShell) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [fixture], selectedIds: new Set<number>() };
  return roomShell === undefined
    ? render(<StageView2D {...props} />)
    : render(<StageView2D {...props} roomShell={roomShell} />);
}

/** The tag's own words, without its tooltip's. */
const words = (tag: Element) => tag.lastChild!.textContent;

describe('StageView2D: the tag on the DJ booth', () => {
  afterEach(cleanup);

  it('is on the first booth of a room nobody marked one in', () => {
    view(shell());
    const raised = screen.getAllByTestId('room-plan-raised');
    const tag = screen.getByTestId('room-plan-dj-booth');
    expect(raised[1].contains(tag)).toBe(true);
    expect(words(tag)).toBe('DJ');
    expect(tag.getAttribute('data-source')).toBe('scan');
    expect(tag.querySelector('title')!.textContent).toContain('the first booth the scan found');
    // Each raised area's own label is still the first text in its group.
    expect(raised[1].querySelector('text')!.textContent).toBe('Bar · 1.10 m high');
  });

  it('is on the marked one, and only on that one', () => {
    view(shell(2));
    const raised = screen.getAllByTestId('room-plan-raised');
    expect(screen.getAllByTestId('room-plan-dj-booth')).toHaveLength(1);
    const tag = screen.getByTestId('room-plan-dj-booth');
    expect(raised[2].contains(tag)).toBe(true);
    expect(words(tag)).toBe('DJ');
    expect(tag.getAttribute('data-source')).toBe('marked');
    expect(tag.getAttribute('fill')).not.toBe('#ffb74d');
  });

  it('is an amber DJ? on the stage of a room with no booth: a guess', () => {
    const guessed = shell();
    guessed.risers = [guessed.risers![0]];
    view(guessed);
    const tag = screen.getByTestId('room-plan-dj-booth');
    expect(words(tag)).toBe('DJ?');
    expect(tag.getAttribute('data-source')).toBe('guess');
    expect(tag.getAttribute('fill')).toBe('#ffb74d');
  });

  it('is not drawn with no scanned room, or in one with no booth and no stage', () => {
    view();
    expect(screen.queryByTestId('room-plan-dj-booth')).toBeNull();
    cleanup();
    const bare = shell();
    bare.risers = [{ center_x: 0, center_z: 0, width: 2, depth: 2, height: 0.3, kind: 'riser' }];
    view(bare);
    expect(screen.getAllByTestId('room-plan-raised')).toHaveLength(1);
    expect(screen.queryByTestId('room-plan-dj-booth')).toBeNull();
  });
});
