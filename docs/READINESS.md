# Venue readiness

One answer to "can I start programming this rig?". In the rig editor, press
**Readiness** on the toolbar. The panel lists every check, worst first, each
labelled **Fail**, **Warn** or **OK** in words (the colour only repeats it),
with a sentence naming the fixtures it is about.

- The rig's status is its worst check. **Fail**: fix it before programming.
  **Warn**: you can program, but something may be wrong on the night.
- **Select on plan** selects the fixtures a check names in the editor and
  closes the panel. A check lists at most 50 fixture ids; the count beside the
  title has them all ("60 fixtures (first 50 listed)").
- **Check again** reads the checks again. Any drag still being written is
  written before the panel opens, so a check sees what the screen shows.
- Opening the panel and Check again **read only**: nothing is written to the
  rig and nothing is sent to a device. The exports are built in memory.

API: `GET /api/rigs/{rig_id}/readiness` (code: `backend/app/services/rig/readiness.py`).

The **MA2 / MVR export** (Import/Export, and the 3D view's Export button)
shows the same answer in one line at the top: the overall status and how many
checks warn or fail, with **Open Readiness**. It never blocks a download, and
it is left out when readiness cannot be read or the export is of a preset
rather than a rig.

## The checks

| Check | Fails when | Warns when |
|---|---|---|
| Fixtures | the rig has no fixtures | never |
| Positions | never | a fixture stands where a layout guessed and nobody confirmed it (`position_unconfirmed`), or has no position at all and sits at 0,0,0 (`unplaced`). Offers **Locate these** |
| DMX addresses | two fixtures with known footprints share a channel, or a fixture runs past channel 512 | the only clashes involve a fixture with no DMX mode (see below). Either way, offers **Re-address** |
| Fixture profiles | a fixture matched no profile, or has the import's placeholder profile | a fixture has a profile but no DMX mode |
| Inside the room | never | a placed fixture is more than 0.25 m outside the scanned room's walls, floor or ceiling, or outside its outline (an L or a notch) |
| Groups | never | a fixture is in no group, so a console would put it in "Ungrouped". Offers **Make groups** |
| Room scan edits | never | hand edits to the last room were not kept when the room was scanned again |
| grandMA2 export | the fixture layer XML or the command-line script stops with an error | never |
| MVR export | the MVR stops with an error | never (it notes fixture types named by GDTF spec with no GDTF file inside) |

### What each one reads

Every check uses the same rule as the view it sends you to, so the panel
does not disagree with the rest of the system:

- **Positions**: the `position_unconfirmed` and `unplaced` tags written by
  the importers, the patch-sheet layout and flash-and-tap. Confirm a fixture
  with Locate (flash-and-tap) or by dragging it.
- **DMX addresses**: the same overlap rule as `/patch-conflicts` and the
  programming audit's 1-512 footprint rule. A fixture with **no DMX mode** has
  no known footprint, so it is counted as 16 channels. A clash that only
  exists because of that guess warns ("Maybe: ...") instead of failing: a
  12-channel par imported with no mode is not really overlapping its
  neighbour 12 channels on. Pick the mode and check again.
- **Fixture profiles**: the `unmatched_type` tag and the import's placeholder
  profile. Unmatched fixtures are switched off and a console cannot patch them.
- **Inside the room**: the stored room's box (width, depth, height) and its
  outline, as positioning reads them. Fixtures with no position are left to
  the Positions check.
- **Groups**: the groups an export would write (group name or `group:` tags).
- **Room scan edits**: the carry-over list kept with the room. Open Room Scan
  to keep the edits or let them go.
- **Exports**: the grandMA2 and MVR writers themselves, run in memory.

## The fixes

Three checks offer a button. The two that write ask first, because **the rig
has no undo for groups or addresses** (the editor's Undo holds positions
only); each answer lists what it changed. After either writes, the editor
reads the rig again and the panel checks again.

## Make groups

On the Groups check. It asks first; the answer lists each fixture it changed.

`POST /api/rigs/{rig_id}/readiness/fix/auto-groups` gives each placed fixture
that is in **no group** a `group_name` of *place* + *kind*, e.g.
"Front truss Spots", "SL tower Washes". The place is, in order:

1. the file's own hang position (a `hang_position:` tag from the import);
2. the named truss line or ring of the scanned room it hangs on;
3. a guess from where it stands: Floor (below 1 m), SL / SR tower (beyond 45%
   of the stage width; stage left is -X), FOH, Front, Mid or Back truss by
   depth.

The kind is the profile's fixture type (Movers, Spots, Washes, Beams, Pars,
Bars, Strobes, Lasers, Effects, Dimmers; anything else is "Fixtures").

