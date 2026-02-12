import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


# -------------------------
# Utils
# -------------------------
def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _norm(s: str) -> str:
    # OCR-safe normalize for matching labels (TR letters + whitespace)
    t = (s or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


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
    """
    Keep it simple (like your original): OCR first page only.
    If you want better OCR later we can add grayscale/autocontrast like Ziraat.
    """
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


# -------------------------
# Field extraction
# -------------------------
def _extract_sender_iban(raw: str) -> Optional[str]:
    s = _find(raw, r"\bIBAN\s*[:\-]?\s*(TR[0-9\s]{20,})")
    return _iban_compact(s)


def _extract_receiver_iban(raw: str, sender_iban: Optional[str]) -> Optional[str]:
    # Prefer the labeled "Alıcı ... IBAN"
    labeled = _find(
        raw,
        r"Al[ıi]c[ıi]\s+Hesap\s*/\s*I?BA\s*N\s+No\s*[:\-]?\s*(TR[0-9\s]{20,})",
    )
    ib = _iban_compact(labeled)
    if ib and (not sender_iban or ib != sender_iban):
        return ib

    # Otherwise: take first IBAN after "alıcı banka" area, else any IBAN not equal to sender
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


def _extract_amount(raw: str) -> Optional[str]:
    # "Tutar : 41.424,00 TRY" or "Tutar : 41.424,00 TL"
    m = re.search(
        r"Tutar\s*[:\-]?\s*([0-9\.\,]+)\s*(TRY|TL)\b", raw, flags=re.IGNORECASE
    )
    if m:
        val = m.group(1).strip()
        cur = m.group(2).upper().replace("TRY", "TL")
        return f"{val} {cur}"

    # fallback: any X,YY TRY/TL in doc
    m2 = re.search(
        r"\b([0-9]{1,3}(?:[.\s][0-9]{3})*(?:[,\.][0-9]{2})?)\s*(TRY|TL)\b",
        raw,
        flags=re.IGNORECASE,
    )
    if m2:
        val = m2.group(1).replace(" ", "").strip()
        cur = m2.group(2).upper().replace("TRY", "TL")
        return f"{val} {cur}"

    return None


def _extract_datetime(raw: str) -> Optional[str]:
    """
    Albaraka layouts vary:
      - "Tarih : 09.02.2026 21:27:56"
      - "İşlem Tarihi : 09.02.2026 21:27:56"
      - "Duzenleme Tarihi : 09.02.2026 21:27:56"
    OCR may turn '.' into '/' etc.
    """
    n = _norm(raw)

    # Try label-based first (most reliable)
    label_pats = [
        r"(?:islem tarihi|işlem tarihi)\s*[:\-]?\s*",
        r"(?:duzenleme tarihi|düzenleme tarihi)\s*[:\-]?\s*",
        r"\btarih\b\s*[:\-]?\s*",
        r"\bsaat\b\s*[:\-]?\s*",
    ]
    dt_pat = r"(\d{2}[./-]\d{2}[./-]\d{4}\s+\d{2}:\d{2}:\d{2})"
    for lp in label_pats:
        m = re.search(lp + dt_pat, n, flags=re.IGNORECASE)
        if m:
            return _clean(m.group(1).replace("/", ".").replace("-", "."))

    # Fallback: any datetime anywhere
    m2 = re.search(dt_pat, n)
    if m2:
        return _clean(m2.group(1).replace("/", ".").replace("-", "."))

    return None


def _extract_receipt_no(raw: str) -> Optional[str]:
    """
    You previously matched only "Dekont No".
    But you also see: "Dekont No/Fiş No", "Fis No", etc.
    """
    n = _norm(raw)

    # Look for the "dekont/fis" block and capture the value (supports 1588191/156381 etc)
    m = re.search(
        r"(?:dekont\s*no(?:/\s*fis\s*no)?|fis\s*no)\s*[:\-]?\s*([0-9]{3,20}(?:\s*/\s*[0-9]{2,20})?)",
        n,
        flags=re.IGNORECASE,
    )
    if m:
        return _clean(m.group(1).replace(" ", ""))

    return None


def _extract_transaction_ref(raw: str) -> Optional[str]:
    """
    Depending on layout it can be:
      - "Referans No : 4081697"
      - "Sorgu No : 4081697"
      - "İşlem No : ..."
    """
    n = _norm(raw)

    # label-based window, then grab a decent-length number
    m = re.search(
        r"(referans\s*no|sorgu\s*no|islem\s*no)\s*[:\-]?\s*", n, flags=re.IGNORECASE
    )
    win = n[m.end() : m.end() + 120] if m else n

    nums = re.findall(r"\b[0-9]{6,20}\b", win)
    if nums:
        # prefer longest
        return max(nums, key=len)

    # fallback: any 6-20 digit number near end (less reliable)
    nums2 = re.findall(r"\b[0-9]{6,20}\b", n)
    if nums2:
        return max(nums2, key=len)

    return None


def parse_albaraka(
    pdf_path: Path,
    *,
    text_raw: Optional[str] = None,
    text_norm: Optional[str] = None,  # unused, kept for compatibility
) -> Dict:
    # text layer first, OCR fallback
    raw = (
        text_raw
        if (text_raw and text_raw.strip())
        else _extract_text(pdf_path, max_pages=1)
    )
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    # Names (keep your working patterns)
    sender_name = _find(raw, r"SAYIN\s+HES.{0,12}\s*SAHIBI\s*[:\-]?\s*([^\n]+)")
    receiver_name = _find(raw, r"Al[ıi]c[ıi]\s+Ad[ıi]\s*[:\-]?\s*([^\n]+)")

    sender_iban = _extract_sender_iban(raw)
    receiver_iban = _extract_receiver_iban(raw, sender_iban)

    amount = _extract_amount(raw)
    transaction_time = _extract_datetime(raw)
    receipt_no = _extract_receipt_no(raw)
    transaction_ref = _extract_transaction_ref(raw)

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
