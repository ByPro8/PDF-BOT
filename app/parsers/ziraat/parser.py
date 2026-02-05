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


def _first(pattern: str, text: str, flags: int = re.I) -> Optional[str]:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    return (m.group(1) or "").strip()


def _first_ddmmyyyy_time(text: str) -> Optional[str]:
    m = re.search(r"İŞLEM\s*TARİHİ\s*:\s*(\d{2})/(\d{2})/(\d{4})-(\d{2}:\d{2}:\d{2})", text, re.I)
    if not m:
        return None
    dd, mm, yyyy, hhmmss = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"{dd}.{mm}.{yyyy} {hhmmss}"


def _iban_digits_only(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    # keep TR + digits only (works even if masked with * and spaces)
    digits = "".join(ch for ch in v if ch.isdigit())
    if not digits:
        return None
    return "TR" + digits


def _amount_try_to_tl(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.strip()
    v = v.replace("TRY", "TL")
    return v


def parse_ziraat(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    up = raw.upper()

    is_fast = ("HESAPTAN FAST" in up) or ("FAST MESAJ KODU" in up) or ("FAST SORGU NO" in up)
    is_havale = ("HESAPTAN HESABA HAVALE" in up)

    transaction_time = _first_ddmmyyyy_time(raw)

    sender_name = None
    receiver_name = None
    receiver_iban = None
    amount = None
    receipt_no = None
    transaction_ref = None

    if is_fast:
        sender_name = _first(r"Gönderen\s*:\s*([^\n]+)", raw) or _first(r"SAYIN\s*\n\s*([^\n]+)", raw)

        # receiver name: always after "Alıcı :"
        receiver_name = _first(r"Alıcı\s*:\s*([^\n]+)", raw)

        # receiver iban: take the "Alıcı Hesap :" line then normalize to TR+digits
        alici_hesap_line = _first(r"Alıcı\s*Hesap\s*:\s*([^\n]+)", raw)
        if alici_hesap_line:
            receiver_iban = _iban_digits_only(alici_hesap_line)

        amt = _first(r"İşlem\s*Tutarı\s*:\s*([0-9\.\,]+)\s*TRY", raw)
        amount = _amount_try_to_tl(f"{amt} TL" if amt else None)

        receipt_no = _first(r"Fast\s*Sorgu\s*No\s*:\s*([0-9]+)", raw)

    elif is_havale:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(r"Alacaklı\s*Adı\s*Soyadı\s*:\s*([^\n]+)", raw)

        alacakli_iban = _first(r"Alacaklı\s*IBAN\s*:\s*([^\n]+)", raw)
        receiver_iban = _iban_digits_only(alacakli_iban)

        amt = _first(r"Havale\s*Tutarı\s*:\s*([0-9\.\,]+)\s*TRY", raw)
        amount = _amount_try_to_tl(f"{amt} TL" if amt else None)

        receipt_no = _first(r"İŞLEM\s*TARİHİ\s*:\s*\d{2}/\d{2}/\d{4}-\d{2}:\d{2}:\d{2}\s*-\s*([A-Z0-9]+)", raw)

    else:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(r"Alıcı\s*:\s*([^\n]+)", raw)
        receiver_iban = _iban_digits_only(_first(r"(TR[0-9 \*]{10,})", raw))
        amount = None
        receipt_no = None

    return {
        "tr_status": "completed",
        "sender_name": sender_name,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
