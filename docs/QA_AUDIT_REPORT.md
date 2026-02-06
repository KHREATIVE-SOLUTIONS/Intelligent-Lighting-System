# QA Audit Report: Intelligent Lighting System

**Date:** 2026-02-06
**Auditor:** QA Agent (Claude Opus 4.6)
**Scope:** Full codebase audit -- backend, frontend, visualizer
**Severity Scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

A comprehensive audit of the Intelligent Lighting System codebase identified **47 bugs** across the backend services, API endpoints, frontend stores, and 3D visualizer.

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 6     | Crashes, data corruption, security vulnerabilities |
| HIGH     | 14    | Logic errors, race conditions, incorrect behavior |
| MEDIUM   | 17    | Performance issues, missing error handling, minor logic bugs |
| LOW      | 10    | Code quality, style, minor improvements |

---

## CRITICAL Severity

### BUG-001: Race Condition on Shared Fixture State (Effects Engine + WebSocket)

**File:** `backend/app/services/effects/effects_engine.py` (lines 361-486)
**File:** `backend/app/api/endpoints/websocket.py` (lines 87-194)

**Description:** The `EffectsEngine.update()` method runs in its own `asyncio.create_task` loop at 60fps, mutating fixture state (`fixture.pan`, `fixture.tilt`, `fixture.dimmer`, `fixture.red`, etc.). Simultaneously, `update_effects_engine_audio()` in the WebSocket handler reads these same fixture properties (lines 141-151) to build `fixture_states` for the visualizer. There is no synchronization mechanism (lock, mutex, or snapshot) between the writer and reader.

**Impact:** Visualizer may receive partially-updated fixture state (e.g., pan from frame N but tilt from frame N+1), causing visual glitches and inconsistent lighting representation.

**Code:**
```python
# effects_engine.py - Writer (running at 60fps in asyncio task)
for i, fixture in enumerate(all_fixtures):
    fixture.pan = 128 + lfo_vals['pan'] * 255
    fixture.tilt = 128 + lfo_vals['tilt'] * 255
    fixture.dimmer = max(0, min(1, lfo_vals['dimmer']))

# websocket.py - Reader (called from WebSocket handler, concurrent)
for fixture in effects_engine.fixtures.fixtures.values():
    fixture_states.append({
        'pan': fixture.pan,      # May be stale
        'tilt': fixture.tilt,    # May be from different frame
        'dimmer': fixture.dimmer,
    })
```

**Suggested Fix:** Use an `asyncio.Lock` or have `update()` produce a snapshot dict that readers consume atomically.

---

### BUG-002: Division by Zero in DMX Fade Operations

**File:** `backend/app/services/dmx/dmx_controller.py` (lines 289-307, 331-349)

**Description:** `_fade_universe()` and `_fade_channel()` calculate `steps = int(duration * self.target_fps)`. If `duration` is very small (e.g., 0.001) and `target_fps` is 40, then `steps = int(0.04) = 0`. The subsequent loop uses `progress = step / steps = 0 / 0`, causing a `ZeroDivisionError`.

**Impact:** Runtime crash when calling `blackout(fade_time=0.001)` or any fade with very short duration.

**Code:**
```python
steps = int(duration * self.target_fps)  # Can be 0
for step in range(steps + 1):
    progress = step / steps              # ZeroDivisionError when steps=0
```

**Suggested Fix:** Add guard: `if steps == 0: steps = 1` or handle the zero case by setting the target value immediately.

---

### BUG-003: Buffer Overflow in Audio Analyzer

**File:** `backend/app/services/audio/audio_analyzer.py` (lines 124-136)

**Description:** `_update_buffer()` assumes `chunk_len <= buffer_size`. If a client sends an audio chunk larger than the 4-second buffer (176400 samples at 44100Hz), the slicing arithmetic breaks: `overflow` would exceed `chunk_len`, making `audio_data[:-overflow]` produce incorrect slices or empty arrays.

**Impact:** Memory corruption or numpy indexing errors if a client sends oversized audio data.

**Code:**
```python
def _update_buffer(self, audio_data: np.ndarray):
    chunk_len = len(audio_data)
    if self.buffer_index + chunk_len <= self.buffer_size:
        self.audio_buffer[self.buffer_index:self.buffer_index + chunk_len] = audio_data
    else:
        overflow = (self.buffer_index + chunk_len) - self.buffer_size
        self.audio_buffer[self.buffer_index:] = audio_data[:-overflow]
        # If chunk_len > buffer_size, overflow > chunk_len -- breaks
```

