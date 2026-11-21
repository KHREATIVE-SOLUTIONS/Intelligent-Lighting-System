# Drop detection bench

Backlog #10. Finding D2 of `ASSESSMENT_AND_ROADMAP_2026-11.md`: the drop was caught in
8 of 12 single plays and 2 of 4 back to back, and every miss followed loud music.

## Result

| | Before | After |
|---|---|---|
| Single plays caught | 9 / 12 | **12 / 12** |
| Back to back caught | 2 / 4 | **4 / 4** |
| False drops in those plays | 0 | 0 |
| False drops in 20 plays with no drop | 3 | 3 (the same three) |
| Other builds | 6 / 8 | **8 / 8** |
| False drops in the other builds | 0 | 0 |

Measured on 2026-11-21 with `scripts/look_bench/drop_bench.py`. The bench is
deterministic: two runs of the unmodified code gave byte-identical reports. Both reports
are kept in `scripts/look_bench/baseline/2026-11-21_drop_bench_{before,after}.json`.

"Before" is the bench run with `--without-release-path`, which switches the new rule
off. The 12 + 4 and the other builds were also run on the code before the change and
gave the same 9 / 12, 2 / 4 and 6 / 8, play for play.

The section detector on its own, with the decision engine's rule taken out of the
picture, went from 6 / 12 and 0 / 4 to 12 / 12 and 4 / 4. That figure came from a
replay script used during the work and since deleted; the bench does not print it.

## What the numbers are, and are not

The assessment's 8 / 12 and 2 / 4 were measured on the wire: a booted backend, audio
over the WebSocket in real time, Art-Net captured on loopback. This bench is the
closest offline equivalent, not a re-run of those passes. It plays the same synthetic
tracks through the real analyser and the real engine on the look bench's virtual clock.
It reproduces the shape of the finding (9 / 12 and 2 / 4, every miss after loud music)
but the two sets of figures are not the same measurement.

- **There is no recorded music in the repository**, and none was downloaded. Every
  drop here is one synthesiser's intro, build and drop, at five tempos and three build
  lengths. Real records are still owed (roadmap G1, item 3). `look_bench.py` already
  takes WAV and FLAC paths; this bench does not yet.
- **Not checked on the wire.** `scripts/venue_sim` was not re-run.

## Running it

From the repository root, with the backend's Python. It takes about five minutes.

```bash
backend/venv/Scripts/python scripts/look_bench/drop_bench.py
backend/venv/Scripts/python scripts/look_bench/drop_bench.py -v --json out.json
backend/venv/Scripts/python scripts/look_bench/drop_bench.py --without-release-path
```

`-v` prints the section timeline of every play. Nothing is sent anywhere.

### What it plays

- **12 single plays.** Each is a fresh analyser and engine, an optional prelude, then
  the drop track. Only the last drop is scored. The preludes are the histories the wire
  passes used (cold; after 14 s and 30 s of dense music; after an earlier drop) plus
  gain changes, a DJ mix and a quiet track.
- **4 back to back.** One boot, the soak's playlist: DJ mix, drop track, four times.
- **20 plays with no drop.** Dense, quiet, DJ mix, song, click, a build that never
  drops, a build that hits once and breaks down, those again after loud music, and four
  steps up in level into music whose bass share swings from phrase to phrase.
- **8 other builds.** The drop track at 100, 120, 128, 140 and 174 BPM with 4, 8 and
  16 bar builds, cold and after loud music. They are not a blind test: they were in
  view while the rule was tuned, and the thinnest margin quoted below is one of them.

A drop is caught when the engine's section reads `drop` at some frame from 1 s before
the true drop to 4 s after it. That is the look bench's own rule. A false drop is any
entry into `drop` outside such a window.

## Per play

| Single play | Before | After |
|---|---|---|
| cold | +716 ms | +716 ms |
| cold, -6 dB | +716 ms | +716 ms |
| cold, +6 dB | +100 ms | +100 ms |
| cold, -12 dB | +716 ms | +716 ms |
| after 14 s dense | **missed** | +905 ms |
| after 30 s dense | **missed** | +896 ms |
| after 14 s dense, -6 dB | **missed** | +905 ms |
| after 14 s dense at +6 dB | +588 ms | +588 ms |
| after a drop | +95 ms | +95 ms |
| after a drop and 30 s dense | +108 ms | +108 ms |
| after a DJ mix | +105 ms | +105 ms |
| after a quiet track | +803 ms | +803 ms |

| Back to back | Before | After |
|---|---|---|
| drop 1 (92.5 s) | **missed** | +904 ms |
| drop 2 (209.1 s) | +102 ms | +102 ms |
| drop 3 (325.6 s) | **missed** | +851 ms |
| drop 4 (442.1 s) | +100 ms | +100 ms |

| Other builds | Before | After |
|---|---|---|
| 140 BPM, 16 bars, cold | +340 ms | +340 ms |
| 140 BPM, 16 bars, after dense | +71 ms | +71 ms |
| 100 BPM, 8 bars, cold | +433 ms | +433 ms |
| 100 BPM, 8 bars, after dense | **missed** | +530 ms |
| 128 BPM, 4 bars, cold | +733 ms | +733 ms |
| 128 BPM, 4 bars, after dense | **missed** | +1380 ms |
| 174 BPM, 16 bars, after a DJ mix | +301 ms | +301 ms |
| 120 BPM, 8 bars, after song | +528 ms | +528 ms |

