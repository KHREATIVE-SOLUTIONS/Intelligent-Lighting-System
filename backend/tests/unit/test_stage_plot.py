"""
Stage plot underlay: reading the file and the calibration maths
================================================================

services/stage_plot.py. The rotated example (ROTATED) is the same one the
frontend's helper is tested with (frontend/src/__tests__/stagePlot.test.ts),
so the plan's live preview and the server cannot drift apart.
docs/STAGE_PLOT.md.
"""

import math
import struct

import pytest

from app.services.stage_plot import (
    JPEG, PDF, PNG, WEBP, Calibration, StagePlotError, image_size, normalise_rotation, sniff, to_room, transform,
)


def png(width: int, height: int) -> bytes:
    """The first bytes of a PNG of this size: enough to sniff and to read the size."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00" * 4


def jpeg(width: int, height: int) -> bytes:
    """A JPEG's markers up to its start of frame: an APP0 first, as a camera writes."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def webp_vp8x(width: int, height: int) -> bytes:
    body = b"VP8X" + struct.pack("<I", 10) + b"\x00" * 4 + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


# Two points 200 px apart along the image's top edge are 4 m apart: 0.02 m a pixel.
# The origin is 200 px below the middle of them, and the plot is turned a quarter clockwise.
ROTATED = Calibration(point_a=(100.0, 100.0), point_b=(300.0, 100.0), distance_m=4.0,
                      origin=(200.0, 300.0), rotation_deg=90.0, opacity=0.4)
ROTATED_MATRIX = [0.0, 0.02, -0.02, 0.0, 6.0, -4.0]


class TestSniffing:

    def test_each_kind_is_known_by_its_first_bytes(self):
        assert sniff(png(10, 10)) == PNG
        assert sniff(jpeg(10, 10)) == JPEG
        assert sniff(webp_vp8x(10, 10)) == WEBP
        assert sniff(b"%PDF-1.7\n...") == PDF

    def test_a_name_or_a_text_file_is_not_an_image(self):
        assert sniff(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
        assert sniff(b"GIF89a....") is None
        assert sniff(b"RIFF\x00\x00\x00\x00WAVE") is None
        assert sniff(b"") is None


class TestImageSize:

    def test_png_jpeg_and_webp_sizes_are_read_from_the_header(self):
        assert image_size(png(1920, 1080), PNG) == (1920, 1080)
        assert image_size(jpeg(4032, 3024), JPEG) == (4032, 3024)
        assert image_size(webp_vp8x(800, 600), WEBP) == (800, 600)

    def test_a_cut_off_header_is_refused_in_a_sentence(self):
        with pytest.raises(StagePlotError, match="damaged"):
            image_size(b"\x89PNG\r\n\x1a\n", PNG)
        with pytest.raises(StagePlotError):
            image_size(b"\xff\xd8\xff\xe0", JPEG)


class TestTransform:

    def test_the_rotated_example(self):
        answer = transform(ROTATED)
        assert answer["scale_m_per_px"] == pytest.approx(0.02)
        assert answer["rotation_deg"] == 90.0
        assert answer["matrix"] == pytest.approx(ROTATED_MATRIX, abs=1e-12)
        assert (answer["offset_x"], answer["offset_z"]) == pytest.approx((6.0, -4.0))
        # The origin is the middle of the stage; point B, right of it on the image, is downstage of it on the plan.
        assert to_room(answer["matrix"], 200, 300) == pytest.approx((0.0, 0.0), abs=1e-12)
        assert to_room(answer["matrix"], 300, 100) == pytest.approx((4.0, 2.0))

    def test_unturned_the_image_down_is_downstage_and_the_distance_holds(self):
        flat = transform(Calibration((0, 0), (30, 40), 10.0, (0, 0)))
        assert flat["scale_m_per_px"] == pytest.approx(0.2)
        assert to_room(flat["matrix"], 0, 100) == pytest.approx((0.0, 20.0))

    @pytest.mark.parametrize("degrees", [0, 30, -45, 135, 271])
    def test_any_turn_keeps_the_measured_distance_and_the_origin(self, degrees):
        cal = Calibration((12.5, 40.0), (212.5, 190.0), 7.5, (60.0, 70.0), degrees)
        m = transform(cal)["matrix"]
        a, b = to_room(m, 12.5, 40.0), to_room(m, 212.5, 190.0)
        assert math.dist(a, b) == pytest.approx(7.5)
        assert to_room(m, 60.0, 70.0) == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_rotation_is_given_back_within_a_half_turn_either_way(self):
        assert normalise_rotation(270) == -90
        assert normalise_rotation(-180) == 180
        assert normalise_rotation(540) == 180
        assert transform(Calibration((0, 0), (10, 0), 1.0, (0, 0), 450))["rotation_deg"] == 90

    @pytest.mark.parametrize("cal, words", [
        (Calibration((5, 5), (5, 5), 2.0, (0, 0)), "on top of each other"),
        (Calibration((0, 0), (10, 0), 0.0, (0, 0)), "distance"),
        (Calibration((0, 0), (10, 0), -3.0, (0, 0)), "distance"),
        (Calibration((0, 0), (10, 0), 5000.0, (0, 0)), "distance"),
        (Calibration((0, 0), (10, 0), 2.0, (0, 0), opacity=1.5), "opacity"),
        (Calibration((0, 0), (10, 0), float("inf"), (0, 0)), "finite"),
        (Calibration((0, float("nan")), (10, 0), 2.0, (0, 0)), "finite"),
    ])
    def test_a_calibration_that_cannot_be_used_is_refused_in_a_sentence(self, cal, words):
        with pytest.raises(StagePlotError, match=words):
            transform(cal)
