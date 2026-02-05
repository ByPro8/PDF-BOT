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
    # normalize PDF weird spaces
    return raw.replace("\u00a0", " ").replace("\u202f", " ")


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_WS = r"[\s\u00A0\u202F]+"


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _find_all_account_owners(raw: str) -> list[str]:
    # IMPORTANT: "Hesap Sahibi:" is often MID-LINE (after "Müşteri Numarası:...")
    # So DO NOT anchor to ^ or \n.
    pat = rf"Hesap{_WS}+Sahibi\s*:\s*([^\n]+)"
    vals = re.findall(pat, raw, flags=re.I)
    out: list[str] = []
    for v in vals:
        v = _clean(v)
        if v:
            out.append(v)
    return out


def _find_sender(raw: str) -> Optional[str]:
    owners = _find_all_account_owners(raw)
    return owners[0] if owners else None


def _find_receiver_name(raw: str) -> Optional[str]:
    # Interbank: "Alacaklı Adı:..."
    m = re.search(rf"Alacakl[ıi]{_WS}+Ad[ıi]\s*:\s*([^\n]+)", raw, flags=re.I)
    if m:
        return _clean(m.group(1))

    # Internal: receiver is the 2nd "Hesap Sahibi"
    owners = _find_all_account_owners(raw)
    if len(owners) >= 2:
        return owners[1]
    return None


def _find_receiver_iban(raw: str) -> Optional[str]:
    # Interbank: "Alacaklı Hesap:TR..."
    m = re.search(
        rf"Alacakl[ıi]{_WS}+Hesap\s*:\s*(TR\s*(?:\d\s*){{24}})\b",
        raw,
        flags=re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).upper().strip()

    # Internal: 2nd IBAN is receiver
    ibans = re.findall(r"\bTR\s*(?:\d\s*){24}\b", raw, flags=re.I)
    if len(ibans) >= 2:
        return re.sub(r"\s+", " ", ibans[1]).upper().strip()
    if ibans:
        return re.sub(r"\s+", " ", ibans[0]).upper().strip()
    return None


def _find_amount(raw: str) -> Optional[str]:
    m = re.search(
        r"Hesaptan\s+toplam\s+TL\.?\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)(?:,-)?",
        raw,
        flags=re.I,
    )
    if m:
        val = m.group(1).strip()
        if "," not in val:
            val += ",00"
        return f"{val} TL"

    m2 = re.search(
        r"\bTL\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)(?:-)?\b",
        raw,
        flags=re.I,
    )
    if m2:
        val = m2.group(1).strip()
        if "," not in val:
            val += ",00"
        return f"{val} TL"

    return None


def _find_time(raw: str) -> Optional[str]:
    m = re.search(
        r"Tarih-Saat\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2})[.:](\d{2})",
        raw,
        flags=re.I,
    )
    if not m:
        return None
    dd, mm, yyyy, hh, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _find_receipt_no(raw: str) -> Optional[str]:
    m = re.search(r"İşlem\s+No\s*:\s*([0-9]{5,})", raw, flags=re.I)
    return m.group(1) if m else None


def _find_transaction_ref(raw: str) -> Optional[str]:
    # ONLY if FAST No exists (interbank). Internal receipts don't have it.
    m = re.search(r"FAST\s+No\s*:\s*([0-9]{6,})", raw, flags=re.I)
    return m.group(1) if m else None


def _detect_status(raw: str) -> str:
    t = _norm(raw)

    if re.search(r"\biptal\b|\biade\b|\bbasarisiz\b|\breddedildi\b|\bcancel", t):
        return "canceled"

    if re.search(
        r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b|\bpending\b|\bprocessing\b", t
    ):
        return "pending"

    # TEB includes this -> treat as completed
    if (
        "elektronik olarak onaylanmıştır".casefold().replace("\u0307", "") in t
        or "elektronik olarak onaylanmis" in t
    ):
        return "completed"

    return "unknown-manually"


def parse_teb(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, 2)

    return {
        "tr_status": _detect_status(raw),
        "sender_name": _find_sender(raw),
        "receiver_name": _find_receiver_name(raw),
        "receiver_iban": _find_receiver_iban(raw),
        "amount": _find_amount(raw),
        "transaction_time": _find_time(raw),
        "receipt_no": _find_receipt_no(raw),
        "transaction_ref": _find_transaction_ref(raw),
    }
