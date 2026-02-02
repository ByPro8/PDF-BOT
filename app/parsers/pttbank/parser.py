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


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")
    tr_map = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr_map)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _value_inline(lines: list[str], label: str) -> Optional[str]:
    want = _norm(label)
    for ln in lines:
        nln = _norm(ln)
        if nln.startswith(want):
            if ":" in ln:
                after = ln.split(":", 1)[1].strip()
                return after or None
            return ln.strip()
    return None


def _value_after_exact_line(lines: list[str], label: str) -> Optional[str]:
    want = _norm(label)
    for i, ln in enumerate(lines):
        if _norm(ln) == want:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                return lines[j].strip()
            return None
    return None


def _parse_ptt_time(s: str) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*-?\s*(\d{2}:\d{2})", s)
    if m:
        dd, mm, yyyy, hhmm = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{dd}.{mm}.{yyyy} {hhmm}"
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})", s)
    if m:
        dd, mm, yyyy, hhmm = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{dd}.{mm}.{yyyy} {hhmm}"
    return None


def _clean_iban(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def _detect_tr_status(raw_text: str) -> str:
    """
    SAFE:
    - completed only if receipt text explicitly proves it.
    - otherwise unknown/pending/failed/canceled by keywords.
    """
    t = _norm(raw_text)

    # Negative states first (generic)
    if re.search(r"\biptal\b|\biptal edildi\b|\bcancel", t):
        return "canceled"
    if re.search(r"\bbasarisiz\b|\bhata\b|\breddedildi\b|\bfailed\b|\brejected\b", t):
        return "failed"
    if re.search(r"\bbeklemede\b|\bonay bekliyor\b|\bonayda\b|\baskida\b|\bisleniyor\b|\bpending\b|\bprocessing\b", t):
        return "pending"

    # PTT explicit completion: "... hesabınızdan ... çekilmiştir."
    if re.search(r"\bhesabinizdan\b.*\bcekilmistir\b", t):
        return "completed"

    return "unknown"


def parse_pttbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    receiver = _value_inline(lines, "Alıcı Adı")
    receiver_iban = _clean_iban(_value_inline(lines, "Alıcı Iban"))

    amount = _value_inline(lines, "Tutar")
    receipt_no = _value_inline(lines, "İşlem Sıra No")

    tt_raw = _value_inline(lines, "İŞLEM TARİHİ") or _value_inline(lines, "İşlem Tarihi")
    transaction_time = _parse_ptt_time(tt_raw or "")

    if not transaction_time:
        for ln in lines:
            if "tarihinde oluşturulmuştur" in ln.lower():
                transaction_time = _parse_ptt_time(ln)
                if transaction_time:
                    break

    sender = _value_after_exact_line(lines, "SAYIN")

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": None,
    }
