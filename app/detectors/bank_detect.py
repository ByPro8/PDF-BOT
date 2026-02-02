import re
from pathlib import Path
from typing import Callable, List, Tuple, Optional

from pypdf import PdfReader


def normalize_text(s: str) -> str:
    if not s:
        return ""

    s = s.casefold()

    tr_map = str.maketrans(
        {
            "ı": "i",
            "İ": "i",
            "ö": "o",
            "Ö": "o",
            "ü": "u",
            "Ü": "u",
            "ş": "s",
            "Ş": "s",
            "ğ": "g",
            "Ğ": "g",
            "ç": "c",
            "Ç": "c",
        }
    )

    s = s.translate(tr_map)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_pdf_text(pdf_path: Path, max_pages: int = 2) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
        return normalize_text("\n".join(parts))
    except Exception:
        return ""


def ocr_pdf_text(pdf_path: Path, max_pages: int = 1, dpi: int = 350) -> str:
    # optional OCR fallback (only works if deps + system packages exist)
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(
            str(pdf_path),
            first_page=1,
            last_page=max_pages,
            dpi=dpi,
        )

        parts = []
        for img in images:
            parts.append(pytesseract.image_to_string(img, lang="tur+eng"))

        return normalize_text("\n".join(parts))
    except Exception:
        return ""


# --- ZIRAAT (2 variants) ---
def is_ziraat_fast(text: str) -> bool:
    return ("ziraatbank.com.tr" in text) and (
        ("hesaptan fast" in text) or ("fast mesaj kodu" in text)
    )


def is_ziraat_havale(text: str) -> bool:
    return ("ziraatbank.com.tr" in text) and (
        ("hesaptan hesaba havale" in text) or ("havale tutari" in text)
    )


# --- YAPI KREDI (2 variants) ---
def is_yapi_kredi_edekont(text: str) -> bool:
    return ("yapikredi.com.tr" in text) and (
        ("e-dekont" in text) and ("elektronik ortamda uretilmistir" in text)
    )


def is_yapi_kredi_bilgi(text: str) -> bool:
    return ("yapikredi.com.tr" in text) and (
        ("bilgi dekontu" in text) and ("e-dekont yerine gecmez" in text)
    )


# --- other banks (domain-based) ---
def is_akbank(text: str) -> bool:
    return "akbank.com" in text


def is_denizbank(text: str) -> bool:
    return "denizbank.com" in text


def is_enpara(text: str) -> bool:
    return "enpara.com" in text


def is_garanti(text: str) -> bool:
    return "garantibbva.com.tr" in text


def is_vakifbank(text: str) -> bool:
    return "vakifbank.com.tr" in text


def is_vakifkatilim(text: str) -> bool:
    return "vakifkatilim.com.tr" in text


def is_teb(text: str) -> bool:
    return "teb.com.tr" in text


def is_kuveyt_turk(text: str) -> bool:
    return "kuveytturk.com.tr" in text


def is_ing(text: str) -> bool:
    return "ing.com.tr" in text


def is_turkiye_finans(text: str) -> bool:
    return "turkiyefinans.com.tr" in text


def is_isbank(text: str) -> bool:
    return "isbank.com.tr" in text


def is_halkbank(text: str) -> bool:
    return "halkbank.com.tr" in text


def is_qnb(text: str) -> bool:
    return "qnb.com.tr" in text


def is_pttbank(text: str) -> bool:
    return "pttbank.ptt.gov.tr" in text


def is_tombank(text: str) -> bool:
    return "tombank.com.tr" in text


# order matters: variants first
DETECTORS: List[Tuple[str, str, Optional[str], Callable[[str], bool]]] = [
    ("ZIRAAT_FAST", "Ziraat", "FAST", is_ziraat_fast),
    ("ZIRAAT_HAVALE", "Ziraat", "Havale", is_ziraat_havale),
    ("YAPI_BILGI", "YapiKredi", "Bilgi Dekontu", is_yapi_kredi_bilgi),
    ("YAPI_EDEKONT", "YapiKredi", "e-Dekont", is_yapi_kredi_edekont),
    ("AKBANK", "Akbank", None, is_akbank),
    ("DENIZBANK", "DenizBank", None, is_denizbank),
    ("ENPARA", "Enpara", None, is_enpara),
    ("GARANTI", "Garanti", None, is_garanti),
    ("VAKIFBANK", "VakifBank", None, is_vakifbank),
    ("VAKIFKATILIM", "VakifKatilim", None, is_vakifkatilim),
    ("TEB", "TEB", None, is_teb),
    ("KUVEYT_TURK", "KuveytTurk", None, is_kuveyt_turk),
    ("ING", "ING", None, is_ing),
    ("TURKIYE_FINANS", "TurkiyeFinans", None, is_turkiye_finans),
    ("ISBANK", "TurkiyeIsBankasi", None, is_isbank),
    ("HALKBANK", "Halkbank", None, is_halkbank),
    ("QNB", "QNB", None, is_qnb),
    ("PTTBANK", "PttBank", None, is_pttbank),
    ("TOMBANK", "TOM Bank", None, is_tombank),
]


def _detect(text: str) -> Optional[dict]:
    for key, bank, variant, fn in DETECTORS:
        if fn(text):
            return {"key": key, "bank": bank, "variant": variant}
    return None


def detect_bank_variant(pdf_path: Path, use_ocr_fallback: bool = False) -> dict:
    text = extract_pdf_text(pdf_path, max_pages=2)
    hit = _detect(text)
    if hit:
        hit["method"] = "text"
        return hit

    if use_ocr_fallback:
        ocr_text = ocr_pdf_text(pdf_path, max_pages=1, dpi=350)
        hit = _detect(ocr_text)
        if hit:
            hit["method"] = "ocr"
            return hit

    return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": "none"}
