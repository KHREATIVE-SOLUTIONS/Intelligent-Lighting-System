# Room builder from a phone scan

Status: **first slice. The scan reader and the API are built and tested against
rooms made in code; no file from a real phone has been read by it yet.** Treat
the first real scan as a test of the reader, not of the room. The frontend
changes (the Room Scan dialog and the scanned room in the 3D view) were not
typechecked or run in the session that wrote them (no `node_modules` in the
worktree, and installing them was refused): run `npm test` and `npm run build`
in `frontend/` before relying on them.

Second slice, **a room from a walkthrough video: built, and tested everywhere
except against a real COLMAP.** COLMAP is not installed on the machine this was
written on, so the reconstruction step has only been driven with a stand-in
process. Frame sampling was run with real ffmpeg and real OpenCV; finding which
way is up, scaling, and the API are tested against a synthetic room handed over
tipped and unscaled, as a photogrammetry tool hands one over. The first real
video is a test of the COLMAP commands (see [What is left](#what-is-left)). The
frontend changes were again not typechecked or run.

Everything here is free and local. Nothing is uploaded anywhere but this
system's own backend, and no outside service or model is called.

## What it is for

A rig laid out on a stage template has every fixture at a guess, in a room the
3D view invents from the stage size. A phone can scan the real room in a couple
of minutes. This reads that scan and suggests:

- the **room shell**: floor, ceiling and the four walls, as a box;
- **raised areas**: a stage, risers, a DJ booth or counter;
- **overhead lines**: trusses and lighting bars, with the height they hang at;
- **where the rig's unconfirmed fixtures should move** to agree with all that.

Every part of it is a **suggestion**. The operator sees a preview first, and
nothing is stored until they apply it. Applied, the room is scenery for the 3D
view, and the moved fixtures are still tagged as unconfirmed guesses:
flash-and-tap (Identify Lights, `FLASH_AND_TAP.md`) and dragging are still what
turn a guess into a position.

Nothing here reaches a device. The engine never reads the room shell, and a
fixture's stored position changes without any DMX being sent.

## Scanning the room

| App | Export | Read as |
| --- | --- | --- |
| Polycam, Scaniverse, 3D Scanner App | **OBJ** (best) or PLY | a mesh |
| Any LiDAR or photogrammetry app | PLY, ASCII or binary, with or without faces | a mesh or a point cloud |
| Apple RoomPlan apps | the RoomPlan **JSON**, or a USDZ that carries it | walls and objects as boxes |
| Anything writing USD | USDA, or a USDZ whose layer is **text** | a mesh, with the units and up axis the file states |

A USDZ whose only layer is binary USD (`.usdc`) **cannot be read**: reading it
needs Pixar's USD library, which is not a dependency of this project. The
server says so and names the fix: export OBJ from Polycam or Scaniverse instead.

Tips that make the reader's job easier: scan the whole room including the
ceiling, keep doors shut where you can, and export at medium detail (the reader
samples the surface, so a 2 GB mesh tells it no more than a 50 MB one). Uploads
over **200 MB** are refused with a message saying to export at a lower detail.

## Using it

Rig editor toolbar, **Room Scan**:

1. Choose the scan file. The server reads it and answers with a preview.
   Nothing is written.
2. Read the preview: the room's size, each raised area and overhead line, how
   the scan was read (units, up axis, which end was taken as upstage), any
   warnings, and a table of the fixtures that would move, from where to where
   and why.
3. If the room came out wrong, correct the guess and the preview is read again:
   **Units** (metres, centimetres, millimetres), **Up axis** (Y or Z), **Turn
   the room** in quarter turns when the wrong wall was taken as upstage.
4. **Store the room** (and, if ticked, move the listed fixtures). Untick the box
   to store the room and leave every fixture where it is.
5. **See it in the 3D view.** Then run Identify Lights: the moved fixtures are
   still unconfirmed.

**Remove the stored room** takes the room off the rig again. It does not put
moved fixtures back; there is no undo for an applied move other than Identify
Lights, dragging, or laying the template out again.

## From a walkthrough video

A phone with no LiDAR and no scanning app can still film the room. **Room
Scan**, **Or a walkthrough video** sends the video to this system's backend,
which rebuilds the room from it with free tools installed on that machine and
hands the result to the same preview and apply as any scan file.

**A scanning app is still the better route** where one is available: Polycam
and Scaniverse give a measured mesh in a minute. A video gives a sparse cloud
with no scale, after several minutes of processor time. Use it when the video
is all there is.

### What has to be installed

| Tool | For | Licence | Needed |
| --- | --- | --- | --- |
| **ffmpeg** on PATH | reading frames out of the video | LGPL/GPL, run as a separate program | this, or OpenCV |
| OpenCV (`cv2`) importable by the backend | the same, when ffmpeg is missing | Apache 2.0 | fallback only; not in `requirements.txt` |
| **COLMAP** | turning frames into a point cloud | BSD | yes |
| OpenMVS (`DensifyPointCloud`, `InterfaceCOLMAP`) | a dense cloud where COLMAP's own cannot run | AGPL, run as a separate program | no |

Nothing is installed by this system. COLMAP: download a release from
<https://github.com/colmap/colmap/releases>, unpack it, and either put its
folder on PATH or set `COLMAP_PATH` in `backend/.env` to the folder (or to
`COLMAP.bat` or the `colmap` executable), then restart the backend. A
`COLMAP_PATH` that points at nothing is reported as "not installed"; PATH is not
searched instead.

With no COLMAP the dialog says so before anything is uploaded, with the
download address and the alternative (scan with Polycam or Scaniverse, export
OBJ or PLY). `GET /api/room-scan/video/tools` gives the same answer.

Settings (`backend/.env`): `COLMAP_PATH`, `OPENMVS_PATH`, `ROOM_VIDEO_MAX_MB`
(default 500), `ROOM_VIDEO_TIMEOUT_MIN` (default 60: the whole job is stopped
after that).

### Filming

One to two minutes, walking slowly round the whole room, lights up. Keep the
floor and the ceiling in shot some of the time, keep part of what you just
filmed in view as you turn, and do not let a blank wall fill the picture:
COLMAP needs things to recognise. Hold the phone the same way up throughout.
1080p is plenty; frames are shrunk to 1600 pixels on their long side.

### Give one measurement

A video carries no real size. Choose **Ceiling height** or **Length of the
longest wall** and type it in metres (1 to 200). It can be given before the
video or after: the scale is applied when the cloud is fetched, so changing the
measurement reads the room again in a moment without rebuilding it.

With no measurement the scale is **assumed**: the phone is taken to have been
held 1.5 m above the floor (or, where the cameras' height is no use, the
ceiling is taken to be 3 m). The preview then leads with a warning that every
size is a guess. Do not apply an assumed-scale room and trust its numbers.

### What the server does

`backend/app/services/room_scan/video.py`, run as a background job by
`video_jobs.py`. One job runs at a time; a second is refused with 409.

1. **Frames.** About `3 x 150` candidate frames are taken evenly through the
   video (at most 4 a second). A frame is dropped as *blurred* when its
   sharpness (variance of the Laplacian over a 512-pixel centre crop) is under
   half that of its neighbours, and as a *repeat* when it shows what the last
   kept frame showed (the phone stood still). At most 150 are kept, the
   sharpest of each stretch. Fewer than 12 is refused with advice on filming.
2. **COLMAP**: `feature_extractor` (one camera for all frames),
   `exhaustive_matcher` up to 100 frames or `sequential_matcher` beyond,
   `mapper`, then `model_converter` to text. If the first two fail they are
   tried again asking for the CPU. Where the mapper writes several models, the
   one holding the most frames is used. COLMAP runs as a separate process at
   low priority with no window, and is killed (with anything it started) when
   the job is stopped, runs out of time, or the backend shuts down.
3. **Dense**, only when asked: COLMAP's `patch_match_stereo` and
   `stereo_fusion` (these need an NVIDIA card with CUDA), else OpenMVS where it
   is installed. Any failure falls back to the sparse cloud, with a note.
4. **Up.** A photogrammetry model has no up. The average of every frame's
   image-down is close to gravity; from there the direction is searched (within
   24 degrees) for the one across which the cloud is thinnest, which is the one
   square to the floor and ceiling. The cloud is turned so that is +Y.
5. **Scale**, when the cloud is fetched: the floor and ceiling (and for a wall
   measurement the walls) are found with the scan reader's own code, and the
   cloud is scaled so the measured thing is the size given.

The cloud is written as a binary PLY in metres, Y-up, whose header carries
what is known about it (`comment room_scan_note ...`,
`comment room_scan_warning ...`, `room_scan_up_axis`,
`room_scan_metres_per_unit`). The PLY reader takes those into the preview's
"How the scan was read" and warnings, so they survive the cloud being
downloaded and sent back. Other PLY comments are ignored as before.

The video, its frames and COLMAP's database are deleted when the job ends,
however it ends. The finished cloud is kept in memory for two hours (the four
most recent), and not across a restart.

### The video API

| Route | Does |
| --- | --- |
| `GET /api/room-scan/video/tools` | what is installed: `ready`, `frames`, `photogrammetry`, `dense`, `message` (what to install; null when ready), `max_upload_mb` |
| `POST /api/rigs/{rig_id}/room-scan/video?filename=walk.mp4&quality=sparse` | starts a job. **The request body is the video itself**, not a form, so the size limit acts while it arrives. Answers `202` with the job |
| `GET /api/rigs/{rig_id}/room-scan/video/{job_id}` | the job: `state` (`queued`, `running`, `done`, `failed`, `cancelled`), `stage`, `stage_label`, `detail`, `progress` (0 to 1, by stage), `elapsed_s`, `error`, `tools`, `frames`, `cloud`, `notes`, `warnings` |
| `GET /api/rigs/{rig_id}/room-scan/video/{job_id}/cloud.ply?ceiling_height=4.2` | the finished cloud, scaled. Or `longest_wall=`; with neither the scale is assumed (`X-Room-Scale-Assumed: true`) |
| `DELETE /api/rigs/{rig_id}/room-scan/video/{job_id}` | stops a running job, or forgets a finished one |

The `cloud.ply` is then sent to `POST /api/rigs/{rig_id}/room-scan` like any
scan file, for the preview and again to apply. No route here writes to a rig.

| Status | When |
| --- | --- |
| 200 with `state: "unavailable"` | the video was sent to a machine with no COLMAP (or no frame reader). `error` says what to install or do instead. Not an error status: nothing went wrong |
| 400 | the name is not a video's (`.mp4 .mov .m4v .avi .mkv .webm .3gp`), the body is empty, both measurements were given, or the measurement is outside 1 to 200 m |
| 404 | no such rig; or no such job **on that rig** (a job is only answered for under the rig it was started for) |
| 409 | another video is being processed; or `cloud.ply` was asked of a job that is not `done` |
| 413 | the video is over the limit (checked from `Content-Length` first, and again as the bytes arrive) |

A job that fails says why in `error`, in words for the operator: which COLMAP
step failed and the end of its output, that the frames could not be joined
(with how to film again), that too few frames or points came out, or that it
ran out of time. Each ends by naming the alternative, a scanning app's OBJ or
PLY.

## The API

All routes need the operator login, like every other `/api` route.

### `POST /api/rigs/{rig_id}/room-scan`

Multipart upload, field `file`. Query parameters:

| Parameter | Values | Meaning |
| --- | --- | --- |
| `apply` | `false` (default), `true` | `false` previews and writes nothing; `true` stores the room and moves fixtures |
| `move_fixtures` | `true` (default), `false` | with `apply`: also move the unconfirmed fixtures as previewed |
| `units` | `auto`, `m`, `cm`, `mm` | the scan's units, when the guess is wrong |
| `up_axis` | `auto`, `y`, `z` | the scan's up axis, when the guess is wrong |
| `rotate` | `0`, `90`, `180`, `270` | a further turn clockwise seen from above |

The file is sent for the preview and sent again to apply. The server keeps
nothing between the two requests, and the reader is deterministic (its random
sampling is seeded), so the same file with the same options gives the same
shell: what is applied is what was previewed.

The answer, for both:

- `room_shell`: the suggested shell (below). `replaces_existing_shell` says
  whether the rig already has one.
- `summary`: width, depth, height, counts, hanging heights, units, up axis.
- `assumptions`: each guess the reader made, in words, with how to override it.
- `warnings`: what looks wrong (a 500 m high room, a sparse scan, missing
  walls, a row longer than the truss it was put under).
- `fixtures`: `total`, `unconfirmed`, `would_move`, and `moves`: each with
  `rig_fixture_id`, `name`, `group`, `from`, `to`, `reason` and
  `suggested: true`.
- `applied`: `null` for a preview. After apply: `room_shell_stored`,
  `fixtures_moved`, `fixtures_still_unconfirmed` and a message.

Refusals, each with a `detail` that says what to do:

| Status | When |
| --- | --- |
| 400 | the file is not a scan this reads (binary-only USDZ: "export OBJ from Polycam or Scaniverse"), is cut short, has no surface, or is not a room at any plausible units; or `rotate` is not a quarter turn |
| 404 | no such rig |
| 409 | `apply` would move fixtures while a locate walkthrough is running on the rig. Finish or end it first. A preview, and an apply with `move_fixtures=false`, are still answered |
| 413 | the file is over 200 MB |
| 422 | `units` or `up_axis` is not one of the values above |

### `DELETE /api/rigs/{rig_id}/room-shell`

Takes the stored room off the rig. Fixtures are left where they are. Answers
`{"rig_id": ..., "removed": true|false}`.

### Where the shell is read

`GET /api/rigs/{id}` and the rig list carry `room_shell` (null when there is
none). It is read-only there: a rig update neither sets nor clears it.

## The shell

Stored in `rigs.room_shell` (JSON, migration `006_rig_room_shell`; additive and
nullable, and applied at startup like the other migrations). Axes are the
rig's: metres, origin at the centre of the floor, X across, Y up, -Z upstage.

```
source: "scan", suggested: true, basis: "Suggested from a room scan (...)"
room:          { width, depth, height, suggested, basis }
risers:        [ { center_x, center_z, width, depth, height, base_height,
                   name, kind: "stage" | "riser" | "booth", suggested, basis } ]
truss_lines:   [ { name, x1, z1, x2, z2, height, top, length, across,
                   axis: "x" | "z", suggested, basis } ]
hanging_bands: [ { height, top, lines, suggested, basis } ]
scan:          { file, format, points, triangles, point_cloud, units, up_axis,
                 wall_turn_deg, quarter_turns, walls_found, ... }
```

It travels under the same name as a demo preset's `room_shell`, which has other
keys (dome, balcony, LED walls). The 3D view draws whichever keys are there.

What a raised area *is* is guessed from its size alone, and its `basis` says
so: 6 m2 or more is a `stage`; smaller and at least 0.6 m high is a `booth`
("Booth or counter": a bar counter looks the same to a scan as a DJ booth);
smaller and lower is a `riser`.

## How the scan is read

`backend/app/services/room_scan/`: `mesh.py` and `usd.py` parse the file,
`extract.py` finds the room, `suggest.py` moves the guesses. In order:

1. **Points.** A mesh is sampled by area into points with normals; a point
   cloud is used as it is.
2. **Up axis.** From the file where it says (USD, RoomPlan), else guessed
   between Y and Z: the axis with most surface at its two ends.
3. **Units.** From the file where it says, else from the floor-to-ceiling
   height: under 100 is metres, under 1800 centimetres, else millimetres.
4. **Floor and ceiling.** The densest level near the bottom and near the top.
5. **Walls.** The scan is turned until its walls line up with the axes, then
   each wall is the densest plane near its side, so a scan that leaks through a
   doorway keeps its walls.
6. **Raised areas.** Level patches 0.12 m to 2.2 m above the floor, at least
   1.5 m2.
7. **Overhead lines.** Long thin things hanging clear of the walls in the upper
   room, grouped into hanging heights.
8. **Upstage.** The side with the largest raised area becomes upstage (-Z).
   With no raised area the scan's own heading is kept. Turns are rotations,
   never a mirror, so stage left stays stage left.

## Which fixtures move, and which never do

Only a fixture tagged `position_source:template` **and** `position_unconfirmed`
is moved: a template guess nobody has confirmed. These are never moved:

| Position | Tags | Why |
| --- | --- | --- |
| Tapped in flash-and-tap, or dragged | `position_source:tap` | a person pointed at it |
| Confirmed | `position_source:confirmed` | a person agreed with it |
| Measured in a file (MVR and the like) | `position_source:mvr`, ... | the file knows more than a scan |
| Fitted between two tapped ends | `position_source:row_fit` | it follows two taps, even though it is unconfirmed |

A row (a group, or ungrouped fixtures at one height and depth) moves as one
piece, so it keeps its spacing and stays a straight line for flash-and-tap's
row fit:

- **Overhead rows** (1.9 m and up) go under the nearest overhead line that runs
  across the room: its height, its depth, and along it far enough to hang under
  it. With no such line, to the lowest hanging height found; with nothing found
  overhead, only down to hang under the ceiling.
- **Floor rows standing where the scan found a stage** go up onto it and in
  from its edges.
- **Every row** comes inside the walls.

A moved fixture keeps `position_source:template` and `position_unconfirmed` and
gains `position_hint:room_scan`. Applying the same scan again moves nothing.

## In the 3D view

For a rig with a scanned room (`room_shell.source == "scan"`):

- the walls and the ceiling are the scan's, not worked out from the stage size
  (`buildVenue`'s `room` argument). A wall still moves out for a fixture patched
  beyond it. The rig's `stage_width/depth/height` are not changed;
- raised areas are drawn as boxes and overhead lines as plain bars. A line is
  not drawn where the view already hangs a truss over the fixtures under it;
- the booth, speaker stacks, square dance floor, crowd, and the bar counter and
  door on the rear wall that the view otherwise invents are **left out**: they
  would stand through the stage and risers the scan found, or claim things about
  a real wall that nobody saw. The ceiling's beams and duct are still the
  view's own.

## What the tests cover

All scans are built in code (`backend/tests/unit/room_scan_meshes.py`); there
are no binary fixtures in the repository.

- `backend/tests/unit/test_room_scan.py`: the parsers (OBJ, PLY in three
  encodings, USDA, USDZ, RoomPlan JSON), the same room recovered whatever the
  units, axes and heading, a point cloud with no normals, a scan leaking through
  a doorway, refusals and their wording, and which rows move where.
- `backend/tests/integration/test_api_room_scan.py`: preview writes nothing;
  apply stores the shell and it comes back on the rig and in the rig list; only
  template guesses move, a row at a time, and stay guesses; tapped, confirmed,
  measured and row-fitted positions do not move; a second scan moves nothing; a
  DJ booth is suggested where there is one; the overrides; binary USDZ and other
  refusals; the size limit; the locate-walkthrough conflict; removal; a rig
  update cannot write the shell; the route is behind the login.
- `frontend/src/__tests__/roomScan.test.ts`: the scanned room's walls, ceiling,
  risers and overhead bars in the view, request parameters, and the dialog's
  wording. **Written but not run** (see Status).

For the walkthrough video:

- `backend/tests/unit/test_room_video.py`: the missing-tool messages and how
  COLMAP is found; which frames are dropped as blurred, repeated or black, and
  how too many are thinned; **frame sampling with real ffmpeg and real OpenCV**
  on clips made by ffmpeg (skipped where they are not installed), including a
  portrait clip, a clip that never moves and a file that is not a video; an
  outside tool run, stopped and timed out for real (with the Python
  interpreter as the tool); COLMAP's text files read back into camera positions;
  a model tipped about every axis stood up to within 0.15 degrees, where the
  phone's own down was more than 3 degrees out; the room recovered at its real
  size from a ceiling height and from a wall length, and through the scan
  reader with its stage intact; the assumed scale, and its warning; the whole
  run in order against a stand-in for COLMAP (CPU retry, the larger of two
  models, each failure's wording, dense falling back to sparse); and the job
  runner (off the calling thread, one at a time, stop, crash, cleanup,
  shutdown).
- `backend/tests/integration/test_api_room_video.py`: the tools answer; a video
  sent with no COLMAP is answered, not failed; starting does not wait; the
  result previews and applies through the ordinary route and lands on the rig;
  the assumed-scale warning reaches the preview; a second measurement needs no
  second reconstruction; stop frees the slot; a job belongs to its rig; the
  size limit, declared and undeclared; the login.
- `frontend/src/__tests__/roomVideo.test.ts`: paths, which files are refused
  before sending, the measurement and its parameters, and the status wording.
  **Written but not run.**

**What these do not show:** that a real COLMAP accepts the commands in step 2,
that its text output is laid out as the stand-in writes it (it follows COLMAP's
documented format), or that a real room's sparse cloud is dense enough for the
reader to find walls in. The stand-in proves the steps are called in order and
their files read. Nothing more.

## What is left

- **A real scan.** Polycam, Scaniverse and RoomPlan exports from a real venue
  have not been read. Expect the thresholds in `extract.py` to need tuning.
- **Binary USDZ** (`.usdc`): not read. Export OBJ.
- **Rooms that are not boxes.** L-shaped rooms, sloped or domed ceilings,
  balconies and mezzanines are read as their bounding box.
- **Angled trusses** and circular truss are read as axis-aligned lines or not
  at all. Fixtures are only moved under lines running across the room.
- **The 2D layout view** does not draw the scanned room; only the 3D view does.
- **Editing the suggestion.** A raised area or line cannot be renamed, moved or
  deleted in the UI; the choice is to store the shell or not.
- **Crowd and booth in a scanned room** are left out rather than fitted round
  what the scan found.
- **A real video through a real COLMAP.** Never run. Expect to adjust the
  COLMAP commands in `video.py` (option names differ between COLMAP versions;
  as few as possible are passed), and the frame thresholds. On Windows COLMAP
  is taken to ship as `COLMAP.bat` beside `bin/colmap.exe`; that layout was not
  checked against a download.
- **Dense clouds**: the COLMAP stereo and OpenMVS commands are the least
  certain part and have no test beyond "a failure falls back to sparse".
- **Up from a sideways video.** If the phone's rotation is not recorded in the
  video, "image down" is not down and the up search starts from the wrong
  place. Set the up axis by hand in the preview if the room comes out on its
  side.
- **Progress inside a step.** The bar moves a stage at a time; COLMAP's mapper,
  the slow one, shows as one long stage.
- **Jobs do not survive a restart**, and closing the dialog stops the job.
- **Measurements** are the ceiling height or the longest wall only; there is no
  picking two points in the cloud.
