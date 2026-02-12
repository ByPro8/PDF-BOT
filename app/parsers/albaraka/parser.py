import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip() or None


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", "", s).upper()
    m = re.search(r"(TR[0-9]{24})", s)
    return m.group(1) if m else None


def _extract_text(pdf_path: Path, max_pages: int = 1) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    except Exception:
        return ""


def _ocr_first_page(pdf_path: Path) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    try:
        img = convert_from_path(str(pdf_path), first_page=1, last_page=1)[0]
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None


def _find_all_ibans(raw: str) -> list[str]:
    hits = re.findall(r"(TR[0-9\s]{24,})", raw, flags=re.IGNORECASE)
    out: list[str] = []
    for h in hits:
        ib = _iban_compact(h)
        if ib and ib not in out:
            out.append(ib)
    return out


def _extract_sender_iban(raw: str) -> Optional[str]:
    s = _find(raw, r"\bIBAN\s*:\s*(TR[0-9\s]{20,})")
    return _iban_compact(s)


def _extract_receiver_iban(raw: str, sender_iban: Optional[str]) -> Optional[str]:
    labeled = _find(
        raw,
        r"Al[ıi]c[ıi]\s+Hesap\s*/\s*IBA\s*N\s+No\s*:\s*(TR[0-9\s]{20,})",
    )
    ib = _iban_compact(labeled)
    if ib and (not sender_iban or ib != sender_iban):
        return ib

    raw_fold = (raw or "").casefold()
    idx = raw_fold.find("alıcı banka")
    if idx == -1:
        idx = raw_fold.find("alici banka")
    tail = raw[idx:] if idx != -1 else raw

    for cand in _find_all_ibans(tail):
        if sender_iban and cand == sender_iban:
            continue
        return cand

    for cand in _find_all_ibans(raw):
        if sender_iban and cand == sender_iban:
            continue
        return cand

    return None


def parse_albaraka(
    pdf_path: Path,
    *,
    text_raw: Optional[str] = None,
    text_norm: Optional[str] = None,  # unused
) -> Dict:
    # Prefer cached text if provided; otherwise read normally.
    raw = text_raw if (text_raw is not None and text_raw.strip()) else _extract_text(pdf_path, max_pages=1)

    # Albaraka PDFs are often image-based => OCR is the reliable source when text layer is empty
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    sender_name = _find(
        raw,
        r"SAYIN\s+HES.{0,8}\s*SAHIBI\s*:\s*([^\n]+)",
    )

    receiver_name = _find(raw, r"Al[ıi]c[ıi]\s+Ad[ıi]\s*:\s*([^\n]+)")

    sender_iban = _extract_sender_iban(raw)
    receiver_iban = _extract_receiver_iban(raw, sender_iban)

    amount = _find(raw, r"Tutar\s*:\s*([0-9\.\,]+)")
    if amount:
        amount = f"{amount} TL"

    transaction_time = _find(
        raw,
        r"Tarih\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*[0-9]{2}:[0-9]{2}:[0-9]{2})",
    )

    receipt_no = _find(raw, r"Dekont\s+No\s*:\s*([0-9\/\-\s]+)")
    transaction_ref = _find(raw, r"Referans\s*No\s*:\s*([0-9]+)")

    return {
        "tr_status": "completed" if (raw or "").strip() else "unknown",
        "sender_name": sender_name,
        "sender_iban": sender_iban,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