**Suggested Fix:** Truncate input at the start: `audio_data = audio_data[-self.buffer_size:]`

---

### BUG-004: Hardcoded Secret Key in Configuration

**File:** `backend/app/core/config.py` (line 19)
**File:** `backend/.env`

**Description:** The `SECRET_KEY` has a hardcoded default of `"your-secret-key-change-in-production"`. The `.env` file is checked into the repository with `SECRET_KEY=dev-secret-key-change-in-production-12345`.

**Impact:** Security vulnerability in production deployments. Any authenticated features are compromised.

**Suggested Fix:** Remove default value, require SECRET_KEY to be set explicitly. Add `.env` to `.gitignore`.

---

### BUG-005: Potential SQL Injection via ILIKE Search

**File:** `backend/app/api/endpoints/audio.py` (lines 151-155)

**Description:** The search parameter is interpolated directly into the ILIKE pattern using f-string formatting without escaping SQL wildcards (`%`, `_`).

**Code:**
```python
query = query.where(
    (AudioFingerprint.track_name.ilike(f"%{search}%")) |
    (AudioFingerprint.artist.ilike(f"%{search}%"))
)
```

**Impact:** SQL wildcard characters in user input are interpreted as wildcards, enabling unintended pattern matching.

**Suggested Fix:** Escape `%` and `_` in the search string, or use SQLAlchemy's `contains()`.

---

### BUG-006: Health Check Always Reports Healthy

**File:** `backend/app/main.py` (lines 205-216)

**Description:** The `/health` endpoint always returns `"status": "healthy"` with all services marked as running/connected/loaded/ready, regardless of actual service state. It does not check `app.state` for actual status.

**Impact:** Monitoring systems will never detect service failures, making outages invisible.

**Suggested Fix:** Check actual service state from `app.state` and return 503 if unhealthy.

---

## HIGH Severity

### BUG-007: Unclamped Pan/Tilt Values from LFO Engine

**File:** `backend/app/services/effects/effects_engine.py` (lines 394-397)

**Description:** LFO pan/tilt values are computed as `128 + lfo_vals['pan'] * 255` with no clamping to 0-255 range.

**Impact:** Invalid DMX values could reach fixtures, causing unpredictable behavior.

**Suggested Fix:** Add clamping: `fixture.pan = max(0, min(255, 128 + lfo_vals['pan'] * 255))`

---

### BUG-008: Beat Detection Double `is_beat` Calculation

**File:** `backend/app/services/audio/audio_analyzer.py` (lines 138-199)

**Description:** `_analyze_beat()` computes `is_beat` twice with different logic:
1. **Line 156:** First calculation with minimum interval guard (>200ms between beats) -- used for BPM tracking.
2. **Line 190:** Second calculation WITHOUT interval guard -- this is the value returned to callers.

The unguarded second check can fire even when the first correctly suppressed a too-close beat, causing spurious beat detections.

**Impact:** Jittery lighting effects and incorrect BPM estimation from spurious beats.

**Suggested Fix:** Remove the second `is_beat` calculation and return the properly guarded first one.

---

### BUG-009: Visualizer WebSocket Protocol Mismatch with Backend

**File:** `visualizer/server.py` (lines 190-213)
**File:** `backend/app/api/endpoints/websocket.py` (lines 197-360)

**Description:** The visualizer server expects `{"type": "dmx", "data": [...]}` and `{"type": "audio", "data": {...}}`. The backend sends `{"type": "analysis", "beat": {...}, "frequency": {...}, "mood": {...}, "lighting": {...}}`. Completely different schemas.

**Impact:** Direct connection between visualizer and backend WebSocket produces no visible output.

---

### BUG-010: LED Bar Channel Layout Mismatch Between Backend and Visualizer

**File:** `backend/app/api/endpoints/websocket.py` (lines 507-527)
**File:** `visualizer/js/fixtures.js` (lines 55-69)

**Description:** Backend reactive lighting uses LED bar channel layout: `Dimmer(0), R(1), G(2), B(3), W(4), A(5), UV(6), Strobe(7)`. Visualizer uses: `Dimmer(0), Strobe(1), R(2), G(3), B(4), W(5), A(6), UV(7)`. Strobe and color channels are at different offsets.

