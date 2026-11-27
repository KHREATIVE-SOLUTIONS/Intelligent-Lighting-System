# Look bench

See and score a whole show without a room, a rig or a login.

`look_bench.py` plays one or more tracks back to back through the real analyser and the
real engine, on a virtual clock, far faster than real time. It uses one engine and one
analyser for the whole sequence, the way a DJ set runs, so anything that depends on what
was played before shows up. Every DMX frame is decoded through the rig's own channel
map. Each run produces one picture and one JSON file of numbers.

## Running

From the repository root, with the backend's Python:

```bash
backend/venv/Scripts/python scripts/look_bench/look_bench.py --rig club_night --tracks ibd,dense:30,ibd,mix --out bench_out --label my_change
```

| Option | Meaning |
|---|---|
| `--rig` | A demo preset (`club_night`, `small_nightclub`, `pro_beam_room`, ...) or `db:<sqlite file>:<rig id>` for a rig patched in a database. |
| `--tracks` | Comma separated. Synthetic: `ibd` (intro, build, drop), `dense[:seconds]`, `quiet`, `mix`, `song`, `click`. Append `@<dB>` for gain, e.g. `ibd@-6`. Or a path to a WAV or FLAC file for real music. |
| `--label` | Names the output files. |
| `--armed` | Also apply what "Start Capture" applies. Off by default, so results line up with audio fed over the WebSocket. |
| `--seed` | Seed for the look library's choices. Default 1, so two runs choose the same looks and can be compared. A live show is unseeded and never repeats a night. |

`club_night` is the reference rig: 12 movers on two trusses, 4 moving washes, 8 LED bars,
4 strobes and 6 pars, mirrored about the centre line. Use it for comparisons.

## Reading the picture

Top to bottom:

1. **Section** — what the engine called each moment. Dashed white lines mark where the
   music really changes, for synthetic tracks that know.
2. **Look** — which look the look library chose, by name, and for how long.
3. **The show** — one row per fixture, grouped by family, upstage to downstage and left
   to right. Colour is the fixture's colour times its level, gamma-lifted so low levels
   can be seen. A chase shows as a diagonal; identical fixtures show as a flat band.
4. **Level** — rig brightness (white) against the music's energy (grey).
5. **Pan** and 6. **Tilt** — where each moving head points, in degrees from straight
   down. Heads left of centre are drawn blue, right of centre red. A mirrored look is a
   blue line and a red line reflected about zero in pan, and lying on top of each other
   in tilt.

## The numbers

| Number | What a good one looks like |
|---|---|
| `mirror_symmetry_pan`, `mirror_symmetry_tilt` | +1: left and right mirror each other. 0: unrelated. -1: all heads move as one. |
| `pan_sweep_deg_median`, `tilt_sweep_deg_median` | How far the heads actually travel. |
| `biggest_step_deg_while_lit` | The largest jump in one frame with the lamp on. A head cannot make a big one. |
| `group_level_correlation_mean` | Near 1: every fixture family does the same thing. Lower: families play different parts. |
| `within_group_spread` | 0: every fixture in a family is identical. Higher: there is a chase or a pattern. |
| `saturation_mean`, `hue_variety` | How coloured the show is, and how much the colour moves over time. |
| `worst_luminance_peaks_in_1s` | Total rig brightness swings of 20% or more in the worst second. Use it to compare one run with another whenever dimmer or flash behaviour changes. It is not the absolute safety figure: on a virtual clock it reads lower than the wire harness does in real time (3 against 4–6 on the same drop). |
| `drop.caught`, `level_8s_before` and `_after` | Whether the drop was labelled, and whether it landed. |
| `looks.distinct`, `looks.changes`, `looks.immediate_repeats` | How many different looks ran, how often the look changed, and how many times a look followed itself. Repeats should be 0. `looks.timeline` lists them. |

## Look sheet

