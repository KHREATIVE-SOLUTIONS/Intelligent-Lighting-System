# Frontend bundle size

`npm run build` used to produce one main JS chunk of about 1.7 MB (about 500 KB
gzip) and a chunk-size warning. That matters on a venue laptop and on a phone
opening the app from a QR code: everything in that chunk downloads and parses
before the first screen shows.

## Before / after

| Chunk | Before raw | Before gzip | After raw | After gzip |
|---|---|---|---|---|
| main entry (`index-*.js`) | ~1.7 MB (reported) | ~500 KB (reported) | **not measured** | **not measured** |
| RigVisualizer (three, fiber, drei, previs) | in main | in main | **not measured** | **not measured** |
| other route chunks | | | **not measured** | **not measured** |

**Not measured yet:** `npm run build`, `npx tsc --noEmit -p .` and
`npx vitest run` were refused by the permission mode of the session that made
this change (2026-11-28), so neither the before nor the after table could be
filled in from a real build. Fill it in with the steps under "How to check":
build on `master` for the before column and on this branch for the after column.

## What is lazy now

Route pages (`frontend/src/App.tsx`, `React.lazy` + `Suspense` with the existing
`Loading` spinner):

- `RigVisualizer` on `/visualizer` and `/rigs/:id/visualizer`. This is the big
  one: `three`, `@react-three/fiber`, `@react-three/drei` and every
  `components/rig/previs/*` geometry module.
- `ShowList`, `ShowEditor`, `RigList`, `RigEditor`.
- Already lazy before this change: `FixtureLibrary`, `FixtureDetail`,
  `FixtureEditor`, `RigBuilder` (and with it the room scan, room shell edit,
  stage plot and readiness dialogs it imports), `RigWizard`.

Still eager, because they are the first screen: `Layout`, `Dashboard`,
`LoginScreen`, MUI, React, react-router, zustand, axios.

Heavy libraries:

- `pdfjs-dist` (stage plot PDF import) was already loaded with a dynamic
  `import()` inside `utils/pdfjsLoader.ts`, worker included. Unchanged.
- There are no QR, zip or PDF-generation libraries in `package.json`.

### three.js leak through the 2D plan

Rollup places a module by the static import graph, not by which exports
survive tree-shaking, and the 2D room builder reached three.js:

```
RigBuilder -> RigEditorToolbar / StageView2D -> rowSpace2d -> roomPlan2d -> previs/roomShell -> three
RigBuilder -> RoomShellEditDialog -> utils/roomShellEdit -> previs/roomShell -> three
```

RigBuilder was already lazy, so this did not put three in the entry chunk,
but it made the 2D builder page download three.js for nothing.

`roomPlan2d` and `roomShellEdit` only need the plain checks `usableBox`,
`usableLine`, `usableRing`, `scanRings` and `scanRisers`. Those now live in
`previs/roomShellData.ts`, which has no three.js import. `roomShell.ts`
re-exports them, so its other importers and the tests are unchanged.

Rule for new code: a module the 2D plan, the editor or the dashboard imports
must not import `three`, `@react-three/*`, or any previs file that does
(`geometryKit`, `materials`, `fixtureGeometry`, `beamShape`, `roomShell`, the
`.tsx` scene parts). Put plain maths in a three-free file as `outline.ts`,
`layout.ts`, `fixtureDrag.ts` and `roomShellData.ts` do.

### Not done

- No `manualChunks`. Splitting React or MUI into a vendor chunk does not cut
  the initial JS (the entry still imports them), and a catch-all
  `node_modules -> vendor` rule would pull three.js back into the first load.
  Rollup already gives three its own lazy chunk once nothing eager imports it.
- Dialogs inside eager-by-route pages (`ImportExportDialog` in `RigList`,
  `FixtureTestPanel` in `RigEditor`) are not lazy. They now ship with their
  page's chunk, not the entry chunk. A lazy dialog rendered with `open={false}`
  still loads as soon as its parent renders, so this would need a "mount on
  first open, then keep mounted" latch and tests using `findBy`. Not worth it
  without a measured build.

## How to check

```
cd frontend
npm run build
```

Vite prints one line per chunk with its raw and gzip size. Check:

1. The entry chunk (`dist/assets/index-*.js`) is far below the old ~1.7 MB and
   the chunk-size warning is gone or names only the visualizer chunk.
2. three.js is not in the entry chunk:
   `grep -l "WebGLRenderer" dist/assets/*.js` should list only the
   RigVisualizer chunk (or a shared three chunk it imports), never `index-*.js`.
3. Open `/` in the browser DevTools Network tab: no three chunk loads until you
   open the visualizer.

Then `npx tsc --noEmit -p .` (13 pre-existing errors, no new ones) and
`npx vitest run`.
