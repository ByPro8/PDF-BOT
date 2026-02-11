import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple

from pypdf import PdfReader


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _norm(s: str) -> str:
    t = (s or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _extract_text(pdf_path: Path, max_pages: int = 1) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])


def _ocr_image(img) -> str:
    """Run OCR on a PIL image with decent defaults."""
    try:
        import pytesseract
    except Exception:
        return ""

    config = "--psm 6"
    # try tur+eng if available, fallback to default
    try:
        txt = pytesseract.image_to_string(img, lang="tur+eng", config=config) or ""
        if txt.strip():
            return txt
    except Exception:
        pass

    try:
        return pytesseract.image_to_string(img, config=config) or ""
    except Exception:
        return ""


def _ocr_first_page(pdf_path: Path, dpi: int = 300) -> str:
    """OCR full first page (general)."""
    try:
        from pdf2image import convert_from_path
        from PIL import ImageOps
    except Exception:
        return ""

    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=dpi)
        if not images:
            return ""
        img = images[0]
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        return _ocr_image(img)
    except Exception:
        return ""


def _ocr_crop_recipient_block(pdf_path: Path, dpi: int = 300) -> str:
    """
    Targeted OCR: crop the LOWER-LEFT transaction block where:
      'Alici IBAN No', 'Alici Adi', 'Tutar', 'Sorgu Numarasi' appear.
    This avoids the noisy 'HESAP SAHIBI' boxes that OCR mangles.
    """
    try:
        from pdf2image import convert_from_path
        from PIL import ImageOps
    except Exception:
        return ""

    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=dpi)
        if not images:
            return ""
        img = images[0]
        w, h = img.size

        # These ratios are tuned for the layout shown in your tr22.pdf. :contentReference[oaicite:1]{index=1}
        # Crop: left ~6% to 62% width, top ~44% to 78% height (the transaction info list).
        x1 = int(w * 0.05)
        x2 = int(w * 0.62)
        y1 = int(h * 0.43)
        y2 = int(h * 0.79)

        crop = img.crop((x1, y1, x2, y2))
        crop = ImageOps.grayscale(crop)
        crop = ImageOps.autocontrast(crop)
        return _ocr_image(crop)
    except Exception:
        return ""


def _iban_from_text(raw: str) -> Optional[str]:
    if not raw:
        return None
    # strict: TR + 24 chars (digits usually, OCR may insert letters, but we keep A-Z too)
    compact = re.sub(r"[^0-9A-Z]", "", raw.upper())
    m = re.search(r"TR[0-9A-Z]{24}", compact)
    return m.group(0) if m else None


def _iban_after_label(raw: str, label_norm: str) -> Optional[str]:
    n = _norm(raw)
    m = re.search(label_norm, n, flags=re.IGNORECASE)
    if not m:
        return None
    # Use a raw window to preserve 'TR' chunking
    raw_win = raw[m.end() : m.end() + 800]
    return _iban_from_text(raw_win) or _iban_from_text(raw)


def _parse_tr_amount_to_float(s: str) -> Optional[float]:
    if not s:
        return None
    s = re.sub(r"[^0-9\.,]", "", s).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _extract_amount(raw: str) -> Optional[str]:
    n = _norm(raw)
    cands = re.findall(r"\b\d{1,3}(?:[.\s]\d{3})*(?:[,\.]\d{2})\b", n)
    vals: List[Tuple[float, str]] = []
    for c in cands:
        v = _parse_tr_amount_to_float(c)
        if v is not None and v > 0.0:
            vals.append((v, c))
    if not vals:
        return None
    _, c = max(vals, key=lambda x: x[0])
    return f"{c.replace(' ', '')} TL"


def _extract_transaction_time(raw: str) -> Optional[str]:
    n = _norm(raw)
    m = re.search(
        r"islem\s*tarihi\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4}\s+\d{2}:\d{2}:\d{2})", n
    )
    if m:
        return _clean(m.group(1))
    m = re.search(r"(\d{2}[./-]\d{2}[./-]\d{4}\s+\d{2}:\d{2}:\d{2})", n)
    return _clean(m.group(1)) if m else None


