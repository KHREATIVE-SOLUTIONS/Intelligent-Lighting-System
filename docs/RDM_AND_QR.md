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
| `rigsApi.scanQr(rigId, code)` | `POST /api/rigs/{id}/scan` (qr_scanning.py) | `{qr_data}` | `{action: added\|identified, rig_fixture_id, dmx_address?, message}` |
| `rigsApi.labelsPdf(rigId)` | `GET /api/rigs/{id}/labels/pdf` (qr_scanning.py) | | a PDF (`application/pdf`, attachment); on error a JSON `{detail}` read out of the blob |

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
- **Scanning a printed label adds the fixture again.** The scan route looks
  for a rig fixture with the same `qr_code_data`, and a fixture patched any
  other way has none, so it adds a second one. It also ignores the label's
  `rig_fixture_id`. Matching on that id first would make a label identify its
  own fixture.

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
route, page counts, and every printed code decoded off the 300 dpi page).
