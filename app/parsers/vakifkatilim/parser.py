import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    raw = "\n".join(parts)
    return raw.replace("\u00a0", " ").replace("\u202f", " ")


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _clean(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def _find_time(raw: str) -> Optional[str]:
    # "İşlem Tarihi : 29/01/2026 17:20:12"
    m = re.search(
        r"İşlem\s*Tarihi\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?",
        raw,
        flags=re.I,
    )
    if not m:
        return None
    dd, mm, yyyy, hh, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _find_sender(raw: str) -> Optional[str]:
    m = re.search(r"Gönderen\s*Kişi\s*:\s*([^\n]+)", raw, flags=re.I)
    return _clean(m.group(1)) if m else None


def _find_receiver(raw: str) -> Optional[str]:
    m = re.search(r"Gönderilen\s*Kişi\s*:\s*([^\n]+)", raw, flags=re.I)
    return _clean(m.group(1)) if m else None


def _find_iban(raw: str) -> Optional[str]:
    m = re.search(r"Alıcı\s*IBAN\s*:\s*(TR\s*(?:\d\s*){24})\b", raw, flags=re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).upper().strip()


def _find_amount(raw: str) -> Optional[str]:
    # "Tutar 3.050,00 TL"
    m = re.search(
        r"Tutar\s+([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)\s*(TL|TRY)\b",
        raw,
        flags=re.I,
    )
    if m:
        val = m.group(1).strip()
        cur = m.group(2).upper()
        if "," not in val:
            val += ",00"
        return f"{val} {cur}"
    return None


def _find_receipt_no(raw: str) -> Optional[str]:
    # "Seri-Sıra No : AA-00022652"
    m = re.search(r"Seri-?Sıra\s*No\s*:\s*([A-Z0-9-]+)", raw, flags=re.I)
    return m.group(1).strip() if m else None


def _find_transaction_ref(raw: str) -> Optional[str]:
    # "İşlem Referans No : -B-2026012915"
    m = re.search(r"İşlem\s*Referans\s*No\s*:\s*([A-Z0-9-]+)", raw, flags=re.I)
    return m.group(1).strip() if m else None


def _detect_status(raw: str) -> str:
    t = _norm(raw)

    if re.search(r"\biptal\b|\biade\b|\bbasarisiz\b|\breddedildi\b|\bcancel", t):
        return "canceled"
    if re.search(r"\bbeklemede\b|\bisleniyor\b|\bpending\b|\bprocessing\b", t):
        return "pending"

    # This template doesn't explicitly say "successful/completed"
    return "unknown-manually"


def parse_vakifkatilim(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, 2)

    return {
        "tr_status": _detect_status(raw),
        "sender_name": _find_sender(raw),
        "receiver_name": _find_receiver(raw),
        "receiver_iban": _find_iban(raw),
        "amount": _find_amount(raw),
        "transaction_time": _find_time(raw),
        "receipt_no": _find_receipt_no(raw),
        "transaction_ref": _find_transaction_ref(raw),
    }