def _extract_receipt_no(raw: str) -> Optional[str]:
    n = _norm(raw)
    m = re.search(r"dekont\s*no[^0-9]*([0-9]{3,20}(?:/[0-9]{2,20})?)", n)
    return _clean(m.group(1)) if m else None


def _extract_transaction_ref(raw: str) -> Optional[str]:
    n = _norm(raw)
    m = re.search(r"sorgu\s*numarasi", n, flags=re.IGNORECASE)
    window = n[m.end() : m.end() + 250] if m else n

    nums = re.findall(r"\b\d{6,12}\b", window)
    if not nums:
        nums = re.findall(r"\b\d{6,12}\b", n)
    if not nums:
        return None

    for x in nums:
        if len(x) == 8:
            return x

    x = max(nums, key=len)
    return x[-8:] if len(x) > 8 else x


def _looks_like_garbage_name(s: str) -> bool:
    """
    Reject OCR garbage like: Qttte Seeeeeee
    """
    if not s:
        return True
    # too many repeated letters
    if re.search(r"(.)\1\1\1", s, flags=re.IGNORECASE):
        return True
    # too few vowels for a Turkish/Latin name
    letters = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü]", "", s)
    if len(letters) < 5:
        return True
    vowels = re.findall(r"[aeiouAEIOUıİöÖüÜ]", s)
    if len(vowels) == 0:
        return True
    return False


def _extract_name_after_label(raw: str, label_pat: str) -> Optional[str]:
    m = re.search(label_pat, raw, flags=re.IGNORECASE)
    if not m:
        return None
    cand = m.group(1)
    cand = re.split(r"(IBAN|Iban|Tutar|Islem|Dekont|Sorgu)\b", cand, maxsplit=1)[0]
    cand = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü'.\- ]+", " ", cand)
    cand = _clean(cand)
    if not cand or _looks_like_garbage_name(cand):
        return None
    # require at least 2 words
    if len(cand.split()) < 2:
        return None
    return cand


def parse_ziraatkatilim(pdf_path: Path) -> Dict:
    # Try text layer first (usually empty for this bank)
    raw = _extract_text(pdf_path, max_pages=1)

    # If empty, do OCR full page
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    # ALSO do targeted crop OCR for the actual transaction block
    crop_raw = _ocr_crop_recipient_block(pdf_path)

    # Combine: crop text first because it's cleaner for these fields
    combined_for_fields = (crop_raw.strip() + "\n" + raw.strip()).strip()

    # Prefer "Alici" fields from crop OCR, fallback to full OCR
    receiver_iban = (
        _iban_after_label(crop_raw, r"alici\s*iban")
        or _iban_after_label(raw, r"alici\s*iban")
        or _iban_from_text(combined_for_fields)
    )

    receiver_name = _extract_name_after_label(
        crop_raw, r"Alici\s*Ad[iı]\s*[:\-]?\s*([^\n]{2,120})"
    ) or _extract_name_after_label(raw, r"Alici\s*Ad[iı]\s*[:\-]?\s*([^\n]{2,120})")

    # Sender name often masked/boxed; only extract if an explicit sender label exists
    sender_name = (
        _extract_name_after_label(
            crop_raw, r"Gonderen\s*Ad[iı]\s*[:\-]?\s*([^\n]{2,120})"
        )
        or _extract_name_after_label(
            raw, r"Gonderen\s*Ad[iı]\s*[:\-]?\s*([^\n]{2,120})"
        )
        or None
    )

    amount = _extract_amount(combined_for_fields)
    transaction_time = _extract_transaction_time(combined_for_fields)
    receipt_no = _extract_receipt_no(combined_for_fields)
    transaction_ref = _extract_transaction_ref(combined_for_fields)

    n = _norm(combined_for_fields)
    tr_status = "completed" if ("dekont" in n or "fast" in n) else "unknown"

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
