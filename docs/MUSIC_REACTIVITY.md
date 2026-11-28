# Music reactivity

How live music reaches the lights, what was wrong, what changed (November 2026,
branch `grok/music-reactive`), the switches, the meter, and how it is tested.

## Signal path

1. **Capture**: `backend/app/services/audio/system_audio_capture.py`. On the
   owner PC this is pyaudiowpatch WASAPI loopback of the Windows default output
   (Studio 24c Main Out 1/2), 48 kHz, 2048-sample blocks (42.7 ms each).
2. **Analysis**: `AudioAnalyzer.process_chunk` gives RMS, bands, beat (`is_beat`,
   `beat_count`, `bpm`, `tempo_confidence`), mood and ML data.
3. **Mapping**: `main.py on_audio_chunk` calls `EffectsEngine.update_audio`.
   `energy = engine_energy(rms)` is roughly `rms * 2`. The same mapping is
   mirrored by `tests/musical/metrics.analysis_to_engine_kwargs`.
4. **Engine**: `EffectsEngine.update` runs at 60 fps. In auto mode the live
   renderer is **`_update_fixtures_rebuild`**. The old `_update_fixtures` chain
   (the dimmer product near the former lines 4007-4222, with
   `section_manager.get_intensity()`, `decision.get_dynamic_intensity_scale()`
   and so on) is *not* the live path in auto mode. The phase-locked beat clock
   (`_beat_clock_*`) gives `beat_phase` / `bar_phase`.
5. **Output**: DMX frames go to the output stage, which applies the grand
   master, blackout, flash limiter and watchdog, then to Art-Net/sACN. The
   broadcast loop also sends them to the 3D view at 30 fps.

## What was wrong

* **Dim, compressed output.** The live renderer sets a fixture to
  `energy × section floor × role shape`. Here `energy ≈ 2·rms ≈ 0.3-0.5`, the
  floor is about 0.68 in verse, and the bar pattern averages 0.5. Dense music
  therefore sat at a 5-21 % rig mean that tracked loudness, with no beat in it.
  Dense music has no gaps between kicks, so loudness alone does not punch.
* **Capture flapping in silence.** The watchdog treated 5 s with no blocks as a
  lost device, and its comment said "silence still delivers blocks". That is
  false for WASAPI loopback: with nothing playing there are no callbacks at
  all. Before the DJ pressed play, the stream was torn down and the devices
  rescanned every 5-10 s. The soundcard scan subprocess crashed each time
  ("aborted the scan"), and music that started mid-rescan was missed.
* **Colour and motion** (diagnosed, not changed; see "Left open"). The base
  colour is blended continuously (`0.018` per frame) toward
  `_rebuild_get_emotional_color`. At mid valence and arousal that is the
  average of four corner colours, about (0.6, 0.4, 0.5): the pale mauve Grok
  measured. The palette colour's HSV value is below 1, and white accents of up
  to 0.42 re-arm whenever bass is at or above 0.62. The breakdown narrative
  (`color_count 1`) turns it grey. The "movement_pattern none" in telemetry
  comes from `pro_movement`, which the live renderer never drives; heads are
  aimed by `live_looks.head_pan_tilt`. It is a label, not proof the heads are
  still.

## What changed

### Beat response stage (engine)

The final stage of `_update_fixtures_rebuild` runs per fixture, after the
dimmer chain and the drop-anticipation dip and before the audience cap. Strobe
flash frames are left untouched.

* **Output make-up gain** (`_makeup_gain_now`, `_makeup_adapt`). A slow AGC
  tracks the rig mean before gain (time constant `makeup_time_constant_s`, 4 s)
  and sets `gain = clamp(makeup_target / ref, 1, makeup_gain_max)`. The default
  maximum is 5x rather than 4x: the pulse's troughs lower the mean and the LIV
  rig's 8 strobes sit dark, so 4x left dense music just under 45 %. The AGC
  learns only during ordinary playing. Silence, breakdown, drop, the
  anticipation dip and strobe windows freeze it, so it cannot pump a noise
  floor or flatten the build-to-drop step. Gained levels clamp at
  `audience_intensity_cap`.
