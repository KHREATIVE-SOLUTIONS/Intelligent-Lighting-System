"""
Patch sheets: reading them
==========================

A patch sheet comes as a CSV, a spreadsheet, text out of a PDF or text off a
photo. Each reader is checked for the thing a wrong answer would put on stage:
an address read from the wrong column, a universe.channel that lost its zeros
in a spreadsheet, a file taken for something it is not.

No spreadsheet, PDF or OCR package is installed with this system, so the
workbooks here are built with zipfile, and the tests that need a real PDF
reader or a real Tesseract skip themselves and say so.
"""

import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from app.services.patch_sheet import extract
from app.services.patch_sheet.reader import detect_kind, read_patch_sheet
from app.services.patch_sheet.text_table import read_text_table
from app.services.patch_sheet.xlsx import read_xlsx
from app.services.venue_import import VenueImportError
from app.services.venue_import.csv_patch import parse_patch_rows


def by_name(parsed) -> dict:
    return {f.name: f for f in parsed.fixtures}


# ---------------------------------------------------------------------------
# A workbook, written the way a spreadsheet program writes one
# ---------------------------------------------------------------------------

def _column(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def workbook(rows, sheet_name="Patch", inline=False, extra_sheets=(), doctype="") -> bytes:
    """An .xlsx holding `rows`. A str cell is a string, an int or float a number,
    None an absent cell (the row is written sparse, as a real file is)."""
    strings = []

    def sheet_xml(sheet_rows) -> str:
        out = [f'<?xml version="1.0" encoding="UTF-8"?>{doctype}'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
        for r, row in enumerate(sheet_rows, start=1):
            out.append(f'<row r="{r}">')
            for c, value in enumerate(row):
                if value is None or value == "":
                    continue
                ref = f"{_column(c)}{r}"
                if isinstance(value, str) and inline:
                    out.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
                elif isinstance(value, str):
                    if value not in strings:
                        strings.append(value)
                    out.append(f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>')
                else:
                    out.append(f'<c r="{ref}"><v>{value!r}</v></c>')
            out.append("</row>")
        out.append("</sheetData></worksheet>")
        return "".join(out)

    sheets = [(sheet_name, rows)] + list(extra_sheets)
    bodies = [sheet_xml(sheet_rows) for _, sheet_rows in sheets]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("xl/workbook.xml", (
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, (name, _) in enumerate(sheets, start=1)
            ) + "</sheets></workbook>"
        ))
        zf.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            ) + "</Relationships>"
        ))
        for i, body in enumerate(bodies, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", body)
        zf.writestr("xl/sharedStrings.xml", (
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings) + "</sst>"
        ))
    return buffer.getvalue()


SHEET_ROWS = [
    ["Festival patch - example"],
    [],
    ["FID", "Label", "Fixture Type", "Footprint", "Univ", "DMX", "Position"],
    [101, "Spot 1", "Acme Beam 300", 16, 1, 1, "US Truss"],
    [102, "Spot 2", "Acme Beam 300", 16, 1, 17, "US Truss"],
    [201, "Wash 1", "Acme Wash 7", 14, 2, 1, None],
]


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def test_rows_keep_a_header_that_starts_with_a_hash():
    # As CSV text a line starting with '#' is a comment. As rows it is the header.
    parsed = parse_patch_rows([
        ["#", "Name", "Type", "Patch"],
        ["1", "Spot 1", "Acme Beam", "1.1"],
        ["2", "Spot 2", "Acme Beam", "1.17"],
    ])
    assert [(f.fixture_number, f.name, f.dmx_address) for f in parsed.fixtures] == [
        (1, "Spot 1", 1), (2, "Spot 2", 17),
    ]


def test_rows_without_a_header_are_refused():
    with pytest.raises(VenueImportError, match="No header row"):
        parse_patch_rows([["just", "some"], ["words", "here"]])


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inline", [False, True])
def test_xlsx_reads_strings_numbers_and_gaps(inline):
    sheet = read_xlsx(workbook(SHEET_ROWS, inline=inline))
    assert sheet.name == "Patch"
    assert sheet.rows[2] == ["FID", "Label", "Fixture Type", "Footprint", "Univ", "DMX", "Position"]
    assert sheet.rows[3] == ["101", "Spot 1", "Acme Beam 300", "16", "1", "1", "US Truss"]
    # The empty cell stays a cell: nothing moved left into it.
    assert sheet.rows[5] == ["201", "Wash 1", "Acme Wash 7", "14", "2", "1", ""]
    assert (3, 0) in sheet.numeric and (3, 1) not in sheet.numeric


