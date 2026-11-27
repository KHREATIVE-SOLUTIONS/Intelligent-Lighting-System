# Focus presets

Position presets for the moving heads, worked out from where each head is in
the rig and the points the room gives to aim at, and written into the grandMA2
script and the handoff pack. The point is to walk into a venue with the focus
already roughed in, then touch each preset up in the room.

**Status:** backend only. The maths is checked against the 3D view's beam
drawing and covered by tests. No preset has been loaded onto a desk, and
nothing has been focused in a real room with these values. No frontend panel
yet.

## Computing is read-only

Nothing here sends DMX or moves a light. There is no preview route: a preview
would have to go through the output stage like any other look. The only write
is adding or removing a custom target, which touches `rigs.focus_targets` and
nothing else (the rig's `updated_at` is left as it was).

## Endpoints

| Method | Route | What |
| --- | --- | --- |
| GET | `/api/rigs/{id}/focus-presets` | Every target against every moving head, JSON |
| GET | `/api/rigs/{id}/focus-presets.csv` | The same table as a CSV (the one in the handoff pack) |
| POST | `/api/rigs/{id}/focus-presets/targets` | Add a custom target `{name, x, y, z}`, metres. 201, or 422 with the reason |
| DELETE | `/api/rigs/{id}/focus-presets/targets/{target_id}` | Remove one. 404 if the rig has no such target |

An unknown rig is a 404 on every route.

The presets also go into:

- `GET /api/rigs/{id}/export/ma2-macro`: with `include=all` (the default) or
  `include=focus`, and `first_preset=N` (default 1). See
  [CONSOLE_EXPORT.md](CONSOLE_EXPORT.md#grandma2-command-line-script).
- The handoff pack: `focus-presets.csv`, and the presets in the script.

Demo presets (`/api/venues/presets/...`) get no focus presets: they have no
stored room to take targets from.

## Targets

Coordinates are the rig's stage axes in metres: X across, Y up from the floor,
-Z upstage (booth end), +Z downstage (crowd end), room centred on the origin.

Five default targets, always in this order, taken from the rig's stored room
(`rigs.room_shell`):

| Key | Name | Where |
| --- | --- | --- |
| `dj_booth` | DJ booth | The raised area marked as the DJ booth, 1.2 m above its deck; else the rig's booth box |
| `dance_floor` | Dance floor centre | The marked dance floor; else the room between the stage front and the downstage wall; else the room's centre. On the floor |
| `audience` | Audience | A line across that same area at 1.7 m, 80% of its width. Heads take places along it in order across X, so the beams fan out without crossing |
| `stage_front` | Stage front | The middle of the downstage edge of the stage, 1.2 m above its deck; else the booth's front edge ("Booth front") |
| `straight_down` | Straight down | The floor under each head |

A target the room cannot place is kept, with `skipped` saying why in words
("Mark the booth's raised area in the room editor"). Its preset slot stays
reserved so preset numbers do not shift when the room is filled in later.

Custom targets come after the defaults, keyed `custom_<id>`. A rig keeps at
most 50; a name is 1 to 60 characters; each coordinate is a number within
500 m; y cannot be below the floor.

## Which heads, and how they are read

- **A moving head** is a fixture whose mode has a pan or tilt channel. If the
  mode has no channel list, its fixture type decides (moving head, spot, wash,
  beam), and it is written 8-bit.
- **16-bit** when the mode has `pan_fine` / `tilt_fine` channels.
- **Hung or standing** is not stored. The tags `floor`, `standing` or
  `floor_standing` mean standing, `hung` means hung; otherwise a head under
  1 m is taken as standing and the rest as hung, and the table and the script
  say it was assumed.
- **Invert**: the `pan_invert` tag (flipped again by the older `is_inverted`
  flag) and the `tilt_invert` tag, as the 3D view reads them.
- **Swap**: the `pan_tilt_swap` tag. Nothing in the system sets it yet.
- **Range**: the profile's `pan_range` and `tilt_range`, else 540 and 270.
- A head with **no position** (tagged unplaced) is left out of every preset
  and listed in `left_out`.

## The maths, in short

`backend/app/services/focus_presets/aim.py`. Pan 0 tilt 0 is straight down
the head's own axis, turned by the rig's rotation as the 3D view turns it
(`hangBeam`); a standing head is turned over, so its tilt 0 points at the
ceiling. Of the solutions inside both travels, the one nearest pan centre is
chosen (ties broken the same way on every machine). A point outside the
travel, or at the head itself, is **unreachable**, with the reason in words.

DMX follows the view's decoding: `0.5 + degrees / range` over the channel,
x65535 for 16-bit, x255 for 8-bit, invert and swap applied.

## In the grandMA2 script

One Position preset per target, at `Preset 2.<first_preset + its place>`:

```
ClearAll
ClearSelection
Fixture 1
Attribute "Pan" At -12.5
Attribute "Tilt" At -38.2
...
Store Preset 2.2
Label Preset 2.2 "Focus Dance floor centre"
ClearAll
```

- Pan and Tilt are **degrees from the centre of each channel's travel**, with
  the rig's invert and swap already applied. Patch these fixtures **without**
  Invert or Swap on the desk, or they are applied twice.
- A skipped target, or one no head can reach, is not stored; a `#` note says
  so at its slot. A head that cannot reach a target is left out of that
  preset, with its reason.
- **Guessed positions are marked.** A head whose position is unconfirmed is
  listed in the notes, and again inside every preset it is in ("position
  guessed (unconfirmed), check this one first"). Its presets are off by as
  much as the guess. Heads whose mount was assumed from height are listed too.
- A rig with no moving heads gets one note and no preset commands.
- Same rig, same bytes: heads are in fixture-id order and nothing reads a clock.

What the operator must still do:

1. **Check the degrees on the desk.** Whether grandMA2 reads `Attribute
   "Pan" At <degrees>` as these degrees depends on its fixture type's pan
   and tilt range. Not checked on a desk.
   Also unchecked: whether a negative value right after `At` (`At -12.5`) is
   taken as an absolute value or as a relative change; and whether
   `Store Preset 2.N`, run with only the last fixture selected, stores every
   fixture with values in the programmer (it depends on the desk's store
   settings). Try one preset on a test show first.
2. **`ClearAll` empties the programmer.** The script uses it before and after
   each preset: do not paste it in the middle of programming.
3. **Pick an empty preset range** with `first_preset`: storing onto an
   existing preset asks or replaces, depending on the desk's settings.
4. **Touch up every preset in the room.** These are computed from the rig's
   positions; a few centimetres of error at the truss is tens of centimetres
   on the floor.

## The CSV

`focus-presets.csv`, one row per target and head:

`target, target_name, fixture_id, name, mount, position, reachable, pan_deg,
tilt_deg, pan_attr_deg, tilt_attr_deg, pan_dmx, pan_fine_dmx, tilt_dmx,
tilt_fine_dmx, target_x, target_y, target_z, throw_m, reason`

`mount` is `hung` or `standing`, with ` (assumed)` when read from height.
`position` is `guessed` or `confirmed`. A skipped target is one row with its
reason and the head columns blank.

## Tests

- `backend/tests/unit/test_focus_presets_aim.py`: the maths, hung and
  standing, invert, swap, range limits, unreachable, 8 and 16 bit, and random
  points landing on target in the view's own beam model.
- `backend/tests/unit/test_focus_presets_table.py`: default and custom
  targets, which rows are movers and how their tags are read, the CSV, the
  MA2 presets, and row order not changing the bytes.
- `backend/tests/integration/test_api_focus_presets.py`: the routes and their
  404s and 422s, reading changes nothing, adding a target writes only
  `focus_targets`, the `ma2-macro` export and the handoff pack.

## What is left

- Not loaded onto a grandMA2 and not focused in a real room.
- No frontend panel to see the table, add targets or preview a preset.
- Mount is guessed from height when not tagged; there is no column for it.
- grandMA3 is not targeted.
