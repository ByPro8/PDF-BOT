import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


# -------------------------------------------------
# CORE HELPERS
# -------------------------------------------------
def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    # normalize common weird spaces
    return "\n".join(parts).replace("\u00a0", " ").replace("\u202f", " ")


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


def _norm_tr(s: str) -> str:
    t = (s or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    return re.sub(r"\s+", " ", t.translate(tr)).strip()


# -------------------------------------------------
# FIELD FINDERS
# -------------------------------------------------
def _find_receipt_no(raw: str) -> Optional[str]:
    """
    Your logs show receipt_no == SORGU NO (FAST docs),
    but for HESAPTAN HESABA HAVALE docs there is NO SORGU NO, so we use Sıra No (5-5/6 digits).
    Must handle pypdf re-ordering where it may appear as: 00167-240000Sıra No
    """
    # Prefer FAST query number (this matches your other QNB outputs)
    m = re.search(r"SORGU\s*NO\s*:\s*([0-9]{6,})", raw, flags=re.IGNORECASE)
    if m:
        return _clean(m.group(1))

    # Now extract "Sıra No 00167-240000" BUT tolerate:
    # - weird dash chars
    # - spaces/newlines
    # - number appearing BEFORE the label (pypdf reorder)
    dash = r"[--–—]"

    # A) number BEFORE label: 00167-240000Sıra No (or spaced)
    m2 = re.search(
        rf"\b(\d{{5}})\s*{dash}\s*(\d{{5,6}})\s*(?:S[ıiİI]ra\s*No)\b",
        raw,
        flags=re.IGNORECASE,
    )
    if m2:
        return f"{m2.group(1)}-{re.sub(r'\\s+', '', m2.group(2))}"

    # B) label BEFORE number: Sıra No 00167-240000
    m3 = re.search(
        rf"(?:S[ıiİI]ra\s*No)\s*[:\-]?\s*(\d{{5}})\s*{dash}\s*(\d{{5,6}})\b",
        raw,
        flags=re.IGNORECASE,
    )
    if m3:
        return f"{m3.group(1)}-{re.sub(r'\\s+', '', m3.group(2))}"

    return None


def _find_fis_no(raw: str) -> Optional[str]:
    m = re.search(r"Fiş\s*No\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _find_datetime(raw: str) -> Optional[str]:
    d = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", raw)
    t = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", raw)
    if not d or not t:
        return None
    dd, mm, yyyy = d.group(1), d.group(2), d.group(3)
    hh, mi = t.group(1), t.group(2)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _find_amount(raw: str) -> Optional[str]:
    # Prefer EFT TUTARI line (FAST)
    m = re.search(r"EFT\s+TUTARI\s*:\s*([0-9\.,]+)\s*TL", raw, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    # Fallback: table "B TL 11,630.00" etc
    m2 = re.search(r"\bTL\s+([0-9\.,]+)", raw, flags=re.IGNORECASE)
    if m2:
        return f"{m2.group(1).strip()} TL"

    return None


def _detect_tr_status(raw: str) -> str:
    t = _norm_tr(raw)
    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t:
        return "pending"
    if "hareketler gerceklestirilmis" in t or "dekont" in t:
        return "completed"
    return "unknown"


# -------------------------------------------------
# NAMES / IBAN (FAST vs HAVALE)
# -------------------------------------------------
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
    # HAVALEYİ ALAN HESAP NO:... IBAN: TR97 0011 ...
    m = re.search(r"IBAN\s*:\s*(TR(?:\s*\d){24})", raw, flags=re.IGNORECASE)
    return _iban_compact(m.group(1)) if m else None


def _find_receiver_fast(raw: str) -> Optional[str]:
    m = re.search(
        r"ALICI\s+ÜNVANI\s*:\s*([^\n]+?)\s+ALICI\s+IBAN", raw, flags=re.IGNORECASE
    )
    return _clean(m.group(1)) if m else None


def _find_receiver_iban_fast(raw: str) -> Optional[str]:
    m = re.search(r"ALICI\s+IBAN\s*:\s*(TR(?:\s*\d){24})", raw, flags=re.IGNORECASE)
    return _iban_compact(m.group(1)) if m else None


def _find_sender_fast(raw: str) -> Optional[str]:
    # Prefer "GÖNDEREN: ... AÇIKLAMA:"
    m = re.search(r"GÖNDEREN\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE)
    if m:
        v = m.group(1)
        v = re.split(r"\bAÇIKLAMA\b", v, flags=re.IGNORECASE)[0]
        return _clean(v)

    # Fallback: "MÜŞTERİ ÜNVANI: X IBAN : TR..."
    m2 = re.search(r"MÜŞTERİ\s+ÜNVANI\s*:\s*([^\n]+?)\s+IBAN", raw, flags=re.IGNORECASE)
    return _clean(m2.group(1)) if m2 else None


# -------------------------------------------------
# MAIN PARSER
# -------------------------------------------------
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

    if is_fast or (not receiver_name and not receiver_iban):
        sender_name = sender_name or _find_sender_fast(raw)
        receiver_name = receiver_name or _find_receiver_fast(raw)
        receiver_iban = receiver_iban or _find_receiver_iban_fast(raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": _find_amount(raw),
        "transaction_time": _find_datetime(raw),
        "receipt_no": _find_receipt_no(raw),
        "transaction_ref": _find_fis_no(raw),
    }
