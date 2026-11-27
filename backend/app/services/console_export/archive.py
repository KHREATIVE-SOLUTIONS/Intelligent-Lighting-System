"""A ZIP that is the same bytes on every machine and on every run."""

import io
import zipfile
from typing import Sequence, Tuple

# Any fixed date does. A ZIP cannot hold one before 1980.
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def deterministic_zip(members: Sequence[Tuple[str, bytes]]) -> bytes:
    """The members, stored uncompressed in the order given, with fixed dates.

    Nothing of the machine or the moment goes in: no clock, no host system, no
    file permissions. Two calls with the same members return the same bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            zf.writestr(info, data)
    return buffer.getvalue()
