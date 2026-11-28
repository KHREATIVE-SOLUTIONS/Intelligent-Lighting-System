# Adding fixtures by RDM and by QR label

Two ways to add fixtures to a database rig without picking each one from the
library, both on the rig builder's toolbar (`/rigs/:id`):

- **Discover RDM** opens RDM discovery: scan the DMX line, tick the devices
  found, **Import Selected**. Each one is added at the universe and address it
  reports.
- **Scan QR** opens the QR scanner: point the camera at a fixture's label, or
  type the code, or click the code box and use a USB handheld barcode scanner
  (it types the code and presses Enter). Each code adds the fixture to the rig
  at the next free address, or says where it already is.

Both write any fixture drag still waiting to be saved first, and the rig is
read again after an import or a scan that added a fixture. The plan's keys are
off while either dialog is open, so typing a code does not move fixtures. Both
go through the app's client (`services/api.ts`), so they carry the operator's
token and are announced as rig changes ([FOCUS_PRESETS.md](FOCUS_PRESETS.md)).

## The contracts

| Call | Route (`backend/app/api/endpoints/`) | Sent | Answered |
|------|------|------|------|
| `rdmApi.devices()` | `GET /api/rdm/devices` (discovery.py) | | `{scanning, live_devices, saved_devices}` |
| `rigsApi.importRdmDevices(rigId, ids)` | `POST /api/rdm/import` | body: a bare JSON list of **stored device ids** (`saved_devices[].id`, integers, not RDM UIDs); query: `rig_id` | `{imported}`, how many were added |
| `rigsApi.scanQr(rigId, code)` | `POST /api/rigs/{id}/scan` (qr_scanning.py) | `{qr_data}` | `{action: added\|identified, already_patched, matched_by?, rig_fixture_id, universe?, dmx_address?, message}` (see [Scanning a label](#scanning-a-label)) |
| `rigsApi.labelsPdf(rigId)` | `GET /api/rigs/{id}/labels/pdf` (qr_scanning.py) | | a PDF (`application/pdf`, attachment); on error a JSON `{detail}` read out of the blob |
| (no client call yet) | `GET /api/fixtures/{id}/qr-code` (qr_scanning.py) | query: `size` (50 to 500 px, default 200), `format=png\|json` | a PNG (`image/png`) of a code holding `{fixture_id, manufacturer, model}`; `?format=json` gives `{qr_data, message}`; 404 for a missing fixture profile |

Only stored devices can be imported: `live_devices` carry no id. A device
already imported is shown but cannot be picked, and the route skips it if sent.
The import's request is pinned on both sides:
`backend/tests/integration/test_api_rdm_import.py` posts exactly what the
client sends, and `frontend/src/__tests__/focusRigWritePaths.test.tsx` checks
that the client sends it.

## What does not work yet

- **RDM discovery finds nothing.** `services/discovery/rdm_service.py` has no
  RDM interface driver. Its scan waits two seconds and stops, and nothing
  writes `RDMDevice` rows. The dialog says so when it is empty. Import works
  for stored devices (the tests write them directly), so a driver that stores
  what it finds is all that is missing.
- **The camera reads QR codes only where the browser has `BarcodeDetector`**
  (Chrome on Android and macOS). Chrome and Edge on Windows and Firefox do
  not have it, and the canvas fallback is a stub. The scanner says so and
  offers the code box, which also takes a USB scanner.

## Scanning a label

The scan route takes three kinds of code, and tries them in this order:

1. **A printed label** (`{"fixture_id", "rig_fixture_id"}`, from Generate
   Labels). If that rig fixture is in this rig and is the same fixture profile,
   the fixture is already patched, however it got there (the UI, an import,
   RDM, an earlier scan). Nothing is added: the answer is `action: identified`,
   `already_patched: true`, `matched_by: "rig_fixture_id"`, with its
   `universe`, `dmx_address` and a message such as "Spot SL is already
   patched at 0.33: nothing added". The label's text is stored as the rig
   fixture's `qr_code_data` if it had none. The profile must agree because
   rig fixture ids are SQLite rowids, which can be reused after a delete, so a
   stale label could otherwise name a different fixture.
2. **A code scanned before** in this rig: a rig fixture of the same profile
   whose `qr_code_data` is this exact text. Same answer, with
   `matched_by: "qr_code_data"`.
3. **Otherwise it adds** the `fixture_id` (from the JSON, or a bare id) at the
   next free address: `action: added`, `already_patched: false`. If the code
   was a label whose rig fixture no longer exists, is in another rig, or is
   now a different fixture (its id reused by another profile), the message
   says so first ("The label's rig fixture 9 no longer exists. Added ...").
   The new rig fixture stores the code's text, so scanning the same label
   again matches by step 2 instead of adding another.

   Not caught: if a deleted rig fixture's id is reused by another unit of the
   **same** profile, its old label identifies the new unit. Closing that needs
   AUTOINCREMENT ids on `rig_fixtures` or a per-label token.

A `rig_fixture_id` that is not a whole number is ignored. The scanner shows
`identified` answers as "Already in the rig" and an add as "Added to the rig",
each with the server's message.

`GET /api/fixtures/{id}/qr-code` draws a single code for a fixture profile
with the same encoder, as a PNG. `size` is rounded down to a whole number of
pixels a module (at least one), so every module is the same width. A profile
whose manufacturer and model are too long for a version 10 code gets
`{"fixture_id"}` alone, which still scans (step 3).

## Printing labels

**Generate Labels** (in the QR scanner) downloads `rig_<id>_labels.pdf` from
`GET /api/rigs/{id}/labels/pdf`: US Letter, laid out for Avery 5160 / 8160
address labels (3 x 10 on a page, 2 5/8" x 1"), with a header line giving the
rig name and page N of M. Print at 100% ("actual size"), not "fit to page", or
the labels drift off the die cuts.

Each label carries a QR code (level M, 0.5 to 0.6 mm a module) holding
`{"fixture_id": ..., "rig_fixture_id": ...}`, the fixture's name (cut short
with an ellipsis if long), its number, `DMX universe.address` as the patch
table numbers them, and its group. A rig with nothing patched gets one page
that says so.

No PDF or QR library is needed: `backend/app/services/qr_encode.py` is a small
QR encoder and `label_sheet.py` draws the pages with Pillow. The pages are
1-bit, so Pillow writes them lossless (CCITT G4) rather than as JPEG, which
would blur the codes. `?format=json` answers the label data instead (`rig_name`,
`labels[]` with `name`, `universe`, `dmx_address`, `fixture_number`, `group`,
`qr_data`, and `total`).

Tests: `backend/tests/test_qr_encode.py` (known answers, and every version and
level decoded by OpenCV) and `backend/tests/test_api_labels_pdf.py` (the
route, page counts, and every printed code decoded off the 300 dpi page),
`backend/tests/test_api_qr_scan_label_match.py` (label scans against fixtures
patched other ways, repeat scans, labels from another rig or a deleted or
reused rig fixture, the old text match, plain ids, and the PNG route decoded by
OpenCV), and the QR scanner cases in
`frontend/src/__tests__/rigAddFixturesEntryPoints.test.tsx`.
