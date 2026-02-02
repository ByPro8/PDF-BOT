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
    return re.sub(r"\s+", " ", s).strip()


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
    m = re.search(label_pattern + r"\s*(TR(?:\s*\d){24})", text, flags=re.IGNORECASE)
    if not m:
        return None
    iban = _clean_spaces(m.group(1))
    digits = re.sub(r"\D", "", iban)
    if len(digits) < 24:
        return iban
    digits = digits[:24]
    return f"TR{digits[0:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:22]} {digits[22:24]}"


def _find_amount(text: str) -> Optional[str]:
    m = re.search(r"EFT\s*TUTARI\s*:\s*([0-9\.,]+)\s*TL", text, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"
    m = re.search(r"\bTL\s+([0-9\.,]+)\b", text, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"
    return None


def _find_datetime(text: str) -> Optional[str]:
    d = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    t = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", text)
    if not d or not t:
        return None
    dd, mm, yyyy = d.group(1), d.group(2), d.group(3)
    hh, mi = t.group(1), t.group(2)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _detect_tr_status(raw_text: str) -> str:
    t = _norm(raw_text)

    # generic negative states
    if re.search(r"\biptal\b|\biptal edildi\b|\bcancel", t):
        return "canceled"
    if re.search(r"\bbasarisiz\b|\bhata\b|\breddedildi\b|\bfailed\b|\brejected\b", t):
        return "failed"
    if re.search(r"\bbeklemede\b|\bonay bekliyor\b|\bonayda\b|\baskida\b|\bisleniyor\b|\bpending\b|\bprocessing\b", t):
        return "pending"

    # QNB explicit completion phrase:
    # "hareketler gerçekleştirilmiştir" -> normalized becomes "hareketler gerceklestirilmiştir"
    # We match the stem to be robust to minor text differences.
    if re.search(r"\bhareketler\s+gerceklestiril", t):
        return "completed"

    return "unknown"


def parse_qnb(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    text = _clean_spaces(raw)

    receiver = _find_group(
        text,
        r"ALICI\s+ÜNVANI\s*:\s*(.*?)\s+ALICI\s+IBAN\s*:",
    )

    sender = _find_group(
        text,
        r"GÖNDEREN\s*:\s*(.*?)\s+AÇIKLAMA\s*:",
    )

    receiver_iban = _find_iban_after(
        text,
        r"ALICI\s+IBAN\s*:\s*",
    )

    amount = _find_amount(text)
    receipt_no = _find_group(text, r"SORGU\s+NO\s*:\s*(\d+)")
    transaction_ref = _find_group(text, r"Fi[şs]\s+No\s*:\s*(\d+)")
    transaction_time = _find_datetime(text)

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
