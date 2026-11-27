# Export back to the console

Status: **built, and tested only by reading the files back with this system's
own importers.** No file here has been loaded into a grandMA2 desk, grandMA2
onPC, MA3D or Capture. Treat the first import on real software as a test, in a
copy of the show. The frontend changes were not typechecked or run in the
session that wrote them (no `node_modules` in the worktree): run `npm test` and
`npm run build` in `frontend/` before relying on them.

## What it is for

A rig is patched, placed and grouped here (imported, laid out on a template,
tapped into place). This writes that rig out again so the house desk and a
visualiser agree with it:

| File | For | Carries |
| --- | --- | --- |
| grandMA2 fixture layer XML | the desk's Import | patch, 3D position, rotation, one layer per group |
| grandMA2 command-line script | reading, then pasting | patch, labels, groups by fixture ID |
| MVR | MA3D, Capture, any MVR reader | patch, 3D position, rotation, groups, GDTF files where held |

## Where the data comes from

One function reads the rig, and all three writers read only what it returns
(`backend/app/services/console_export/model.py`, `ExportRig`):

- **A database rig** is read from its `RigFixture` rows at the moment of the
  request: `universe`, `dmx_address`, `position_x/y/z`, `rotation_x/y/z`,
  `group_name`, `tags`, `fixture_number`. These are the rows the layout view
  edits, the 3D view draws and `rig_loader` gives the engine. Nothing is cached,
  so a fixture moved in the layout view is moved in the next download.
- **A demo preset** is read from its `FixtureSpec` list: the list
  `/api/demo/rig` serves to the 3D view and `create_venue_rig` gives the engine.

Tests hold this: the export is compared with `create_venue_rig`, with
`/api/demo/rig`, and with the database rows after an edit.

## Endpoints

All are `GET`, read-only, and send nothing to any device.

| Database rig | Demo preset |
| --- | --- |
| `/api/rigs/{id}/export/ma2-xml` | `/api/venues/presets/{name}/export/ma2-xml` |
| `/api/rigs/{id}/export/ma2-macro` | `/api/venues/presets/{name}/export/ma2-macro` |
| `/api/rigs/{id}/export/mvr` | `/api/venues/presets/{name}/export/mvr` |
| `/api/rigs/{id}/export/console-summary` | `/api/venues/presets/{name}/export/console-summary` |

`console-summary` is JSON: fixture and group counts, how many positions are
unplaced or unconfirmed, which GDTF files are in the MVR and which are only
named, and the notes below in words.

Query parameters:

- `mark_names=true` (all three files): append ` (position unconfirmed)` to the
  name of each fixture whose position nobody has confirmed.
- `first_group=N` (script): the group number the first group is stored at.
  Default 1.
- `include=all|patch|groups|focus` (script): which part to write. `focus` is
  the moving heads' Position presets, database rigs only: see
  [FOCUS_PRESETS.md](FOCUS_PRESETS.md).
- `first_preset=N` (script): the first focus target is stored at
  `Preset 2.N`. Default 1.
- `notes=false` (script): leave out the `#` note lines, for a file that is
  commands only.

In the app: **Rigs > Import / Export > Export** has an *Export to a console*
section, and the 3D view's header has an **Export** button for the rig on
screen (a database rig or the demo preset).

## Conventions, and the one assumption

This system: metres from the centre of the floor, X across, Y up, -Z upstage;
universes counted from 0; addresses 1 to 512.

Both grandMA2 and MVR are right-handed with Z up. The files are written with
**+Y upstage**, which is the same assumption the importers make
(`backend/app/services/fixture_library/stage_axes.py`):

    file x =  stage x
    file y = -stage z
    file z =  stage y      (height)

If the desk's stage is drawn with +Y toward the audience, the rig arrives
turned front to back. Check one fixture you can recognise before trusting the
rest.

Universes are written counted from 1 (this system's universe 0 is the desk's
universe 1). The XML and the MVR carry an absolute address: universe 2,
address 1 is 513.

## grandMA2 fixture layer XML

The layout the desk's own layer export uses, and the layout this system's
importer reads:

