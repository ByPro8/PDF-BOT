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


def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")
    tr_map = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr_map)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _find_group(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_spaces(m.group(1))


def _find_iban_after(text: str, label_pattern: str) -> Optional[str]:
    """
    Extract IBAN after a label. Garanti PDFs often space digits: 'TR29 0001 ...'
    """
    m = re.search(label_pattern + r"\s*(TR(?:\s*\d){24})", text, flags=re.IGNORECASE)
    if not m:
        return None
    iban = _clean_spaces(m.group(1))
    digits = re.sub(r"\D", "", iban)
    if len(digits) < 24:
        return iban
    digits = digits[:24]
    return f"TR{digits[0:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:22]} {digits[22:24]}"


def _find_sender_name(raw: str) -> Optional[str]:
    # SAYIN\nNAME SURNAME\nADDRESS...
    m = re.search(r"SAYIN\s*\n\s*([^\n]+)", raw, flags=re.IGNORECASE)
    if not m:
        # fallback if newlines got collapsed
        return _find_group(_clean_spaces(raw), r"SAYIN\s+(.+?)\s+(?:FAST\s+REF\s+NO|ALACAKLI|IBAN)")
    name = re.sub(r"\s+", " ", m.group(1)).strip()
    return name or None


def _find_receiver_name(raw: str) -> Optional[str]:
    # FAST: ALACAKLI : NAME
    m = re.search(r"ALACAKLI\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE)
    if m:
        return _clean_spaces(m.group(1))

    # HAVALE: ALACAKLI HESAP : 00765 / 6853696 FURKAN YILDIZ
    m = re.search(r"ALACAKLI\s+HESAP\s*:\s*[0-9/\s]+\s*([^\n]+)", raw, flags=re.IGNORECASE)
    if m:
        return _clean_spaces(m.group(1))

    return None


def _find_amount(raw: str) -> Optional[str]:
    m = re.search(r"TUTAR\s*:\s*-\s*([0-9\.\,]+)\s*TL", raw, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"
    return None


def _find_transaction_time(raw: str) -> Optional[str]:
    # SIRA NO : 2026-01-31-20.39.54.283610  -> 31.01.2026 20:39
    m = re.search(
        r"SIRA\s+NO\s*:\s*(\d{4})-(\d{2})-(\d{2})-(\d{2})\.(\d{2})(?:\.\d{2})?",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        yyyy, mm, dd, hh, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        return f"{dd}.{mm}.{yyyy} {hh}:{mi}"

    # Fallback: İŞLEM TARİHİ : 31/01/2026
    m = re.search(r"İŞLEM\s+TARİHİ\s*:\s*(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{dd}.{mm}.{yyyy}"

    return None


def _find_receipt_no(raw: str) -> Optional[str]:
    m = re.search(r"SIRA\s+NO\s*:\s*([0-9\-\.\:]+)", raw, flags=re.IGNORECASE)
    if m:
        return _clean_spaces(m.group(1))
    return None


def _find_transaction_ref(raw: str) -> Optional[str]:
    m = re.search(r"FAST\s+REF\s+NO\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _detect_tr_status(raw_text: str) -> str:
    t = _norm(raw_text)

    if re.search(r"\biptal\b|\biptal edildi\b|\bcancel", t):
        return "canceled"
    if re.search(r"\bbasarisiz\b|\bhata\b|\breddedildi\b|\bfailed\b|\brejected\b", t):
        return "failed"
    if re.search(r"\bbeklemede\b|\bonay bekliyor\b|\bonayda\b|\baskida\b|\bisleniyor\b|\bpending\b|\bprocessing\b", t):
        return "pending"

    # These PDFs are typically produced after completion
    if "dekont" in t:
        return "completed"

    return "unknown"


def parse_garanti(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    sender = _find_sender_name(raw)
    receiver = _find_receiver_name(raw)

    receiver_iban = _find_iban_after(raw, r"ALACAKLI\s+IBAN\s*:\s*")

    amount = _find_amount(raw)
    receipt_no = _find_receipt_no(raw)
    transaction_ref = _find_transaction_ref(raw)
    transaction_time = _find_transaction_time(raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
