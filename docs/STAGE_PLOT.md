# Stage plot underlay

Status: **built. The backend is tested (pytest, full suite passing). The
frontend tests were written but not run**, and the frontend was not built, in
the sessions that wrote them: `npm test -- --run`, `npx vitest run`,
`npm run build` and `npx vite build` were each refused by the session's
permissions. `npx tsc --noEmit -p .` was run and shows only the 13 errors
already in the app. Run `npm test -- --run` and `npm run build` in
`frontend/` before relying on it.

## The problem it solves

A patch sheet import (`POST /api/import/patch-sheet`, see
[FLASH_AND_TAP.md](FLASH_AND_TAP.md)) builds a 3D layout on a stage template.
Every position in it is a guess, tagged `position_unconfirmed`. The venue
usually has a stage plot, as a PDF or a photo of one on the wall. Laid under
the 2D plan at the right scale, it shows where each light really hangs, and
the operator drags the guesses onto it.

## Using it (2D plan in the rig builder)

1. **Stage plot → Upload.** Choose a PNG, JPEG or WebP image of the plot, or
   a PDF. Until it is calibrated, the image is drawn fitted to the stage.
   - **A PDF** is opened in the browser (pdf.js, bundled with the app: nothing
     is sent anywhere but this app's own server). A one-page PDF goes straight
     up. With more pages, a dialog asks **which page is the stage plot**: Prev
     and Next, or type the page number, with a small picture of the page.
   - The page is drawn as a PNG about 3000 px on its long side. If that PNG
     would be over the server's 15 MB, it is drawn smaller (at most four
     tries, never below 1000 px); if it still does not fit, you are asked to
     export the page as a JPEG.
   - The PNG is stored as `<name>.pdf, page N.png`, so the info's `filename`
     says which PDF and page the plot came from.
   - A password-protected, damaged, empty or page-less PDF is not uploaded;
     a sentence says which, and what to do.
2. **Calibrate.**
   - Click point **A** and point **B** at the two ends of a length you know: a
     truss, the stage edge, a dimension line.
   - Click the **origin** (O), the point on the plot that is the middle of the
     stage.
   - Type the distance from A to B in metres. Turn the plot with **Rotate**
     until upstage is up, then **Save calibration**. The preview follows as you
     go.
   - **Pick again** clears the three points; **Cancel** keeps what was stored.
   - Fixtures cannot be picked up while calibrating.
3. **Drag the amber-ringed fixtures** onto where the plot shows them. A dashed
   amber ring marks every fixture whose position is still a guess. While the
   stage plot is shown, a guessed fixture dragged (or nudged with the arrow
   keys) is stored through the same route the 3D view's drag uses
   (`PUT /api/rigs/{id}/fixtures/{fixture_id}/position`). That takes the guess
   flag off, and the ring goes. With the plot hidden or absent, a drag on the
   plan leaves a guess a guess, as it always did. Undo puts a fixture back
   where it was, but does not make it a guess again.
4. **Opacity** sets how strongly the plot shows. It is saved with the
   calibration; without a calibration it only applies on screen.
   **Hide/Show** is for this screen only. **Remove** asks first, then takes
   the image and its calibration off the rig. Fixtures stay where they are.

## API

All routes are under `/api` and behind the operator token. Nothing here
reaches a device.

| Route | What it does |
|---|---|
| `POST /rigs/{id}/stage-plot` (multipart `file`) | Stores the image, replacing one before it and clearing its calibration. 201 with the info below. |
| `GET /rigs/{id}/stage-plot` | The image as uploaded, with its sniffed `Content-Type` and `Cache-Control: no-store`. 404 when there is none. |
| `GET /rigs/{id}/stage-plot/info` | `present`, `filename`, `content_type`, `byte_size`, `width_px`, `height_px`, `uploaded_at`, `calibration`, `transform`. `present: false` when there is none. |
| `DELETE /rigs/{id}/stage-plot` | Removes the underlay only. `{"removed": true/false}`. |
| `PUT /rigs/{id}/stage-plot/calibration` | Body below. Answers `{calibration, transform}`. 404 when there is no plot. |