```xml
<MA xmlns="http://schemas.malighting.de/grandma2/xml/MA" major_vers="3" minor_vers="9" stream_vers="0">
  <Layer index="1" name="Dance Floor Spots">
    <Fixture index="0" name="Design Spot A1" fixture_id="1">
      <FixtureType name="2 ILS Demo Spot 16ch"><No>2</No></FixtureType>
      <SubFixture index="0" react_to_grandmaster="true" color="ffffff">
        <Patch><Address>1</Address></Patch>
        <AbsolutePosition>
          <Location x="-6" y="7.5" z="6.5"/>
          <Rotation x="0" y="0" z="0"/>
          <Scaling x="1" y="1" z="1"/>
        </AbsolutePosition>
      </SubFixture>
    </Fixture>
```

- One `Layer` per group the patch sheet shows (`group_name`). Fixtures with no
  group go in a layer called `Ungrouped`.
- `fixture_id` is the rig's fixture number.
- `Location` is metres, `Rotation` degrees.
- A fixture the rig never placed has no `AbsolutePosition` at all.
- The `Info datetime` is a fixed value, not the time of export, so the same rig
  is the same file.

### What the operator must still do on the desk

1. **The fixture types must already be in the show.** The file says where
   fixtures go, not what they are: it holds no channel definitions. Each type
   is referred to by a number and a name (`2 ILS Demo Spot 16ch`); the numbers
   start at 2 and are listed in a comment at the top of the file. Import the
   real fixture types into the show first, and make the numbers in the file
   match the show's (edit the file, or renumber in the show). A type whose
   footprint differs from the one patched here will overlap its neighbours:
   the script's notes list each type's channel count.
2. **Put the file where the desk imports from** (the `importexport` folder of
   the show drive or USB stick) and import it into the fixture layers from the
   setup's layer list. MA's documentation gives the command-line form
   `Import "file name" At Layers` from `EditSetup/Layers`
   (see the links below). Check it against your software version.
3. **Check the fixture IDs after import.** At least one report (Capture's
   forum) describes an XML layer import that kept the fixtures and lost their
   numbers. The script's patch lines address fixtures by ID, so they need the
   IDs to be right.
4. **Check one position and one rotation in the desk's 3D or stage view**
   before trusting the rest (see the axis assumption above).
5. **Fixtures turned about more than one axis.** One angle about one axis is
   exact. With two or three non-zero angles the result depends on the order
   the desk applies them in, which this system does not know. The MVR does not
   have this problem (it carries a matrix); the XML does.

## grandMA2 command-line script

Plain text, one command a line. Lines starting with `#` are notes for the
reader; they are not commands and should not be pasted (or use `notes=false`).

```
Assign Fixture 23 At DMX 1.353
Label Fixture 23 "Mezzanine Spot 1"
ClearSelection
Fixture 1 Thru 22
Store Group 1
Label Group 1 "Dance Floor Spots"
```

