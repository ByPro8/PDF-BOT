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


def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", "", s).upper()


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean(m.group(1))


def _pick_transfer_amount(raw: str) -> Optional[str]:
    # Prefer "ŞCH 0,00 TL 50.000,00 TL"
    m = re.search(
        r"^\s*ŞCH\s+[0-9\.\,]+\s*TL\s+([0-9\.\,]+)\s*TL\s*$",
        raw,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return f"{m.group(1).strip()} TL"

    # Fallback: choose biggest TL amount (transfer is usually biggest)
    nums = re.findall(r"([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\s*TL", raw)
    if not nums:
        return None

    def to_float(tr: str) -> float:
        return float(tr.replace(".", "").replace(",", "."))

    best = max(nums, key=to_float)
    return f"{best} TL"


def _detect_tr_status(raw: str) -> str:
    t = (raw or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t:
        return "pending"
    if "dekont" in t and "akbank" in t:
        return "completed"
    return "unknown"


def parse_akbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    # Akbank puts BOTH "Adı Soyadı/Unvan :" on the same line.
    # Capture each name separately (non-greedy, stop before next label).
    names = re.findall(
        r"Adı\s+Soyadı/Unvan\s*:\s*(.+?)(?=\s+Adı\s+Soyadı/Unvan\s*:|\n|$)",
        raw,
        flags=re.IGNORECASE,
    )
    names = [_clean(n) for n in names if _clean(n)]

    sender_name = names[0] if len(names) >= 1 else None
    receiver_name = names[1] if len(names) >= 2 else None

    receiver_iban = _find(raw, r"Alacaklı\s+Hesap\s+No\s*:\s*(TR[0-9\s]{20,})")
    receiver_iban = _iban_compact(receiver_iban)

    # Sender IBAN is a standalone TR... line in your PDFs
    sender_iban = _find(raw, r"\n(TR[0-9\s]{20,})\n")
    sender_iban = _iban_compact(sender_iban)

    amount = _pick_transfer_amount(raw)

    transaction_time = _find(
        raw,
        r"İşlem\s+Tarihi/Saati\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    )

    # This appears as: "30940173 / 458578 /"
    receipt_no = _find(raw, r"([0-9]{5,}\s*/\s*[0-9]{3,}\s*/)")

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "sender_iban": sender_iban,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": None,
    }
