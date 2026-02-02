import re
import os
import logging
from pathlib import Path
from typing import Optional, Dict

from pypdf import PdfReader

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

DEBUG = os.getenv("DEBUG_TOMBANK", "0") == "1"


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
    tr_map = str.maketrans(
        {"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"}
    )
    s = s.translate(tr_map)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _flex_datetime_from_text(text: str) -> Optional[str]:
    m = re.search(
        r"((?:\d\s*){2})\.\s*((?:\d\s*){2})\.\s*((?:\d\s*){4})\s+((?:\d\s*){2})\:\s*((?:\d\s*){2})",
        text,
    )
    if not m:
        return None

    dd = re.sub(r"\s+", "", m.group(1))
    mm = re.sub(r"\s+", "", m.group(2))
    yyyy = re.sub(r"\s+", "", m.group(3))
    hh = re.sub(r"\s+", "", m.group(4))
    mi = re.sub(r"\s+", "", m.group(5))

    if not (len(dd) == 2 and len(mm) == 2 and len(yyyy) == 4 and len(hh) == 2 and len(mi) == 2):
        return None

    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _value_after_label(lines: list[str], label: str) -> Optional[str]:
    want = _norm(label)

    for i, ln in enumerate(lines):
        nln = _norm(ln)

        # exact label line -> next line
        if nln == want:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                return lines[j].strip()
            return None

        # inline: label: value
        if nln.startswith(want):
            if ":" in ln:
                after = ln.split(":", 1)[1].strip()
                if after:
                    return after
            dt = _flex_datetime_from_text(ln)
            if dt:
                return dt

    return None


def _extract_time_tombank(raw: str, lines: list[str]) -> Optional[str]:
    t1 = _value_after_label(lines, "İşlem Tarihi")
    if t1:
        return _flex_datetime_from_text(t1) or t1.strip()

    norm_raw = _norm(raw)

    hit = re.search(r"islem\s*tarihi", norm_raw) or re.search(r"islemtarihi", norm_raw)
    if hit:
        window = norm_raw[hit.start(): hit.start() + 120]
        t2 = _flex_datetime_from_text(window)
        if t2:
            return t2

    t3 = _flex_datetime_from_text(norm_raw)
    if t3:
        return t3

    return None


def _clean_iban(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def parse_tombank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    sender = _value_after_label(lines, "Gönderen Kişi")
    receiver = _value_after_label(lines, "Gönderilen Kişi")
    receiver_iban = _clean_iban(_value_after_label(lines, "Gönderilen IBAN"))

    amount = _value_after_label(lines, "Tutar")
    transaction_time = _extract_time_tombank(raw, lines)
    receipt_no = _value_after_label(lines, "Sorgu Numarası")
    transaction_ref = _value_after_label(lines, "İşlem Referansı")

    if DEBUG:
        log.info("TOMBANK parsed receiver_iban=%r transaction_time=%r", receiver_iban, transaction_time)

    return {
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
