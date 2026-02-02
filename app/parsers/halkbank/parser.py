import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _find_line_value(raw: str, label: str) -> Optional[str]:
    # Matches: LABEL : value (until line end)
    # Works even if there are many spaces around ":"
    m = re.search(rf"^{re.escape(label)}\s*:\s*(.+)$", raw, flags=re.MULTILINE)
    return _clean(m.group(1)) if m else None


def _find_iban_after(label: str, raw: str) -> Optional[str]:
    # Find IBAN on the same line after a specific label (e.g. "ALICI IBAN")
    m = re.search(rf"{re.escape(label)}\s*:\s*(TR(?:\s*\d){{24}})", raw, flags=re.IGNORECASE)
    if not m:
        return None
    iban = re.sub(r"\s+", " ", m.group(1)).upper().strip()
    return iban


def _find_any_iban(raw: str) -> Optional[str]:
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


def _find_amount(raw: str) -> Optional[str]:
    # Example in your PDF: "İŞLEM TUTARI (TL) : 30,700.00"
    m = re.search(r"İŞLEM\s+TUTARI\s*\(TL\)\s*:\s*([0-9][0-9\.,]*)", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).strip()} TL"


def _find_transaction_time(raw: str) -> Optional[str]:
    # Example: "İŞLEM TARİHİ : 24/01/2026 - 23:54"
    m = re.search(r"İŞLEM\s+TARİHİ\s*:\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}:\d{2})", raw, flags=re.IGNORECASE)
    if not m:
        return None
    dd, mm, yyyy, hhmm = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"{dd}.{mm}.{yyyy} {hhmm}"


def _detect_status_halkbank(raw: str) -> str:
    # STRICT RULE:
    # - Only claim completed if the PDF explicitly says so (your current samples do not).
    # - If it doesn't explicitly state status -> unknown + manual check message.
    t = raw.lower()

    # If it explicitly says failed/canceled:
    if any(k in t for k in ["iptal", "iade", "başarısız", "basarisiz", "reddedildi", "hata", "failed", "cancelled", "canceled"]):
        return "❌ canceled/failed (PDF states failure)"

    # If it explicitly says pending:
    if any(k in t for k in ["beklemede", "işleniyor", "isleniyor", "onay bekliyor", "pending", "processing"]):
        return "❌ pending (PDF states pending)"

    # If it explicitly says success/completed:
    if any(k in t for k in ["başarılı", "basarili", "işlem başarılı", "islem basarili", "tamamlandı", "tamamlandi", "successful", "completed"]):
        return "✅ completed"

    # Otherwise:
    return "❌ unknown — PDF does not state status; check manually"


def parse_halkbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    sender = _find_line_value(raw, "GÖNDEREN")
    receiver = _find_line_value(raw, "ALICI")

    receiver_iban = _find_iban_after("ALICI IBAN", raw) or _find_any_iban(raw)

    receipt_no = _find_line_value(raw, "SORGU NO")

    transaction_ref = (
        _find_line_value(raw, "BİMREF-SERİSIRANO")
        or _find_line_value(raw, "BIMREF-SERISIRANO")
    )

    return {
        "tr_status": _detect_status_halkbank(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": _find_amount(raw),
        "transaction_time": _find_transaction_time(raw),
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
