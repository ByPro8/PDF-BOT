from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from app.detectors.text_layer import normalize_text


@dataclass
class PDFContext:
    """
    Per-request PDF cache.

    Goal:
    - Read PDF bytes once
    - Build PdfReader once (prefer BytesIO)
    - Extract first-N-pages text once
    - Reuse these for detection + metadata in the same request
    """
    path: Path
    display_name: str = "file.pdf"
    max_pages_text: int = 2

    _pdf_bytes: Optional[bytes] = None
    _reader: Optional[PdfReader] = None
    _reader_attempted: bool = False
    _text_raw: Optional[str] = None
    _text_norm: Optional[str] = None

    @property
    def pdf_bytes(self) -> bytes:
        if self._pdf_bytes is None:
            self._pdf_bytes = self.path.read_bytes()
        return self._pdf_bytes

    @property
    def reader(self) -> Optional[PdfReader]:
        if self._reader_attempted:
            return self._reader

        self._reader_attempted = True

        # Prefer BytesIO so we reuse cached bytes and avoid holding a file handle open.
        try:
            self._reader = PdfReader(io.BytesIO(self.pdf_bytes))
            return self._reader
        except Exception:
            pass

        # Fallback: some edge-case PDFs behave better opened from a path.
        try:
            self._reader = PdfReader(str(self.path))
        except Exception:
            self._reader = None

        return self._reader

    def _extract_text_from_reader(self, max_pages: int) -> str:
        r = self.reader
        if not r:
            return ""

        try:
            parts: list[str] = []
            for page in r.pages[:max_pages]:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception:
            return ""

    @property
    def text_raw(self) -> str:
        if self._text_raw is None:
            self._text_raw = self._extract_text_from_reader(self.max_pages_text)
        return self._text_raw

    @property
    def text_norm(self) -> str:
        if self._text_norm is None:
            self._text_norm = normalize_text(self.text_raw)
        return self._text_norm
