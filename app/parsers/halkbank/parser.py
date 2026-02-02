import re
from pathlib import Path
from typing import Dict
from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages=2) -> str:
    reader = PdfReader(str(pdf_path))
    out = []
    for p in reader.pages[:max_pages]:
        out.append(p.extract_text() or "")
    return "\n".join(out)


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307","")
    tr = str.maketrans({"ı":"i","ö":"o","ü":"u","ş":"s","ğ":"g","ç":"c"})
    s = s.translate(tr)
    s = re.sub(r"\s+"," ",s)
    return s.strip()


def _find_iban(raw):
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, re.I)
    if not m:
        return None
    return re.sub(r"\s+"," ",m.group(0)).upper().strip()


def _find_amount(raw):
    m = re.search(r"([0-9\.,]+)\s*TL", raw, re.I)
    return f"{m.group(1)} TL" if m else None


def _find_time(raw):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4}).*?(\d{2}:\d{2})", raw)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)} {m.group(4)}"


def _find_receipt(raw):
    m = re.search(r"\b(\d{10,})\b", raw)
    return m.group(1) if m else None


def _detect_status_halk(raw):
    t = _norm(raw)

    if re.search(r"\biptal\b|\bbasarisiz\b|\breddedildi\b", t):
        return "canceled"

    if re.search(r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b", t):
        return "pending"

    # Halkbank sample has no completion text
    return "unknown — PDF does not state status; check manually"


def parse_halkbank(pdf_path: Path) -> Dict:

    raw = _extract_text(pdf_path)

    return {
        "tr_status": _detect_status_halk(raw),
        "sender_name": None,
        "receiver_name": None,
        "receiver_iban": _find_iban(raw),
        "amount": _find_amount(raw),
        "transaction_time": _find_time(raw),
        "receipt_no": _find_receipt(raw),
        "transaction_ref": None,
    }