`look_sheet.py` judges the movements themselves, before they reach a rig. For each rig
it draws each one from above and from the front: where each beam lands at the start, and
the path that landing point traces over one cycle.

```bash
backend/venv/Scripts/python scripts/look_bench/look_sheet.py --rigs club_night,small_nightclub --section chorus --out look_sheets
```

`--rigs all` draws every demo rig. `--section` sizes the looks as that section would
(`breakdown`, `verse`, `buildup`, `chorus`, `drop`). `--looks` chooses what is drawn:
`library` (the default) is the fifteen movements the look library uses, `all` is every
generated combination of position, motion and phase (44), or give a comma-separated
list of names. It runs no engine: it calls the same functions the engine calls
(`backend/app/services/effects/live_looks.py`), so it is instant.

Each look is checked and flagged in red on the sheet if it fails:

| Check | Meaning |
|---|---|
| `mirror err` | How far a head's landing point is from the reflection of its partner's. 0 is a perfect mirror. |
| `uneven` | How irregular the gaps between neighbouring landing points are at the start of the look. 0 is evenly spaced. |
| `lean` | The furthest any beam leans from straight down. Capped at 68 degrees. |
| `pan` | The largest pan angle used. Kept under a quarter turn, so no head swaps to its other pan and tilt answer. |
| `deg/s` | The fastest pan and tilt the look asks for at 128 BPM. Flagged `TOO FAST` above 240 and 180. |
| `LANDS OUTSIDE` | A beam lands well beyond the room. |

`sheets/` holds the sheets for three rigs of very different size. The same fifteen
movements make the same picture on all of them, which is the point of aiming at the
room. All 44 generated combinations pass every check on all seven demo rigs.

## Checked against the wire

On the Small Club rig with the intro/build/drop track, the bench reproduces what was
measured from captured Art-Net packets on 2026-11-17: build labelled at 19.0 s (wire
18.9 s), drop at 31.0 s (30.7 s), level before and after the drop 0.14 and 0.41 (0.14
and 0.40), three white flashes in the worst second (three).

## Baselines

`baseline/` holds dated before-and-after runs on `club_night` with
`ibd,dense:30,ibd,mix`. Add one whenever the show's behaviour is changed on purpose.

`2026-11-17_after_looks` is the look system with the look library choosing: 22 looks
run across the four tracks in 21 changes, 18 of them different, none following itself.
Against `2026-11-17_after_roles` its levels, colour, flashes, sections and drops are
identical; only the pan and tilt rows differ, and there is a look row where there was
none. A look's dimmer effect, chase, strobe mode and colour treatment are not performed
yet, so they cannot have changed anything. Travel changed both ways: median pan is 68,
97, 128 and 131 degrees on the four tracks against 84, 70, 76 and 57 in `after_roles`,
and median tilt is 25, 24, 46 and 35 against 65, 48, 70 and 48. Tilt is smaller
because a look stretches its throw toward a point in the room instead of swinging
through a set angle, and many library looks run at less than full size.

The `peaks/s` figures in `2026-11-17_before` and `2026-11-17_after_moves` (7 and 9)
were produced by an earlier peak counter that counted a held level two or three
times. Under the current counter both read 3. Everything else in those files stands.

## Drop bench

`drop_bench.py` asks one question of the same machinery: how often is the drop caught,
and how often is one invented? It plays 12 single plays, 4 drops back to back, 20
plays with no drop and 8 other builds, and prints hits, misses and false drops. See
`docs/DROP_DETECTION_BENCH.md`.

```bash
backend/venv/Scripts/python scripts/look_bench/drop_bench.py
```

## Limits

- Synthetic tracks are drums over thin pads. Colour-to-mood and structure on real music
  need real recordings: pass WAV or FLAC paths to `--tracks`.
- The bench decodes DMX; it does not draw beams in a room. Use the 3D view for that.
- Level is dimmer times the brightest colour channel, a linear DMX figure.
