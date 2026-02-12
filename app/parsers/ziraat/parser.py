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


def _first(pattern: str, text: str, flags: int = re.I) -> Optional[str]:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    return (m.group(1) or "").strip()


def _first_ddmmyyyy_time(text: str) -> Optional[str]:
    m = re.search(
        r"İŞLEM\s*TARİHİ\s*:\s*(\d{2})/(\d{2})/(\d{4})-(\d{2}:\d{2}:\d{2})",
        text,
        re.I,
    )
    if not m:
        # fallback: sometimes OCR/text-layer changes : to =
        m = re.search(
            r"İŞLEM\s*TARİHİ\s*[=:]\s*(\d{2})/(\d{2})/(\d{4})-(\d{2}:\d{2}:\d{2})",
            text,
            re.I,
        )
    if not m:
        return None
    dd, mm, yyyy, hhmmss = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"{dd}.{mm}.{yyyy} {hhmmss}"


def _amount_try_to_tl(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.strip()
    v = v.replace("TRY", "TL")
    return v


def _iban_digits_only(v: Optional[str]) -> Optional[str]:
    """
    Strict IBAN builder: TR + 24 digits.
    If the pdf masks digits with * then this returns None.
    """
    if not v:
        return None
    digits = "".join(ch for ch in v if ch.isdigit())
    if len(digits) != 24:
        return None
    return "TR" + digits


def _iban_masked_or_full(v: Optional[str]) -> Optional[str]:
    """
    If full IBAN digits exist -> TR + 24 digits.
    Otherwise, return masked IBAN as shown (e.g. 'TR18 **** ... 8306 41').
    """
    if not v:
        return None

    full = _iban_digits_only(v)
    if full:
        return full

    # masked fallback: keep TR + digits + * + spaces
    # and cut trailing junk if OCR glued it.
    m = re.search(r"\bTR[0-9][0-9A-Z *]{8,}\b", v, flags=re.I)
    if not m:
        # sometimes the line continues; take from first TR
        i = v.upper().find("TR")
        if i == -1:
            return None
        chunk = v[i:]
    else:
        chunk = m.group(0)

    chunk = re.sub(r"\s+", " ", chunk).strip()
    # If it’s extremely short, it’s not useful
    return chunk if len(chunk) >= 10 else None


def parse_ziraat(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    up = raw.upper()

    is_fast = (
        ("HESAPTAN FAST" in up) or ("FAST MESAJ KODU" in up) or ("FAST SORGU NO" in up)
    )
    is_havale = "HESAPTAN HESABA HAVALE" in up

    transaction_time = _first_ddmmyyyy_time(raw)

    sender_name = None
    receiver_name = None
    receiver_iban = None
    amount = None
    receipt_no = None
    transaction_ref = None

    if is_fast:
        sender_name = _first(r"Gönderen\s*:\s*([^\n]+)", raw) or _first(
            r"SAYIN\s*\n\s*([^\n]+)", raw
        )

        receiver_name = _first(r"Alıcı\s*:\s*([^\n]+)", raw)

        # This line is sometimes fully visible, sometimes masked with ****
        alici_hesap_line = _first(r"Alıcı\s*Hesap\s*:\s*([^\n]+)", raw)
        # IMPORTANT: in some PDFs, "Alıcı :" is on the same line as "Alıcı Hesap :"
        if not alici_hesap_line:
            alici_hesap_line = _first(
                r"Alıcı\s*Hesap\s*:\s*(TR[0-9 \*]{10,}.*?)\s+Alıcı\s*:", raw
            )

        receiver_iban = _iban_masked_or_full(alici_hesap_line)

        amt = _first(r"İşlem\s*Tutarı\s*:\s*([0-9\.\,]+)\s*TRY", raw)
        amount = _amount_try_to_tl(f"{amt} TL" if amt else None)

        # receipt_no = Fast Sorgu No (this is what you already show in logs)
        receipt_no = _first(r"Fast\s*Sorgu\s*No\s*:\s*([0-9]+)", raw)

    elif is_havale:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(r"Alacaklı\s*Adı\s*Soyadı\s*:\s*([^\n]+)", raw)

        alacakli_iban = _first(r"Alacaklı\s*IBAN\s*:\s*([^\n]+)", raw)
        receiver_iban = _iban_masked_or_full(alacakli_iban)

        amt = _first(r"Havale\s*Tutarı\s*:\s*([0-9\.\,]+)\s*TRY", raw)
        amount = _amount_try_to_tl(f"{amt} TL" if amt else None)

        receipt_no = _first(
            r"İŞLEM\s*TARİHİ\s*:\s*\d{2}/\d{2}/\d{4}-\d{2}:\d{2}:\d{2}\s*-\s*([A-Z0-9]+)",
            raw,
        )

    else:
        sender_name = _first(r"SAYIN\s*\n\s*([^\n]+)", raw)
        receiver_name = _first(r"Alıcı\s*:\s*([^\n]+)", raw)

        # try a generic IBAN occurrence (masked/full)
        any_tr = _first(r"\b(TR[0-9 \*]{10,})", raw)
        receiver_iban = _iban_masked_or_full(any_tr)

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
