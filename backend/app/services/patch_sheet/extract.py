"""
Text out of a PDF or a photo
============================

Both are optional. Neither a PDF reader nor an OCR engine is a dependency of
this system, and nothing here installs one, calls a network service or costs
money. Each function uses a local library if the machine happens to have it
and otherwise says, in words an operator can act on, what to do instead.

PDF: pypdf (or the older PyPDF2), then pdfminer.six, whichever imports.
Layout-preserving extraction is asked for where the library offers it, because
the table reader needs the gaps between columns.

Photo: an OCR engine is a function from image bytes to text. The default is
pytesseract over a local Tesseract, when both the Python module and the
tesseract program are present. set_ocr_engine swaps in another local engine
without touching the import code.
"""

import io
from typing import Callable, Optional

from app.services.venue_import.model import VenueImportError

OcrEngine = Callable[[bytes], str]

NO_PDF_READER = (
    "PDF files cannot be read on this machine: no PDF reader (pypdf or pdfminer.six) is "
    "installed. Export the patch as CSV or XLSX instead, or copy the table out of the PDF "
    "into a .txt file and import that."
)
NO_PDF_TEXT = (
    "The PDF holds no text, so it is probably a scan. Export the patch as CSV or XLSX, or "
    "import a photo of the page on a machine with local OCR set up."
)
NO_OCR = (
    "Photos cannot be read on this machine: no local OCR engine is set up (pytesseract "
    "with the Tesseract program). Export the patch as CSV or XLSX, or type the table "
    "into a .txt file and import that."
)

_ocr_engine: Optional[OcrEngine] = None


def _pypdf_text(content: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return None
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text(extraction_mode="layout") or "")
        except TypeError:
            # An older release with no layout mode.
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _pdfminer_text(content: bytes) -> Optional[str]:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
    except ImportError:
        return None
    return extract_text(io.BytesIO(content)) or ""


def pdf_reader_available() -> bool:
    for module in ("pypdf", "PyPDF2", "pdfminer.high_level"):
        try:
            __import__(module)
            return True
        except ImportError:
            continue
    return False


def pdf_text(content: bytes) -> str:
    """The text of a PDF. Raises VenueImportError when it cannot be had."""
    text: Optional[str] = None
    for reader in (_pypdf_text, _pdfminer_text):
        try:
            text = reader(content)
        except VenueImportError:
            raise
        except Exception as e:  # a damaged or encrypted file, whatever the library calls it
            raise VenueImportError(f"The PDF could not be read: {e}")
        if text is not None:
            break
    if text is None:
        raise VenueImportError(NO_PDF_READER)
    if not text.strip():
        raise VenueImportError(NO_PDF_TEXT)
    return text


def _tesseract(content: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image

    with Image.open(io.BytesIO(content)) as image:
        # Page segmentation 6: one uniform block of text, which keeps a table's
        # rows as lines. preserve_interword_spaces keeps the gaps between columns.
        return pytesseract.image_to_string(
            image.convert("L"), config="--psm 6 -c preserve_interword_spaces=1"
        )


def _tesseract_available() -> bool:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def set_ocr_engine(engine: Optional[OcrEngine]) -> None:
    """Use `engine` (image bytes -> text) for photos. None goes back to the default."""
    global _ocr_engine
    _ocr_engine = engine


def ocr_available() -> bool:
    return _ocr_engine is not None or _tesseract_available()


def image_text(content: bytes) -> str:
    """The text read off a photo. Raises VenueImportError when no engine is set up."""
    engine = _ocr_engine or (_tesseract if _tesseract_available() else None)
    if engine is None:
        raise VenueImportError(NO_OCR)
    try:
        text = engine(content)
    except VenueImportError:
        raise
    except Exception as e:
        raise VenueImportError(f"The photo could not be read: {e}")
    if not (text or "").strip():
        raise VenueImportError("No text was found in the photo.")
    return text