**Impact:** LED bars display wrong colors in the visualizer -- Red is interpreted as Strobe, Green as Red, Blue as Green, etc.

---

### BUG-011: Fire-and-Forget Fade Tasks in DMX Controller

**File:** `backend/app/services/dmx/dmx_controller.py` (lines 325-327)

**Description:** `execute_cue()` creates fade tasks with `asyncio.create_task()` but discards the task reference. Orphaned tasks continue running unmanaged.

**Impact:** Resource leak from orphaned asyncio tasks; potential errors during shutdown.

---

### BUG-012: Spectral Flux Inconsistency Between Beat Detection and Frequency Analysis

**File:** `backend/app/services/audio/audio_analyzer.py` (lines 138-169)

**Description:** Beat detection computes its own spectrum from raw FFT, while frequency analysis computes a separate spectrum potentially with different windowing. The spectral flux values diverge.

**Impact:** Spectral flux sent to the effects engine does not correlate with beat detections.

---

### BUG-013: WebSocket Config Update Passes Dict Instead of Pydantic Model

**File:** `backend/app/api/endpoints/websocket.py` (line 336)

**Description:** The handler passes `message.get("config", {})` (raw dict) to `audio_analyzer.update_config()`, which expects `AudioStreamConfig`.

**Impact:** `TypeError` at runtime when a client sends a config update via WebSocket.

**Suggested Fix:** `AudioStreamConfig(**message.get("config", {}))`

---

### BUG-014: Delete Operations Missing Explicit Commit

**File:** `backend/app/api/endpoints/audio.py` (lines 129-138, 225-238)

**Description:** `clear_analysis_history()` and `delete_fingerprint()` call `await db.delete()` without `await db.commit()`.

**Impact:** Delete operations appear to succeed (204) but data is not actually removed.

---

### BUG-015: Color Mapper Returns Stale Smoothed Color

**File:** `backend/app/services/effects/color_mapper.py` (lines 132-170)

**Description:** `get_color()` sets `self._target_color` but returns `self._current_color` (the old smoothed value from the previous frame). Since `update()` runs before `get_color()` in the effects loop, colors are always one frame behind.

**Impact:** Perceptible lag in color response to audio.

---

### BUG-016: Effects Engine Task Not Stored or Cancelled on Shutdown

**File:** `backend/app/main.py` (lines 83-84, 155-156)

**Description:** `asyncio.create_task(app.state.effects_engine.run())` discards the task reference. Shutdown only sets a flag without cancelling/awaiting the task.

**Impact:** Unclean shutdown; effects engine may continue after other services are torn down.

---

### BUG-017: Silenced Send Errors in ArtNet Output

**File:** `backend/app/services/dmx/dmx_controller.py` (lines 185-186)

**Description:** All socket send errors silently swallowed with `except Exception: pass`.

**Impact:** DMX output failures are invisible; lighting stops with no indication why.

---

### BUG-018: Non-Blocking Socket Used Synchronously

**File:** `backend/app/services/dmx/dmx_controller.py` (lines 111, 182)

**Description:** UDP socket set to non-blocking but used with synchronous `sendto()`, which can raise `BlockingIOError` when the send buffer is full.

**Impact:** Intermittent silent packet drops under load.

---

### BUG-019: Bare `except:` in WebSocket Handler

**File:** `backend/app/api/endpoints/websocket.py` (lines 185-186)

**Description:** Bare `except:` catches `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit`, preventing clean shutdown.

---

### BUG-020: Visualizer Server Creates New HTTP Session Every 16ms

**File:** `visualizer/server.py` (lines 110-168)

**Description:** `fetch_audio_data()` and `fetch_dmx_data()` each create new `aiohttp.ClientSession()` per call at 60Hz. That is 120 sessions created and destroyed per second.

**Impact:** TCP port exhaustion, high GC pressure, potential `OSError: Too many open files`.

**Suggested Fix:** Create one `aiohttp.ClientSession` at startup and reuse it.

---

## MEDIUM Severity

### BUG-021: Transition Speed Not Frame-Rate Independent (Color Mapper)
**File:** `backend/app/services/effects/color_mapper.py` (lines 122-130)
Color blending uses fixed factor without `delta_time` compensation. Transitions run faster at higher FPS.

### BUG-022: Movement Smoothing Not Frame-Rate Independent
**File:** `backend/app/services/effects/movement_patterns.py`
Smoothing factor applied per-frame without delta_time compensation.

