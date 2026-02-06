import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip() or None


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", "", s).upper()
    m = re.search(r"(TR[0-9]{24})", s)
    return m.group(1) if m else None


def _extract_text(pdf_path: Path, max_pages: int = 1) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    except Exception:
        return ""


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


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def parse_albaraka(pdf_path: Path) -> Dict:
    # Albaraka PDFs we saw are image-based => OCR is the reliable source
    raw = _extract_text(pdf_path, max_pages=1)
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    # Sender (OCR sometimes corrupts "HESAP" like HESA&P, so match loosely)
    sender_name = _find(
        raw,
        r"SAYIN\s+HES.{0,8}\s*SAHIBI\s*:\s*([^\n]+)",
    )

    # Receiver
    receiver_name = _find(raw, r"Alici\s+Adi\s*:\s*([^\n]+)")
    receiver_iban = _iban_compact(
        _find(raw, r"Alici\s+Hesap/IBA[Nn]\s+No\s*:\s*(TR[0-9\s]{20,})")
    )

    # Amount
    amount = _find(raw, r"Tutar\s*:\s*([0-9\.\,]+)")
    if amount:
        amount = f"{amount} TL"

    # Transaction time (this one is clean in OCR)
    transaction_time = _find(
        raw,
        r"ISLEM\s+TARIHI\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    )

    # Receipt number (OCR may read FİŞ as FIs/FIS etc)
    receipt_no = _find(
        raw,
        r"DEKONT\s+NO/F\w*\s+NO\s*:\s*([0-9]+/[0-9]+)",
    )

    # FAST query number
    transaction_ref = _find(raw, r"FAST\s+sorgu\s+numaraniz\s+([0-9]+)")

    t = raw.upper()
    tr_status = (
        "completed"
        if (
            "PARA CIKISI GERCEKLESM" in t
            or "PARA GIKIS1 GERCEKLESM" in t
            or "DEKONT" in t
        )
        else "unknown"
    )

    return {
        "tr_status": tr_status,
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
