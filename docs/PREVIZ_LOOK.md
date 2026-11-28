# Previz look: haze, soft beams, bloom, gobos

The 3D visualizer is meant to read like a club in haze: beams bright at the lens and fading into the room, soft at the cone edge, lenses that glow, gobo patterns in the pools. Each part can be switched off. Performance work it builds on: [PREVIZ_PERFORMANCE.md](PREVIZ_PERFORMANCE.md).

## Controls

In the toolbar: a **Haze** slider and a **Look** button. Look opens Exposure, Bloom, Soft beams, Gobos, Drifting haze and Reset look. Everything is kept in localStorage under `previz:look` (`previs/lookSettings.ts`). Bloom is kept separately for each quality.

| Control | Default | What it does | Expected cost |
|---|---|---|---|
| Haze (0-1) | 0.5 | Scales beam visibility, FogExp2 density (0.0015 + 0.009 x haze; 0.006 at the default, as before), and the old static haze sheets and specks (unchanged at 0.5, gone at 0). At 0, beams show only at the lens and in their pools. | none (uniforms) |
| Soft beams | on | Beam alpha = level x (1.2 x haze x falloff(d) + lens glow(d)) x edge(\|N.V\|). falloff = 0.2 + 0.8 / (1 + (d/3 m)^2). The lens glow is 0.35 x e^(-d/0.35 m). The edge is a smoothstep with a 0.12 floor, so a beam seen end on does not vanish. Off: the old flat 0.42, scaled by haze / 0.5. | a few ALU per beam fragment |
| Bloom | on in Balanced/Ultra, off in Perf | EffectComposer: RenderPass, then UnrealBloomPass (strength 0.55, radius 0.45, threshold 0.82), then OutputPass. HalfFloat target, MSAA 4 in Balanced/Ultra. Driven by `useFrame(..., 1)` so r3f does not render a second time. Unmounted when off. | the largest item: about 1 ms/frame at 1080p on a desktop GPU (expected), plus about 10 draw calls |
| Exposure | 1.2 | `gl.toneMappingExposure`, set only through the Canvas `gl` prop. Ultra multiplies it by 1.1, as before. OutputPass reads the same value when bloom is on. | none |
| Gobos | on | Pools sample a 512x64 procedural atlas (open, dots, breakup, star, ring, lines). Each instance carries its own pattern and angle. Open pools never touch the atlas. | one texture read per gobo pool fragment |
| Drifting haze | on | 5/8/12 camera-facing soft noise puffs (Perf/Balanced/Ultra) in one instanced draw. They drift slowly and glow faintly with the rig's average colour. They fade near the camera, the floor and the ceiling. | fill rate: a few screens of additive quads; 1 draw call |

## Where it lives
- `previs/beamLook.ts`: the beam falloff, lens glow and edge maths. It is written once in JS, and the same constants generate the GLSL (`BEAM_LOOK_GLSL`).
- `previs/beamShape.ts`: the instanced beam shaders. The vertex shader passes the distance down the beam, a radial world normal and the eye vector.
- `previs/lookUniforms.ts`: the uniform objects shared by the beam, pool and haze materials. A slider writes one number and nothing re-renders.
- `previs/HazeDrift.tsx`, `previs/hazePuffs.ts`: the drift layer and its pure helpers (seeded noise, puff layout).
- `previs/PostFX.tsx`: `BloomComposer`. Only `RigVisualizer` imports it.
- `previs/gobo.ts`: the patterns, the atlas pixels, `goboAtlasUv`, and decoding of the gobo channels. `FloorPools.tsx` holds the texture and the pool shader.
- `previs/LookControls.tsx`: the toolbar group.

The beam, pool and haze shaders end with three's `tonemapping_fragment` and `colorspace_fragment`, so the image grades the same with bloom on or off. When drawing into the composer's render target those includes do nothing and OutputPass does the work. Before this change the beams and pools skipped tone mapping. They now go through ACES like everything else, so saturated beams look slightly less hot with Bloom off than they did.

## How the gobo is read
From the output frame, through the fixture's profile (`beamState.ts`, then `gobo.ts`):
- **Gobo channel.** Named value ranges decide first. "Open" gives an open pool. A name that says what the gobo looks like ("Dots", "Star", "Ring", "Leaves") gets that pattern. Any other name ("Gobo 3") gets a pattern by its place on the wheel. With no names, the value is matched to the nearest of the engine's `GOBO_SLOTS` positions (`gobo_engine.py`). Below 15 is open.
- **Gobo rotation.** Named ranges decide first: CW and CCW (speed rises across the range), Stop, and Index (a fixed angle). With no names, the byte is the wheel angle, 0-255 for one turn, which is what the engine writes. Angles are never smoothed, because they wrap.

**Known gap (backend, not changed here):** the gobo engine sets `fixture.gobo_index`, but `_render_fixture` writes `fixture.gobo` to the wire, and nothing sets that. So on the demo rigs the gobo byte stays at its home value and the pools show open, even with Gobos on. The rotation byte is written. Gobo patterns appear for any frame that actually carries a gobo value, such as a desk, a test frame, or a future engine fix.

With **Shadows** on, the brightest few pools become real spot lights. Those pools show no gobo.

## Not measured yet
This was written without running the app, so none of the costs above have been measured. To measure them, open the visualizer on the LIV demo rig at 1080p, press **Stats** (or read `window.__previzStats`), and toggle each control. The same scripted headless method as in PREVIZ_PERFORMANCE.md applies. Bloom adds its passes to the draw-call count, since the sampler counts every render call in a frame.

These values need tuning by eye: bloom strength and threshold, `BEAM_HAZE_GAIN`, the falloff half distance, the lens glow, the puff brightness (`HAZE_PUFF_BASE`, `HAZE_PUFF_GLOW`), `GOBO_FILL`, `GOBO_POOL_SPAN`, and pool brightness now that pools are tone mapped.

The task asked for a CanvasTexture for the gobo atlas. It is a DataTexture built from plain pixels instead, so it needs no 2D canvas and the tests can check its pixels under jsdom.
