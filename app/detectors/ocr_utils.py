from pathlib import Path


def ocr_first_page_text(pdf_path: Path) -> str:
    """OCR the first page ONLY (slow path)."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
        if not images:
            return ""
        return pytesseract.image_to_string(images[0]) or ""
    except Exception:
        return ""
