import re
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader


def extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    """Fast text-layer extraction (first N pages)."""
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def normalize_text(text: str) -> str:
    """Normalize for robust substring checks (TR letters + whitespace + dotted-i bug)."""
    t = (text or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ----------------------------
# Bank detectors (high precision: prefer official website domains)
# ----------------------------
def is_pttbank(text: str) -> bool:
    t = normalize_text(text)
    return "pttbank.ptt.gov.tr" in t


def is_halkbank(text: str) -> bool:
    t = normalize_text(text)
    return ("www.halkbank.com.tr" in t) or ("halkbank.com.tr" in t)


def is_tombank(text: str) -> bool:
    t = normalize_text(text)
    return ("www.tombank.com.tr" in t) or ("tombank.com.tr" in t)


def is_isbank(text: str) -> bool:
    t = normalize_text(text)

    has_site = ("www.isbank.com.tr" in t) or ("isbank.com.tr" in t)
    if not has_site:
        return False

    looks_like_receipt = (
        ("e-dekont" in t)
        or ("bilgi dekontu" in t)
        or ("iscep" in t)
        or ("musteri no" in t)
        or ("mușteri no" in t)
    )
    return looks_like_receipt


def is_turkiye_finans(text: str) -> bool:
    t = normalize_text(text)
    return ("www.turkiyefinans.com.tr" in t) or ("turkiyefinans.com.tr" in t)


def is_ing(text: str) -> bool:
    t = normalize_text(text)
    return ("www.ing.com.tr" in t) or ("ing.com.tr" in t)


def is_teb(text: str) -> bool:
    t = normalize_text(text)
    return ("www.teb.com.tr" in t) or ("teb.com.tr" in t)


def is_qnb(text: str) -> bool:
    t = normalize_text(text)
    return ("www.qnb.com.tr" in t) or ("qnb.com.tr" in t)


def is_kuveyt_turk(text: str) -> bool:
    t = normalize_text(text)
    return ("kuveytturk.com.tr" in t) or ("www.kuveytturk.com.tr" in t)


def is_kuveyt_turk_en(text: str) -> bool:
    t = normalize_text(text)
    return ("kuveytturk.com.tr" in t) and (
        ("kuveyt turk participation bank" in t)
        or ("money transfer to iban" in t)
        or ("outgoing" in t)
        or ("transactiondate" in t)
        or ("query number" in t)
    )


def is_kuveyt_turk_tr(text: str) -> bool:
    t = normalize_text(text)
    return ("kuveytturk.com.tr" in t) and (
        ("kuveyt turk katilim bankasi" in t)
        or ("iban'a para transferi" in t)
        or ("mobil sube" in t)
        or ("aciklama" in t)
        or ("sorgu numarasi" in t)
        or ("islem tarihi" in t)
    )


Detector = tuple[str, str, Optional[str], Callable[[str], bool]]

DETECTORS: list[Detector] = [
    ("PTTBANK", "PttBank", None, is_pttbank),
    ("HALKBANK", "Halkbank", None, is_halkbank),
    ("TOMBANK", "TOM Bank", None, is_tombank),
    ("ISBANK", "Isbank", None, is_isbank),
    ("TURKIYE_FINANS", "TurkiyeFinans", None, is_turkiye_finans),
    ("ING", "ING", None, is_ing),
    ("TEB", "TEB", None, is_teb),

    # KuveytTurk variants first
    ("KUVEYT_TURK_EN", "KuveytTurk", "EN", is_kuveyt_turk_en),
    ("KUVEYT_TURK_TR", "KuveytTurk", "TR", is_kuveyt_turk_tr),

    ("QNB", "QNB", None, is_qnb),

    # Kuveyt fallback
    ("KUVEYT_TURK", "KuveytTurk", "UNKNOWN", is_kuveyt_turk),
]


def _ocr_text(pdf_path: Path) -> str:
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
                return {"key": key, "bank": bank_name, "variant": variant, "method": method}
        except Exception:
            continue

    return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": method}
