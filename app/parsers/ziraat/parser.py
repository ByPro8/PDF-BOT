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
    # normalize weird spaces that frequently break regex
    return (
        raw.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2009", " ")
        .replace("\ufeff", "")
    )


def _strip_invisibles(s: str) -> str:
    # bidi marks + zero-width chars
    return re.sub(
        r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff\u200b-\u200d]", "", s or ""
    )


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = _collapse_ws(s)
    return s or None


def _first(pattern: str, text: str, flags: int = re.I | re.M) -> Optional[str]:
    m = re.search(pattern, text or "", flags)
    if not m:
        return None
    return _clean(m.group(1))


def _iban_digits_only(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    digits = "".join(ch for ch in v if ch.isdigit())
    if len(digits) < 24:
        return None
    return "TR" + digits[:24]


def _amount_try_to_tl(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return v.strip().replace("TRY", "TL")


# -------------------------------------------------
# VERY ROBUST TIME + RECEIPT FOR FAST PDFs
# -------------------------------------------------
def _find_any_ddmmyyyy_time(raw: str) -> Optional[str]:
    """
    Finds the first occurrence of dd/mm/yyyy and hh:mm:ss anywhere,
    tolerant of separators like '-' '–' '—' spaces and line breaks.
    """
    t = _collapse_ws(_strip_invisibles(raw))
    # dd/mm/yyyy then optional junk then hh:mm:ss
    m = re.search(
        r"\b(\d{2})/(\d{2})/(\d{4})\b.{0,20}\b(\d{2}):(\d{2}):(\d{2})\b",
        t,
        flags=re.I,
    )
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    hh, mi, ss = m.group(4), m.group(5), m.group(6)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}:{ss}"


def _find_fast_sorgu_no(raw: str) -> Optional[str]:
    """
    Handles even broken tokens like 'FA ST', 'SOR GU', 'N O' due to pypdf text ordering.
    Strategy:
      1) Normalize/flatten whitespace and remove invisibles.
      2) Look for a window that contains FAST + SORGU + NO (allowing spaces between letters),
         then take the first 6+ digit number inside that window.
    """
    flat = _collapse_ws(_strip_invisibles(raw)).casefold()

    # helper that makes "FAST" match "F A S T" etc
    FAST = r"f\s*a\s*s\s*t"
    SORGU = r"s\s*o\s*r\s*g\s*u"
    NO = r"n\s*o"

    # Find a window starting at FAST ... SORGU ... NO
    m = re.search(
        rf"({FAST}[\s\S]{{0,120}}?{SORGU}[\s\S]{{0,80}}?{NO})", flat, flags=re.I
    )
    if m:
        start = m.start()
        window = flat[start : start + 250]
        mnum = re.search(r"\b(\d{6,})\b", window)
        if mnum:
            return mnum.group(1)

    # Alternative: SORGU window (sometimes 'FAST' appears earlier/later)
    ms = re.search(rf"{SORGU}[\s\S]{{0,200}}?{NO}", flat, flags=re.I)
    if ms:
        start = ms.start()
        window = flat[start : start + 250]
        mnum = re.search(r"\b(\d{6,})\b", window)
        if mnum:
            return mnum.group(1)

    # Last fallback: if document clearly talks about FAST+SORGU somewhere, pick the closest number after 'sorgu'
    idx = flat.find("sorgu")
    if idx != -1:
        window = flat[idx : idx + 300]
        mnum = re.search(r"\b(\d{6,})\b", window)
        if mnum:
            return mnum.group(1)

    return None


def parse_ziraat(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    up = _collapse_ws(_strip_invisibles(raw)).upper()

    is_fast = (
        ("HESAPTAN FAST" in up)
        or ("FAST MESAJ KODU" in up)
        or ("FAST SORGU NO" in up)
        or ("FAST" in up and "SORGU" in up)
    )
    is_havale = "HESAPTAN HESABA HAVALE" in up

    sender_name = None
    receiver_name = None
    receiver_iban = None
    amount = None
    receipt_no = None
    transaction_ref = None

    # --- time: robust for all layouts ---
    transaction_time = _find_any_ddmmyyyy_time(raw)

    if is_fast:
        sender_name = _first(r"(?:Gönderen|Gonderen)\s*:\s*([^\n]+)", raw) or _first(
            r"SAYIN\s*\n\s*([^\n]+)", raw
        )

        receiver_name = _first(r"(?:Alıcı|Alici)\s*:\s*([^\n]+)", raw)

        alici_hesap_line = _first(r"(?:Alıcı|Alici)\s*Hesap\s*:\s*([^\n]+)", raw)
        if alici_hesap_line:
            receiver_iban = _iban_digits_only(alici_hesap_line)

        # accept TRY or TL, and tolerate spacing
        amt = _first(r"(?:İşlem|Islem)\s*Tutarı\s*:\s*([0-9\.\,]+)\s*(?:TRY|TL)\b", raw)
        if amt:
            # keep your existing output style like "20.001,00 TL"
            amount = _amount_try_to_tl(f"{amt} TL")

        # ✅ FIX: receipt_no = FAST Sorgu No (robust)
        receipt_no = _find_fast_sorgu_no(raw)

    elif is_havale:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(
            r"Alacaklı\s*Adı\s*Soyadı\s*:\s*([^\n]+)", raw
        ) or _first(r"Alacakli\s*Adi\s*Soyadi\s*:\s*([^\n]+)", raw)

        alacakli_iban = _first(r"Alacaklı\s*IBAN\s*:\s*([^\n]+)", raw) or _first(
            r"Alacakli\s*IBAN\s*:\s*([^\n]+)", raw
        )
        receiver_iban = _iban_digits_only(alacakli_iban)

        amt = _first(r"Havale\s*Tutarı\s*:\s*([0-9\.\,]+)\s*(?:TRY|TL)\b", raw)
        if amt:
            amount = _amount_try_to_tl(f"{amt} TL")

        # keep your old behavior: receipt_no is trailing code like F21018 if present
        receipt_no = _first(
            r"(?:İŞLEM|ISLEM)\s*TAR[İI]H[İI]\s*:\s*\d{2}/\d{2}/\d{4}.{0,10}\d{2}:\d{2}:\d{2}\s*-\s*([A-Z0-9]+)",
            raw,
            re.I,
        )

    else:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(r"(?:Alıcı|Alici)\s*:\s*([^\n]+)", raw)
        receiver_iban = _iban_digits_only(_first(r"(TR[0-9 \*]{10,})", raw))
        # amount/receipt_no often not present in this branch

    return {
        "tr_status": "completed",
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
    }
