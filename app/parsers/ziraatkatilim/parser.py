import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


# -----------------------------
# Basics
# -----------------------------
def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _norm(s: str) -> str:
    t = (s or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = t.replace("\u00a0", " ").replace("\u202f", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _extract_text_layer(pdf_path: Path, max_pages: int = 1) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    except Exception:
        return ""


# -----------------------------
# OCR helpers
# -----------------------------
def _ocr_image(img) -> str:
    try:
        import pytesseract
    except Exception:
        return ""

    config = "--psm 6"
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


def _ocr_first_page(pdf_path: Path, dpi: int = 320) -> str:
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


# -----------------------------
# Field extraction
# -----------------------------
_OCR_DIGIT_FIX = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "D": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
        "G": "6",
    }
)


def _iban_from_text(raw: str) -> Optional[str]:
    """Return IBAN as TR + 24 digits, correcting common OCR swaps."""
    if not raw:
        return None

    up = raw.upper()

    i = up.find("TR")
    window = up[i : i + 140] if i != -1 else up

    window = window.translate(_OCR_DIGIT_FIX)
    window = re.sub(r"[^0-9TR]", "", window)

    m = re.search(r"TR(\d{24})", window)
    if m:
        return "TR" + m.group(1)

    all_fixed = up.translate(_OCR_DIGIT_FIX)
    all_fixed = re.sub(r"[^0-9TR]", "", all_fixed)
    m2 = re.search(r"TR(\d{24})", all_fixed)
    if m2:
        return "TR" + m2.group(1)

    return None


def _clean_name_value(v: str) -> Optional[str]:
    if not v:
        return None
    v = v.strip()

    # remove leading OCR junk like "zAhmet" -> "Ahmet"
    v = re.sub(r"^[^A-Za-zÇĞİÖŞÜçğıöşü]+", "", v)

    # remove anything after glued labels
    v = re.split(
        r"\b(IBAN|Iban|Tutar|Dekont|Sorgu|Islem|İşlem|Vale|Val[oö]r)\b",
        v,
        maxsplit=1,
    )[0]

    v = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü'.\- ]+", " ", v)
    v = _clean(v)

    if not v:
        return None

    # must look like a name
    if len(v.split()) >= 2:
        return v
    if len(v) >= 6:
        return v
    return None


def _extract_receiver_name(raw: str) -> Optional[str]:
    """
    OCR in tr22.pdf shows:
      "Alic1 Ach :Ahmet Yaprak"
    (1 instead of i, and Ach instead of Adi)

    Strategy:
      - scan lines
      - match label like: (Alici/Alic1/4lici) + (A... short token) + ':' + value
      - clean the value
    """
    if not raw:
        return None

    for ln in raw.splitlines():
        line = ln.strip()
        if not line:
            continue

        # Example match: "Alic1 Ach :Ahmet Yaprak"
        m = re.search(
            r"(?i)^\s*(?:4|A)lic[ıi1]\s+A\w{1,5}\s*[:=\-]\s*([^\n]{2,120})\s*$",
            line,
        )
        if m:
            v = _clean_name_value(m.group(1))
            if v:
                return v

        # More standard cases:
        m2 = re.search(
            r"(?i)^\s*(?:4|A)lic[ıi1]\s+Ad[ıi1]?\w{0,3}\s*[:=\-]?\s*([^\n]{2,120})\s*$",
            line,
        )
        if m2:
            v = _clean_name_value(m2.group(1))
            if v:
                return v

    # fallback: try whole raw (in case OCR collapsed lines)
    m3 = re.search(
        r"(?i)(?:^|\n)\s*(?:4|A)lic[ıi1]\s+A\w{1,5}\s*[:=\-]\s*([^\n]{2,120})",
        raw,
    )
    if m3:
        return _clean_name_value(m3.group(1))

    return None


