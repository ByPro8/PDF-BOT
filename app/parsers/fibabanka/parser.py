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


def parse_fibabanka(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=1)

    # Sender is usually "FULL NAME"
    sender_name = _find(raw, r"FULL NAME\s+([^\n]+)") or _find(
        raw, r"ADI SOYADI[^\n]*\s+([^\n]+)"
    )

    # Receiver name appears in explanation after "ALICI:"
    receiver_name = _find(raw, r"ALICI:\s*([^\-\n]+)")
    receiver_iban = _find(raw, r"ALICI\s*IBAN\s*:\s*(TR[0-9\s]{10,})")

    # Amount line: "(-)TRY 30,000.00"
    amount = _find(raw, r"\(\-\)\s*TRY\s*([0-9\.,]+)")
    if amount:
        amount = f"{amount} TL"

    transaction_time = _find(
        raw, r"(?:TARİH\s*/\s*DATE)\s*([0-9]{2}/[0-9]{2}/[0-9]{4})"
    )
    receipt_no = _find(raw, r"(?:DEKONT NO\s*/\s*RECEIPT NUMBER)\s*([0-9\-]+)")
    transaction_ref = _find(raw, r"(?:Ürün Referansı|Urun Referansi)\s*:\s*([0-9]+)")

    tr_status = (
        "completed"
        if ("E - DEKONT" in raw or "E-DEKONT" in raw or "DEKONT" in raw)
        else "unknown"
    )

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
