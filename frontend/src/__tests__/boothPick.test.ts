// "This one is the DJ's booth" (docs/ROOM_SCAN.md, slice 28): which raised area
// the booth is on, that the 3D view's booth and the 2D plan's tag go by the
// same choice, and that a room nobody marked one in is exactly what it was.
import { describe, expect, it } from 'vitest';
import { isDjBooth, pickDjBooth } from '../components/rig/previs/boothPick';
import { areaDistance, boxFloor, placeScanBooth, placeScanCrowd } from '../components/rig/previs/scanFloor';
import { DJ_BOOTH_TAG_SIZE, djBoothTag, planLabels, roomPlan } from '../components/rig/roomPlan2d';
import type { RoomShell, RoomShellBox } from '../types';

const area = (
  kind: string, center_x: number, center_z: number, width: number, depth: number, height: number,
): RoomShellBox => ({ kind, center_x, center_z, width, depth, height, base_height: 0 });

const marked = (shape: RoomShellBox): RoomShellBox => ({ ...shape, is_dj_booth: true });

// A box room 12 m by 10 m: a stage against the upstage wall, the bar downstage left, the DJ's own
// booth by the stage right wall, and a low riser.
const ROOM = boxFloor(-6, 6, -5, 5);
const STAGE = area('stage', 0, -3.5, 8, 3, 1);
const BAR = area('booth', 4, 3, 2, 1, 1.1);
const DECKS = area('booth', -4, 0, 1, 2, 1);
const RISER = area('riser', 4, -0.5, 2, 2, 0.4);

describe('pickDjBooth', () => {
  it('is nothing for a room with no booth and no stage', () => {
    expect(pickDjBooth([])).toBeNull();
    expect(pickDjBooth([RISER])).toBeNull();
    expect(pickDjBooth([null, undefined, { kind: 'balcony' }])).toBeNull();
  });

  it('is the first raised area the room calls a booth when nobody marked one', () => {
    expect(pickDjBooth([STAGE, BAR, DECKS])).toEqual({ index: 1, source: 'scan' });
    expect(pickDjBooth([DECKS, STAGE, BAR])).toEqual({ index: 0, source: 'scan' });
  });

  it('is a guess on the first stage of a room with no booth', () => {
    expect(pickDjBooth([RISER, STAGE, area('stage', -4, 3, 3, 2, 0.5)])).toEqual({ index: 1, source: 'guess' });
  });

  it('is the marked one, whatever comes first and whatever kind it is', () => {
    expect(pickDjBooth([STAGE, BAR, marked(DECKS)])).toEqual({ index: 2, source: 'marked' });
    // The DJ plays on the stage, and the room's only "booth" is the bar.
    expect(pickDjBooth([BAR, marked(STAGE)])).toEqual({ index: 1, source: 'marked' });
    expect(pickDjBooth([STAGE, BAR, marked(RISER)])).toEqual({ index: 2, source: 'marked' });
  });

  it('takes the first of two marked, and only a stored true for a mark', () => {
    expect(pickDjBooth([STAGE, marked(DECKS), marked(BAR)])).toEqual({ index: 1, source: 'marked' });
    const odd = (value: unknown) => ({ ...DECKS, is_dj_booth: value }) as unknown as RoomShellBox;
    for (const value of [false, null, undefined, 1, 'true', 'yes']) {
      expect(isDjBooth(odd(value))).toBe(false);
      expect(pickDjBooth([STAGE, BAR, odd(value)])).toEqual({ index: 1, source: 'scan' });
    }
    expect(isDjBooth(marked(DECKS))).toBe(true);
    expect(isDjBooth(null)).toBe(false);
  });
});