* **Beat pulse** (`_beat_pulse_step`). Each fixture's factor is
  `1 − depth·(1 − env)`: a dip between beats and the full gained level on the
  beat. It is a trough under the clamped level, never a lift above it, so
  nothing clips on the beat.
  * **Envelope**: 8 ms attack, then a decay of `0.33 × beat`, clamped to
    120-200 ms (155 ms at 128 BPM).
  * **Who gets it**: bars, pars/beds and moving washes get the full depth;
    beams (movers) get half; strobes get gain only.
  * **Depth by section** (× `beat_pulse_depth`, 0.6): drop/peak/chorus 1.0,
    buildup 0.9, verse 0.8, intro 0.7, breakdown 0.35.
  * **Trigger**: the locked beat clock's integer crossing, timestamped at the
    crossing rather than the frame, else the analyser's `is_beat`.
* **Silence**: nothing happens without music. The stage runs only while the
  raw input is above `silence_threshold`, audio arrived within the last 0.5 s
  (loopback sends nothing in silence), audio is not lost and the idle look is
  down. It ramps in over 0.5 s and out over 0.25 s. Idle and idle-look
  behaviour is unchanged.
* **Photosensitivity**:
  * Pulses are at most `min(3 Hz, strobe_hz_cap)` (2 Hz if the cap is
    unreadable), with a 20 ms margin. Beats faster than that pulse every other
    beat.
  * No pulse fires while a drop or snare strobe window is open.
  * In `no_strobe` and similar postures (any posture other than
    `conservative`/`performance`, camera mode, theatre/broadcast/corporate
    venues) the pulse is gentle: depth at most 0.15 and a 60 ms attack. That
    keeps it under the output stage's flash rise of 0.18 in 100 ms, so it is
    never a flash.
  * The output stage's flash limiter still applies on the wire. At 128 BPM
    the pulses (2.1 Hz) fit inside the conservative 3 Hz budget.

### Config switches (`EffectsConfig`)

| field | default | meaning |
|---|---|---|
| `beat_pulse_enabled` | `True` | beat pulse on/off |
| `beat_pulse_depth` | `0.6` | depth in drop/chorus (0-0.9); sections scale it |
| `output_makeup_gain_enabled` | `True` | output AGC on/off |
| `makeup_target` | `0.5` | rig mean dimmer the AGC aims for |
| `makeup_gain_max` | `5.0` | upper bound of the gain (lower bound is 1x) |
| `makeup_time_constant_s` | `4.0` | AGC time constant |

Turning both switches off gives exactly the previous output.

### Capture watchdog

For `pyaudio_loopback` and `soundcard_loopback`, a gap in blocks while the
stream is open and active counts as **silence**, not as a lost device. Capture
reconnects only when:

* the stream reports inactive (`is_active()` is false, or the soundcard thread
  has died), or
* the device has left the list. This check runs at most every 30 s while
  silent and scans only the backend in use. A scan that fails or finds nothing
  means "unknown", never "gone".

sounddevice (line-in, interface) keeps the old 5 s rule. The status shows
`silent: true` while loopback is quiet.

### Meter

`meter` is a new key in the websocket `analysis` payload (broadcast loop) and in
`GET /api/audio/capture/status`. Existing fields are unchanged. It is built by
`app/services/audio/meter.py` and contains:

* level: `rms`, `peak`, `rms_dbfs`, `peak_dbfs`. Zeroed once the last block is
  more than 0.5 s old, so the meter never freezes at the last loud block.
* tempo: `bpm`, `beat_count`, `seconds_since_beat`, `beat_phase` (only when
  the clock is locked), `clock_locked`.
* capture: `running`, `silent`, `device_name`, `capture_method`, `block_age_s`.
* stage: `pulse_level`, `pulse_count`, `makeup_gain`.

**UI**: `frontend/src/components/common/LevelMeter.tsx` sits next to the audio
device chooser in the 3D visualizer toolbar and on the dashboard.