Every play that was caught before is caught at the same millisecond now. The change
only adds drops; it does not move the ones that already worked.

## Why the drop was being missed

Two separate rules can put the engine into `drop`.

1. **`StreamingSectionDetector`** (`backend/app/services/lighting/section_manager.py`).
   It weighs every feature against a running centre of the last 30 seconds. On a cold
   play of the drop track that centre is still at intro level (0.04) when the drop
   lands, so every "is this loud for this track" gate is saturated. After 14 s of
   dense music the centre is 0.185, the fast z-score peaks at 1.24 against the 1.4 it
   needs, and the drop is refused. On this track the drop is not louder than the top
   of its own build at all (energy 0.23 before, 0.22 after); what changes is the low
   end.
2. **The decision engine** (`decision_engine.py`, `is_drop`): bass above 0.8, flux
   above 0.5, while in its own build-up state. Absolute thresholds, and it only reaches
   the section when strobe is enabled. It accounts for the +100 ms hits above and for 5
   of the 11 hits in the "before" column. It was not changed.

Neither rule was reliable after loud music, and which one fired depended on history.

## What changed

One file, `section_manager.py`: a second way into a drop inside
`StreamingSectionDetector`, beside the existing one. It asks the build, not the last
half minute.

- **A build**: the smoothed level stands at least 1.15 times above where it was a few
  seconds ago, and has done for at least 4 s. It is a ratio, so it does not move with
  the fader.
- **A release**: the bass share rises 0.20 above its own last few seconds. Bass
  arrives as a share of the spectrum, so that is level-free as well.
- **In that order.** The climb has to be 4 s old on the frame the bass comes back. A
  hard cut from a quiet record to a loud one jumps both at once and is refused.
- **The level holds.** A build that hits once and falls into a breakdown also gets its
  bass back; its level does not hold and its programme is no longer loud.
- **Still loud.** The same 0.60 programme-loudness gate as before, asked of about half
  a beat rather than one frame. The analyser's beat event arrives one block late, in
  the trough between two kicks, where the instantaneous value read 0.58 to 0.61 in the
  middle of a drop.
- **Same guard rails.** A beat event, the sections a drop may be entered from, and the
  4 s refractory all apply. The minimum time in the current section does not: after a
  loud record the build is often only named `buildup` as the drop lands, and waiting
  out that hold used up the release window.

Measured across every play in the bench before the thresholds were set: the bass jump
at a true drop peaked between 0.22 and 0.37, after a climb of at least 6.1 s. The only
material without a drop that showed a jump after a climb was the build that hits once
and breaks down (0.30), and there the fast level was 0.26 of the smoothed level against
a gate of 0.5, and programme loudness was 0.41 against 0.60.

## Still open

- **Three false drops, there before and after.** A quiet track cut straight into loud
  music (dense, the song, the DJ mix) is called a drop 0.7 to 3.5 s after the cut, at
  the same instant with the new rule on or off. It comes from the rules that were
  already there. Fixing it means changing them, which would move results that work
  today, so it was left alone.
- **A step up in level counts as a climb.** After a hard step the level stays above
  its lagged self for several seconds, so "a climb at least 4 s old" can be met with no
  build. A bass return of 0.20 in that window, with the level holding, would be called
  a drop. The four step-up plays above did not produce one, with the new rule on or
  off, but they are the only evidence.
- **Thin margin on short builds.** A 4-bar build gives a bass jump of 0.22 against the
  0.20 threshold, and is named 1.4 s late after loud music.
- **Late.** The new rule names the drop 0.5 to 0.9 s after it lands. That is the same
  order as the existing 716 ms and is covered by the same anticipation path; it is not
  an improvement on finding D2's "about one beat late".
- **Bass-light music.** The 0.20 jump assumes the low end carries a large share of the
  spectrum when it is present, as it does in dance music. A record whose bass share
  never exceeds about 0.3 cannot produce it and falls back to the older rule.
- **D3, the drop fading after ten seconds, is untouched.**

## Tests

`backend/tests/unit/test_drop_after_loud_music.py`, 16 tests.

- On hand-made features: a drop after loud music is caught; the same input is missed
  with the new rule switched off; a cold drop is caught once; the answer is the same at
  a quarter and at twice the level; two drops back to back are both caught. No drop on
  a cut from a thin quiet record to a loud one, a build that never releases, a build
  that falls into a breakdown, a quiet build and release, or a steady groove whose bass
  comes and goes. A second bass return inside the refractory does not re-trigger.
- On real synthesised audio, one continuous run through the analyser and the venue
  engine: the drop track after 14 s of dense music is caught, with no other drop named;
  a 100 BPM build after dense music is caught; dense, quiet, dense draws no drop.

Full backend suite: 1097 passed, 8 skipped, 5 expected failures (1081 / 8 / 5 before).
No expected-failure test changed state, so no marker was touched.
