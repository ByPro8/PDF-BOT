import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s2 = re.sub(r"\s+", "", s).upper()
    m = re.search(r"(TR[0-9]{24})", s2)
    return m.group(1) if m else None


def _find_receipt_no(raw: str) -> Optional[str]:
    """
    receipt_no for your bot should be "Sıra No" (stable in all QNB dekonts).
    Example: "Sıra No 00093-164893" :contentReference[oaicite:2]{index=2}
    Fallback: "SORGU NO: 1385006596" :contentReference[oaicite:3]{index=3}
    """
    # Primary: Sıra No
    m = re.search(r"Sıra\s+No\s+([0-9]{3,}-[0-9]{3,})", raw, flags=re.IGNORECASE)
    if m:
        return _clean(m.group(1))

    # Fallback: SORGU NO
    m2 = re.search(r"SORGU\s+NO\s*:\s*([0-9]{6,})", raw, flags=re.IGNORECASE)
    if m2:
        return _clean(m2.group(1))

    return None


def _find_fis_no(raw: str) -> Optional[str]:
    # Fiş No : 202602096061444 :contentReference[oaicite:4]{index=4}
    m = re.search(r"Fiş\s+No\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _find_datetime(raw: str) -> Optional[str]:
    d = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", raw)
    t = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", raw)
    if not d or not t:
        return None
    dd, mm, yyyy = d.group(1), d.group(2), d.group(3)
    hh, mi = t.group(1), t.group(2)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _find_sender_fast(raw: str) -> Optional[str]:
    m = re.search(r"(?:^|\n)\s*GÖNDEREN\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE)
    if not m:
        return None
    v = m.group(1)
    v = re.split(r"\bAÇIKLAMA\b\s*:", v, maxsplit=1, flags=re.IGNORECASE)[0]
    return _clean(v)


def _find_receiver_fast(raw: str) -> Optional[str]:
    m = re.search(
        r"ALICI\s+ÜNVANI:\s*([^\n]+?)\s+ALICI\s+IBAN\s*:",
        raw,
        flags=re.IGNORECASE,
    )
    return _clean(m.group(1)) if m else None


def _find_receiver_iban_fast(raw: str) -> Optional[str]:
    # ALICI IBAN: TR....
    m = re.search(r"ALICI\s+IBAN\s*:\s*(TR(?:\s*\d){24})", raw, flags=re.IGNORECASE)
    if m:
        return _iban_compact(m.group(1))

    # Sometimes extracted without spaces
    m2 = re.search(r"ALICI\s+IBAN\s*:\s*(TR[0-9]{24})", raw, flags=re.IGNORECASE)
    return _iban_compact(m2.group(1)) if m2 else None


def _find_sender_havale(raw: str) -> Optional[str]:
    m = re.search(
        r"HAVALEY[İI]\s+G[ÖO]NDEREN\s+HESAP\s+UNVANI\s*:\s*([^\n]+)",
        raw,
        flags=re.IGNORECASE,
    )
    return _clean(m.group(1)) if m else None


def _find_receiver_havale(raw: str) -> Optional[str]:
    m = re.search(
        r"HAVALEY[İI]\s+ALAN\s+MUSTERI\s+UNVANI\s*:\s*([^\n]+)",
        raw,
        flags=re.IGNORECASE,
    )
    return _clean(m.group(1)) if m else None


def _find_receiver_iban_havale(raw: str) -> Optional[str]:
    m = re.search(r"IBAN\s*:\s*(TR(?:\s*\d){24})", raw, flags=re.IGNORECASE)
    return _iban_compact(m.group(1)) if m else None


def _find_amount(raw: str) -> Optional[str]:
    # Prefer EFT TUTARI
    m = re.search(r"EFT\s+TUTARI\s*:\s*([0-9\.,]+)\s*TL", raw, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    # Fallback: first TL amount in table
    m2 = re.search(r"\bTL\s+([0-9\.,]+)", raw, flags=re.IGNORECASE)
    if m2:
        return f"{m2.group(1).strip()} TL"

    return None


def _detect_tr_status(raw: str) -> str:
    t = (raw or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t:
        return "pending"
    if "hareketler gerceklestirilmis" in t or "dekont" in t:
        return "completed"
    return "unknown"


def parse_qnb(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    is_havale = bool(re.search(r"HESAPTAN\s+HESABA\s+HAVALE", raw, flags=re.IGNORECASE))
    is_fast = bool(re.search(r"GIDEN\s+FAST\s+EFT", raw, flags=re.IGNORECASE))

    sender_name = None
    receiver_name = None
    receiver_iban = None

    if is_havale:
        sender_name = _find_sender_havale(raw)
        receiver_name = _find_receiver_havale(raw)
        receiver_iban = _find_receiver_iban_havale(raw)

    if is_fast or (not sender_name and not receiver_name):
        sender_name = sender_name or _find_sender_fast(raw)
        receiver_name = receiver_name or _find_receiver_fast(raw)
        receiver_iban = receiver_iban or _find_receiver_iban_fast(raw)

    amount = _find_amount(raw)
    transaction_time = _find_datetime(raw)
    receipt_no = _find_receipt_no(raw)
    transaction_ref = _find_fis_no(raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
