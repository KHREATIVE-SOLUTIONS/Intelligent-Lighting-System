"""
XML from an upload
==================

Every importer reads XML that came from outside. None of the formats read here
(GDTF, MVR, grandMA exports) declares entities, so a document that does is
refused rather than expanded.
"""

import re
from typing import Union
from xml.etree import ElementTree

# Generous for a patch or a fixture description, small enough to refuse a
# file that is not one.
MAX_XML_BYTES = 64 * 1024 * 1024

_ENTITY_DECLARATION = re.compile(rb"<!ENTITY", re.IGNORECASE)


def parse_xml(content: Union[bytes, str], what: str = "XML") -> ElementTree.Element:
    """Parse uploaded XML. Raises ValueError with a message an operator can read."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if len(raw) > MAX_XML_BYTES:
        raise ValueError(f"Invalid {what}: larger than {MAX_XML_BYTES // (1024 * 1024)} MB")
    if _ENTITY_DECLARATION.search(raw):
        raise ValueError(f"Invalid {what}: entity declarations are not accepted")
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError as e:
        raise ValueError(f"Invalid {what}: {e}")


def local_name(tag) -> str:
    """An element's tag without its XML namespace."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
