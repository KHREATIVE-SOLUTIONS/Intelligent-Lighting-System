"""
Fixture label sheet, drawn with Pillow
======================================

A US Letter PDF at 300 dpi laid out for Avery 5160 / 8160 address labels
(3 columns x 10 rows, 2 5/8" x 1"), one label per patched fixture: a QR code
the scanner reads back (qr_scanning.py, /rigs/{id}/scan) beside the fixture's
name, number, universe.address and group.

No reportlab: Pillow writes the PDF. The pages are kept 1-bit so Pillow does
not JPEG-compress them (it would for greyscale or colour pages), which would
blur the QR's module edges.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.services.qr_encode import encode, to_image

DPI = 300
PAGE_W, PAGE_H = int(8.5 * DPI), 11 * DPI  # 2550 x 3300

# Avery 5160: labels 2.625" x 1", 3 x 10, top margin 0.5", side margin
# 0.1875", columns 2.75" apart (0.125" gutter), rows 1" apart.
COLS, ROWS = 3, 10
PER_PAGE = COLS * ROWS
LABEL_W, LABEL_H = 2.625 * DPI, 1.0 * DPI
LEFT, TOP = 0.1875 * DPI, 0.5 * DPI
PITCH_X, PITCH_Y = 2.75 * DPI, 1.0 * DPI

PADDING = 18          # px inside each label edge (0.06")
MIN_MODULE_PX = 4     # below this (0.34 mm a module) phones struggle; refuse instead
QUIET = 4             # modules of light margin around each code


@dataclass
class Label:
    name: str
    fixture_number: Optional[int]
    universe: int
    dmx_address: int
    group: Optional[str]
    qr_data: str


def label_box(slot: int) -> Tuple[int, int, int, int]:
    """Pixel box (left, top, right, bottom) of label `slot` (0 to 29) on a page."""
    col, row = slot % COLS, slot // COLS
    x0 = LEFT + col * PITCH_X
    y0 = TOP + row * PITCH_Y
    return round(x0), round(y0), round(x0 + LABEL_W), round(y0 + LABEL_H)


def _font(size: int):
    return ImageFont.load_default(size=size)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: float) -> str:
    """`text`, cut with an ellipsis where it would run past `width` pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _qr(data: str, side: int) -> Image.Image:
    matrix = encode(data, "M")
    modules = len(matrix) + 2 * QUIET
    module_px = side // modules
    if module_px < MIN_MODULE_PX:
        raise ValueError(f"QR payload too long for a 1 inch label ({len(data)} bytes)")
    return to_image(matrix, module_px, QUIET)


def _draw_label(page: Image.Image, draw: ImageDraw.ImageDraw, slot: int, label: Label) -> None:
    x0, y0, x1, y1 = label_box(slot)
    qr = _qr(label.qr_data, (y1 - y0) - 2 * PADDING)
    qy = y0 + ((y1 - y0) - qr.height) // 2
    page.paste(qr.convert("L"), (x0 + PADDING, qy))

    tx = x0 + PADDING + qr.width + 12
    width = x1 - PADDING - tx
    name_font, body_font = _font(40), _font(30)
    number = f"#{label.fixture_number}" if label.fixture_number is not None else "#–"
    lines = [
        (_fit(draw, label.name, name_font, width), name_font),
        (_fit(draw, f"{number}    DMX {label.universe}.{label.dmx_address}", body_font, width), body_font),
        (_fit(draw, label.group or "", body_font, width), body_font),
    ]
    y = y0 + PADDING + 8
    for text, font in lines:
        if text:
            draw.text((tx, y), text, fill=0, font=font)
        y += font.size + 22


def render_pages(rig_name: str, labels: Sequence[Label]) -> List[Image.Image]:
    """The sheet's pages as 1-bit images, 300 dpi US Letter."""
    chunks = [labels[i:i + PER_PAGE] for i in range(0, len(labels), PER_PAGE)] or [[]]
    pages = []
    header_font = _font(36)
    for index, chunk in enumerate(chunks):
        page = Image.new("L", (PAGE_W, PAGE_H), 255)
        draw = ImageDraw.Draw(page)
        header = f"{rig_name}: fixture labels    page {index + 1} of {len(chunks)}"
        draw.text((round(LEFT) + PADDING, 60), _fit(draw, header, header_font, PAGE_W - 2 * LEFT),
                  fill=0, font=header_font)
        if not labels:
            draw.text((round(LEFT) + PADDING, 400), "No fixtures are patched in this rig.",
                      fill=0, font=_font(60))
        for slot, label in enumerate(chunk):
            _draw_label(page, draw, slot, label)
        # Threshold, not dither: crisp text and exact QR modules.
        pages.append(page.point(lambda p: 255 if p >= 128 else 0, mode="1"))
    return pages


def to_pdf(pages: Sequence[Image.Image]) -> bytes:
    buf = io.BytesIO()
    first, rest = pages[0], list(pages[1:])
    first.save(buf, "PDF", save_all=True, append_images=rest, resolution=float(DPI))
    return buf.getvalue()


def label_sheet_pdf(rig_name: str, labels: Sequence[Label]) -> bytes:
    """The printable label sheet for `labels`, as PDF bytes."""
    return to_pdf(render_pages(rig_name, labels))
