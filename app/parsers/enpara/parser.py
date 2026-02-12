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


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _find_group(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_spaces(m.group(1))


def _iban_clean(s: str) -> str:
    return _clean_spaces(s)


def _find_any_iban(raw: str) -> Optional[str]:
    # Finds first IBAN-ish TR.. anywhere (with or without spaces)
    m = re.search(r"\bTR(?:\s*\d){24,}\b", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _iban_clean(m.group(0))


def _find_sender_name(raw: str) -> Optional[str]:
    # "Sayın NAME SURNAME"
    m = re.search(r"Sayın\s+([^\n]+)", raw, flags=re.IGNORECASE)
    if m:
        name = _clean_spaces(m.group(1))
        name = name.split("*")[0].strip()
        return name or None

    # fallback: "MÜŞTERİ ÜNVANI:"
    return _find_group(raw, r"MÜŞTERİ\s+ÜNVANI\s*:\s*([^:\n]+?)\s+IBAN")


def _find_sender_iban(raw: str) -> Optional[str]:
    # FAST format
    m = re.search(
        r"MÜŞTERİ\s+ÜNVANI\s*:\s*.*?\s+IBAN\s*:\s*(TR[0-9\s]{24,})",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return _iban_clean(m.group(1))

    # Older/table extraction often scrambles spacing; just take first IBAN in doc
    return _find_any_iban(raw)


def _find_receiver_name(raw: str) -> Optional[str]:
    # FAST format: "ALICI ÜNVANI: X  ALICI IBAN:"
    m = re.search(
        r"ALICI\s+ÜNVANI\s*:\s*([^\n]+?)\s+ALICI\s+IBAN", raw, flags=re.IGNORECASE
    )
    if m:
        return _clean_spaces(m.group(1)) or None

    # HAVALE format: "HAVALEYİ ALAN MUSTERİ UNVANI: X"
    m = re.search(
        r"HAVALEYİ\s+ALAN\s+MUSTERI\s+UNVANI\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE
    )
    if m:
        return _clean_spaces(m.group(1)) or None

    return None


def _find_receiver_iban(raw: str) -> Optional[str]:
    # FAST format
    m = re.search(r"ALICI\s+IBAN\s*:\s*(TR[0-9\s]{24,})", raw, flags=re.IGNORECASE)
    if m:
        return _iban_clean(m.group(1))

    # HAVALE format (often: "... IBAN: TR95 0015 ...")
    m = re.search(
        r"HAVALEYİ\s+ALAN.*?\bIBAN\s*:\s*(TR[0-9\s]{24,})",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        return _iban_clean(m.group(1))

    return None


def _find_amount(raw: str) -> Optional[str]:
    # Prefer "EFT TUTARI : X TL"
    m = re.search(r"EFT\s+TUTARI\s*:\s*([0-9\.\,]+)\s*TL", raw, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    # HAVALE table line sometimes extracts like: "... TLB 8,326.00TR03..."
    m = re.search(r"\bTL\s*B?\s*([0-9][0-9\.\,]+)\b", raw, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    # Last-resort: line that ends with "TL <amount>" (older behavior)
    m = re.search(r"\bTL\s+([0-9\.\,]+)\s*$", raw, flags=re.IGNORECASE | re.MULTILINE)
    if m:
        return f"{m.group(1).strip()} TL"

    return None


def _find_query_no(raw: str) -> Optional[str]:
    # FAST "SORGU NO"
    m = re.search(r"SORGU\s+NO\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"sorgu\s+no\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _find_fis_no(raw: str) -> Optional[str]:
    # "Fiş No 2026...." or extracted as "Sıra No Fiş No 2026...."
    m = re.search(r"Fiş\s+No\s+([0-9]+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"Sıra\s+No\s+Fiş\s+No\s+([0-9]+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _find_sira_no(raw: str) -> Optional[str]:
    # "Sıra No 03663-03663-xxxx"
    m = re.search(
        r"Sıra\s+No\s+([0-9]{4,}(?:-[0-9]{2,}){1,})", raw, flags=re.IGNORECASE
    )
    if m:
        return _clean_spaces(m.group(1))
    return None


def _find_transaction_time(raw: str) -> Optional[str]:
    m = re.search(
        r"İşlem\s+tarihi\s+ve\s+saati\s+(\d{2}\.\d{2}\.\d{4})(?:\s+(\d{2}:\d{2}))?",
        raw,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    date = m.group(1)
    tm = m.group(2)

    if not tm:
        t2 = re.search(r"\b(\d{2}:\d{2})\b", raw)
        tm = t2.group(1) if t2 else None

    return f"{date} {tm}" if tm else date


def _detect_tr_status(raw: str) -> str:
    t = _norm(raw)
    if re.search(r"\biptal\b|\biptal edildi\b", t):
        return "canceled"
    if re.search(r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b", t):
        return "pending"
    if "dekont" in t:
        return "completed"
    return "unknown"


def _find_transaction_ref(raw: str) -> Optional[str]:
    # FAST: SORGU NO, otherwise use Fiş No for HAVALE docs
    q = _find_query_no(raw)
    if q:
        return q
    f = _find_fis_no(raw)
    if f:
        return f
    return None


def parse_enpara(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": _find_sender_name(raw),
        "sender_iban": _find_sender_iban(raw),
        "receiver_name": _find_receiver_name(raw),
        "receiver_iban": _find_receiver_iban(raw),
        "amount": _find_amount(raw),
        "transaction_time": _find_transaction_time(raw),
        "sira_no": _find_sira_no(raw),
        "fis_no": _find_fis_no(raw),
        "transaction_ref": _find_transaction_ref(raw),
    }