def _extract_amount(raw: str) -> Optional[str]:
    m = re.search(
        r"(?:^|\n)\s*Tutar\s*[:\-]?\s*([0-9]{1,3}(?:[.\s][0-9]{3})*(?:[,\.][0-9]{2}))\s*(TRY|TL)\b",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        num = m.group(1).replace(" ", "")
        cur = m.group(2).upper().replace("TRY", "TL")
        return f"{num} {cur}"

    cands = re.findall(r"\b\d{1,3}(?:[.\s]\d{3})*(?:[,\.]\d{2})\b", raw)
    if not cands:
        return None

    def to_float(s: str) -> float:
        s = s.replace(" ", "")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    best = max(cands, key=to_float)
    return f"{best.replace(' ', '')} TL"


def _extract_time(raw: str) -> Optional[str]:
    for lab in ["İŞLEM TARİHİ", "ISLEM TARIHI", "DUZENLEME TARIHI", "DÜZENLEME TARIHI"]:
        m = re.search(
            rf"(?:^|\n)\s*{lab}\s*[:=\-]?\s*(\d{{2}}[./-]\d{{2}}[./-]\d{{4}}\s+\d{{2}}:\d{{2}}:\d{{2}})",
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            v = m.group(1).replace("/", ".").replace("-", ".")
            return _clean(v)

    m2 = re.search(r"\b(\d{2}[./-]\d{2}[./-]\d{4})\s+(\d{2}:\d{2}:\d{2})\b", raw)
    if m2:
        d = m2.group(1).replace("/", ".").replace("-", ".")
        return f"{d} {m2.group(2)}"
    return None


def _extract_receipt_no(raw: str) -> Optional[str]:
    m = re.search(
        r"(?:^|\n)\s*DEKONT\s*NO\s*/\s*FIS\s*NO\s*[:=\-]?\s*([0-9]{3,20}(?:/[0-9]{2,20})?)",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return _clean(m.group(1))

    m2 = re.search(
        r"(?:^|\n)\s*DEKONT\s*NO[^0-9]*([0-9]{3,20}(?:/[0-9]{2,20})?)",
        raw,
        flags=re.IGNORECASE,
    )
    return _clean(m2.group(1)) if m2 else None


def _extract_tx_ref(raw: str) -> Optional[str]:
    m = re.search(
        r"(?:^|\n)\s*Sorgu\s*Numarasi\s*[:=\-]?\s*([0-9]{6,12})\b",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return _clean(m.group(1))

    n = _norm(raw)
    j = n.find("sorgu")
    window = n[j : j + 220] if j != -1 else n
    nums = re.findall(r"\b\d{8}\b", window)
    return nums[0] if nums else None


def parse_ziraatkatilim(pdf_path: Path) -> Dict:
    raw = _extract_text_layer(pdf_path, max_pages=1)
    if not raw.strip():
        raw = _ocr_first_page(pdf_path)

    raw = raw or ""

    receiver_name = _extract_receiver_name(raw)
    receiver_iban = _iban_from_text(raw)
    amount = _extract_amount(raw)
    transaction_time = _extract_time(raw)
    receipt_no = _extract_receipt_no(raw)
    transaction_ref = _extract_tx_ref(raw)

    sender_name = None  # masked in this template; don't guess

    n = _norm(raw)
    tr_status = "completed" if ("dekont" in n or "fast" in n) else "unknown"

    return {
        "tr_status": "FUCK ZIRAAT KATILIM ",
        "sender_name": "FUCK ZIRAAT KATILIM ",
        "receiver_name": "FUCK ZIRAAT KATILIM ",
        "receiver_iban": "FUCK ZIRAAT KATILIM ",
        "amount": "FUCK ZIRAAT KATILIM ",
        "transaction_time": "FUCK ZIRAAT KATILIM ",
        "receipt_no": "FUCK ZIRAAT KATILIM ",
        "transaction_ref": "FUCK ZIRAAT KATILIM ",
    }
