import re
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader

# Optional OCR fallback: keep import inside function so it doesn't break deployments
# if pytesseract isn't installed.


def extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def normalize_text(text: str) -> str:
    """
    Normalize text for robust matching:
    - casefold
    - remove Turkish dotted-i combining dot (U+0307) that appears after casefold on some PDFs
    - map TR chars to ASCII-ish
    - collapse whitespace
    """
    t = (text or "").casefold().replace("\u0307", "")
    tr = str.maketrans(
        {
            "ı": "i",
            "ö": "o",
            "ü": "u",
            "ş": "s",
            "ğ": "g",
            "ç": "c",
        }
    )
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ----------------------------
# Bank detectors (bool)
# ----------------------------


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def is_pttbank(text: str) -> bool:
    t = text
    # HARD RULE: require official site
    has_site = _has_any(t, ["pttbank.ptt.gov.tr"])
    if not has_site:
        return False

    # sanity signals
    return _has_any(t, ["pttbank", "ptt bank", "ptt"])


def is_halkbank(text: str) -> bool:
    t = text
    # HARD RULE: require official site
    has_site = _has_any(t, ["halkbank.com.tr", "www.halkbank.com.tr"])
    if not has_site:
        return False

    # sanity signals
    return _has_any(t, ["halkbank", "halk bankasi", "dekont", "internet sube", "mobil"])


def is_tombank(text: str) -> bool:
    t = text
    # HARD RULE: require official site
    has_site = _has_any(t, ["tombank.com.tr", "www.tombank.com.tr"])
    if not has_site:
        return False

    # sanity signals
    return _has_any(t, ["tom bank", "tombank", "dekont", "mobil", "internet"])


def is_isbank(text: str) -> bool:
    t = text  # already normalized in detect_bank_variant()

    # HARD RULE: detect Isbank only when the official website exists in the PDF.
    # This prevents false positives when other banks mention "Türkiye İş Bankası" as counter bank.
    has_site = _has_any(t, ["www.isbank.com.tr", "isbank.com.tr"])
    if not has_site:
        return False

    # Extra sanity: typical Isbank receipt headers/phrases
    looks_like_isbank_receipt = _has_any(
        t,
        [
            "e-dekont",
            "bilgi dekontu",
            "iscep",
            "musteri no",
            "mușteri no",  # some PDFs produce odd combining chars; keep both
        ],
    )

    return looks_like_isbank_receipt


def is_turkiye_finans(text: str) -> bool:
    t = text
    # HARD RULE: require official site
    has_site = _has_any(t, ["www.turkiyefinans.com.tr", "turkiyefinans.com.tr"])
    if not has_site:
        return False

    # sanity signals
    return _has_any(
        t, ["turkiye finans", "turkiyefinans", "dekont", "fast", "referans no"]
    )


def is_ing(text: str) -> bool:
    t = text
    # HARD RULE: require official site
    has_site = _has_any(t, ["www.ing.com.tr", "ing.com.tr"])
    if not has_site:
        return False

    # sanity signals (keep minimal, but helpful)
    return _has_any(t, ["ing bank", "ingbank", "dekont", "fon transfer", "fast"])


def is_qnb(text: str) -> bool:
    t = text
    # HARD RULE: require official site OR strong QNB platform signals
    has_site = _has_any(t, ["qnb.com.tr", "www.qnb.com.tr"])
    strong = _has_any(
        t,
        [
            "qnb mobil",
            "qnb internet",
            "qnb finansbank",
            "finansbank",
            "alici unvani",
            "sorgu no",
            "fis no",
        ],
    )
    # Must have QNB + (site OR strong signals)
    return ("qnb" in t) and (has_site or strong)


def is_kuveyt_turk(text: str) -> bool:
    # fallback only: domain present
    return _has_any(text, ["kuveytturk.com.tr", "www.kuveytturk.com.tr"])


# --- KuveytTurk variants ---
# text is already normalized by normalize_text()


def is_kuveyt_turk_en(text: str) -> bool:
    """
    EN variant (English template).
    Requires:
    - kuveytturk.com.tr
    AND at least one strong English signal.
    """
    t = text
    has_site = _has_any(t, ["kuveytturk.com.tr", "www.kuveytturk.com.tr"])
    if not has_site:
        return False

    return _has_any(
        t,
        [
            "kuveyt turk participation bank",
            "money transfer to iban",
            "outgoing",
            "transactiondate",
            "query number",
        ],
    )


def is_kuveyt_turk_tr(text: str) -> bool:
    """
    TR variant (Turkish template).
    Requires:
    - kuveytturk.com.tr
    AND at least one strong Turkish signal.
    """
    t = text
    has_site = _has_any(t, ["kuveytturk.com.tr", "www.kuveytturk.com.tr"])
    if not has_site:
        return False

    return _has_any(
        t,
        [
            "kuveyt turk katilim bankasi",
            "iban'a para transferi",
            "mobil sube",
            "aciklama",
            "sorgu numarasi",
            "islem tarihi",
        ],
    )


Detector = tuple[str, str, Optional[str], Callable[[str], bool]]

# IMPORTANT:
# - Put more specific templates BEFORE generic ones.
DETECTORS: list[Detector] = [
    ("PTTBANK", "PttBank", None, is_pttbank),
    ("HALKBANK", "Halkbank", None, is_halkbank),
    ("TOMBANK", "TOM Bank", None, is_tombank),
    # Isbank strict (website + receipt signals)
    ("ISBANK", "Isbank", None, is_isbank),
    # Website-based strict
    ("TURKIYE_FINANS", "TurkiyeFinans", None, is_turkiye_finans),
    ("ING", "ING", None, is_ing),
    # KuveytTurk variants first
    ("KUVEYT_TURK_EN", "KuveytTurk", "EN", is_kuveyt_turk_en),
    ("KUVEYT_TURK_TR", "KuveytTurk", "TR", is_kuveyt_turk_tr),
    # QNB strict (site or strong platform signals)
    ("QNB", "QNB", None, is_qnb),
    # fallback if domain exists but we can't classify
    ("KUVEYT_TURK", "KuveytTurk", "UNKNOWN", is_kuveyt_turk),
]


def _ocr_text(pdf_path: Path) -> str:
    # optional OCR fallback (only if you enabled it)
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0]) or ""


def detect_bank_variant(pdf_path: Path, use_ocr_fallback: bool = False) -> dict:
    raw = extract_text(pdf_path, max_pages=2)
    text = normalize_text(raw)

    method = "text"
    if not text and use_ocr_fallback:
        raw2 = _ocr_text(pdf_path)
        text = normalize_text(raw2)
        method = "ocr" if text else "none"

    for key, bank_name, variant, pred in DETECTORS:
        try:
            if pred(text):
                return {
                    "key": key,
                    "bank": bank_name,
                    "variant": variant,
                    "method": method,
                }
        except Exception:
            continue

    return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": method}
