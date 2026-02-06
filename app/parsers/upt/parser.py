import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 1) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def parse_upt(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=1)

    sender_name = _find(raw, r"Originator Name Surname\s+([^\n]+)")
    receiver_name = _find(raw, r"Receiver Name Surname\s+([^\n]+)")
    receiver_iban = _find(raw, r"Receiver IBAN\s+(TR[0-9\s]{10,})")
    amount = _find(raw, r"Transaction Amount\s+([0-9\.,]+)\s*TL")
    if amount:
        amount = f"{amount} TL"

    transaction_time = _find(
        raw,
        r"(?:Issue Date|Transaction Date)\s+([0-9]{2}/[0-9]{2}/[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    )
    receipt_no = _find(raw, r"Receipt No\s+([A-Z0-9\-]+)")
    transaction_ref = _find(
        raw, r"(?:Transaction Number|Transaction Reference Number)\s+([0-9]+)"
    )

    # Receipt => completed
    tr_status = "completed" if ("Receipt" in raw or "Receipt No" in raw) else "unknown"

    return {
        "tr_status": tr_status,
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