- `Assign Fixture N At DMX u.a` patches an existing fixture and **replaces any
  patch it had** (this is the desk's live-patch form).
- Every group in the rig is stored, in the order the patch first names it:
  the `group_name` shown on the patch sheet, then any further groups (a
  database rig's `group:<name>` tags, a preset's engine groups such as
  `floor_spots`). Fixtures are selected by ID, in patch order.
- If any position is unconfirmed, one more group, `Position unconfirmed`,
  holds those fixtures, so they can be found on the desk.

What the operator must still do:

1. **The fixtures must already exist under these IDs**, on types with the
   right footprint. The script creates no fixtures: this system could not
   confirm a command-line way to add them outside the setup dialogs, so it
   does not pretend to. Add them by importing the XML above or by hand.
2. **Choose where the groups go.** `Store Group N` onto a group that already
   exists makes the desk ask what to do, or replaces it, depending on the
   desk's settings. Use `first_group` to start in an empty range of the pool.
3. **Read it first.** `Assign ... At DMX` and `Label` are taken from MA's
   keyword pages; `Store Group N`, the bare `Fixture ...` selection line and
   `ClearSelection` are standard grandMA2 commands that were not individually
   re-checked against the manual in this session. Nothing was run on a desk.
4. The script carries **no fixture positions**. Those travel in the XML or the MVR.

For a database rig with moving heads, the script ends with one **focus
Position preset** per target (DJ booth, dance floor, audience, stage front,
straight down, and any custom points), with guessed positions marked in the
notes. How they are worked out and what to check on the desk:
[FOCUS_PRESETS.md](FOCUS_PRESETS.md).

## MVR

A ZIP holding `GeneralSceneDescription.xml` (MVR 1.6) and GDTF files.

```xml
<GeneralSceneDescription verMajor="1" verMinor="6" provider="Intelligent Lighting System" ...>
  <UserData><Data provider="Intelligent Lighting System" ver="1"> ... </Data></UserData>
  <Scene>
    <AUXData><Class uuid="..." name="Dance Floor Spots"/></AUXData>
    <Layers>
      <Layer name="Dance Floor Spots" uuid="...">
        <ChildList>
          <Fixture name="Design Spot A1" uuid="...">
            <Matrix>{1.000000,0.000000,0.000000}{0.000000,1.000000,0.000000}{0.000000,0.000000,1.000000}{-6000.000000,7500.000000,6500.000000}</Matrix>
            <Classing>...</Classing>
            <GDTFSpec>ILS Demo@Demo Spot 16ch.gdtf</GDTFSpec>
            <GDTFMode>Standard 16ch</GDTFMode>
            <Addresses><Address break="0">1</Address></Addresses>
            <FixtureID>1</FixtureID>
            <FixtureIDNumeric>1</FixtureIDNumeric>
```

- `Matrix` is MVR's 4x3 form: the fixture's three axes, then its origin in
  **millimetres**. Rotation is exact for any combination of angles: it is the
  matrix `Ry(rotation_y) * Rx(rotation_x) * Rz(rotation_z)` the 3D view turns
  the fixture by, moved into Z-up axes.
- Every fixture is a direct child of its layer, so its matrix is its place in
  the room.
- `Address` is absolute, on break 0. A fixture has one address here; a second
  DMX break is not modelled.
- A fixture the rig never placed has no `Matrix`.
- UUIDs are derived from the rig's id and the fixture's id (UUID version 5),
  so a fixture keeps its UUID across exports, renames and repatches, and a
  visualiser that matches on UUID updates the fixture instead of duplicating
  it.

### Groups in an MVR

A fixture can be in one layer and one class. The group the patch sheet shows
is written as both the fixture's `Layer` and its `Classing`. Groups overlap
(one spot is in `floor_spots`, `spots_chord_a` and `spots_left`), and MVR has
no element for that short of nesting, which allows one parent. So **every**
group, with its members, is also written in the `UserData` block:

```xml
<FixtureGroups>
  <FixtureGroup name="floor_spots">
    <Member fixture="<uuid>" fixtureId="1"/>
```

MA3D and Capture will not read that block. To get the overlapping groups onto
a desk, use the grandMA2 script.

### GDTF files

The fixture library stores a GDTF's file name, not the file. So the only GDTF
files this system can put in an archive are the ones it can write itself: its
three demo profiles (`ILS Demo@Demo Spot 16ch.gdtf`,
`ILS Demo@Demo Compact Spot 12ch.gdtf`, `ILS Demo@Demo Wash 14ch.gdtf`).

Every other fixture type is **named and not embedded**: `GDTFSpec` holds the
file name the library recorded, or `Maker@Model.gdtf` built from the profile
when it recorded none. The scene carries a comment listing them, and
`console-summary` lists them under `gdtf_not_embedded`. A visualiser will show
those fixtures as unknown until it is given a profile for each: add the real
GDTF files to the archive (it is a ZIP) under exactly those names, or assign
the types in the visualiser.

For the demo presets this means the bars, pars and strobes
(`ILS Demo@Demo LED 12ch.gdtf`, `ILS Demo@Demo Strobe 4ch.gdtf`) have no file.

## Fixtures whose position is unconfirmed

A fixture tagged `position_unconfirmed` (laid out on a template and not yet
tapped in place: see `FLASH_AND_TAP.md`) **is exported, at the position the rig
has for it**, and marked. The choice made here is to leave the fixture's name
alone by default, because a name is what the desk and the importer match on:

| File | Mark |
| --- | --- |
| MVR | listed under `UserData/Data/ConsoleExport/UnconfirmedPositions` by UUID and fixture ID |
| grandMA2 XML | an XML comment before the fixture (a desk ignores it) |
| grandMA2 script | a group `Position unconfirmed` holding those fixtures, and a note |
| all three, with `mark_names=true` | ` (position unconfirmed)` appended to the name |

Only the script's group and `mark_names=true` are visible on a desk or in a
visualiser. If the file is going to someone who will trust the positions, use
`mark_names=true`.

Importing this system's own MVR again reads the `UnconfirmedPositions` list
back, so a guess is still a guess afterwards (it returns with
`position_source:template` and `position_unconfirmed`). The grandMA2 XML has
no such read-back: a guessed position imported from it arrives looking
confirmed.

## Fixture numbers

A console needs each fixture ID once. `fixture_number` in a database rig may be
missing or repeated. The first fixture (in universe, address order) to ask for
a number keeps it; any fixture with no number, or one already taken, is given
the next number above every number that was kept. The summary says how many
were renumbered. A demo preset is numbered as its patch sheet is: 1 upward in
universe, address order.

## Fixtures that are switched off

A fixture switched off in the rig (an unmatched type, or an address clash found
at import) is still exported: the desk needs to know what sits on those
channels. The summary counts them. An address clash here is an address clash on
the desk too.

## Demo presets

A preset fixture is patched on this system's generic demo profile for its type
(16, 14, 12 or 4 channels), not on the real fixture it stands in for. The
export therefore names the demo profile as the type, so the footprint on the
desk matches the addresses. The real fixture is the *Source Fixture* column of
the preset's patch sheet (`docs/venues/`). The LIV preset's disclaimer is
written at the top of every file: it is an approximate recreation, not that
venue's patch.

## Deterministic output

The same rig gives the same bytes, every time and on every machine: fixtures
are written in universe, address, id order; UUIDs are derived, not random; no
clock is read (the XML's `Info datetime` and the ZIP's file dates are fixed);
the ZIP is stored uncompressed with no host information. Tests compare two
exports byte for byte.

## Tests

- `backend/tests/unit/test_console_export.py`: the LIV demo rig (131 fixtures,
  4 universes) exported to MVR and to grandMA2 XML and read back with
  `read_venue_file`: same count, universes, addresses, names, numbers and
  groups, positions within 1 mm. Every other preset the same. A small made-up
  rig covers what LIV lacks: fixtures turned about one and about three axes, an
  unplaced fixture, an unconfirmed one, missing and repeated numbers, names
  with quotes and ampersands. Script syntax, group order, determinism. The
  unconfirmed fixture is still unconfirmed after MVR export and import, and
  the same list under another program's provider name marks nothing.
- `backend/tests/integration/test_api_console_export.py`: the routes, against a
  rig imported into the database; an edit showing in the next export; the
  export matching `/api/demo/rig`; a rig's MVR posted back to
  `/api/import/venue` previews its one guessed position as not confirmed.
- `frontend/src/__tests__/consoleExport.test.ts`: paths and file names.

## What is left

- **Nothing has been loaded into grandMA2, MA3D or Capture.** That is the next
  step, and the import command, the type numbering and the axis direction are
  the three things to check first.
- **No grandMA2 group XML.** Groups go to the desk through the script. The
  desk's group export layout was not verified, so no file imitates it.
- **GDTF files are not kept by the library**, so real fixture types are named
  in the MVR and not embedded. Storing the uploaded `.gdtf` beside the library
  row would fix this.
- **The demo bars, pars and strobes have no GDTF.**
- **Overlapping groups in MVR** are in `UserData` only, which other software
  does not read. This system's importer does not read them back either: after
  export and import a fixture has its patch-sheet group and loses the rest.
- **The grandMA2 XML does not carry the unconfirmed mark back in.**
- **No trusses, room shell or scenery** are exported: fixtures only.
- **One address per fixture.** Multi-break fixtures and multipatch are not
  written.
- **grandMA3** is not targeted. MVR is the route into it.

## Sources for the grandMA2 commands

- Assign / live patch: <https://help.malighting.com/grandMA2/en/help/key_patch_livepatch.html>,
  <https://help.malighting.com/grandMA2/en/help/key_keyword_assign.html>
- Label: <https://help.malighting.com/grandMA2/en/help/key_keyword_label.html>
- Groups: <https://help.malighting.com/grandMA2/en/help/key_groups_create_groups.html>
- Export and import: <https://help.malighting.com/grandMA2/en/help/key_export_and_import.html>
- Layer import (`Import "file" At Layers`): <https://help.malighting.com/utility/en/help/ma_vectorworks_spotlight_plugin/key_vw_spotlight_plugin_import.html>
