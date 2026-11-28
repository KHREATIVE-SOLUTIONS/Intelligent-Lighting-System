# Previz performance (3D visualizer)

## What changed
- Canvas asks for the discrete GPU (`powerPreference: 'high-performance'`); pixel ratio capped at 1.25 (Perf), 1.5 (Balanced), 2 (Ultra), never above the screen's own.
- Shadows are off by default (toolbar **Shadows** toggle). Fixture labels are off by default on rigs over ~40 fixtures (toolbar **IDs**).
- Floor pools are one instanced additive decal draw instead of up to 24-40 real SpotLights (each of which every lit pixel had to loop over).
- Fixture bodies (yoke, head, lens) and beams are InstancedMesh per model kind, all updated in one Scene-level frame callback from refs (`previs/fixtureRuntime.ts`, `previs/FixtureRig.tsx`). The DMX readout, smoothing and pan/tilt motion maths are unchanged.
- Static haze sheets merged into one draw.
- The analysis websocket still feeds the 3D view every message (refs), but store writes for the readouts are throttled to 10/s and skipped when unchanged (`previs/storeThrottle.ts`).
- **Stats** toggle: overlay with fps, frame ms, draw calls, triangles; the same numbers on `window.__previzStats` every 500 ms.

## Measured (LIV Miami demo rig, 131 fixtures, Balanced, live music feeding the engine)
Headless Chrome on the owner's RTX 4070 (ANGLE D3D11), vsync off, 10 s, scripted (`requestAnimationFrame` frame times, WebGL draw calls counted by wrapping drawElements/drawArrays).

| | before | after |
|---|---|---|
| 1080p viewport: frame median / p95 / p99 | 5.8 / 12.0 / 17.7 ms | 0.8 / 2.2 / 6.3 ms |
| 2560x1440 at dpr 1.5 (4K-class): median / p95 / p99 | 7.8 / 25.2 / 56.6 ms | 0.8 / 2.0 / 5.2 ms |
| draw calls per frame | ~810 | 47 |
| triangles per frame | ~1.02 M | ~0.45 M |

Headless numbers on one GPU; a real browser at vsync will show a flat 60 (or the monitor rate). On a laptop iGPU expect lower but the same relative gain.

## How to measure yourself
Open the visualizer, press **Stats**. Or in the browser console: `window.__previzStats`.

## Look controls
Haze, soft beams, bloom, exposure, gobos and drifting haze, with what each is expected to cost, are in [PREVIZ_LOOK.md](PREVIZ_LOOK.md). The numbers above were measured before those were added. With Bloom on, the draw-call count includes the bloom passes.