When the rig already has a group of **exactly** the name it would make (same
letters, same case: the name Make groups itself writes, as a group name or a
`group:` tag), an ungrouped fixture of that place and kind **joins** it, and
the answer lists the group under `added` ("Added 1 fixture to Front truss
Spots."). This is how a fixture patched after an earlier run gets into the
group made for it. The rig does not record who made a group, so that exact
name is the only sign one was made here.

It leaves alone:

- fixtures already in a group, in any way: no fixture is ever taken out of a
  group or moved from one group to another;
- fixtures with no position (there is no place to name them by): the answer
  counts them;
- a name the rig already has that differs only in case ("front truss spots"):
  someone typed it, so those fixtures are **not** added to it. The name is
  listed as skipped and the Groups check keeps warning about them, to be
  grouped by hand.

A second call changes nothing.

## Re-address

On the DMX addresses check. Pressing it changes nothing yet: it asks for the
plan (`?dry_run=true`) and shows each move, "Spot 2: 1.005 to 1.017", plus
anything it could not move. **Move N** applies exactly that plan; Cancel
writes nothing.

`POST /api/rigs/{rig_id}/readiness/fix/readdress` writes `universe` and
`dmx_address` on the fixtures that clash, and nothing else. It uses the
check's own rules (the `/patch-conflicts` overlap rule, the audit's 1-512
footprint rule, 16 channels for a fixture with no DMX mode) and the patcher's
free-range finder.

- A fixture clashes when its footprint overlaps one kept in place, or runs
  past channel 512.
- Fixtures are kept in place in this order: every **address-locked** fixture
  first, then by id. Of two that overlap, the one patched first (lower id)
  stays. In a chain A-B-C where only B touches both, only B moves.
- A fixture that does not clash never moves.
- Each one that moves goes to the first free range at or after its own
  address in its universe, else the first free range in that universe, else
  the next universe with room.
- A second call finds nothing to move.

It leaves out:

- **address-locked fixtures**: they never move, even if that leaves a clash.
  The answer names them under `left` and the check keeps failing;
- a clash with **no room** anywhere to move to: also listed under `left`;
- the fixture itself. Nothing is sent to a device: **set each moved fixture
  to its new address on the fixture**, or the rig and the room will disagree;
- choosing a DMX mode. A fixture with no mode is moved by its guessed
  16-channel footprint and the plan says so ("may not be real"); picking the
  mode first may be the better fix;
- undo: put an address back by hand from the `from_label` in the answer.

## Locate these

On the Positions check. It closes the panel and opens **Identify Lights**
(flash-and-tap) with exactly the fixtures the check names, including ones
with no position at all. Nothing is lit until you press **Check these N**
there; then it walks them a row at a time, as locate mode does, and each tap
confirms a position.

`POST /api/rigs/{rig_id}/identify/start?only=unconfirmed` with a body of
`{"fixture_ids": [...]}`. Switched-off fixtures among them are reported, not
walked; an empty list, or ids none of which is on the rig and switched on, is
refused before anything is lit.

It leaves out: a check lists at most 50 fixture ids, so on a rig with more
the button reads **Locate the first 50**. Check again after the walk and the
next ones are named.

## What it leaves out

Readiness is a check of the rig as stored, not of the venue. It does not:

- talk to any device: it does not know whether a node, a universe or a
  fixture is actually connected, powered or answering (flash them with
  Identify Lights for that);
- check that a fixture's stored position is where it really hangs: only that
  someone confirmed it, and that it is inside the scanned room;
- check the room scan itself, or truss trims and loads;
- check that a DMX mode chosen is the mode the fixture is really set to;
- judge the groups that exist: any group counts, however it was named;
- check looks, cues, shows, or the music side at all;
- write the exports to disk or open them in a console or visualiser: a
  writer that runs without error can still produce a file a console reads
  differently;
- undo Make groups: put a fixture back by clearing its group by hand, using
  the `changed` list (`group_before` is always empty, since only fixtures in
  no group are changed);
- undo Re-address: the answer's `moves` hold each address before and after;
- fix the Fixture profiles, Inside the room, Room scan edits or export checks
  from the panel: Select on plan finds the fixtures, the fix is by hand.