def test_xlsx_patch_is_read_like_a_csv():
    parsed = read_patch_sheet("festival.xlsx", workbook(SHEET_ROWS))
    assert parsed.format == "xlsx" and parsed.source_file == "festival.xlsx"
    rows = by_name(parsed)
    assert set(rows) == {"Spot 1", "Spot 2", "Wash 1"}
    # The Universe column holds no 0, so it counts from 1: its 1 is universe 0.
    assert (rows["Spot 2"].universe, rows["Spot 2"].dmx_address) == (0, 17)
    assert (rows["Wash 1"].universe, rows["Wash 1"].dmx_address) == (1, 1)
    assert rows["Spot 1"].channel_count == 16 and rows["Spot 1"].fixture_number == 101
    assert rows["Spot 1"].position_label == "US Truss" and rows["Spot 1"].position is None
    assert rows["Wash 1"].position_label == ""
    assert any("worksheet 'Patch'" in a for a in parsed.assumptions)


def test_xlsx_picks_the_worksheet_that_holds_the_patch():
    notes = [["Notes"], ["Load in 08:00"]]
    content = workbook(notes, sheet_name="Notes", extra_sheets=[("Patch", SHEET_ROWS)])
    assert read_xlsx(content).name == "Patch"
    assert len(read_patch_sheet("show.xlsx", content).fixtures) == 3


def test_xlsx_whole_number_cells_are_not_decimals():
    # 613 arrives as "613", and a float that happens to be whole as a whole number.
    sheet = read_xlsx(workbook([["Name", "Type", "Patch"], ["A", "Par", 613], ["B", "Par", 101.0]]))
    assert [row[2] for row in sheet.rows[1:]] == ["613", "101"]
    parsed = read_patch_sheet("p.xlsx", workbook([["Name", "Type", "Patch"], ["A", "Par", 613]]))
    assert (parsed.fixtures[0].universe, parsed.fixtures[0].dmx_address) == (1, 101)


def test_xlsx_decimal_number_addresses_are_called_out():
    # 2.100 typed into a number cell is stored as 2.1. It cannot be told from 2.1.
    content = workbook([
        ["Name", "Type", "Patch"],
        ["Numeric", "Par", 2.1],
        ["Typed as text", "Par", "2.100"],
        ["Three digits", "Par", 2.101],
    ])
    parsed = read_patch_sheet("patch.xlsx", content)
    rows = by_name(parsed)
    assert (rows["Numeric"].universe, rows["Numeric"].dmx_address) == (1, 1)
    assert (rows["Typed as text"].universe, rows["Typed as text"].dmx_address) == (1, 100)
    assert (rows["Three digits"].universe, rows["Three digits"].dmx_address) == (1, 101)
    warnings = [w for w in parsed.warnings if "decimal numbers" in w]
    assert len(warnings) == 1
    assert warnings[0].startswith("1 address(es)") and "(2.1)" in warnings[0]


def test_xlsx_with_entity_declarations_is_refused():
    content = workbook(SHEET_ROWS, doctype='<!DOCTYPE x [<!ENTITY a "aaaa">]>')
    with pytest.raises(VenueImportError, match="entity declarations"):
        read_patch_sheet("patch.xlsx", content)


def test_xlsx_without_a_patch_table_is_refused():
    with pytest.raises(VenueImportError, match="No header row"):
        read_patch_sheet("notes.xlsx", workbook([["Notes"], ["Load in 08:00"]]))


# ---------------------------------------------------------------------------
# Text tables
# ---------------------------------------------------------------------------

ALIGNED = """\
Example Festival - Main Stage Patch                    Page 1 of 1

FID    Label        Fixture Type      Footprint    Patch     Position
101    Spot 1       Acme Beam 300     16           1.1       US Truss
102    Spot 2       Acme Beam 300     16           1.17      US Truss
201    Wash 1       Acme Wash 7       14           2.1
202    Wash 2       Acme Wash 7                    2.15      DS Truss

Printed by the console
"""


