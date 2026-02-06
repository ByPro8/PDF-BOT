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


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", "", s).upper()
    m = re.search(r"(TR[0-9]{24})", s)
    return m.group(1) if m else None


def _find_line_value(lines: list[str], prefix_regex: str) -> Optional[str]:
    rx = re.compile(prefix_regex, flags=re.IGNORECASE)
    for ln in lines:
        m = rx.search(ln)
        if m:
            return _clean(m.group(1))
    return None


def _find_receipt_no_anywhere(raw: str) -> Optional[str]:
    # Works for both PDFs:
    # "Sıra No 00167-240000" :contentReference[oaicite:2]{index=2}
    # "Sıra No 01164-450426" :contentReference[oaicite:3]{index=3}
    m = re.search(r"Sıra\s+No\s+([0-9]{3,}-[0-9]{3,})", raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _find_tx_ref(raw: str) -> Optional[str]:
    m = re.search(r"Fiş\s+No\s*:\s*([0-9]+)", raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _find_datetime(raw: str) -> Optional[str]:
    d = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", raw)
    t = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", raw)
    if not d or not t:
        return None
    dd, mm, yyyy = d.group(1), d.group(2), d.group(3)
    hh, mi = t.group(1), t.group(2)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def _find_amount(raw: str) -> Optional[str]:
    # In both PDFs: "... TL 11,630.00" or "... TL 30,350.00"
    m = re.search(r"\bTL\s+([0-9\.,]+)", raw, flags=re.IGNORECASE)
    if not m:
        return None
    amt = m.group(1).strip()
    if amt.endswith(".00"):
        amt = amt[:-3]
    return f"{amt} TL"


def _detect_tr_status(raw: str) -> str:
    t = (raw or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t:
        return "pending"
    if "hareketler gerceklestirilmis" in t or "dekont" in t:
        return "completed"
    return "unknown"


def parse_qnb(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # ------------------------------------------------------------
    # Layout A: HESAPTAN HESABA HAVALE (your 11,630 PDF)
    # ------------------------------------------------------------
    sender_name = _find_line_value(
        lines,
        r"^HAVALEY[İI]\s+G[ÖO]NDEREN\s+HESAP\s+UNVANI\s*:\s*(.+)$",
    )
    receiver_name = _find_line_value(
        lines,
        r"^HAVALEY[İI]\s+ALAN\s+MUSTERI\s+UNVANI\s*:\s*(.+)$",
    )

    receiver_iban_raw = _find_line_value(
        lines,
        r"^HAVALEY[İI]\s+ALAN\s+HESAP\s+NO\s*:\s*\d+\s+IBAN\s*:\s*(TR.*)$",
    )
    receiver_iban = _iban_compact(receiver_iban_raw)

    # ------------------------------------------------------------
    # Layout B: GIDEN FAST EFT (your 30,350 PDF)
    # ------------------------------------------------------------
    if not receiver_name:
        receiver_name = _find_line_value(
            lines, r"^ALICI\s+ÜNVANI:\s*(.+?)\s+ALICI\s+IBAN:"
        )
    if not receiver_iban:
        receiver_iban = _iban_compact(
            _find_line_value(lines, r"^ALICI\s+ÜNVANI:.*?ALICI\s+IBAN:\s*(TR.*)$")
        )

    if not sender_name:
        # "GÖNDEREN: HAMZA GEZER AÇIKLAMA:..."
        m = re.search(r"GÖNDEREN\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE)
        if m:
            sender_name = _clean(m.group(1).split("AÇIKLAMA")[0])

    amount = _find_amount(raw)
    transaction_time = _find_datetime(raw)
    receipt_no = _find_receipt_no_anywhere(raw)
    transaction_ref = _find_tx_ref(raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
