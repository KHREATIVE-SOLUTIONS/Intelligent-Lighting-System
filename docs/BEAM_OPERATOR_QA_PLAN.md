# Beam Operator QA Plan

This QA plan defines deterministic, objective pass criteria for beam-operator behavior using canned timelines (no live audio dependency).

## Scope

The regression harness validates five quality dimensions:

1. **Section contrast ratio (verse vs chorus/drop)**
2. **Transition alignment error to downbeat**
3. **Beam-width intent adherence by section**
4. **Strobe budget compliance + anti-fatigue limits**
5. **Color novelty on section/song change**

Implementation lives under `backend/tests/qa/`.

## Canned Timeline Strategy

The harness uses a fixed synthetic song case (`stable-dance-track`) with:

- 24 seconds of 4/4 beat grid sampled every second
- Labeled sections (`verse`, `chorus`, `drop`)
- Deterministic effect outcomes per timestamp:
  - intensity
  - beam width
  - strobe on/off state
  - hue
- Explicit transition events near section boundaries

Because all inputs are static and in-repo, test results are repeatable across CI and local environments.

## Objective Thresholds (Pass Criteria)

| Metric | Threshold | Notes |
|---|---:|---|
| Section contrast ratio | `>= 1.8` | Chorus/Drop mean intensity divided by Verse mean intensity |
| Transition alignment error | `<= 120 ms` | Absolute error to nearest downbeat for each transition cue |
| Beam-width intent tolerance | `± 2.0°` | Average per-section beam width must fit section target window within tolerance |
| Strobe budget ratio | `<= 0.35` | Strobe-active frames divided by total frames |
| Max continuous strobe streak | `<= 2.0 s` | Anti-fatigue guardrail |
| Color novelty at boundaries | `>= 0.20` hue distance | Circular hue distance at section/song transitions |

### Section Beam-Width Targets

- **Verse:** `30°–35°`
- **Chorus:** `20°–24°`
- **Drop:** `10°–14°`

## Regression Test Inventory

- `test_section_contrast_ratio`
- `test_transition_alignment_to_downbeat`
- `test_beam_width_intent_adherence`
- `test_strobe_budget_and_anti_fatigue`
- `test_color_novelty_on_section_and_song_change`

## How to Run

From repository root:

```bash
cd backend
pytest tests/qa -v
```

Or run with full backend suite:

```bash
cd backend
pytest tests/ -v
```
