# `diagnostic_show` Regression Mode

Use the **Diagnostic Show** toggle in the visualizer (`/index.html`) to run a deterministic 25s sequence that ignores incoming audio and websocket DMX/audio updates.

Sequence:
1. Wide pan sweep
2. Tilt fan
3. Zoom from tight to wide
4. Strobe burst
5. Crisscross phase pattern

## Why this exists

Run this mode as a quick regression check any time fixture channel mapping or controller/animation logic changes. It verifies the full path from:

- logical value generation,
- mapped DMX channel writes,
- rendered fixture/head output.

If a step looks wrong, open the browser console and inspect `diagnostic_show` warnings. Each warning reports:

- fixture and step,
- logical parameter value,
- mapped channel value,
- rendered output value (when available).

This helps isolate whether the breakage is in authoring logic, fixture mapping, or rendering.
