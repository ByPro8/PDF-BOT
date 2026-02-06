import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _extract_text(pdf_path: Path, max_pages: int = 1) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])


def _ocr_first_page(pdf_path: Path) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    try:
        img = convert_from_path(str(pdf_path), first_page=1, last_page=1)[0]
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def parse_ziraatkatilim(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=1)

    # Image-only PDFs -> OCR
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    receiver_iban = _find(raw, r"Alici\s*IBAN\s*No\s*:\s*(TR[0-9A-Z\s]{10,})")
    receiver_name = _find(raw, r"Alici\s*Adi\s*:\s*([^\n]+)")
    amount = _find(raw, r"Tutar\s*:\s*([0-9\.,]+)\s*(?:TL|TRY)")
    if amount:
        amount = f"{amount} TL"

    transaction_time = _find(
        raw,
        r"(?:ISLEM TARIHI|IGLEM TARIHI)\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    )
    receipt_no = _find(raw, r"(?:DEKONT NO|DEKONT NO/FI[SŞ] NO)\s*:\s*([0-9/]+)")
    transaction_ref = _find(raw, r"Sorgu\s*Numarasi\s*[:\-]?\s*([0-9]+)")

    tr_status = (
        "completed" if ("FAST" in raw.upper() or "DEKONT" in raw.upper()) else "unknown"
    )

    return {
        "tr_status": tr_status,
        "sender_name": None,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
