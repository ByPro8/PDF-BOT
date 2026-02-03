import re
from pathlib import Path
from typing import Optional, Dict

from pypdf import PdfReader


# ----------------------------
# Extract
# ----------------------------


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []

    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")

    return "\n".join(parts)


# ----------------------------
# Normalize
# ----------------------------


def _norm(s: str) -> str:
    if not s:
        return ""

    s = s.casefold().replace("\u0307", "")

    tr = str.maketrans(
        {
            "ı": "i",
            "ö": "o",
            "ü": "u",
            "ş": "s",
            "ğ": "g",
            "ç": "c",
        }
    )

    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)

    return s.strip()


# ----------------------------
# Helpers
# ----------------------------


def _value_after_label(lines, label):
    want = _norm(label)

    for i, ln in enumerate(lines):
        if _norm(ln) == want:
            j = i + 1

            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                return lines[j].strip()

    return None


def _find_iban(raw: str) -> Optional[str]:
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, re.I)

    if not m:
        return None

    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


def _find_datetime_anywhere(raw: str) -> Optional[str]:
    """
    Catch inline dates like:
    İşlem Tarihi: 31.01.2026 16:31
    """

    m = re.search(r"(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})", raw)

    return m.group(1) if m else None


# ----------------------------
# Status
# ----------------------------


def _detect_status_tom(raw: str) -> str:
    t = _norm(raw)

    if re.search(r"\biptal\b|\bbasarisiz\b|\breddedildi\b", t):
        return "❌ canceled"

    if re.search(r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b", t):
        return "⏳ pending"

    # TOM does not explicitly confirm completion
    return "❌ unknown — pdf does not state status, check manually"


# ----------------------------
# Main
# ----------------------------


def parse_tombank(pdf_path: Path) -> Dict:

    raw = _extract_text(pdf_path, 2)

    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    sender = _value_after_label(lines, "Gönderen Kişi")
    receiver = _value_after_label(lines, "Gönderilen Kişi")
    amount = _value_after_label(lines, "Tutar")

    # ---- TIME (2 ways) ----

    # 1) Try classic label-based
    time = _value_after_label(lines, "İşlem Tarihi")

    if time:
        m = re.search(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}", time)
        time = m.group(0) if m else time

    # 2) Fallback: scan whole PDF
    if not time:
        time = _find_datetime_anywhere(raw)

    receipt = _value_after_label(lines, "Sorgu Numarası")
    ref = _value_after_label(lines, "İşlem Referansı")

    iban = _find_iban(raw)

    status = _detect_status_tom(raw)

    return {
        "tr_status": status,
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": iban,
        "amount": amount,
        "transaction_time": time,
        "receipt_no": receipt,
        "transaction_ref": ref,
    }