def test_aligned_text_is_read_by_column_position():
    table = read_text_table(ALIGNED)
    assert table.layout == "aligned"
    assert table.rows[0] == ["FID", "Label", "Fixture Type", "Footprint", "Patch", "Position"]
    assert table.rows[1] == ["101", "Spot 1", "Acme Beam 300", "16", "1.1", "US Truss"]
    # A missing last cell and a missing middle cell both stay where they are.
    assert table.rows[3] == ["201", "Wash 1", "Acme Wash 7", "14", "2.1", ""]
    assert table.rows[4] == ["202", "Wash 2", "Acme Wash 7", "", "2.15", "DS Truss"]
    assert table.skipped == []


def test_aligned_text_patch_keeps_the_address_under_its_own_heading():
    parsed = read_patch_sheet("patch.txt", ALIGNED.encode())
    assert parsed.format == "text"
    rows = by_name(parsed)
    assert len(rows) == 4
    # The empty Footprint cell did not pull 2.15 into the Footprint column.
    assert rows["Wash 2"].channel_count is None
    assert (rows["Wash 2"].universe, rows["Wash 2"].dmx_address) == (1, 15)
    assert rows["Wash 2"].position_label == "DS Truss"
    assert (rows["Spot 2"].universe, rows["Spot 2"].dmx_address) == (0, 17)


def test_a_line_that_cannot_be_lined_up_is_left_out_and_reported():
    text = (
        "FID    Label        Fixture Type      Patch\n"
        "101    Spot 1       Acme Beam 300     1.1\n"
        "102    Spot 2       Acme Beam     300 with a very long name   1.17   extra   more\n"
        "103    Spot 3       Acme Beam 300     1.33\n"
    )
    parsed = read_patch_sheet("patch.txt", text.encode())
    assert [f.name for f in parsed.fixtures] == ["Spot 1", "Spot 3"]
    assert any("could not be lined up" in w and "102" in w for w in parsed.warnings)


def test_ruled_text_is_read_as_a_table():
    text = (
        "| # | Name | Type | Patch |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | Spot 1 | Acme Beam | 1.1 |\n"
        "| 2 | Spot 2 |  | 1.17 |\n"
    )
    table = read_text_table(text)
    assert table.layout == "ruled"
    assert table.rows == [
        ["#", "Name", "Type", "Patch"], ["1", "Spot 1", "Acme Beam", "1.1"], ["2", "Spot 2", "", "1.17"],
    ]
    parsed = read_patch_sheet("patch.md", text.encode())
    assert [(f.fixture_number, f.dmx_address) for f in parsed.fixtures] == [(1, 1), (2, 17)]


def test_text_with_no_table_is_refused():
    with pytest.raises(VenueImportError, match="No patch table"):
        read_patch_sheet("notes.txt", b"nothing here\nlooks like a patch\n")


# ---------------------------------------------------------------------------
# What a file is
# ---------------------------------------------------------------------------

def test_kinds_are_told_apart_by_their_contents():
    assert detect_kind("patch.bin", workbook(SHEET_ROWS)) == "xlsx"
    assert detect_kind("patch", b"%PDF-1.7\n...") == "pdf"
    assert detect_kind("photo", b"\x89PNG\r\n\x1a\n....") == "image"
    assert detect_kind("photo.JPG", b"\xff\xd8\xff\xe0....") == "image"
    assert detect_kind("patch.csv", b"Name,Type,Patch\n") == "csv"
    assert detect_kind("patch.txt", b"Name  Type  Patch\n") == "text"


@pytest.mark.parametrize("name, content, says", [
    ("empty.csv", b"  \n", "empty"),
    ("rig.xml", b"<MA><Layers/></MA>", "venue importer"),
    ("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1....", "Save the sheet"),
    ("patch.xlsx", b"not a workbook", "not a spreadsheet"),
    ("patch.pdf", b"not a pdf", "not a PDF"),
])
def test_files_that_are_not_patch_sheets_are_refused_with_a_reason(name, content, says):
    with pytest.raises(VenueImportError, match=says):
        read_patch_sheet(name, content)


