import re
from pathlib import Path
from typing import Dict, Optional

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

    s = s.casefold()

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
# Finders
# ----------------------------


def _find_sender(raw: str) -> Optional[str]:
    m = re.search(r"GÖNDEREN\s*İsim\s*:\s*(.+)", raw, re.I)
    return m.group(1).strip() if m else None


def _find_receiver(raw: str) -> Optional[str]:
    m = re.search(r"ALICI\s*İsim\s*:\s*(.+)", raw, re.I)
    return m.group(1).strip() if m else None


def _find_iban(raw: str) -> Optional[str]:
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, re.I)

    if not m:
        return None

    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


def _find_amount(raw: str) -> Optional[str]:
    m = re.search(r"Tutar\s*:\s*([\d.,]+)", raw, re.I)

    if not m:
        return None

    return f"{m.group(1)} TL"


def _find_time(raw: str) -> Optional[str]:
    m = re.search(
        r"Düzenleme Tarihi\s*:\s*([0-9./]+\s+[0-9:]+)",
        raw,
        re.I,
    )

    return m.group(1).strip() if m else None


def _find_ref(raw: str) -> Optional[str]:
    m = re.search(r"Referans No\s*:\s*([A-Z0-9\-]+)", raw, re.I)

    return m.group(1) if m else None


# ----------------------------
# Status (STRICT - SAFE)
# ----------------------------


def _detect_status(raw: str) -> str:
    t = _norm(raw)

    # Only explicit confirmations allowed
    if (
        "isleminiz gerceklestirilmistir" in t
        or "basariyla gerceklesti" in t
        or "basarili" in t
        or "tamamlandi" in t
    ):
        return "completed"

    # Explicit failures
    if "iptal" in t or "basarisiz" in t or "reddedildi" in t:
        return "canceled"

    # Explicit pending
    if "beklemede" in t or "isleniyor" in t or "onay bekliyor" in t:
        return "pending"

    # Default: unknown (Türkiye Finans does NOT confirm in your samples)
    return "unknown-manually"


# ----------------------------
# Main
# ----------------------------


def parse_turkiyefinans(pdf_path: Path) -> Dict:

    raw = _extract_text(pdf_path, 2)

    sender = _find_sender(raw)
    receiver = _find_receiver(raw)
    iban = _find_iban(raw)
    amount = _find_amount(raw)
    time = _find_time(raw)
    ref = _find_ref(raw)

    status = _detect_status(raw)

    return {
        "tr_status": status,
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": iban,
        "amount": amount,
        "transaction_time": time,
        "receipt_no": ref,
        "transaction_ref": ref,
    }