describe('the booth of a scanned room with one marked as the DJ\'s', () => {
  it('goes to the bar when the bar comes first and nobody has said otherwise', () => {
    const booth = placeScanBooth(ROOM, [STAGE, BAR, DECKS])!;
    expect(booth.source).toBe('scan');
    expect(booth.riser).toBe(1);
  });

  it('goes to the marked booth instead, as a counter facing the open floor', () => {
    const risers = [STAGE, BAR, marked(DECKS)];
    const booth = placeScanBooth(ROOM, risers)!;
    expect(booth.source).toBe('marked');
    expect(booth.riser).toBe(2);
    // A metre high: the counter itself, with the decks on its top and no desk of the view's own.
    expect(booth.desk).toBe(false);
    expect(booth.deskTopY).toBeCloseTo(1);
    // The middle of its front face is on its own edge, not on the bar's.
    expect(areaDistance(DECKS, booth.x, booth.z)).toBeCloseTo(0);
    expect(areaDistance(BAR, booth.x, booth.z)).toBeGreaterThan(5);
    // It stands by the stage right wall, so the floor is to stage left of it.
    expect([booth.faceX, booth.faceZ]).toEqual([1, 0]);
    expect(booth.x).toBeCloseTo(-3.5);
    expect(booth.z).toBeCloseTo(0);
  });

  it('draws a marked booth exactly as it drew the same one found first', () => {
    const found = placeScanBooth(ROOM, [STAGE, BAR, DECKS])!;
    expect(placeScanBooth(ROOM, [STAGE, marked(BAR), DECKS])).toEqual({ ...found, source: 'marked' });
  });

  it('draws a marked stage as a stage is played, with no guess about it', () => {
    const guessed = placeScanBooth(ROOM, [STAGE])!;
    expect(guessed.source).toBe('guess');
    // The bar no longer takes the decks: they are at the downstage middle of the stage, on a desk.
    const booth = placeScanBooth(ROOM, [marked(STAGE), BAR])!;
    expect(booth).toEqual({ ...guessed, source: 'marked' });
    expect(booth.desk).toBe(true);
    expect([booth.faceX, booth.faceZ]).toEqual([0, 1]);
  });

  it('draws a marked low riser as a platform with a desk on it', () => {
    const booth = placeScanBooth(ROOM, [STAGE, BAR, marked(RISER)])!;
    expect(booth.source).toBe('marked');
    expect(booth.riser).toBe(2);
    expect(booth.desk).toBe(true);
    expect(booth.baseY).toBeCloseTo(0.4);
    expect(booth.deskTopY).toBeCloseTo(1.35);
  });

  it('leaves a room nobody marked one in exactly as it was', () => {
    const plain = [STAGE, BAR, DECKS];
    const unmarked = [STAGE, { ...BAR, is_dj_booth: false }, { ...DECKS, is_dj_booth: undefined }];
    const booth = placeScanBooth(ROOM, plain)!;
    expect(placeScanBooth(ROOM, unmarked)).toEqual(booth);
    expect(placeScanCrowd(ROOM, unmarked, booth, 60)).toEqual(placeScanCrowd(ROOM, plain, booth, 60));
    // And a room with a stage and no booth still has its guess.
    expect(placeScanBooth(ROOM, [STAGE, RISER])!.source).toBe('guess');
  });

  it('turns the crowd to the marked booth', () => {
    const risers = [STAGE, BAR, marked(DECKS)];
    const booth = placeScanBooth(ROOM, risers)!;
    const toBar = placeScanCrowd(ROOM, [STAGE, BAR, DECKS], placeScanBooth(ROOM, [STAGE, BAR, DECKS]), 60);
    const toDecks = placeScanCrowd(ROOM, risers, booth, 60);
    expect(toDecks.length).toBeGreaterThan(0);
    expect(toDecks).not.toEqual(toBar);
  });
});

describe('the 2D plan\'s tag on the DJ booth', () => {
  const shell = (risers: RoomShellBox[]): RoomShell => ({
    source: 'scan', room: { width: 12, depth: 10, height: 5 }, risers, truss_lines: [], truss_rings: [],
  });

  it('is on the first booth of a room nobody marked one in, and on no other raised area', () => {
    const plan = roomPlan(shell([STAGE, RISER, DECKS, BAR]))!;
    expect(plan.raised.map((raised) => raised.djBooth)).toEqual([undefined, undefined, 'scan', undefined]);
    expect(djBoothTag(plan.raised[0])).toBeNull();
    const tag = djBoothTag(plan.raised[2])!;
    expect(tag.text).toBe('DJ');
    expect(tag.guess).toBe(false);
    expect(tag.tooltip).toContain('the first booth the scan found');
    // Over the middle of the booth, one label line above its own label.
    expect(tag.x).toBeCloseTo(-4);
    expect(tag.z).toBeCloseTo(0 + 0.08 - 0.24 * 1.4);
    expect(DJ_BOOTH_TAG_SIZE).toBeLessThan(0.24);
  });

  it('moves to the marked one, the same raised area the 3D view puts the booth on', () => {
    const risers = [STAGE, RISER, DECKS, marked(BAR)];
    const plan = roomPlan(shell(risers))!;
    expect(plan.raised.map((raised) => raised.djBooth)).toEqual([undefined, undefined, undefined, 'marked']);
    expect(djBoothTag(plan.raised[3])).toMatchObject({ text: 'DJ', guess: false });
    expect(djBoothTag(plan.raised[3])!.tooltip).toContain('marked in Edit Room');
    expect(placeScanBooth(ROOM, risers)!.riser).toBe(3);
  });

  it('says a guess is one: DJ? on the first stage of a room with no booth', () => {
    const plan = roomPlan(shell([RISER, STAGE]))!;
    expect(plan.raised.map((raised) => raised.djBooth)).toEqual([undefined, 'guess']);
    const tag = djBoothTag(plan.raised[1])!;
    expect(tag.text).toBe('DJ?');
    expect(tag.guess).toBe(true);
    expect(tag.tooltip).toContain('A guess');
  });

  it('is on nothing in a room with no booth and no stage', () => {
    const plan = roomPlan(shell([RISER]))!;
    expect(plan.raised.map((raised) => raised.djBooth)).toEqual([undefined]);
  });

  it('counts only what the plan draws, as the 3D view does', () => {
    // A marked raised area with no size cannot be drawn, so the booth is the next choice among the rest.
    const broken = { ...marked(DECKS), width: 0 };
    const plan = roomPlan(shell([broken, STAGE, BAR]))!;
    expect(plan.raised).toHaveLength(2);
    expect(plan.raised.map((raised) => raised.djBooth)).toEqual([undefined, 'scan']);
  });

  it('changes no label and no tooltip of the room layer', () => {
    const plain = roomPlan(shell([STAGE, RISER, DECKS, BAR]))!;
    const with_mark = roomPlan(shell([STAGE, RISER, DECKS, marked(BAR)]))!;
    expect(with_mark.raised.map((raised) => [raised.label, raised.tooltip]))
      .toEqual(plain.raised.map((raised) => [raised.label, raised.tooltip]));
    expect(planLabels(with_mark)).toEqual(planLabels(plain));
    expect(with_mark.bounds).toEqual(plain.bounds);
  });
});
