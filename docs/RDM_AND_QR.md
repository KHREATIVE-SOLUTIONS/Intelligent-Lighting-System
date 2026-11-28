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
- **Generate Labels gives JSON, not a PDF.** `/rigs/{id}/labels/pdf` returns
  the label data (name, address, QR payload) until it can draw a PDF. The
  button saves it as `.json`.