### BUG-023: O(n) List pop(0) in Decision Engine Energy History
**File:** `backend/app/services/effects/decision_engine.py`
Use `collections.deque(maxlen=N)` instead.

### BUG-024: O(n^2) Wings Order Calculation in LFO Engine
**File:** `backend/app/services/effects/lfo_engine.py` (lines 188-191)
`get_wings_order_index()` rebuilds full order list and calls `.index()` for every fixture every frame. Pre-compute a lookup dict.

### BUG-025: `hashlib` Import Inside Hot Path
**File:** `backend/app/services/effects/lfo_engine.py` (lines 150, 240)
Move import to top of file.

### BUG-026: Markov Chain Missing Coverage for All Movement Types
**File:** `backend/app/services/effects/decision_engine.py` (lines 233-280)
Transition matrix only covers a subset of `MovementType` enum values.

### BUG-027: Waveform Function Signature Inconsistency (PWM and Random)
**File:** `backend/app/services/effects/lfo_engine.py` (lines 142-168)
`pwm()` needs `duty_cycle` and `random()` needs `seed` -- extra params not provided by generic caller. Causes `TypeError` at runtime.

### BUG-028: Three.js Resource Disposal Missing
**File:** `visualizer/js/visualizer.js`
No `.dispose()` calls on geometries, materials, or textures. GPU memory leak.

### BUG-029: WebSocket Reconnection Without Backoff
**File:** `visualizer/js/visualizer.js`
No exponential backoff on reconnection -- hammers server during outages.

### BUG-030: Random Strobe Probability Not Frame-Rate Independent
**File:** `backend/app/services/effects/strobe_controller.py`
Per-frame probability check frequency depends on FPS, potentially violating OSHA limits.

### BUG-031: Flicker Rate Assumes 60fps
**File:** `backend/app/services/effects/dimmer_effects.py` (line 60)
Hz-specified rate but frame-dependent evaluation.

### BUG-032: Channel Indexing Inconsistency in Frontend DMX Store
**File:** `frontend/src/stores/dmxStore.ts` (lines 69-76)
`setChannel` uses 1-based (`data[channel - 1]`), `setUniverse` uses 0-based.

### BUG-033: Training Recorder Flash Trigger No Auto-Reset
**File:** `backend/app/services/ml/training_recorder.py`
Flash state persists if caller forgets to reset, corrupting training data.

### BUG-034: Unbounded Test Pattern Task in DMX Controller
**File:** `backend/app/services/dmx/dmx_controller.py` (lines 372-398)
Infinite-loop test patterns persist after disconnect.

### BUG-035: GET Endpoint for State-Changing Test Pattern
**File:** `backend/app/api/endpoints/dmx.py`
Should use POST per REST conventions.

### BUG-036: broadcast() Iterates Over Set Without Snapshot
**File:** `backend/app/api/endpoints/websocket.py` (lines 59-81)
Concurrent `connect()`/`disconnect()` can cause `RuntimeError: Set changed size during iteration`. Use `list()` snapshot.

### BUG-037: `import random` Inside Broadcast Method
**File:** `backend/app/api/endpoints/websocket.py` (lines 67-68)
Unnecessary import in hot path for logging throttle.

---

## LOW Severity

### BUG-038: Missing `await db.commit()` After Fingerprint Delete
**File:** `backend/app/api/endpoints/audio.py` (lines 225-238)

### BUG-039: Deprecated `@app.on_event("startup")` in Visualizer Server
**File:** `visualizer/server.py` (lines 273-277)

### BUG-040: Silenced Polling Errors in Visualizer Server
**File:** `visualizer/server.py` (lines 185-186)

### BUG-041: LFO API Output Endpoint Causes Double-Update
**File:** `backend/app/api/endpoints/lfo.py` (lines 396-401)
Polling `/lfo/output` advances LFO phase, doubling effect speed.

### BUG-042: Bare `except:` Broadcast Error Handling in Visualizer
**File:** `visualizer/server.py` (lines 88, 105)

### BUG-043: Circle Floor Static Look Hardcoded for 8 Fixtures
**File:** `backend/app/services/effects/movement_patterns.py`

### BUG-044: `set_fixture_state` Method Is a No-Op
**File:** `backend/app/services/dmx/dmx_controller.py` (lines 351-362)

### BUG-045: `get_scene_state` Returns Empty Fixture List
**File:** `backend/app/services/dmx/dmx_controller.py` (lines 364-370)