Refusals:

- **415:** not a PNG, JPEG or WebP, or a PDF. The type is read from the
  file's first bytes; the name and the client's content type are ignored.
  The server has no PDF renderer, so a raw PDF sent to the route is still
  refused; the sentence says to choose it in the app's Stage plot control,
  which converts it, or to export the page as an image.
- **413:** over 15 MB.
- **400:** an empty file, a header whose size cannot be read, or a
  calibration that cannot be used. The detail is a sentence.
- **404:** an unknown rig, on every route.

Calibration body (image pixels: x right, y down, from the top-left corner):

```json
{
  "point_a": {"x": 100, "y": 100},
  "point_b": {"x": 300, "y": 100},
  "distance_m": 4.0,
  "origin": {"x": 200, "y": 300},
  "rotation_deg": 90,
  "opacity": 0.4
}
```

Refused with a 400 for any of these:

- a number that is not finite;
- A and B less than 2 px apart;
- a distance that is not more than 0 and at most 1000 m;
- an opacity outside 0 to 1.

The rotation is given back within (-180, 180].

## The transform

`room = s · R(rotation) · (pixel − origin)`, where
`s = distance_m / |B − A|` is metres per pixel.

- Plan x runs across the stage; plan z runs downstage, which is down the plan.
- With no rotation, the image's down is downstage.
- A positive rotation turns the plot clockwise as seen on the plan.
- The origin pixel lands on (0, 0), the middle of the stage.

`transform` carries:

- `scale_m_per_px` and `rotation_deg`;
- `offset_x` and `offset_z`: where the image's top-left pixel lands on the plan;
- `matrix`: SVG's `matrix(a b c d e f)`, with
  `x = a·u + c·v + e` and `z = b·u + d·v + f`.

For the example above, the matrix is `[0, 0.02, −0.02, 0, 6, −4]`. Both
`backend/tests/unit/test_stage_plot.py` and
`frontend/src/__tests__/stagePlot.test.ts` check that example, so the server
and the plan's live preview (`frontend/src/utils/stagePlot.ts`) cannot drift
apart.

## Where it lives

- `backend/app/models/stage_plot.py` and `backend/alembic/versions/010_rig_stage_plots.py`:
  - One row per rig in its own table, `rig_stage_plots`.
  - The image is never read with the rig. Uploading, calibrating and removing
    change nothing on the rig, not even its `updated_at`.
  - Deleting a rig deletes its plot.
- `backend/app/services/stage_plot.py`: magic-byte sniffing, pixel size read
  from the PNG/JPEG/WebP header (no imaging library), and the calibration maths.
- `backend/app/api/endpoints/stage_plot.py`: the routes.
- Frontend files:
  - `frontend/src/services/stagePlotApi.ts`: the requests. The image is
    fetched as a blob with the token and shown from an object URL, as the
    patch sheet is.
  - `frontend/src/components/rig/useStagePlot.ts`: the state and the
    calibration draft.
  - `frontend/src/components/rig/StagePlotControl.tsx`: the control.
  - `StageView2D`'s `underlay`, `onPlanPick` and `pickMarks` props, and the
    guess ring in `StageView2D`.

- PDF stage plots (browser only):
  - `frontend/src/utils/pdfjsLoader.ts`: loads `pdfjs-dist` and its worker
    only when a PDF is chosen (a lazy `import()`; the worker is Vite's bundled
    copy through `?url`, typed in `src/pdfjs-worker.d.ts`). Tests mock this
    module, so vitest never loads pdf.js.
  - `frontend/src/utils/pdfStagePlot.ts`: which files are PDFs, the sentences
    for each failure, the scale and the shrink-until-15-MB loop, the PNG's
    name. Opened with `isEvalSupported: false`; no fonts or cMaps are fetched.
  - `frontend/src/components/rig/StagePlotPdfPicker.tsx`: the page dialog.

The one dependency added is `pdfjs-dist` (frontend, Apache-2.0, free, runs
locally). The backend gained none: it still takes images only. No database
change was needed: the source PDF and page are kept in the existing
`filename` column.