* **Bar**: RMS on a −60…0 dBFS scale, with a white peak tick.
* **Pink dot**: flashes on each new `beat_count`.
* **BPM text**: the tempo.
* **Hints**:
  * "Audio capture is not running".
  * "Signal too low - check the output device / volume" when RMS stays below
    −50 dBFS for 1.5 s while capture runs.
  * "Waiting for audio data" when no meter arrives.

It draws with `requestAnimationFrame` from refs, with no React state per
message; text refreshes at most 4 times a second.

**Reading it**: a healthy club feed sits around −20 to −10 dBFS RMS with peaks
near −3. The dot should blink in time with the kick and the BPM should settle
within a few seconds.
* **Silent dot, healthy level**: the analyser has not locked a beat yet.
* **Moving bar, "Signal too low"**: Windows is playing to a different output
  than the one captured, or the volume is down.

## Tests

* `backend/tests/unit/test_beat_response_stage.py` drives the engine directly.
  It checks that the stage lifts the rig and deepens the per-beat swing, that
  switched off it does nothing, that the gain is bounded, that silence and a
  paused feed stand it down, and that pulses stay at or under 3 per second at
  240 BPM. It also checks `no_strobe` depth ≤ 0.15, breakdown < drop, and the
  beat meter.
* `backend/tests/musical/test_beat_response.py` uses a generated 20 s, 48 kHz,
  128 BPM track (kick, offbeat hats, offbeat bass, sustained pad; no
  downloads). It runs through the real analyser, main.py's mapping and the
  venue-posture engine with the accent governor on the LIV rig, **causally**:
  every frame up to a chunk's completion is rendered before that chunk is fed.
  After 4 s of lock-in it asserts:
  * a rig-mean local peak on ≥ 90 % of kicks;
  * a peak-to-trough swing ≥ 0.2 on ≥ 90 % of beats;
  * added latency < 50 ms on ≥ 90 % of beats. Latency runs from the moment the
    chunk holding the kick completes to the first frame at half the pulse
    height.
  * a rig mean of 0.3-0.7 with a p95−p5 spread of at least 0.2;
  * the beat survives a real `OutputStage` flash limiter (bytes only, nothing
    sent);
  * silence and −70/−60 dBFS noise stay dark, with gain at 1;
  * `no_strobe` stays gentle, and pulses stay at or under 3 per second.

  A wall-clock test checks that `process_chunk + update_audio` takes under
  20 ms median; skip it with `SKIP_PERF_TESTS=1`.
* **Inherent block duration: 2048 / 48000 = 42.7 ms.** A kick is not available
  to the backend until its block completes. That wait is reported separately
  and is *not* part of "added latency". With the beat clock locked the pulse
  is **predictive**: the clock fires on the learned grid, so the light can land
  on the kick before its block is even complete, and the added latency can be
  negative. On `is_beat` fallback it is one frame (≤ 16.7 ms) plus the attack.
* The existing contract suites hold the stage off because their baselines
  predate it. That covers `tests/musical/metrics.LIVE_ENGINE_KWARGS` and
  `VENUE_ENGINE_KWARGS` (drop step, anticipation deltas) and
  `tests/unit/test_live_roles._club_engine` ("never brighter than energy ×
  floor"). The safety properties with the stage on are asserted in
  `test_beat_response.py`.

**Results**: not yet run in this environment. Python and pytest are run by
Grok. Paste the printed lines from `pytest -s tests/musical/test_beat_response.py`
here: local-peak share, swing median/p10, added-latency median/p90/worst,
rig mean, gain, and per-chunk wall time.

## Left open

* Colour saturation and the motion checks (see "What was wrong"). Diagnosed
  but not changed in this branch.
* The bare-`EffectsConfig()` users in `test_rig_swap_repairs.py` and
  `test_accent_governor.py` were not individually audited. If one asserts
  absolute dimmer levels under music, pass `beat_pulse_enabled=False,
  output_makeup_gain_enabled=False` there.