### BUG-046: Missing `__init__.py` Validation for Effects Package Imports
**File:** `backend/app/services/effects/__init__.py`

### BUG-047: No Validation on WebSocket Binary Audio Data Size
**File:** `backend/app/api/endpoints/websocket.py` (lines 228-234)
No size limit on binary audio data from WebSocket clients. Memory exhaustion risk.

---

## Architectural Concerns

**A-001: No Async Lock on Shared Fixture State** -- `Fixture` objects are mutated by the effects engine loop and read by WebSocket handlers with no synchronization.

**A-002: Dual Data Flow to Visualizer** -- ArtNet UDP and REST API polling at 60Hz create conflicting state and 120 TCP connections/second.

**A-003: Training Mode Architecture Complexity** -- Full 4-layer effects engine maintained but mostly disabled, creating unnecessary complexity.

**A-004: No Rate Limiting** -- No rate limiting on any API endpoint or WebSocket.

---

## Recommended Test Cases

1. Send audio chunk larger than buffer_size, verify no crash (BUG-003)
2. Call `blackout(fade_time=0.001)`, verify no ZeroDivisionError (BUG-002)
3. Connect visualizer to backend WebSocket, verify data renders (BUG-009)
4. Concurrent effects update + WebSocket fixture read (BUG-001)
5. Verify `is_beat` consistency (BUG-008)
6. Rapid audio chunks with beats <200ms apart (BUG-008)
7. Verify LFO pan/tilt clamped to 0-255 (BUG-007)
8. Test pattern survive disconnect cycle (BUG-034)
9. LED bar channel layout cross-system match (BUG-010)
10. DELETE history actually removes data (BUG-014)
11. Search with `%` and `_` characters (BUG-005)
12. Visualizer server 1-hour TCP/memory monitor (BUG-020)
13. LFO wings at 64 fixtures -- frame time (BUG-024)
14. GPU memory during extended visualizer use (BUG-028)
15. WebSocket config update (BUG-013)
16. Oversized binary audio via WebSocket (BUG-047)
17. Rapid WebSocket connect/disconnect during broadcast (BUG-036)
18. Color mapper frame timing (BUG-015)
19. Effects at 30fps vs 60fps smoothing comparison (BUG-021/022)
20. PWM waveform selection in LFO engine (BUG-027)
21. SECRET_KEY not default in production (BUG-004)
22. Health endpoint reflects actual state (BUG-006)
23. Full pipeline: audio -> analysis -> effects -> DMX -> visualizer
24. Training data recording synchronization
25. LFO BPM sync via API
26. Song change detection via silence
27. Poll `/lfo/output` while running -- verify no speed doubling (BUG-041)
28. `set_fixture_state` method functionality (BUG-044)

---

## Summary of Affected Files

| File | Bug Count | Highest Severity |
|------|-----------|-----------------|
| `backend/app/services/dmx/dmx_controller.py` | 7 | CRITICAL |
| `backend/app/api/endpoints/websocket.py` | 6 | CRITICAL |
| `backend/app/services/audio/audio_analyzer.py` | 4 | CRITICAL |
| `backend/app/services/effects/effects_engine.py` | 4 | CRITICAL |
| `backend/app/services/effects/lfo_engine.py` | 4 | MEDIUM |
| `backend/app/api/endpoints/audio.py` | 3 | CRITICAL |
| `visualizer/server.py` | 3 | HIGH |
| `backend/app/services/effects/color_mapper.py` | 2 | HIGH |
| `backend/app/services/effects/decision_engine.py` | 2 | MEDIUM |
| `backend/app/services/effects/movement_patterns.py` | 2 | MEDIUM |
| `backend/app/main.py` | 2 | CRITICAL |
| `visualizer/js/visualizer.js` | 2 | MEDIUM |
| `backend/app/core/config.py` | 1 | CRITICAL |
| `backend/app/services/effects/dimmer_effects.py` | 1 | MEDIUM |
| `backend/app/services/effects/strobe_controller.py` | 1 | MEDIUM |
| `backend/app/services/ml/training_recorder.py` | 1 | MEDIUM |
| `backend/app/api/endpoints/lfo.py` | 1 | LOW |
| `frontend/src/stores/dmxStore.ts` | 1 | MEDIUM |
| `visualizer/js/fixtures.js` | 1 | HIGH |
