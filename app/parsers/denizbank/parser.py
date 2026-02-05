import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).replace("\u00a0", " ").replace("\u202f", " ")


def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _find_group(raw: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_spaces(m.group(1))


def _iban(raw: str, key: str) -> Optional[str]:
    # key like "IBAN" or "Alıcı IBAN"
    m = re.search(rf"{re.escape(key)}\s+(TR[0-9\s]{{20,}})", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_spaces(m.group(1))


def _money_tl(raw: str, key: str) -> Optional[str]:
    # key like "Tutar" or "Masraf"
    m = re.search(rf"{re.escape(key)}\s+([0-9\.\,]+)\s*TL", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).strip()} TL"


def _detect_tr_status(raw: str) -> str:
    t = (raw or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)

    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t or "onay bekliyor" in t:
        return "pending"
    # Deniz FAST PDFs are "Dekont ..." receipts → treat as completed
    if "dekont" in t:
        return "completed"
    return "unknown"


def parse_denizbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    sender_name = _find_group(raw, r"Adı\s+Soyadı\s+([^\n]+)")
    sender_iban = _iban(raw, "IBAN")

    receiver_iban = _iban(raw, "Alıcı IBAN")
    receiver_name = _find_group(raw, r"Alıcı\s+Adı\s+Soyadı\s+([^\n]+)")

    amount = _money_tl(raw, "Tutar")

    transaction_time = _find_group(raw, r"İşlem\s+Tarihi\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})")

    receipt_no = _find_group(raw, r"Referans\s+Bilgisi\s*:\s*([0-9]{8}\s*-\s*[0-9]{4}\s*-\s*[0-9]+)")
    transaction_ref = _find_group(raw, r"FAST\s+Sorgu\s+Numarası\s*:\s*([0-9]+)")

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "sender_iban": sender_iban,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,          # "Referans Bilgisi : ..."
        "transaction_ref": transaction_ref # "FAST Sorgu Numarası: ..."
    }
