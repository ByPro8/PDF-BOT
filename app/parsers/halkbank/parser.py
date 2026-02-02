import re
from pathlib import Path
from typing import Optional, Dict

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _digits_after_label(text: str, label: str) -> Optional[str]:
    """
    Extract only digits after 'LABEL :'
    e.g. 'SORGU NO : 1240647512 İŞLEM TUTARI ...' -> '1240647512'
    """
    t = _clean_spaces(text)
    m = re.search(re.escape(label) + r"\s*:\s*([0-9]{3,})", t, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _name_for_label(text: str, label: str) -> Optional[str]:
    """
    Handles both:
      'GÖNDEREN : MUSTAFA ÇETİN'
      'MUSTAFA ÇETİN GÖNDEREN'
    """
    t = _clean_spaces(text)

    # 1) normal: LABEL : value (stop before next label-ish token)
    m = re.search(
        re.escape(label) + r"\s*:\s*(.+?)(?=\s+[A-ZÇĞİÖŞÜ0-9()/.-]{2,}\s*:\s*|$)",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        val = _clean_spaces(m.group(1))
        # if it still accidentally ends with the label, trim it
        val = re.sub(rf"\s+{re.escape(label)}\s*$", "", val, flags=re.IGNORECASE).strip()
        return val or None

    # 2) reversed: value LABEL  (capture a reasonable name chunk before the label)
    m = re.search(rf"\b(.+?)\s+{re.escape(label)}\b", t, flags=re.IGNORECASE)
    if m:
        val = _clean_spaces(m.group(1))
        # Often there are other fields before; keep only the last 2-6 "words"
        parts = val.split(" ")
        if len(parts) > 6:
            val = " ".join(parts[-6:])
        return val or None

    return None


def _extract_iban(text: str, label: str) -> Optional[str]:
    """
    Extract TR IBAN after 'label :' as TR + 24 digits. Keeps readable spacing.
    """
    t = _clean_spaces(text)
    m = re.search(re.escape(label) + r"\s*:\s*(TR(?:\s*\d){24})", t, flags=re.IGNORECASE)
    if not m:
        return None

    raw = m.group(1)
    digits = re.sub(r"\D", "", raw)[:24]
    if len(digits) < 24:
        return _clean_spaces(raw)

    return f"TR{digits[0:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:22]} {digits[22:24]}"


def _extract_datetime(text: str) -> Optional[str]:
    """
    Halkbank: 'İŞLEM TARİHİ : 29/01/2026 - 18:22'
    Output: '29.01.2026 18:22'
    """
    t = _clean_spaces(text)
    m = re.search(
        r"İŞLEM\s+TARİHİ\s*:\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}):(\d{2})",
        t,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    dd, mm, yyyy, hh, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _extract_amount(text: str) -> Optional[str]:
    """
    Halkbank: 'İŞLEM TUTARI (TL) : 50,000.00'
    Return as '50,000.00 TL'
    """
    t = _clean_spaces(text)
    m = re.search(r"İŞLEM\s+TUTARI\s*\(TL\)\s*:\s*([0-9\.,]+)", t, flags=re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).strip()} TL"


def parse_halkbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    sender = _name_for_label(raw, "GÖNDEREN")
    receiver = _name_for_label(raw, "ALICI")

    receiver_iban = _extract_iban(raw, "ALICI IBAN")
    amount = _extract_amount(raw)
    transaction_time = _extract_datetime(raw)

    receipt_no = _digits_after_label(raw, "SORGU NO")

    transaction_ref = None
    # Sometimes label appears as 'BİMREF-SERİSIRANO' or without dotted İ in extraction
    m = re.search(r"B[İI]MREF-?SER[İI]SIRANO\s*:\s*([A-Za-z0-9\.\-]+)", _clean_spaces(raw), flags=re.IGNORECASE)
    if m:
        transaction_ref = m.group(1).strip()

    return {
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
