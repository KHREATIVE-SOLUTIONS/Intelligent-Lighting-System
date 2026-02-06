# Product Design: Dead-Simple Fixture Integration

**Document Version:** 1.0
**Date:** 2026-02-06
**Author:** Product Design Agent
**Status:** Proposed

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis and Pain Points](#2-current-state-analysis-and-pain-points)
3. [Feature Designs](#3-feature-designs)
   - [3.1 Fixture Library / Marketplace](#31-fixture-library--marketplace)
   - [3.2 Quick Rig Setup Wizard](#32-quick-rig-setup-wizard)
   - [3.3 Smart DMX Auto-Patching](#33-smart-dmx-auto-patching)
   - [3.4 Drag-and-Drop Rig Builder](#34-drag-and-drop-rig-builder)
   - [3.5 Live Fixture Test](#35-live-fixture-test)
   - [3.6 Rig Templates](#36-rig-templates)
   - [3.7 Import/Export](#37-importexport-gdtfmvrconsole)
   - [3.8 Fixture Profile Editor](#38-fixture-profile-editor)
   - [3.9 Auto-Discovery and Import (RDM)](#39-auto-discovery-and-import-rdm)
   - [3.10 QR Code / NFC Fixture Scanning](#310-qr-code--nfc-fixture-scanning)
4. [Priority Matrix](#4-priority-matrix)
5. [Implementation Plan: Top 5 Features](#5-implementation-plan-top-5-features)
6. [Data Model Changes Summary](#6-data-model-changes-summary)
7. [API Endpoints Summary](#7-api-endpoints-summary)
8. [Appendix: Files to Create and Modify](#8-appendix-files-to-create-and-modify)

---

## 1. Executive Summary

The Intelligent Lighting System has a solid technical foundation: a working DMX/ArtNet
pipeline, 3D rig visualization in Three.js, and a structured fixture/mode/channel data
model. However, the current fixture integration experience is painful. A venue operator
today must (a) manually define every fixture profile channel-by-channel, (b) manually
calculate and assign DMX addresses, (c) manually type 3D coordinates for placement, and
(d) work from a library of only 2 generic fixtures. This document proposes 10 features
that transform this into a dead-simple, guided experience where a venue can go from zero
to a fully patched, tested rig in under 10 minutes.

### Design Principles

- **Zero-to-working in 5 clicks.** The wizard path (pick venue type, pick fixtures,
  auto-patch, auto-place, done) should be completable in under 2 minutes.
- **No DMX knowledge required.** Auto-patching, conflict detection, and smart defaults
  mean operators never need to manually calculate channel addresses.
- **Library-first, not editor-first.** Users should almost never need to manually create
  a fixture profile. A massive library with one-click import should cover 95%+ of
  real-world fixtures.
- **Visual-first.** Every operation that can be spatial (placement, grouping, testing)
  should happen in the 2D/3D visual editor, not in forms.
- **Fail-safe.** Live fixture testing, conflict warnings, and validation at every step
  prevent silent patching errors that waste hours during load-in.

---

## 2. Current State Analysis and Pain Points

### What Exists Today

| Component | File(s) | What It Does | Gaps |
|-----------|---------|-------------|------|
| Fixture Model | `backend/app/models/fixture.py` | Stores fixture profiles with modes, channels, physical properties, GDTF ID field | Only 2 sample fixtures; GDTF import is a placeholder stub |
| Rig Model | `backend/app/models/rig.py` | Stores rig with 3D placement, DMX addressing, grouping | No auto-patching, no templates, no conflict detection |
| Fixture API | `backend/app/api/endpoints/fixtures.py` | CRUD + search + GDTF upload endpoint | GDTF parser not implemented; no library sync; no bulk operations |
| RigEditor | `frontend/src/components/rig/RigEditor.tsx` | Form-based fixture add dialog with manual position/address entry | No visual placement; no auto-address; dropdown only shows 2 fixtures |
| RigVisualizer | `frontend/src/components/rig/RigVisualizer.tsx` | Read-only Three.js 3D view of the rig | No interaction (cannot drag fixtures); hardcoded channel mapping; no fixture test |
| RigList | `frontend/src/components/rig/RigList.tsx` | Card grid to browse/create rigs | No templates; create dialog is bare-bones |
| DMX Controller | `backend/app/services/dmx/dmx_controller.py` | ArtNet output, test patterns (universe-wide only), blackout | No per-fixture test; test patterns are raw channel chases, not fixture-aware |
| Sample Data | `data/fixtures/*.json`, `data/rigs/sample_rig.json` | 2 generic fixtures, 1 sample rig with 8 fixtures | Manually authored JSON; no real manufacturer profiles |

### Top Pain Points (Ranked by Severity)

**Pain Point 1: Empty fixture library.**
With only 2 generic fixtures (`Generic Moving Head 200W` and `Generic LED PAR 64 RGBW`),
users must manually create profiles for every real fixture they own. This requires knowing
the exact DMX channel map from the fixture's manual -- the single biggest barrier to
adoption.

**Pain Point 2: Manual DMX addressing.**
The `getNextAddress()` function in `RigEditor.tsx` (line 129-133) just adds 16 to the
highest address. It does not know the actual channel count of the selected fixture's mode,
leading to either wasted channels or overlapping addresses:
```typescript
const getNextAddress = (): number => {
    if (!rig?.fixtures?.length) return 1;
    const maxAddress = Math.max(...rig.fixtures.map((f) => f.dmx_address));
    return Math.min(maxAddress + 16, 512); // hardcoded +16 regardless of mode
};
```

**Pain Point 3: No mode selection during fixture add.**
When adding a fixture to a rig, the dialog (`RigEditor.tsx` lines 300-393) has no mode
picker. The `mode_id` field on `RigFixture` exists in the model but is never populated
through the UI. This means the system cannot know how many channels a fixture actually
uses.

**Pain Point 4: Manual position entry.**
Users must type X/Y/Z coordinates into text fields. There is no visual way to place
fixtures on the stage. The 3D visualizer is read-only.

**Pain Point 5: No fixture testing.**
The DMX controller has `run_test_pattern()` but it operates on an entire universe with
raw channel chases. There is no way to test a single fixture (turn it on, cycle colors,
move it) to verify patching is correct.

**Pain Point 6: Hardcoded channel mapping in visualizer.**
`RigVisualizer.tsx` lines 36-52 hardcode which DMX offset is dimmer vs. RGB based on
`fixture.dmx_address < 213`. This breaks for any non-sample fixture:
```typescript
const isMover = fixture.dmx_address < 213; // <-- this is fragile
if (isMover) {
    dimmer = (dmxData[baseAddr + 5] || 0) / 255;
    red = (dmxData[baseAddr + 7] || 0) / 255;
    // ...
} else {
    dimmer = (dmxData[baseAddr] || 0) / 255;
    red = (dmxData[baseAddr + 2] || 0) / 255;
    // ...
}
```

**Pain Point 7: No conflict detection.**
Nothing prevents two fixtures from being assigned overlapping DMX addresses. No warning
is shown anywhere in the UI.

**Pain Point 8: No rig templates.**
Every new rig starts blank. Common setups (club, church, theater) must be recreated from
scratch every time.

**Pain Point 9: GDTF import is a stub.**
The endpoint exists (`POST /fixtures/import/gdtf`) but the body is a TODO comment on line
249 of `fixtures.py`. The entire GDTF/Open Fixture Library ecosystem is inaccessible.

**Pain Point 10: No import/export.**
Rigs cannot be shared, backed up, or imported from professional consoles (grandMA, Hog,
ETC).

---

## 3. Feature Designs

---

### 3.1 Fixture Library / Marketplace

**Priority:** P0 (Must Have)
**Complexity:** High
**Rationale:** Without fixtures in the library, nothing else works. This is the
foundation that every other feature depends on.

#### User Flow

1. User navigates to a new **Fixtures** tab (new top-level nav item).
2. Landing page shows a searchable/filterable grid of fixture cards.
3. **Two tabs** at the top: "My Library" (locally stored) and "Browse Online" (Open
   Fixture Library).
4. In "Browse Online," user types manufacturer or model name (e.g., "Chauvet Rogue R2").
5. Results appear as cards showing: manufacturer, model, thumbnail, fixture type icon,
   channel count per mode.
6. User clicks the **"+ Add to Library"** button on the card.
7. System downloads the fixture definition from the Open Fixture Library API, converts it
   to the internal format, and saves it. A toast confirms: "Chauvet Rogue R2 Spot added
   to your library."
8. Fixture now appears in "My Library" and is available when adding fixtures to rigs.

**Bulk import variant:** User can select multiple fixtures with checkboxes and click
"Add All Selected."

**Offline bundle variant:** The app ships with a curated bundle of the 200 most popular
fixtures pre-loaded on first install, so the library is never completely empty.

#### UI Concept

```
+------------------------------------------------------------------+
| Fixtures                                          [+ Create New]  |
|------------------------------------------------------------------|
| [My Library (47)]  [Browse Online (18,000+)]                     |
|------------------------------------------------------------------|
| Search: [___________________________]  Type: [All v]             |
| Manufacturer: [All v]                  Sort: [Popular v]         |
|------------------------------------------------------------------|
| +------------------+ +------------------+ +------------------+   |
| | [Moving Head]    | | [LED PAR]        | | [LED Bar]        |   |
| | Chauvet          | | ETC              | | Elation          |   |
| | Rogue R2 Spot    | | ColorSource PAR  | | SixBar 1000     |   |
| | 21ch / 16ch      | | 8ch / 5ch        | | 12ch / 6ch       |   |
| | [+ Add to Lib]   | | [+ Add to Lib]   | | [Already Added]  |   |
| +------------------+ +------------------+ +------------------+   |
|                                                                   |
| +------------------+ +------------------+ +------------------+   |
| | [Spot]           | | [Wash]           | | [Strobe]         |   |
| | Clay Paky        | | Robe             | | Martin           |   |
| | Sharpy Plus      | | Robin 600E Wash  | | Atomic 3000      |   |
| | 24ch / 16ch      | | 18ch / 12ch      | | 3ch / 1ch        |   |
| | [+ Add to Lib]   | | [+ Add to Lib]   | | [+ Add to Lib]   |   |
| +------------------+ +------------------+ +------------------+   |
+------------------------------------------------------------------+
```

#### Data Model Changes

**New table: `fixture_library_sources`**
```python
class FixtureLibrarySource(Base):
    __tablename__ = "fixture_library_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))              # "Open Fixture Library"
    base_url = Column(String(500))          # "https://open-fixture-library.org/api/v1"
    source_type = Column(String(50))        # "ofl", "gdtf_share", "custom"
    last_synced = Column(DateTime)
    is_enabled = Column(Boolean, default=True)
```

**New fields on existing `Fixture` model:**
```python
source = Column(String(50), default="local")       # "local", "ofl", "gdtf_share"
source_id = Column(String(255), nullable=True)      # External ID from source
categories = Column(JSON, default=list)              # ["moving_head", "spot", "led"]
popularity_score = Column(Integer, default=0)        # Usage count for sorting
is_bundled = Column(Boolean, default=False)          # Part of the starter bundle
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/fixtures/library/search` | Search the Open Fixture Library (proxied to avoid CORS) |
| `POST` | `/api/fixtures/library/import` | Import one or more fixtures from an external source by source ID |
| `POST` | `/api/fixtures/library/import-bulk` | Bulk import from external source |
| `GET` | `/api/fixtures/library/popular` | Get the top N most-used fixtures across all rigs |
| `POST` | `/api/fixtures/library/sync` | Trigger a background sync of the bundled fixture list |
| `GET` | `/api/fixtures/library/manufacturers` | List all manufacturers from the external source |

---

### 3.2 Quick Rig Setup Wizard

**Priority:** P0 (Must Have)
**Complexity:** Medium
**Rationale:** The guided wizard is the "happy path" for new users. It makes the entire
flow linear and obvious.

#### User Flow

1. From the Rigs page, user clicks **"+ New Rig"** and sees options: "Start from Scratch"
   or **"Quick Setup Wizard"**.
2. **Step 1 - Venue Type:** User picks from visual cards: Small Club, Medium Venue, Large
   Venue, Church, Theater, Festival Stage, Outdoor, Custom. Selecting one pre-fills stage
   dimensions and suggests a fixture count.
3. **Step 2 - Stage Dimensions:** Pre-filled from venue type. User can adjust width, depth,
   height with sliders. A live mini 3D preview updates in real time.
4. **Step 3 - Pick Fixtures:** System suggests a fixture list based on venue type (e.g.,
   Small Club = "4x LED PAR + 4x Moving Head"). User sees the suggestions as a list they
   can modify:
   - Change quantity with +/- buttons.
   - Swap fixture model by clicking on it (opens a mini fixture browser).
   - Add more fixture types with "+ Add Row."
   - Each row shows: fixture thumbnail, name, qty, mode selector.
5. **Step 4 - Auto-Patch and Place:** System runs auto-patching (see section 3.3) and
   auto-placement. User sees a 2D top-down stage view with fixtures placed in sensible
   default positions (PARs evenly spaced on front/back truss, movers on mid truss). A DMX
   address table shows the assignments. User can adjust by dragging.
6. **Step 5 - Review and Create:** Summary screen showing fixture count, total DMX channels
   used, universe count, 3D preview. User clicks **"Create Rig"**.
7. Rig is created and user is taken to the full Rig Editor.

#### UI Concept

```
Quick Rig Setup                                    Step 3 of 5
+------------------------------------------------------------------+
| Pick Your Fixtures                                                |
|                                                                   |
| Based on "Small Club" venue, we suggest:                         |
|                                                                   |
| +----------------------------------------------------+           |
| | [PAR icon]  Generic LED PAR 64 RGBW   x [- 4 +]   |  8ch mode |
| |             [Change fixture...]                v    |           |
| +----------------------------------------------------+           |
| | [Mover icon] Generic Moving Head 200W  x [- 4 +]   | 16ch mode|
| |              [Change fixture...]               v    |           |
| +----------------------------------------------------+           |
| | [+ Add another fixture type]                        |           |
| +----------------------------------------------------+           |
|                                                                   |
| Total: 8 fixtures | 96 DMX channels | 1 universe                |
|                                                                   |
|                                    [Back]  [Next: Auto-Patch ->] |
+------------------------------------------------------------------+
```

#### Data Model Changes

**New table: `venue_presets`** (can alternatively be hardcoded in a service class)
```python
class VenuePreset(Base):
    __tablename__ = "venue_presets"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))             # "Small Club"
    description = Column(Text)
    icon = Column(String(50))              # "nightclub", "church", "theater"
    stage_width = Column(Float)
    stage_depth = Column(Float)
    stage_height = Column(Float)
    suggested_fixtures = Column(JSON)       # [{fixture_type, quantity, mode_preference}]
    placement_strategy = Column(String(50)) # "symmetric", "front_heavy", "surround"
    typical_universes = Column(Integer, default=1)
```

**New table: `wizard_sessions`** (optional, for resume support)
```python
class WizardSession(Base):
    __tablename__ = "wizard_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=True)
    current_step = Column(Integer, default=1)
    wizard_data = Column(JSON)              # Full state snapshot
    created_at = Column(DateTime)
    expires_at = Column(DateTime)
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/wizard/venue-presets` | List all venue preset options |
| `GET` | `/api/wizard/venue-presets/{key}/suggestions` | Get fixture suggestions for a venue type |
| `POST` | `/api/wizard/auto-place` | Given fixtures + stage dims, compute optimal placement |
| `POST` | `/api/wizard/create-rig` | Create rig from wizard data (fixtures + placement + patch) |

---

### 3.3 Smart DMX Auto-Patching

**Priority:** P0 (Must Have)
**Complexity:** Low
**Rationale:** Manual DMX addressing is the number-one source of errors. Auto-patching is
straightforward to implement and immediately eliminates an entire class of bugs.

#### User Flow

**Scenario A - Auto-patch on fixture add:**
1. User adds a fixture to a rig and selects a mode (e.g., "Standard 16ch").
2. The DMX address field auto-fills with the next available address that avoids conflicts.
3. A green checkmark appears: "Address 49 - no conflicts."

**Scenario B - Batch re-patch:**
1. User clicks **"Auto-Patch All"** button in the rig editor toolbar.
2. System recalculates all DMX addresses sequentially, respecting: universe boundaries
   (512 channels max), fixture mode channel counts, and user-locked addresses (fixtures
   the user has manually set and pinned).
3. A confirmation dialog shows before/after: "5 fixtures will be re-addressed. 2 fixtures
   are locked and will not move."
4. User confirms. Addresses update.

**Scenario C - Conflict detection:**
1. User manually types a DMX address that overlaps with another fixture.
2. The field turns red. A tooltip appears: "Conflicts with 'Front Left PAR' (channels
   1-8). Next available: 9."
3. A "Fix" button auto-corrects to the next available address.

#### UI Concept

```
Fixture List in Rig Editor:
+------------------------------------------------------------------+
| Fixtures (8)                    [Auto-Patch All] [+ Add Fixture] |
|------------------------------------------------------------------|
| # | Name            | Fixture          | Mode     | Addr | Univ |
|---|-----------------|------------------|----------|------|------|
| 1 | Front Left PAR  | LED PAR 64 RGBW  | 8ch   v | 1    | 0    |
| 2 | Front Right PAR | LED PAR 64 RGBW  | 8ch   v | 9    | 0    |
| 3 | Back Left PAR   | LED PAR 64 RGBW  | 8ch   v | 17   | 0    |
| 4 | Moving Head 1   | Moving Head 200W | 16ch  v | 33   | 0    |
| 5 | Moving Head 2   | Moving Head 200W | 16ch  v | 49   | 0    |
|---|-----------------|------------------|----------|------|------|
| Channels used: 97/512 (Universe 0)     [======----] 19%         |
+------------------------------------------------------------------+

Conflict indicator example:
| 4 | Moving Head 1   | Moving Head 200W | 16ch  v | 35 ! | 0   |
|   |                 | CONFLICT with "Back Left PAR" (17-24)      |
|   |                 | [Fix: Move to 49]                          |
```

#### Data Model Changes

**New field on existing `RigFixture` model:**
```python
is_address_locked = Column(Boolean, default=False)  # User pinned this address
```

No new tables required. The patching algorithm is a pure function operating on the
existing fixture list and mode channel counts.

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rigs/{id}/auto-patch` | Recalculate all non-locked DMX addresses |
| `GET` | `/api/rigs/{id}/patch-conflicts` | Return list of address conflicts |
| `GET` | `/api/rigs/{id}/next-address` | Get the next available DMX address for a given mode channel count and universe |

#### Algorithm Sketch

```python
def auto_patch(fixtures, modes):
    """Assign DMX addresses sequentially, respecting locks and universe boundaries."""
    locked = [f for f in fixtures if f.is_address_locked]
    unlocked = [f for f in fixtures if not f.is_address_locked]

    # Build occupied ranges per universe from locked fixtures
    occupied = defaultdict(list)  # universe -> [(start, end), ...]
    for f in locked:
        mode = modes[f.mode_id]
        occupied[f.universe].append(
            (f.dmx_address, f.dmx_address + mode.channel_count - 1)
        )

    # Assign addresses to unlocked fixtures
    for f in unlocked:
        mode = modes[f.mode_id]
        channel_count = mode.channel_count
        universe = f.universe
        address = find_next_available(occupied[universe], channel_count)
        if address + channel_count - 1 > 512:
            universe += 1  # Spill to next universe
            address = find_next_available(occupied[universe], channel_count)
        f.dmx_address = address
        f.universe = universe
        occupied[universe].append((address, address + channel_count - 1))

    return fixtures

def find_next_available(occupied_ranges, channel_count):
    """Find first gap that fits channel_count channels."""
    if not occupied_ranges:
        return 1
    sorted_ranges = sorted(occupied_ranges, key=lambda x: x[0])
    # Try before first fixture
    if sorted_ranges[0][0] >= channel_count + 1:
        return 1
    # Try gaps between fixtures
    for i in range(len(sorted_ranges) - 1):
        gap_start = sorted_ranges[i][1] + 1
        gap_end = sorted_ranges[i + 1][0] - 1
        if gap_end - gap_start + 1 >= channel_count:
            return gap_start
    # After last fixture
    return sorted_ranges[-1][1] + 1
```

---

### 3.4 Drag-and-Drop Rig Builder

**Priority:** P0 (Must Have)
**Complexity:** High
**Rationale:** Visual placement replaces the most tedious part of rig setup (typing X/Y/Z
coordinates). Combined with the existing Three.js infrastructure, this becomes the
centerpiece of the rig editing experience.

#### User Flow

1. User opens a rig in the editor. The layout changes to a **split view**: left panel =
   fixture palette/properties, center = 2D/3D stage view, right panel = DMX patch table.
2. **2D Top-Down View (default):** The stage is shown from above as a rectangle with grid
   lines. Existing fixtures appear as icons at their positions. Truss lines are drawn as
   horizontal bars.
3. **Adding fixtures:** User drags a fixture type from the left palette onto the stage. A
   ghost icon follows the cursor. When dropped, the fixture snaps to the nearest grid
   point. The fixture is created with auto-patched DMX address and the Y coordinate
   defaults to truss height.
4. **Moving fixtures:** User clicks an existing fixture icon and drags it to a new
   position. The X and Z coordinates update in real time. A tooltip shows the coordinates.
5. **Multi-select:** User draws a selection rectangle around multiple fixtures to
   group-select. Can then drag the group, or assign a group name, or batch-edit properties.
6. **Switching to 3D:** A toggle in the toolbar switches to the Three.js 3D view (existing
   `RigVisualizer`), now with drag interaction enabled. Fixtures can be dragged along
   constrained axes (hold Shift for Y-only, Ctrl for XZ-only).
7. **Snap controls:** Toolbar toggles for: Snap to Grid (0.5m increments), Snap to Truss,
   Free Position.
8. **Context menu:** Right-click a fixture to: Rename, Change Mode, Test (see 3.5),
   Duplicate, Delete, Lock Position, Set as Group Leader.

#### UI Concept

```
+------------------------------------------------------------------+
| Rig: Small Club    [2D] [3D]  [Snap: Grid v]  [Save] [Test All] |
|------------------------------------------------------------------|
| Palette    |            Stage (Top-Down)          | DMX Patch     |
|------------|--------------------------------------|---------------|
| Search:    |     .  .  .  .  .  .  .  .  .       | Univ 0        |
| [_______]  |     ==================== (truss)     | 1: PAR-FL 1-8 |
|            |     P1      P2      P3      P4       | 9: PAR-FR 9-16|
| [PAR icon] |     .  .  .  .  .  .  .  .  .       | 17:PAR-BL ... |
| LED PAR 64 |                                      | 33:MH1  33-48 |
|            |     .  M1  .  .  .  M2  .  .  .      | 49:MH2  49-64 |
| [MH icon]  |     ==================== (truss)     |               |
| Mov Head   |     P3      M3      M4      P4       | Used: 97/512  |
|            |     .  .  .  .  .  .  .  .  .        |               |
| [Bar icon] |                                      |               |
| LED Bar    |          (audience)                   |               |
|------------|--------------------------------------|---------------|
| Properties: (when fixture selected)               |               |
| Name: [Front Left PAR___]                         |               |
| Mode: [8 Channel      v]                          |               |
| Group: [front_wash____]                           |               |
| Addr: [1] Univ: [0]  [Lock]                      |               |
+------------------------------------------------------------------+
```

#### Data Model Changes

No new database tables. The existing `RigFixture` position/rotation fields are sufficient.

**New frontend state (Zustand store):**
```typescript
interface RigEditorState {
  viewMode: '2d' | '3d';
  snapMode: 'grid' | 'truss' | 'free';
  gridSize: number;                    // default 0.5 meters
  selectedFixtureIds: number[];
  dragState: {
    isDragging: boolean;
    fixtureId: number | null;
    startPos: { x: number; y: number; z: number };
  };
  clipboard: RigFixture[];
  undoStack: RigFixture[][];
  redoStack: RigFixture[][];
}
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `PUT` | `/api/rigs/{id}/fixtures/batch-update` | Update positions/addresses for multiple fixtures in one call |
| `POST` | `/api/rigs/{id}/fixtures/duplicate/{fixture_id}` | Duplicate a fixture (copies all properties, auto-patches new address) |

#### New Frontend Components

| Component | File | Description |
|-----------|------|-------------|
| `RigBuilder` | `frontend/src/components/rig/RigBuilder.tsx` | New main layout with split panels |
| `StageView2D` | `frontend/src/components/rig/StageView2D.tsx` | SVG/Canvas 2D top-down stage with drag support |
| `FixturePalette` | `frontend/src/components/rig/FixturePalette.tsx` | Left sidebar with draggable fixture types |
| `PatchTable` | `frontend/src/components/rig/PatchTable.tsx` | Right sidebar DMX address table |
| `FixtureProperties` | `frontend/src/components/rig/FixtureProperties.tsx` | Bottom-left property editor for selected fixture |
| `RigEditorToolbar` | `frontend/src/components/rig/RigEditorToolbar.tsx` | Top toolbar with view/snap/action controls |

---

### 3.5 Live Fixture Test

**Priority:** P0 (Must Have)
**Complexity:** Low
**Rationale:** Without live testing, users cannot verify that their patching is correct
until they run a show -- at which point debugging is extremely difficult. Per-fixture
testing is the "moment of truth" that builds confidence.

#### User Flow

**Scenario A - Test single fixture:**
1. User right-clicks a fixture in the rig editor (or clicks a "Test" icon).
2. A test panel appears with buttons:
   - **Identify** (Lamp On): Sets dimmer to 100%, white, for 3 seconds, then restores.
   - **Color Cycle**: Cycles through R, G, B, W, Amber, UV (if supported) with 1-second
     holds.
   - **Movement Test** (for movers): Slowly pans 0-100%, then tilts 0-100%, then returns
     to center.
   - **Full Test**: Runs Identify + Color Cycle + Movement sequentially.
   - **Strobe Test**: Pulses strobe channel at medium rate.
   - **All Off**: Immediately zeros all channels for this fixture.
3. During test, the fixture's card in the editor highlights with a pulsing blue border.
4. Only one fixture is tested at a time to make identification easy.

**Scenario B - Test all fixtures sequentially:**
1. User clicks **"Test All"** in the toolbar.
2. System runs Identify on each fixture one at a time, 2 seconds per fixture, in DMX
   address order.
3. A progress bar shows: "Testing fixture 3/8: Moving Head 1..."
4. User can click "Stop" at any time.

**Scenario C - Interactive DMX faders:**
1. User selects a fixture and opens the "Advanced Test" panel.
2. Sliders appear for each channel in the fixture's mode (e.g., Dimmer, Red, Green, Blue,
   Pan, Tilt...).
3. Dragging a slider immediately sends the DMX value. This is a live, real-time control
   surface.

#### UI Concept

```
Test Panel (appears as a popover or bottom drawer):
+------------------------------------------+
| Test: Moving Head 1 (Addr 33, Univ 0)   |
|------------------------------------------|
| [Identify]  [Color Cycle]  [Move Test]   |
| [Full Test] [Strobe]       [ALL OFF]     |
|------------------------------------------|
| Advanced:                                |
| Pan     [=====|=============] 128        |
| Tilt    [=====|=============] 128        |
| Dimmer  [========================] 255   |
| Red     [========================] 255   |
| Green   [                       ] 0      |
| Blue    [                       ] 0      |
| Shutter [                       ] 0      |
| Gobo    [                       ] 0      |
+------------------------------------------+
```

#### Data Model Changes

None. Fixture testing is a transient operation that sends DMX commands via the existing
`DMXController` without persisting state.

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rigs/{rig_id}/fixtures/{fixture_id}/test` | Run a named test pattern on a single fixture |
| `POST` | `/api/rigs/{rig_id}/fixtures/{fixture_id}/test/stop` | Stop current test on a fixture |
| `POST` | `/api/rigs/{rig_id}/fixtures/{fixture_id}/set-channels` | Set individual channel values for live fader control |
| `POST` | `/api/rigs/{rig_id}/test-all` | Sequential identify test across all fixtures |
| `POST` | `/api/rigs/{rig_id}/test-all/stop` | Stop the sequential test |

#### Backend Logic

The test endpoints need to be **fixture-aware**: they must look up the fixture's mode,
find which channel offset corresponds to "dimmer," "red," "pan," etc., and send the
correct DMX values. This replaces the current raw-channel test patterns in `DMXController`.

```python
class FixtureTestService:
    """Runs fixture-aware test patterns."""

    async def identify(self, rig_fixture, mode, dmx_controller):
        """Lamp on for 3 seconds."""
        channel_map = self._build_channel_map(mode)
        base = rig_fixture.dmx_address
        universe = rig_fixture.universe

        # Set dimmer to full, white color
        if 'dimmer' in channel_map:
            await dmx_controller.set_channel(
                universe, base + channel_map['dimmer'], 255
            )
        for color in ['red', 'green', 'blue', 'white']:
            if color in channel_map:
                await dmx_controller.set_channel(
                    universe, base + channel_map[color], 255
                )
        await asyncio.sleep(3)

        # Restore to zero
        for offset in channel_map.values():
            await dmx_controller.set_channel(universe, base + offset, 0)

    def _build_channel_map(self, mode):
        """Build a map of channel_type -> offset (0-indexed)."""
        return {
            ch.channel_type.value: ch.channel_number - 1
            for ch in mode.channels
        }
```

---

### 3.6 Rig Templates

**Priority:** P1 (Should Have)
**Complexity:** Medium
**Rationale:** Templates let experienced users share proven rig layouts and let newcomers
start with something that works. They feed directly into the wizard.

#### User Flow

1. **Using a template:** During rig creation (or in the wizard), user sees a "Templates"
   tab with cards: "Small Club (8 fixtures)," "Medium Venue (24 fixtures)," "Festival
   Main Stage (64 fixtures)," "Church Service (12 fixtures)," "Theater Pros (32 fixtures)."
2. User clicks a template card. A preview appears showing the 2D stage layout and fixture
   list.
3. User clicks **"Use This Template."** The fixtures and positions are populated but the
   user can modify everything before creating.
4. **Saving as template:** In any rig editor, user clicks **"Save as Template"** in the
   menu. A dialog asks for template name, description, and whether to make it "public"
   (available to all users on this instance).
5. **Template abstraction:** Templates store fixture types (e.g., "moving_head") rather
   than specific fixture IDs, so they work across different libraries. When applying a
   template, the system maps each slot to the best matching fixture in the user's library,
   or prompts the user to pick one.

#### UI Concept

```
Templates Gallery:
+------------------------------------------------------------------+
| Choose a Template                                     [My Saved] |
|------------------------------------------------------------------|
| +--------------------+  +--------------------+  +--------------+ |
| | Small Club         |  | Medium Venue       |  | Church       | |
| | [2D Preview]       |  | [2D Preview]       |  | [2D Preview] | |
| | 8 fixtures         |  | 24 fixtures        |  | 12 fixtures  | |
| | 4 PAR + 4 Mover    |  | 8 PAR + 8 Mover   |  | 8 PAR +      | |
| | 1 universe         |  | + 4 Bar + 4 Strobe |  | 4 Spot       | |
| | 8x6x4m stage      |  | 2 universes        |  | 1 universe   | |
| | [Use Template]     |  | [Use Template]     |  | [Use Templ.] | |
| +--------------------+  +--------------------+  +--------------+ |
+------------------------------------------------------------------+
```

#### Data Model Changes

**New table: `rig_templates`**
```python
class RigTemplate(Base):
    __tablename__ = "rig_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    venue_type = Column(String(100))           # "club", "church", "theater"
    stage_width = Column(Float)
    stage_depth = Column(Float)
    stage_height = Column(Float)
    fixture_slots = Column(JSON)               # [{fixture_type, mode_channels, position, group}]
    thumbnail_url = Column(String(500))
    is_system = Column(Boolean, default=False)  # Built-in vs. user-created
    is_public = Column(Boolean, default=False)
    created_by = Column(String(255))
    created_at = Column(DateTime)
    usage_count = Column(Integer, default=0)
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/templates` | List available rig templates (filterable by venue_type) |
| `GET` | `/api/templates/{id}` | Get template details with fixture slots |
| `POST` | `/api/templates` | Create a new template from a rig |
| `POST` | `/api/templates/{id}/apply` | Apply template to create a new rig, with fixture mapping |
| `DELETE` | `/api/templates/{id}` | Delete a user-created template |

---

### 3.7 Import/Export (GDTF/MVR/Console)

**Priority:** P1 (Should Have)
**Complexity:** High
**Rationale:** Professional venues already have rig data in their lighting consoles.
Importing eliminates double-entry. GDTF is the industry standard that the app already
has a placeholder for.

#### User Flow

**GDTF Fixture Import:**
1. User goes to Fixtures > "Import" button.
2. Selects one or more `.gdtf` files from their computer.
3. System parses each GDTF archive (ZIP containing `description.xml` + optional 3D models).
4. A preview shows the parsed fixture with all modes and channels. User confirms import.
5. Fixture is added to the library.

**MVR Rig Import (My Virtual Rig):**
1. User goes to Rigs > "Import" button.
2. Selects an `.mvr` file (exported from grandMA3, Vectorworks, etc.).
3. System parses the MVR archive (ZIP containing GDTF fixtures + 3D scene graph + patch).
4. A preview shows: stage dimensions, fixture count, DMX addressing.
5. User can choose which elements to import: "Fixtures Only," "Patch Only," "Full Rig."
6. System creates fixtures (if not already in library) and the rig with placements.

**Console Patch Import:**
1. User goes to Rigs > "Import" > "From Console Patch."
2. Selects format: grandMA2/3 XML, Hog CSV, ETC Eos CSV.
3. Uploads the export file.
4. System parses the patch sheet and creates a rig with fixtures at the correct addresses.
5. For fixtures not in the library, the system shows a mapping dialog: "Console says 'Robe
   Robin 600E LED Wash' -- match to which library fixture?"

**Rig Export:**
1. User clicks "Export" on any rig.
2. Chooses format: JSON (native), MVR, CSV Patch Sheet, PDF Patch Report.
3. File downloads.

#### UI Concept

```
Import Dialog:
+------------------------------------------+
| Import Rig                               |
|------------------------------------------|
| Format:  [MVR (.mvr)          v]         |
|                                           |
| [Drop file here or click to browse]      |
|                                           |
| Preview:                                  |
| Stage: 12m x 10m x 8m                   |
| Fixtures: 24 total                       |
|   - 8x Robe Robin 600E (found in lib)   |
|   - 8x Chauvet COLORado (found in lib)  |
|   - 8x Martin MAC Aura (NOT in lib)     |
|     [Import fixture] [Map to existing v] |
|                                           |
| Import: (o) Full Rig  ( ) Patch Only    |
|                                           |
|               [Cancel]    [Import]        |
+------------------------------------------+
```

#### Data Model Changes

No new tables required. The existing Fixture and Rig models are sufficient. The import
parsers are service-layer logic.

**New fields on existing `Rig` model:**
```python
source_format = Column(String(50), nullable=True)   # "mvr", "grandma", "hog", "native"
source_file = Column(String(500), nullable=True)     # Original import filename
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/fixtures/import/gdtf` | Import fixture from GDTF file (replace existing stub) |
| `POST` | `/api/fixtures/import/gdtf-bulk` | Import multiple GDTF files at once |
| `POST` | `/api/rigs/import/mvr` | Import rig from MVR file |
| `POST` | `/api/rigs/import/console-patch` | Import patch from console export (grandMA/Hog/ETC) |
| `GET` | `/api/rigs/{id}/export/json` | Export rig as JSON |
| `GET` | `/api/rigs/{id}/export/mvr` | Export rig as MVR |
| `GET` | `/api/rigs/{id}/export/csv` | Export rig as CSV patch sheet |
| `GET` | `/api/rigs/{id}/export/pdf` | Export rig as PDF patch report |

---

### 3.8 Fixture Profile Editor

**Priority:** P1 (Should Have)
**Complexity:** Medium
**Rationale:** Even with a large library, some users will have obscure or custom fixtures.
The current fixture creation API requires raw JSON with channel type enums -- a visual
editor makes this accessible.

#### User Flow

1. User goes to Fixtures > **"+ Create New Fixture"** (or clicks "Edit" on an existing
   fixture).
2. **Step 1 - Basic Info:** Form fields for manufacturer, model name, type (dropdown with
   icons), physical specs (weight, power, beam angle).
3. **Step 2 - Modes:** User adds one or more modes. For each mode:
   - Names the mode (e.g., "Standard 16ch").
   - Sets channel count.
   - A channel table appears where each row is a channel.
4. **Step 3 - Channel Mapping:** For each channel, user picks from a dropdown of channel
   types (Dimmer, Red, Green, Blue, Pan, Tilt, etc.). The dropdown uses icons and colors
   to make types instantly recognizable:
   - Red circle for Red, green circle for Green, blue circle for Blue.
   - Arrow icons for Pan/Tilt.
   - Sun icon for Dimmer.
5. **Smart suggestions:** When the user selects a fixture type (e.g., "Moving Head"), the
   system pre-fills a common channel layout that the user can modify.
6. **Validation:** The system warns if expected channels are missing (e.g., a "Moving Head"
   type with no Pan/Tilt channels).
7. **Value ranges:** For channels like Gobo or Color Wheel, user can define named value
   ranges (e.g., "Open" = 0-7, "Gobo 1" = 8-15, etc.).
8. User clicks **"Save Fixture"**. It appears in the library.

#### UI Concept

```
Fixture Editor - Step 3: Channel Mapping
+------------------------------------------------------------------+
| Mode: Standard (16ch)                                            |
|------------------------------------------------------------------|
| Ch# | Type              | Name            | Default | Range      |
|-----|-------------------|-----------------|---------|------------|
|  1  | [Pan      ->v]    | [Pan__________] |  128    | 0-255      |
|  2  | [Pan Fine ->v]    | [Pan Fine_____] |    0    | 0-255      |
|  3  | [Tilt     ->v]    | [Tilt_________] |  128    | 0-255      |
|  4  | [Tilt Fine->v]    | [Tilt Fine____] |    0    | 0-255      |
|  5  | [Speed    ->v]    | [PT Speed_____] |    0    | 0-255      |
|  6  | [Dimmer   ->v]    | [Dimmer_______] |    0    | 0-255      |
|  7  | [Shutter  ->v]    | [Shutter______] |    0    | [Ranges..] |
|  8  | [Red      ->v]    | [Red__________] |  255    | 0-255      |
|  ...                                                              |
| [+ Add Channel]   [Auto-fill from template: Moving Head v]       |
|                                                                   |
| Validation: All good!                                            |
|                                    [Cancel]    [Save Fixture]    |
+------------------------------------------------------------------+
```

#### Data Model Changes

None. The existing `Fixture`, `FixtureMode`, and `FixtureChannel` models already support
everything needed. The editor is purely a frontend improvement over the raw API.

#### API Endpoints

Existing CRUD endpoints are sufficient. One new helper:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/fixtures/channel-templates/{fixture_type}` | Get a suggested channel layout for a fixture type |

---

### 3.9 Auto-Discovery and Import (RDM)

**Priority:** P2 (Nice to Have)
**Complexity:** Very High
**Rationale:** RDM auto-discovery is the gold standard for professional setups, but
requires hardware support (RDM-compatible DMX interface) and significant protocol
implementation work.

#### User Flow

1. User connects an RDM-compatible DMX interface (e.g., ENTTEC DMXIS, Chamsys MagicDMX).
2. User goes to Rigs > **"Discover Fixtures on Network"**.
3. System sends RDM Discovery packets on all connected universes.
4. As fixtures respond, they appear in a live-updating list:
   ```
   Discovering... 6 fixtures found
   - Universe 0, Addr 1:  Robe Robin 600E LED Wash (UID: 0x12AB:00001234)
   - Universe 0, Addr 25: Robe Robin 600E LED Wash (UID: 0x12AB:00001235)
   - Universe 0, Addr 49: Martin MAC Aura XB       (UID: 0x4D41:00005678)
   ```
5. For each discovered fixture, the system checks the library for a matching profile (by
   manufacturer ID and model).
6. User clicks **"Import All"** to create a rig from the discovered fixtures, or selects
   individual fixtures.
7. If a fixture profile is not in the library, the system uses RDM to query the fixture's
   personality (mode) and channel count, then creates a basic profile automatically.

#### UI Concept

```
+------------------------------------------+
| Discover Fixtures (RDM)                  |
|------------------------------------------|
| Interface: [ENTTEC Pro Mk2    v]         |
| Universes: [x] 0  [x] 1  [ ] 2-15      |
| [Start Discovery]  [Stop]               |
|                                           |
| Found: 6 fixtures                        |
| +--------------------------------------+ |
| | [x] Univ 0 Addr 1  Robe Robin 600E  | |
| |     Status: In Library               | |
| | [x] Univ 0 Addr 25 Robe Robin 600E  | |
| |     Status: In Library               | |
| | [x] Univ 0 Addr 49 Martin MAC Aura  | |
| |     Status: NOT in library           | |
| |     [Auto-create profile from RDM]   | |
| +--------------------------------------+ |
|                                           |
|    [Import Selected to New Rig]          |
+------------------------------------------+
```

#### Data Model Changes

**New table: `rdm_devices`**
```python
class RDMDevice(Base):
    __tablename__ = "rdm_devices"
    id = Column(Integer, primary_key=True)
    uid_manufacturer = Column(Integer)       # RDM manufacturer ID
    uid_device = Column(Integer)             # RDM device ID
    manufacturer_label = Column(String(255))
    model_description = Column(String(255))
    dmx_footprint = Column(Integer)          # Channel count in current personality
    current_personality = Column(Integer)
    universe = Column(Integer)
    dmx_address = Column(Integer)
    software_version = Column(String(50))
    last_seen = Column(DateTime)
    matched_fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=True)
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/discovery/rdm/start` | Start RDM discovery on specified universes |
| `POST` | `/api/discovery/rdm/stop` | Stop discovery |
| `GET` | `/api/discovery/rdm/devices` | Get list of discovered devices |
| `POST` | `/api/discovery/rdm/import` | Import discovered devices as a rig |
| `GET` | `/api/discovery/rdm/device/{uid}/identify` | Send RDM IDENTIFY to a specific device |

---

### 3.10 QR Code / NFC Fixture Scanning

**Priority:** P2 (Nice to Have)
**Complexity:** Medium
**Rationale:** Physical scanning is a convenient shortcut during load-in but requires
fixtures to have QR codes/NFC tags, which is not yet universal in the industry.

#### User Flow

1. User opens the mobile-responsive version of the app (or a companion PWA).
2. Taps **"Scan Fixture"** which opens the device camera.
3. Points camera at a QR code on the fixture (printed by the rental house, or a custom
   label generated by this app).
4. QR code contains: fixture manufacturer, model, serial number, and optionally a URL to
   the fixture profile.
5. System looks up the fixture in the library and adds it to the current rig.
6. If the fixture has NFC, tapping the phone to the NFC tag achieves the same result.

**QR Code Generation:**
1. In the fixture library, each fixture has a **"Print QR Label"** option.
2. Generates a printable label sheet (PDF) with QR codes for each fixture instance in a
   rig, showing: fixture name, DMX address, QR data.

#### UI Concept

```
Mobile Scan View:
+---------------------------+
|   Scan Fixture            |
|                           |
|   +-------------------+   |
|   |                   |   |
|   |   [Camera View]   |   |
|   |                   |   |
|   |    [ QR Frame ]   |   |
|   |                   |   |
|   +-------------------+   |
|                           |
| Last scanned:             |
| Robe Robin 600E (#3)     |
| Added to rig at Addr 49  |
|                           |
| Scanned: 3/24 fixtures   |
| [View Rig] [Print Labels] |
+---------------------------+
```

#### Data Model Changes

**New fields on existing `RigFixture` model:**
```python
serial_number = Column(String(100), nullable=True)
qr_code_data = Column(String(500), nullable=True)   # Encoded QR payload
```

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rigs/{id}/scan` | Process scanned QR/NFC data and add fixture to rig |
| `GET` | `/api/rigs/{id}/labels/pdf` | Generate printable QR label sheet |
| `GET` | `/api/fixtures/{id}/qr-code` | Get QR code image for a fixture type |

---

## 4. Priority Matrix

| # | Feature | Priority | Complexity | Impact | Dependencies |
|---|---------|----------|------------|--------|-------------|
| 3.1 | Fixture Library / Marketplace | **P0** | High | Critical: enables all other features | None |
| 3.2 | Quick Rig Setup Wizard | **P0** | Medium | Critical: primary onboarding flow | 3.1, 3.3 |
| 3.3 | Smart DMX Auto-Patching | **P0** | Low | Critical: eliminates #1 error source | None |
| 3.4 | Drag-and-Drop Rig Builder | **P0** | High | Critical: replaces manual coordinate entry | None |
| 3.5 | Live Fixture Test | **P0** | Low | Critical: validates the entire pipeline | None |
| 3.6 | Rig Templates | **P1** | Medium | High: accelerates repeat setups | 3.1 |
| 3.7 | Import/Export (GDTF/MVR) | **P1** | High | High: bridges professional workflow | 3.1 |
| 3.8 | Fixture Profile Editor | **P1** | Medium | Medium: fallback for missing fixtures | None |
| 3.9 | Auto-Discovery (RDM) | **P2** | Very High | Medium: requires specific hardware | 3.1 |
| 3.10 | QR/NFC Scanning | **P2** | Medium | Low: requires physical labels | 3.1 |

### Recommended Build Order (16-Week Roadmap)

**Phase 1 (Weeks 1-4): Foundation**
- Fixture Library with Open Fixture Library integration (3.1)
- Smart DMX Auto-Patching with conflict detection (3.3)
- Live Fixture Test with per-fixture identify/color/movement (3.5)

**Phase 2 (Weeks 5-8): Visual Editing**
- Drag-and-Drop Rig Builder with 2D stage view (3.4)
- Quick Rig Setup Wizard with venue presets (3.2)

**Phase 3 (Weeks 9-12): Power Features**
- Rig Templates with save/load/share (3.6)
- Fixture Profile Editor with smart suggestions (3.8)

**Phase 4 (Weeks 13-16): Professional Integration**
- GDTF/MVR Import and Export (3.7)

**Phase 5 (Future): Advanced**
- RDM Auto-Discovery (3.9)
- QR/NFC Scanning (3.10)

---

## 5. Implementation Plan: Top 5 Features

### 5.1 Fixture Library / Marketplace - Implementation Details

#### Backend Changes

**File: `backend/app/models/fixture.py`**
Add the following fields to the `Fixture` class (after the `model_3d_url` column,
around line 92):
```python
# Library source tracking
source = Column(String(50), default="local")
source_id = Column(String(255), nullable=True)
categories = Column(JSON, default=list)
popularity_score = Column(Integer, default=0)
is_bundled = Column(Boolean, default=False)
```

**New file: `backend/app/services/fixture_library/__init__.py`**
Empty init file.

**New file: `backend/app/services/fixture_library/ofl_client.py`**
Create an HTTP client that integrates with the Open Fixture Library API
(`https://open-fixture-library.org/api/v1`):
```python
import httpx
from typing import List, Optional
from app.schemas.fixture import FixtureCreate, FixtureModeCreate, FixtureChannelCreate

class OFLClient:
    """Client for the Open Fixture Library API."""

    BASE_URL = "https://open-fixture-library.org/api/v1"

    def __init__(self):
        self.client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=30.0)

    async def search_fixtures(
        self, query: str, manufacturer: Optional[str] = None
    ) -> List[dict]:
        """Search OFL for fixtures by name or manufacturer."""
        params = {"search": query}
        if manufacturer:
            params["manufacturer"] = manufacturer
        response = await self.client.get("/fixtures", params=params)
        response.raise_for_status()
        return response.json()

    async def get_fixture(
        self, manufacturer_key: str, fixture_key: str
    ) -> dict:
        """Get full fixture definition from OFL."""
        response = await self.client.get(
            f"/fixtures/{manufacturer_key}/{fixture_key}"
        )
        response.raise_for_status()
        return response.json()

    async def list_manufacturers(self) -> List[dict]:
        """List all manufacturers in OFL."""
        response = await self.client.get("/manufacturers")
        response.raise_for_status()
        return response.json()

    def convert_ofl_to_internal(self, ofl_data: dict) -> FixtureCreate:
        """Convert an OFL fixture definition to our internal schema."""
        # Map OFL channel types to our ChannelType enum
        # Map OFL modes to our FixtureMode/FixtureChannel structure
        # Extract physical properties (weight, power, beam angle)
        ...
```

**New file: `backend/app/api/endpoints/fixture_library.py`**
New router mounted at `/api/fixtures/library/`:
```python
from fastapi import APIRouter, Depends
from app.services.fixture_library.ofl_client import OFLClient

router = APIRouter()

@router.get("/search")
async def search_online_library(query: str, manufacturer: str = None):
    """Proxy search to Open Fixture Library."""
    client = OFLClient()
    results = await client.search_fixtures(query, manufacturer)
    return results

@router.post("/import")
async def import_from_library(source: str, source_id: str, db=Depends(get_db)):
    """Import a fixture from an external library source."""
    ...

@router.post("/import-bulk")
async def import_bulk(items: List[dict], db=Depends(get_db)):
    """Bulk import multiple fixtures."""
    ...

@router.get("/popular")
async def get_popular_fixtures(limit: int = 20, db=Depends(get_db)):
    """Get the most-used fixtures across all rigs."""
    ...

@router.get("/manufacturers")
async def list_external_manufacturers():
    """List all manufacturers from OFL."""
    ...
```

**File: `backend/app/api/endpoints/__init__.py`**
Register the new `fixture_library` router.

**New directory: `data/fixtures/bundled/`**
Create 200 pre-authored fixture JSON files for the most popular real-world fixtures
(Chauvet, Martin, Robe, ETC, Elation, ADJ, Clay Paky, etc.). The `scripts/init_db.py`
script should be updated to load these from `data/fixtures/bundled/` on first run.

#### Frontend Changes

**New file: `frontend/src/components/fixtures/FixtureLibrary.tsx`**
New top-level page component with two tabs (My Library / Browse Online), search bar,
manufacturer filter dropdown, fixture type filter chips, and a paginated fixture card
grid.

**New file: `frontend/src/components/fixtures/FixtureCard.tsx`**
Reusable card component displaying: fixture type icon, manufacturer, model name, mode
count with channel counts, and an "Add to Library" or "Already Added" button.

**New file: `frontend/src/components/fixtures/FixtureDetail.tsx`**
Detail view showing all modes, channel maps, physical properties, and a mini 3D preview
if a model is available.

**File: `frontend/src/App.tsx`** (line 19-26)
Add new routes:
```tsx
<Route path="fixtures" element={<FixtureLibrary />} />
<Route path="fixtures/:id" element={<FixtureDetail />} />
```

**File: `frontend/src/components/common/Layout.tsx`**
Add "Fixtures" to the navigation menu items.

**File: `frontend/src/services/api.ts`** (extend `fixturesApi` around line 171-199)
Add library methods:
```typescript
searchOnline: async (query: string, manufacturer?: string) => {
    const params = new URLSearchParams({ query });
    if (manufacturer) params.append('manufacturer', manufacturer);
    const response = await api.get(`/fixtures/library/search?${params}`);
    return response.data;
},
importFromLibrary: async (source: string, sourceId: string) => {
    const response = await api.post('/fixtures/library/import', { source, source_id: sourceId });
    return response.data;
},
importBulk: async (items: { source: string; sourceId: string }[]) => {
    const response = await api.post('/fixtures/library/import-bulk', items);
    return response.data;
},
```

**File: `frontend/src/types/index.ts`**
Add types for library search results:
```typescript
export interface OFLFixtureResult {
    manufacturer_key: string;
    fixture_key: string;
    manufacturer: string;
    model: string;
    fixture_type: string;
    modes: { name: string; channel_count: number }[];
    already_imported: boolean;
}
```

---

### 5.2 Smart DMX Auto-Patching - Implementation Details

#### Backend Changes

**File: `backend/app/models/rig.py`** (after line 82)
Add to `RigFixture` class:
```python
is_address_locked = Column(Boolean, default=False)
```

**New file: `backend/app/services/rig/__init__.py`**
Empty init file.

**New file: `backend/app/services/rig/patching_service.py`**
```python
from collections import defaultdict
from typing import List, Tuple, Dict, Set, Optional

class PatchingService:
    """Smart DMX address assignment and conflict detection."""

    @staticmethod
    def find_conflicts(fixtures: List[dict]) -> List[dict]:
        """Find all DMX address conflicts in a fixture list.

        Each fixture dict must have: id, name, universe, dmx_address,
        mode_channel_count.

        Returns list of conflict objects with fixture_a, fixture_b,
        universe, overlap_start, overlap_end.
        """
        conflicts = []
        by_universe: Dict[int, list] = defaultdict(list)
        for f in fixtures:
            channel_count = f.get('mode_channel_count') or 1
            by_universe[f['universe']].append({
                'id': f['id'],
                'name': f.get('name', f'Fixture {f["id"]}'),
                'start': f['dmx_address'],
                'end': f['dmx_address'] + channel_count - 1,
            })

        for universe, fxs in by_universe.items():
            fxs.sort(key=lambda x: x['start'])
            for i in range(len(fxs)):
                for j in range(i + 1, len(fxs)):
                    if fxs[j]['start'] <= fxs[i]['end']:
                        conflicts.append({
                            'fixture_a': fxs[i],
                            'fixture_b': fxs[j],
                            'universe': universe,
                            'overlap_start': fxs[j]['start'],
                            'overlap_end': min(fxs[i]['end'], fxs[j]['end']),
                        })
        return conflicts

    @staticmethod
    def auto_patch(
        fixtures: List[dict], locked_ids: Optional[Set[int]] = None
    ) -> List[dict]:
        """Reassign DMX addresses to avoid conflicts.

        Locked fixtures keep their addresses; unlocked are reassigned
        sequentially.
        """
        locked_ids = locked_ids or set()
        locked = [f for f in fixtures if f['id'] in locked_ids]
        unlocked = [f for f in fixtures if f['id'] not in locked_ids]

        occupied: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        for f in locked:
            ch_count = f.get('mode_channel_count') or 1
            occupied[f['universe']].append(
                (f['dmx_address'], f['dmx_address'] + ch_count - 1)
            )

        for f in unlocked:
            ch_count = f.get('mode_channel_count') or 1
            universe = f.get('universe', 0)
            addr = PatchingService._find_next_available(
                occupied[universe], ch_count
            )
            if addr + ch_count - 1 > 512:
                universe += 1
                addr = PatchingService._find_next_available(
                    occupied[universe], ch_count
                )
            f['dmx_address'] = addr
            f['universe'] = universe
            occupied[universe].append((addr, addr + ch_count - 1))

        return locked + unlocked

    @staticmethod
    def get_next_address(
        occupied: List[Tuple[int, int]], channel_count: int
    ) -> int:
        """Find the next available starting address."""
        return PatchingService._find_next_available(occupied, channel_count)

    @staticmethod
    def _find_next_available(
        occupied: List[Tuple[int, int]], channel_count: int
    ) -> int:
        """Find first gap that fits channel_count channels."""
        if not occupied:
            return 1
        sorted_occ = sorted(occupied, key=lambda x: x[0])
        if sorted_occ[0][0] >= channel_count + 1:
            return 1
        for i in range(len(sorted_occ) - 1):
            gap_start = sorted_occ[i][1] + 1
            gap_end = sorted_occ[i + 1][0] - 1
            if gap_end - gap_start + 1 >= channel_count:
                return gap_start
        return sorted_occ[-1][1] + 1
```

**Add to rigs API router (or new file `backend/app/api/endpoints/rig_patching.py`):**
```python
@router.post("/{rig_id}/auto-patch")
async def auto_patch_rig(rig_id: int, db=Depends(get_db)):
    """Recalculate DMX addresses for all non-locked fixtures."""
    ...

@router.get("/{rig_id}/patch-conflicts")
async def get_patch_conflicts(rig_id: int, db=Depends(get_db)):
    """Return list of DMX address conflicts."""
    ...

@router.get("/{rig_id}/next-address")
async def get_next_address(
    rig_id: int, universe: int = 0, channel_count: int = 1,
    db=Depends(get_db),
):
    """Get the next available DMX address."""
    ...
```

#### Frontend Changes

**File: `frontend/src/components/rig/RigEditor.tsx`**
Major changes to the Add Fixture dialog (lines 291-404):
1. Add a mode selector dropdown that populates when a fixture is selected. When the user
   picks a fixture from the dropdown, fetch its modes and show a second dropdown. When a
   mode is selected, auto-calculate the next available DMX address using
   `GET /api/rigs/{id}/next-address?channel_count=X&universe=Y`.
2. Replace the `getNextAddress()` function (lines 129-133) with an async API call.
3. Add a "Lock Address" toggle checkbox next to the DMX address field.
4. Add an "Auto-Patch All" button to the fixture list header (line 238-249).
5. After saving/loading, call `GET /api/rigs/{id}/patch-conflicts` and display red
   conflict indicators on any fixtures with overlapping addresses.

**File: `frontend/src/services/api.ts`**
Add to `rigsApi` (after line 163):
```typescript
autoPatch: async (rigId: number): Promise<RigFixture[]> => {
    const response = await api.post(`/rigs/${rigId}/auto-patch`);
    return response.data;
},
getConflicts: async (rigId: number): Promise<PatchConflict[]> => {
    const response = await api.get(`/rigs/${rigId}/patch-conflicts`);
    return response.data;
},
getNextAddress: async (
    rigId: number, universe: number, channelCount: number
): Promise<{ address: number }> => {
    const response = await api.get(`/rigs/${rigId}/next-address`, {
        params: { universe, channel_count: channelCount },
    });
    return response.data;
},
```

**File: `frontend/src/types/index.ts`**
Add (after `RigFixtureCreate` interface around line 254):
```typescript
export interface PatchConflict {
    fixture_a: { id: number; name: string; start: number; end: number };
    fixture_b: { id: number; name: string; start: number; end: number };
    universe: number;
    overlap_start: number;
    overlap_end: number;
}
```

---

### 5.3 Live Fixture Test - Implementation Details

#### Backend Changes

**New file: `backend/app/services/fixture_test/__init__.py`**
Empty init file.

**New file: `backend/app/services/fixture_test/fixture_test_service.py`**
```python
import asyncio
from typing import Dict, Optional
from app.models.fixture import FixtureMode, FixtureChannel, ChannelType
from app.models.rig import RigFixture
from app.services.dmx.dmx_controller import DMXController


class FixtureTestService:
    """Fixture-aware test patterns."""

    def __init__(self, dmx_controller: DMXController):
        self.dmx = dmx_controller
        self.active_tests: Dict[int, asyncio.Task] = {}

    def _build_channel_map(self, mode: FixtureMode) -> Dict[str, int]:
        """Map channel type names to 0-indexed offsets."""
        return {
            ch.channel_type.value: ch.channel_number - 1
            for ch in sorted(mode.channels, key=lambda c: c.channel_number)
        }

    async def _set(self, rf: RigFixture, offset: int, value: int):
        """Set a single channel on a fixture by offset."""
        await self.dmx.set_channel(
            rf.universe, rf.dmx_address + offset, value
        )

    async def _zero(self, rf: RigFixture, mode: FixtureMode):
        """Set all channels to zero."""
        for ch in mode.channels:
            await self._set(rf, ch.channel_number - 1, 0)

    async def identify(self, rf: RigFixture, mode: FixtureMode):
        """Lamp on white at full for 3 seconds, then restore."""
        cm = self._build_channel_map(mode)
        try:
            if 'dimmer' in cm:
                await self._set(rf, cm['dimmer'], 255)
            for color in ['red', 'green', 'blue', 'white']:
                if color in cm:
                    await self._set(rf, cm[color], 255)
            await asyncio.sleep(3.0)
        finally:
            await self._zero(rf, mode)

    async def color_cycle(self, rf: RigFixture, mode: FixtureMode):
        """Cycle through primary colors with 1-second holds."""
        cm = self._build_channel_map(mode)
        colors = [
            {'red': 255, 'green': 0,   'blue': 0},
            {'red': 0,   'green': 255, 'blue': 0},
            {'red': 0,   'green': 0,   'blue': 255},
            {'red': 255, 'green': 255, 'blue': 0},
            {'red': 255, 'green': 0,   'blue': 255},
            {'red': 0,   'green': 255, 'blue': 255},
            {'red': 255, 'green': 255, 'blue': 255},
        ]
        try:
            if 'dimmer' in cm:
                await self._set(rf, cm['dimmer'], 255)
            for color in colors:
                for ch_type, val in color.items():
                    if ch_type in cm:
                        await self._set(rf, cm[ch_type], val)
                await asyncio.sleep(1.0)
        finally:
            await self._zero(rf, mode)

    async def movement_test(self, rf: RigFixture, mode: FixtureMode):
        """Slow pan sweep, then tilt sweep, then center."""
        cm = self._build_channel_map(mode)
        try:
            if 'dimmer' in cm:
                await self._set(rf, cm['dimmer'], 200)
            for ch in ['red', 'green', 'blue']:
                if ch in cm:
                    await self._set(rf, cm[ch], 255)
            if 'pan' in cm:
                for val in range(0, 256, 5):
                    await self._set(rf, cm['pan'], val)
                    await asyncio.sleep(0.03)
            if 'tilt' in cm:
                for val in range(0, 256, 5):
                    await self._set(rf, cm['tilt'], val)
                    await asyncio.sleep(0.03)
            if 'pan' in cm:
                await self._set(rf, cm['pan'], 128)
            if 'tilt' in cm:
                await self._set(rf, cm['tilt'], 128)
            await asyncio.sleep(1.0)
        finally:
            await self._zero(rf, mode)

    async def run_test(
        self, rf: RigFixture, mode: FixtureMode, test_type: str
    ):
        """Run a named test type."""
        await self.stop_test(rf.id)
        test_fn = {
            'identify': self.identify,
            'color_cycle': self.color_cycle,
            'movement': self.movement_test,
            'full': self._full_test,
        }.get(test_type)
        if test_fn:
            task = asyncio.create_task(test_fn(rf, mode))
            self.active_tests[rf.id] = task

    async def _full_test(self, rf: RigFixture, mode: FixtureMode):
        """Run identify + color cycle + movement sequentially."""
        await self.identify(rf, mode)
        await asyncio.sleep(0.5)
        await self.color_cycle(rf, mode)
        await asyncio.sleep(0.5)
        await self.movement_test(rf, mode)

    async def stop_test(self, rig_fixture_id: int):
        """Stop a running test on a fixture."""
        if rig_fixture_id in self.active_tests:
            self.active_tests[rig_fixture_id].cancel()
            try:
                await self.active_tests[rig_fixture_id]
            except asyncio.CancelledError:
                pass
            del self.active_tests[rig_fixture_id]

    async def set_channels(
        self, rf: RigFixture, channel_values: Dict[int, int]
    ):
        """Set arbitrary channel values for live fader control."""
        for offset, value in channel_values.items():
            await self._set(rf, offset, value)
```

**Add API endpoints (new file or extend rigs router):**
```python
@router.post("/{rig_id}/fixtures/{rig_fixture_id}/test")
async def test_fixture(
    rig_id: int, rig_fixture_id: int,
    test_type: str = Query(..., regex="^(identify|color_cycle|movement|full)$"),
    db=Depends(get_db),
):
    """Run a test pattern on a single fixture."""
    # 1. Load RigFixture with its mode (eager load channels)
    # 2. Call fixture_test_service.run_test(rig_fixture, mode, test_type)
    ...

@router.post("/{rig_id}/fixtures/{rig_fixture_id}/test/stop")
async def stop_fixture_test(rig_id: int, rig_fixture_id: int):
    """Stop a running test."""
    ...

@router.post("/{rig_id}/fixtures/{rig_fixture_id}/set-channels")
async def set_fixture_channels(
    rig_id: int, rig_fixture_id: int,
    channel_values: Dict[int, int],
    db=Depends(get_db),
):
    """Set individual channel values for live fader control."""
    ...

@router.post("/{rig_id}/test-all")
async def test_all_fixtures(rig_id: int, db=Depends(get_db)):
    """Sequential identify test across all fixtures in address order."""
    ...

@router.post("/{rig_id}/test-all/stop")
async def stop_test_all(rig_id: int):
    """Stop the sequential test."""
    ...
```

#### Frontend Changes

**New file: `frontend/src/components/rig/FixtureTestPanel.tsx`**
A popover or bottom-drawer component with:
- Header showing fixture name, address, universe.
- Row of test action buttons: Identify, Color Cycle, Movement, Full Test, All Off.
- "Advanced" expandable section with dynamically generated slider for each channel in the
  fixture's mode. Each slider calls `POST /set-channels` on change with debouncing.

**File: `frontend/src/components/rig/RigEditor.tsx`** (around line 266)
Add a "Test" icon button to each fixture list item alongside the existing Delete button:
```tsx
<IconButton
    onClick={() => setTestingFixtureId(fixture.id)}
    color="primary"
    size="small"
    title="Test Fixture"
>
    <FlashOnIcon />
</IconButton>
```

**File: `frontend/src/services/api.ts`** (add to `rigsApi`)
```typescript
testFixture: async (rigId: number, fixtureId: number, testType: string) => {
    await api.post(`/rigs/${rigId}/fixtures/${fixtureId}/test`, null, {
        params: { test_type: testType },
    });
},
stopFixtureTest: async (rigId: number, fixtureId: number) => {
    await api.post(`/rigs/${rigId}/fixtures/${fixtureId}/test/stop`);
},
setFixtureChannels: async (
    rigId: number, fixtureId: number, channels: Record<number, number>
) => {
    await api.post(`/rigs/${rigId}/fixtures/${fixtureId}/set-channels`, channels);
},
testAll: async (rigId: number) => {
    await api.post(`/rigs/${rigId}/test-all`);
},
stopTestAll: async (rigId: number) => {
    await api.post(`/rigs/${rigId}/test-all/stop`);
},
```

---

### 5.4 Drag-and-Drop Rig Builder - Implementation Details

#### Frontend Changes (Primary)

**New file: `frontend/src/components/rig/RigBuilder.tsx`**
The new main rig editing layout that replaces the form-based `RigEditor` as the primary
editing experience. Uses `@dnd-kit/core` for drag-and-drop:
```typescript
import { DndContext, closestCenter } from '@dnd-kit/core';

export default function RigBuilder() {
    return (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <Box sx={{ display: 'flex', height: '100%' }}>
                <FixturePalette />         {/* Left: ~200px wide */}
                <Box sx={{ flex: 1 }}>
                    <RigEditorToolbar />
                    <StageView2D />        {/* Center: fills remaining space */}
                </Box>
                <PatchTable />             {/* Right: ~280px wide */}
            </Box>
        </DndContext>
    );
}
```

**New file: `frontend/src/components/rig/StageView2D.tsx`**
SVG-based 2D top-down stage view:
- Renders the stage as a rectangle with meter grid lines using SVG `<rect>` and `<line>`.
- Renders truss positions as horizontal bars at configurable Y positions.
- Each fixture is an SVG `<g>` element with a type-specific icon, label, and drag handle.
- Uses `@dnd-kit/core` `useDraggable` on each fixture group.
- On drag end, converts pixel delta to meter delta using the SVG viewBox scale, then calls
  `PUT /api/rigs/{id}/fixtures/batch-update` with new positions.
- Supports multi-select with Shift+click or rectangle selection (uses SVG overlay for the
  selection rectangle).
- Drop targets on the stage surface accept drags from the FixturePalette; dropping creates
  a new RigFixture via `POST /api/rigs/{id}/fixtures`.
- Snap-to-grid: rounds positions to nearest `gridSize` (default 0.5m).
- The SVG `viewBox` is set to `[0, 0, stage_width, stage_depth]` so 1 SVG unit = 1 meter.

**New file: `frontend/src/components/rig/FixturePalette.tsx`**
Left sidebar listing fixture types from the user's library:
- Grouped by fixture type (Moving Heads, PARs, Bars, etc.) with collapsible sections.
- Search box at the top to filter.
- Each item shows a small icon, manufacturer/model, and default mode channel count.
- Each item is a drag source using `@dnd-kit/core` `useDraggable`.

**New file: `frontend/src/components/rig/PatchTable.tsx`**
Right sidebar showing the DMX patch as a compact table:
- Tab buttons for each used universe (Universe 0, Universe 1, ...).
- Visual address bar: a horizontal strip 512px wide showing used (colored) vs. free
  (gray) channel ranges. Hovering shows the fixture name.
- Sortable fixture list with columns: Address, Name, Mode, Channels.
- Red highlight on any row with conflicts.
- Usage summary: "97/512 channels used (19%)".

**New file: `frontend/src/components/rig/FixtureProperties.tsx`**
Bottom-left property editor panel that appears when one or more fixtures are selected:
- Name text field, Mode dropdown, Group dropdown, Tags multi-select.
- DMX Address field with lock toggle and conflict indicator.
- Position fields (X, Y, Z) that update from drag and can be typed manually.
- Rotation fields (Rx, Ry, Rz).

**New file: `frontend/src/components/rig/RigEditorToolbar.tsx`**
Top toolbar with:
- Rig name (editable inline).
- View mode toggle: [2D] [3D].
- Snap mode: dropdown with Grid (0.5m) / Truss / Free.
- Action buttons: Save, Auto-Patch All, Test All.
- Undo/Redo buttons.

**New file: `frontend/src/stores/rigEditorStore.ts`**
Zustand store for editor-specific state:
```typescript
import { create } from 'zustand';

interface RigEditorState {
    viewMode: '2d' | '3d';
    snapMode: 'grid' | 'truss' | 'free';
    gridSize: number;
    selectedFixtureIds: number[];
    hoveredFixtureId: number | null;
    isDragging: boolean;
    showPatchTable: boolean;
    showProperties: boolean;
    undoStack: any[];
    redoStack: any[];
    selectFixture: (id: number, multi?: boolean) => void;
    deselectAll: () => void;
    setViewMode: (mode: '2d' | '3d') => void;
    setSnapMode: (mode: 'grid' | 'truss' | 'free') => void;
    pushUndo: (state: any) => void;
    undo: () => any;
    redo: () => any;
}

export const useRigEditorStore = create<RigEditorState>((set, get) => ({
    viewMode: '2d',
    snapMode: 'grid',
    gridSize: 0.5,
    selectedFixtureIds: [],
    hoveredFixtureId: null,
    isDragging: false,
    showPatchTable: true,
    showProperties: true,
    undoStack: [],
    redoStack: [],
    selectFixture: (id, multi = false) => set((state) => ({
        selectedFixtureIds: multi
            ? state.selectedFixtureIds.includes(id)
                ? state.selectedFixtureIds.filter((fid) => fid !== id)
                : [...state.selectedFixtureIds, id]
            : [id],
    })),
    deselectAll: () => set({ selectedFixtureIds: [] }),
    setViewMode: (mode) => set({ viewMode: mode }),
    setSnapMode: (mode) => set({ snapMode: mode }),
    pushUndo: (snapshot) => set((state) => ({
        undoStack: [...state.undoStack, snapshot],
        redoStack: [],
    })),
    undo: () => { /* pop from undoStack, push current to redoStack */ },
    redo: () => { /* pop from redoStack, push current to undoStack */ },
}));
```

**File: `frontend/src/App.tsx`** (line 19-26)
Update the rig edit route to point to the new builder:
```tsx
<Route path="rigs/:id" element={<RigBuilder />} />
```
Keep old editor as a fallback route if needed during transition.

**File: `frontend/package.json`**
Add dependency: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`.

#### Backend Changes

**Add to rigs API router:**
```python
@router.put("/{rig_id}/fixtures/batch-update")
async def batch_update_fixtures(
    rig_id: int,
    updates: List[dict],  # [{id, position_x, position_y, position_z, ...}]
    db=Depends(get_db),
):
    """Update multiple fixture positions/properties in a single call."""
    ...

@router.post("/{rig_id}/fixtures/duplicate/{fixture_id}")
async def duplicate_fixture(rig_id: int, fixture_id: int, db=Depends(get_db)):
    """Duplicate a fixture in the rig with auto-patched address."""
    ...
```

---

### 5.5 Quick Rig Setup Wizard - Implementation Details

#### Backend Changes

**New file: `backend/app/services/rig/wizard_service.py`**
```python
from collections import defaultdict
from typing import List, Dict

class WizardService:
    """Generates rig configurations from venue presets."""

    VENUE_PRESETS = {
        "small_club": {
            "name": "Small Club",
            "stage_width": 8.0, "stage_depth": 6.0, "stage_height": 4.0,
            "suggested_fixtures": [
                {"fixture_type": "led_par", "quantity": 4, "group": "front_wash"},
                {"fixture_type": "moving_head", "quantity": 4, "group": "movers"},
            ],
            "placement_strategy": "symmetric",
        },
        "medium_venue": {
            "name": "Medium Venue",
            "stage_width": 12.0, "stage_depth": 10.0, "stage_height": 6.0,
            "suggested_fixtures": [
                {"fixture_type": "led_par", "quantity": 8, "group": "wash"},
                {"fixture_type": "moving_head", "quantity": 8, "group": "movers"},
                {"fixture_type": "led_bar", "quantity": 4, "group": "back_light"},
                {"fixture_type": "strobe", "quantity": 4, "group": "effects"},
            ],
            "placement_strategy": "symmetric",
        },
        "church": {
            "name": "Church / House of Worship",
            "stage_width": 10.0, "stage_depth": 8.0, "stage_height": 5.0,
            "suggested_fixtures": [
                {"fixture_type": "led_par", "quantity": 8, "group": "wash"},
                {"fixture_type": "spot", "quantity": 4, "group": "key_light"},
            ],
            "placement_strategy": "front_heavy",
        },
        "theater": {
            "name": "Theater",
            "stage_width": 14.0, "stage_depth": 12.0, "stage_height": 8.0,
            "suggested_fixtures": [
                {"fixture_type": "spot", "quantity": 12, "group": "front_of_house"},
                {"fixture_type": "wash", "quantity": 8, "group": "wash"},
                {"fixture_type": "moving_head", "quantity": 8, "group": "movers"},
                {"fixture_type": "led_bar", "quantity": 6, "group": "cyc"},
            ],
            "placement_strategy": "layered",
        },
        "festival_stage": {
            "name": "Festival Stage",
            "stage_width": 18.0, "stage_depth": 14.0, "stage_height": 10.0,
            "suggested_fixtures": [
                {"fixture_type": "wash", "quantity": 16, "group": "wash"},
                {"fixture_type": "moving_head", "quantity": 16, "group": "movers"},
                {"fixture_type": "beam", "quantity": 8, "group": "beams"},
                {"fixture_type": "strobe", "quantity": 8, "group": "effects"},
                {"fixture_type": "led_bar", "quantity": 8, "group": "blinders"},
            ],
            "placement_strategy": "symmetric",
        },
    }

    @classmethod
    def get_venue_presets(cls) -> list:
        return [{"key": k, **v} for k, v in cls.VENUE_PRESETS.items()]

    @classmethod
    def compute_placement(
        cls, stage_width: float, stage_depth: float,
        stage_height: float, fixtures: list,
        strategy: str = "symmetric",
    ) -> list:
        """Compute optimal fixture positions."""
        groups: Dict[str, list] = defaultdict(list)
        for f in fixtures:
            groups[f.get('group', 'default')].append(f)

        truss_height = stage_height - 0.5

        for group_name, group_fxs in groups.items():
            count = len(group_fxs)
            if group_name in ('front_wash', 'front_of_house'):
                z = -stage_depth / 2 + 1.0
            elif group_name in ('back_wash', 'back_light', 'cyc', 'blinders'):
                z = stage_depth / 2 - 1.0
            else:
                z = 0.0

            for i, f in enumerate(group_fxs):
                x = -stage_width / 2 + stage_width * (i + 1) / (count + 1)
                f['position_x'] = round(x, 1)
                f['position_y'] = round(truss_height, 1)
                f['position_z'] = round(z, 1)

        return fixtures
```

**New file: `backend/app/api/endpoints/wizard.py`**
```python
from fastapi import APIRouter, Depends
from app.services.rig.wizard_service import WizardService

router = APIRouter()

@router.get("/venue-presets")
async def get_venue_presets():
    """Return all available venue presets."""
    return WizardService.get_venue_presets()

@router.get("/venue-presets/{key}/suggestions")
async def get_venue_suggestions(key: str, db=Depends(get_db)):
    """Get fixture suggestions for a venue type, matched to library."""
    preset = WizardService.VENUE_PRESETS.get(key)
    if not preset:
        raise HTTPException(status_code=404, detail="Unknown venue preset")
    # For each suggested fixture_type, find the best match in the library
    # Return the suggestions with matched fixture IDs and modes
    ...

@router.post("/auto-place")
async def auto_place(request: dict):
    """Compute optimal fixture positions given stage dims and fixture list."""
    return WizardService.compute_placement(
        request['stage_width'], request['stage_depth'],
        request['stage_height'], request['fixtures'],
        request.get('strategy', 'symmetric'),
    )

@router.post("/create-rig")
async def wizard_create_rig(request: dict, db=Depends(get_db)):
    """Create a complete rig from wizard data (all fixtures + placements)."""
    # 1. Create Rig record with stage dimensions
    # 2. For each fixture in request, create RigFixture with positions and
    #    auto-patched DMX addresses
    # 3. Return the created rig
    ...
```

#### Frontend Changes

**New file: `frontend/src/components/rig/RigWizard.tsx`**
Multi-step wizard component using MUI Stepper:
```typescript
import { Stepper, Step, StepLabel } from '@mui/material';

const steps = [
    'Choose Venue Type',
    'Stage Dimensions',
    'Pick Fixtures',
    'Review Placement & Patch',
    'Create Rig',
];

export default function RigWizard() {
    const [activeStep, setActiveStep] = useState(0);
    const [wizardData, setWizardData] = useState({
        venuePreset: null,
        stageWidth: 10, stageDepth: 8, stageHeight: 6,
        fixtures: [],
        placements: [],
    });

    return (
        <Box sx={{ maxWidth: 900, mx: 'auto', py: 4 }}>
            <Typography variant="h4" gutterBottom>Quick Rig Setup</Typography>
            <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
                {steps.map((label) => (
                    <Step key={label}><StepLabel>{label}</StepLabel></Step>
                ))}
            </Stepper>
            {activeStep === 0 && <VenueTypeStep ... />}
            {activeStep === 1 && <StageDimensionsStep ... />}
            {activeStep === 2 && <PickFixturesStep ... />}
            {activeStep === 3 && <ReviewPlacementStep ... />}
            {activeStep === 4 && <CreateRigStep ... />}
        </Box>
    );
}
```

**New files for each wizard step:**
- `frontend/src/components/rig/wizard/VenueTypeStep.tsx` - Grid of venue type cards with
  icons; clicking one populates stage dimensions and fixture suggestions.
- `frontend/src/components/rig/wizard/StageDimensionsStep.tsx` - Width/depth/height
  sliders with a live mini 3D canvas preview.
- `frontend/src/components/rig/wizard/PickFixturesStep.tsx` - Suggested fixture list with
  +/- quantity buttons, fixture swap button (opens mini browser), mode selector, and
  "+ Add Row" to add more types.
- `frontend/src/components/rig/wizard/ReviewPlacementStep.tsx` - 2D top-down stage preview
  (reuses `StageView2D` in read-only mode) plus DMX address table. User can drag fixtures
  to adjust before confirming.

**File: `frontend/src/App.tsx`**
Add route:
```tsx
<Route path="rigs/new/wizard" element={<RigWizard />} />
```

**File: `frontend/src/components/rig/RigList.tsx`** (line 102-106)
Change the "New Rig" button to open a choice dialog instead of directly opening the
create form:
```
"How would you like to create your rig?"
[Quick Setup Wizard]  [Start from Scratch]  [From Template]  [Import File]
```

---

## 6. Data Model Changes Summary

### New Tables

| Table | Feature | Purpose |
|-------|---------|---------|
| `fixture_library_sources` | 3.1 Fixture Library | Tracks external fixture library source configurations |
| `venue_presets` | 3.2 Wizard | Stores venue type presets (can be hardcoded as alternative) |
| `rig_templates` | 3.6 Templates | Stores reusable rig templates with abstract fixture slots |
| `rdm_devices` | 3.9 RDM Discovery | Caches RDM-discovered devices on the network |

### Modified Tables

| Table | Column | Feature | Type | Default | Description |
|-------|--------|---------|------|---------|-------------|
| `fixtures` | `source` | 3.1 | `String(50)` | `"local"` | Origin of the fixture profile |
| `fixtures` | `source_id` | 3.1 | `String(255)` | `NULL` | External source identifier |
| `fixtures` | `categories` | 3.1 | `JSON` | `[]` | Categorization tags |
| `fixtures` | `popularity_score` | 3.1 | `Integer` | `0` | Usage counter for sorting |
| `fixtures` | `is_bundled` | 3.1 | `Boolean` | `False` | Part of the pre-installed kit |
| `rig_fixtures` | `is_address_locked` | 3.3 | `Boolean` | `False` | User pinned this DMX address |
| `rig_fixtures` | `serial_number` | 3.10 | `String(100)` | `NULL` | Physical fixture serial |
| `rig_fixtures` | `qr_code_data` | 3.10 | `String(500)` | `NULL` | Encoded QR payload |
| `rigs` | `source_format` | 3.7 | `String(50)` | `NULL` | Import origin format |
| `rigs` | `source_file` | 3.7 | `String(500)` | `NULL` | Original import filename |

### Database Migration

A new Alembic migration file should be created at
`backend/alembic/versions/002_fixture_integration_features.py` to add all new tables
and columns. All new columns have sensible defaults to preserve existing data.

---

## 7. API Endpoints Summary

### All New Endpoints

| Priority | Method | Path | Feature |
|----------|--------|------|---------|
| P0 | `GET` | `/api/fixtures/library/search` | 3.1 Fixture Library |
| P0 | `POST` | `/api/fixtures/library/import` | 3.1 Fixture Library |
| P0 | `POST` | `/api/fixtures/library/import-bulk` | 3.1 Fixture Library |
| P0 | `GET` | `/api/fixtures/library/popular` | 3.1 Fixture Library |
| P0 | `GET` | `/api/fixtures/library/manufacturers` | 3.1 Fixture Library |
| P0 | `POST` | `/api/fixtures/library/sync` | 3.1 Fixture Library |
| P0 | `GET` | `/api/wizard/venue-presets` | 3.2 Wizard |
| P0 | `GET` | `/api/wizard/venue-presets/{key}/suggestions` | 3.2 Wizard |
| P0 | `POST` | `/api/wizard/auto-place` | 3.2 Wizard |
| P0 | `POST` | `/api/wizard/create-rig` | 3.2 Wizard |
| P0 | `POST` | `/api/rigs/{id}/auto-patch` | 3.3 Auto-Patching |
| P0 | `GET` | `/api/rigs/{id}/patch-conflicts` | 3.3 Auto-Patching |
| P0 | `GET` | `/api/rigs/{id}/next-address` | 3.3 Auto-Patching |
| P0 | `PUT` | `/api/rigs/{id}/fixtures/batch-update` | 3.4 Rig Builder |
| P0 | `POST` | `/api/rigs/{id}/fixtures/duplicate/{fid}` | 3.4 Rig Builder |
| P0 | `POST` | `/api/rigs/{id}/fixtures/{fid}/test` | 3.5 Fixture Test |
| P0 | `POST` | `/api/rigs/{id}/fixtures/{fid}/test/stop` | 3.5 Fixture Test |
| P0 | `POST` | `/api/rigs/{id}/fixtures/{fid}/set-channels` | 3.5 Fixture Test |
| P0 | `POST` | `/api/rigs/{id}/test-all` | 3.5 Fixture Test |
| P0 | `POST` | `/api/rigs/{id}/test-all/stop` | 3.5 Fixture Test |
| P1 | `GET` | `/api/templates` | 3.6 Templates |
| P1 | `GET` | `/api/templates/{id}` | 3.6 Templates |
| P1 | `POST` | `/api/templates` | 3.6 Templates |
| P1 | `POST` | `/api/templates/{id}/apply` | 3.6 Templates |
| P1 | `DELETE` | `/api/templates/{id}` | 3.6 Templates |
| P1 | `POST` | `/api/fixtures/import/gdtf` | 3.7 Import (replace existing stub) |
| P1 | `POST` | `/api/fixtures/import/gdtf-bulk` | 3.7 Import |
| P1 | `POST` | `/api/rigs/import/mvr` | 3.7 Import |
| P1 | `POST` | `/api/rigs/import/console-patch` | 3.7 Import |
| P1 | `GET` | `/api/rigs/{id}/export/json` | 3.7 Export |
| P1 | `GET` | `/api/rigs/{id}/export/mvr` | 3.7 Export |
| P1 | `GET` | `/api/rigs/{id}/export/csv` | 3.7 Export |
| P1 | `GET` | `/api/rigs/{id}/export/pdf` | 3.7 Export |
| P1 | `GET` | `/api/fixtures/channel-templates/{type}` | 3.8 Profile Editor |
| P2 | `POST` | `/api/discovery/rdm/start` | 3.9 RDM |
| P2 | `POST` | `/api/discovery/rdm/stop` | 3.9 RDM |
| P2 | `GET` | `/api/discovery/rdm/devices` | 3.9 RDM |
| P2 | `POST` | `/api/discovery/rdm/import` | 3.9 RDM |
| P2 | `GET` | `/api/discovery/rdm/device/{uid}/identify` | 3.9 RDM |
| P2 | `POST` | `/api/rigs/{id}/scan` | 3.10 QR/NFC |
| P2 | `GET` | `/api/rigs/{id}/labels/pdf` | 3.10 QR/NFC |
| P2 | `GET` | `/api/fixtures/{id}/qr-code` | 3.10 QR/NFC |

### Existing Endpoints to Modify

| Method | Path | Change |
|--------|------|--------|
| `POST` | `/api/fixtures/import/gdtf` | Replace stub (line 238-259 of `fixtures.py`) with full GDTF parser |
| `POST` | `/api/rigs/{id}/fixtures` | Add mode selection validation; return auto-patch suggestion |
| `GET` | `/api/rigs/{id}` | Eager load fixture mode and channel data in response |

---

## 8. Appendix: Files to Create and Modify

### New Backend Files

| File | Feature |
|------|---------|
| `backend/app/services/fixture_library/__init__.py` | 3.1 |
| `backend/app/services/fixture_library/ofl_client.py` | 3.1 |
| `backend/app/services/rig/__init__.py` | 3.3 |
| `backend/app/services/rig/patching_service.py` | 3.3 |
| `backend/app/services/rig/wizard_service.py` | 3.2 |
| `backend/app/services/fixture_test/__init__.py` | 3.5 |
| `backend/app/services/fixture_test/fixture_test_service.py` | 3.5 |
| `backend/app/api/endpoints/fixture_library.py` | 3.1 |
| `backend/app/api/endpoints/wizard.py` | 3.2 |
| `backend/app/api/endpoints/fixture_test.py` | 3.5 |
| `backend/app/api/endpoints/rig_patching.py` | 3.3 |
| `backend/app/schemas/rig.py` | 3.3, 3.4 |
| `backend/alembic/versions/002_fixture_integration_features.py` | All |
| `data/fixtures/bundled/*.json` (200 files) | 3.1 |

### Modified Backend Files

| File | Changes | Feature |
|------|---------|---------|
| `backend/app/models/fixture.py` | Add source, source_id, categories, popularity_score, is_bundled columns | 3.1 |
| `backend/app/models/rig.py` | Add is_address_locked to RigFixture; source_format, source_file to Rig | 3.3, 3.7 |
| `backend/app/schemas/fixture.py` | Add new fields to FixtureBase, FixtureResponse schemas | 3.1 |
| `backend/app/api/endpoints/fixtures.py` | Implement GDTF parser (replace stub at line 238); register library sub-router | 3.1, 3.7 |
| `backend/app/api/endpoints/__init__.py` | Register new routers (fixture_library, wizard, fixture_test, rig_patching) | All |
| `scripts/init_db.py` | Load bundled fixtures from data/fixtures/bundled/ on first run | 3.1 |

### New Frontend Files

| File | Feature |
|------|---------|
| `frontend/src/components/fixtures/FixtureLibrary.tsx` | 3.1 |
| `frontend/src/components/fixtures/FixtureCard.tsx` | 3.1 |
| `frontend/src/components/fixtures/FixtureDetail.tsx` | 3.1 |
| `frontend/src/components/rig/RigBuilder.tsx` | 3.4 |
| `frontend/src/components/rig/StageView2D.tsx` | 3.4 |
| `frontend/src/components/rig/FixturePalette.tsx` | 3.4 |
| `frontend/src/components/rig/PatchTable.tsx` | 3.4 |
| `frontend/src/components/rig/FixtureProperties.tsx` | 3.4 |
| `frontend/src/components/rig/RigEditorToolbar.tsx` | 3.4 |
| `frontend/src/components/rig/FixtureTestPanel.tsx` | 3.5 |
| `frontend/src/components/rig/RigWizard.tsx` | 3.2 |
| `frontend/src/components/rig/wizard/VenueTypeStep.tsx` | 3.2 |
| `frontend/src/components/rig/wizard/StageDimensionsStep.tsx` | 3.2 |
| `frontend/src/components/rig/wizard/PickFixturesStep.tsx` | 3.2 |
| `frontend/src/components/rig/wizard/ReviewPlacementStep.tsx` | 3.2 |
| `frontend/src/stores/rigEditorStore.ts` | 3.4 |

### Modified Frontend Files

| File | Changes | Feature |
|------|---------|---------|
| `frontend/src/App.tsx` | Add routes for /fixtures, /fixtures/:id, /rigs/new/wizard; update /rigs/:id to use RigBuilder | 3.1, 3.2, 3.4 |
| `frontend/src/components/common/Layout.tsx` | Add "Fixtures" to navigation menu items | 3.1 |
| `frontend/src/components/rig/RigList.tsx` | Change "New Rig" button to show wizard/scratch/template/import options | 3.2 |
| `frontend/src/components/rig/RigEditor.tsx` | Add mode selector to fixture add dialog; replace getNextAddress() with API call; add conflict indicators; add Test button per fixture | 3.3, 3.5 |
| `frontend/src/components/rig/RigVisualizer.tsx` | Replace hardcoded channel mapping (lines 36-52) with mode-aware logic that reads channel types from the fixture's mode definition | 3.5 |
| `frontend/src/services/api.ts` | Add all new API methods to fixturesApi and rigsApi | All |
| `frontend/src/types/index.ts` | Add PatchConflict, OFLFixtureResult, WizardData, VenuePreset, RigTemplate types | All |
| `frontend/package.json` | Add @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities dependencies | 3.4 |
