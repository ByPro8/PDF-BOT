from pathlib import Path
from typing import Optional

from app.detectors.rules import (
    apply_variant,
    detect_bank_by_ocr_domains,
    detect_bank_by_text_domains,
    detect_deniz_by_text_name,
)
from app.detectors.text_layer import extract_text, normalize_text


def detect_bank_variant(
    pdf_path: Path,
    use_ocr_fallback: bool = True,
    *,
    text_raw: Optional[str] = None,
    text_norm: Optional[str] = None,
    max_pages: int = 2,
) -> dict:
    """Detect bank + variant.

    Rules:
    - Strict bank detection by WEBSITE domain in the PDF text layer.
    - If NO domain found: DenizBank can fall back to legal-name/text markers.
    - If still no bank: OCR first page ONLY, and ONLY match allowlisted banks.

    New:
    - You may pass text_raw/text_norm to avoid reading the PDF again.
    """
    if text_norm is None:
        if text_raw is None:
            text_raw = extract_text(pdf_path, max_pages=max_pages)
        text_norm = normalize_text(text_raw)

    det = detect_bank_by_text_domains(text_norm)

    # Deniz fallback (name-based) only if no domain
    if not det:
        det = detect_deniz_by_text_name(text_norm)

    # OCR only if still nothing (and only for allowlist)
    if not det and use_ocr_fallback:
        det = detect_bank_by_ocr_domains(pdf_path)

    if not det:
        return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": "none"}

    base_key = det["key"]
    parser_key, variant = apply_variant(base_key, text_norm)

    det["key"] = parser_key
    det["variant"] = variant
    return det