def test_an_mvr_is_sent_to_the_venue_importer():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("GeneralSceneDescription.xml", "<GeneralSceneDescription/>")
    with pytest.raises(VenueImportError, match="venue importer"):
        read_patch_sheet("rig.mvr", buffer.getvalue())


def test_a_plain_csv_patch_sheet_reads_as_before():
    parsed = read_patch_sheet("patch.csv", b"FID;Label;Type;Patch\n1;Spot 1;Acme Beam;2/101\n")
    assert parsed.format == "csv"
    assert (parsed.fixtures[0].universe, parsed.fixtures[0].dmx_address) == (1, 101)


# ---------------------------------------------------------------------------
# PDF and photo: optional, local, never required
# ---------------------------------------------------------------------------

def test_pdf_without_a_reader_says_what_to_do_instead():
    if extract.pdf_reader_available():
        pytest.skip("a PDF reader is installed here, so the 'none installed' answer cannot be seen")
    with pytest.raises(VenueImportError, match="no PDF reader"):
        read_patch_sheet("patch.pdf", b"%PDF-1.4\n%%EOF\n")


def test_pdf_text_goes_through_the_table_reader(monkeypatch):
    # The PDF library is stood in for; what is tested is everything after it.
    monkeypatch.setattr("app.services.patch_sheet.reader.pdf_text", lambda content: ALIGNED)
    parsed = read_patch_sheet("patch.pdf", b"%PDF-1.4\n%%EOF\n")
    assert parsed.format == "pdf" and len(parsed.fixtures) == 4
    assert (by_name(parsed)["Wash 2"].universe, by_name(parsed)["Wash 2"].dmx_address) == (1, 15)


def _one_page_pdf(lines) -> bytes:
    """A minimal one-page PDF in a monospaced font, one text line per row."""
    stream = ["BT", "/F1 9 Tf", "11 TL", "40 760 Td"]
    for line in lines:
        text = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.append(f"({text}) Tj T*")
    stream.append("ET")
    body = "\n".join(stream).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n"
    out += str(xref).encode() + b"\n%%EOF\n"
    return bytes(out)


def test_a_real_pdf_is_read_when_a_reader_is_installed():
    if not extract.pdf_reader_available():
        pytest.skip(
            "no PDF reader (pypdf or pdfminer.six) is installed in this environment, and this "
            "system does not require one; PDF text is covered through the table reader instead"
        )
    parsed = read_patch_sheet("patch.pdf", _one_page_pdf(ALIGNED.splitlines()))
    assert parsed.format == "pdf"
    assert {f.name for f in parsed.fixtures} >= {"Spot 1", "Spot 2"}


def test_photo_without_ocr_says_what_to_do_instead():
    if extract.ocr_available():
        pytest.skip("a local OCR engine is set up here, so the 'none set up' answer cannot be seen")
    with pytest.raises(VenueImportError, match="no local OCR engine"):
        read_patch_sheet("sheet.jpg", b"\xff\xd8\xff\xe0 not really a photo")


def test_a_local_ocr_engine_can_be_plugged_in():
    seen = []

    def engine(content: bytes) -> str:
        seen.append(content)
        return ALIGNED

    extract.set_ocr_engine(engine)
    try:
        assert extract.ocr_available()
        parsed = read_patch_sheet("sheet.png", b"\x89PNG\r\n\x1a\n pixels")
    finally:
        extract.set_ocr_engine(None)
    assert seen == [b"\x89PNG\r\n\x1a\n pixels"]
    assert parsed.format == "image" and len(parsed.fixtures) == 4
    assert any("OCR" in w and "Check every address" in w for w in parsed.warnings)


def test_tesseract_reads_a_photo_when_it_is_installed():
    pytesseract = pytest.importorskip(
        "pytesseract", reason="pytesseract is not installed; local OCR is optional"
    )
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("pytesseract is installed but the Tesseract program is not; local OCR is optional")
    from PIL import Image, ImageDraw

    image = Image.new("L", (900, 160), 255)
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(["Name      Type      Patch", "Spot      Beam      1.17"]):
        draw.text((20, 20 + 50 * row), line, fill=0)
    buffer = io.BytesIO()
    image.resize((2700, 480)).save(buffer, format="PNG")
    assert extract.image_text(buffer.getvalue()).strip()
