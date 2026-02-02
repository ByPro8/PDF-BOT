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


def _find_group(text: str, pattern: str) -> Optional[str]:
    """
    Search on a single-line normalized text, return group(1) trimmed.
    """
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean_spaces(m.group(1))


def _find_iban_after(text: str, label_pattern: str) -> Optional[str]:
    """
    Extract TR IBAN after label, and STOP strictly after the TR+24 digits.
    Accept spaces between digits.
    """
    # TR + 24 digits (TR is 2 letters + 24 digits = 26 chars total)
    m = re.search(label_pattern + r"\s*(TR(?:\s*\d){24})", text, flags=re.IGNORECASE)
    if not m:
        return None
    iban = m.group(1)
    iban = _clean_spaces(iban)

    # Ensure it's exactly TR + 24 digits (spaces allowed in between)
    digits = re.sub(r"\D", "", iban)  # keep digits only
    if len(digits) < 24:
        return iban  # fallback
    digits = digits[:24]

    # Format nicely: TRxx xxxx xxxx xxxx xxxx xxxx xx (common TR grouping)
    # TR + 2 + 4*5 + 2
    return f"TR{digits[0:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:22]} {digits[22:24]}"


def _find_amount(text: str) -> Optional[str]:
    # Prefer explicit EFT TUTARI if present
    m = re.search(r"EFT\s*TUTARI\s*:\s*([0-9\.,]+)\s*TL", text, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    # Fallback: table line "... TL 30,350.00"
    m = re.search(r"\bTL\s+([0-9\.,]+)\b", text, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} TL"

    return None


def _find_datetime(text: str) -> Optional[str]:
    # 25/01/2026 + 14:04:01  -> 25.01.2026 14:04
    d = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    t = re.search(r"\b(\d{2}):(\d{2})(?::\d{2})?\b", text)
    if not d or not t:
        return None
    dd, mm, yyyy = d.group(1), d.group(2), d.group(3)
    hh, mi = t.group(1), t.group(2)
    return f"{dd}.{mm}.{yyyy} {hh}:{mi}"


def parse_qnb(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    text = _clean_spaces(raw)  # single-line text so regex boundaries work reliably

    # Receiver name: between "ALICI ÜNVANI:" and "ALICI IBAN:"
    receiver = _find_group(
        text,
        r"ALICI\s+ÜNVANI\s*:\s*(.*?)\s+ALICI\s+IBAN\s*:",
    )

    # Sender name: between "GÖNDEREN:" and "AÇIKLAMA:"
    sender = _find_group(
        text,
        r"GÖNDEREN\s*:\s*(.*?)\s+AÇIKLAMA\s*:",
    )

    # Receiver IBAN: after "ALICI IBAN:"
    receiver_iban = _find_iban_after(
        text,
        r"ALICI\s+IBAN\s*:\s*",
    )

    amount = _find_amount(text)

    receipt_no = _find_group(text, r"SORGU\s+NO\s*:\s*(\d+)")
    transaction_ref = _find_group(text, r"Fi[şs]\s+No\s*:\s*(\d+)")
    transaction_time = _find_datetime(text)

    return {
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
