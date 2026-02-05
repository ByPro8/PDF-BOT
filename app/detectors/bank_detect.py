import re
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader


def extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    t = (text or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def has_domain(text_norm: str, domain: str) -> bool:
    t = text_norm or ""
    compact = re.sub(r"\s+", "", t)

    dom = domain.casefold().strip()
    if dom in t or dom in compact:
        return True

    dom_no_www = dom.replace("www.", "")
    parts = [re.escape(p) for p in dom_no_www.split(".") if p]
    if not parts:
        return False

    pat = r"(?:www\s*\.\s*)?" + r"\s*\.\s*".join(parts)
    return re.search(pat, t, flags=re.I) is not None


# WEBSITE-ONLY detectors
def is_pttbank(text_norm: str) -> bool:
    return has_domain(text_norm, "pttbank.ptt.gov.tr")


def is_halkbank(text_norm: str) -> bool:
    return has_domain(text_norm, "halkbank.com.tr")


def is_tombank(text_norm: str) -> bool:
    return has_domain(text_norm, "tombank.com.tr")


def is_isbank(text_norm: str) -> bool:
    if not has_domain(text_norm, "isbank.com.tr"):
        return False
    return any(k in text_norm for k in ["e-dekont", "bilgi dekontu", "iscep", "musteri no", "mușteri no"])


def is_turkiye_finans(text_norm: str) -> bool:
    return has_domain(text_norm, "turkiyefinans.com.tr")


def is_ing(text_norm: str) -> bool:
    return has_domain(text_norm, "ing.com.tr")


def is_teb(text_norm: str) -> bool:
    return has_domain(text_norm, "teb.com.tr")


def is_vakif_katilim(text_norm: str) -> bool:
    return has_domain(text_norm, "vakifkatilim.com.tr")


def is_vakifbank(text_norm: str) -> bool:
    return has_domain(text_norm, "vakifbank.com.tr")


def is_garanti(text_norm: str) -> bool:
    return has_domain(text_norm, "garantibbva.com.tr")


def is_enpara(text_norm: str) -> bool:
    return has_domain(text_norm, "enpara.com")


def is_qnb(text_norm: str) -> bool:
    return has_domain(text_norm, "qnb.com.tr")


def is_kuveyt_turk(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr")


def is_kuveyt_turk_en(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr") and any(
        k in text_norm
        for k in ["kuveyt turk participation bank", "money transfer to iban", "outgoing", "transactiondate", "query number"]
    )


def is_kuveyt_turk_tr(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr") and any(
        k in text_norm
        for k in ["kuveyt turk katilim bankasi", "iban'a para transferi", "mobil sube", "aciklama", "sorgu numarasi", "islem tarihi"]
    )


# TEXT-ANCHOR detector (Deniz PDFs don't include website domain)
def is_denizbank(text_norm: str) -> bool:
    # Strong anchors: "denizbank a.s." + "dekont fast"
    if "denizbank a.s." in text_norm and "dekont fast" in text_norm:
        return True
    # Fallback: still very Deniz-specific
    return ("denizbank a.s." in text_norm) and ("mobildeniz" in text_norm or "fast sorgu numarasi" in text_norm)


Detector = tuple[str, str, Optional[str], Callable[[str], bool]]

DETECTORS: list[Detector] = [
    ("DENIZBANK", "DenizBank", None, is_denizbank),

    ("PTTBANK", "PttBank", None, is_pttbank),
    ("HALKBANK", "Halkbank", None, is_halkbank),
    ("TOMBANK", "TOM Bank", None, is_tombank),
    ("ISBANK", "Isbank", None, is_isbank),
    ("TURKIYE_FINANS", "TurkiyeFinans", None, is_turkiye_finans),
    ("ING", "ING", None, is_ing),
    ("TEB", "TEB", None, is_teb),
    ("VAKIF_KATILIM", "VakifKatilim", None, is_vakif_katilim),
    ("VAKIFBANK", "VakifBank", None, is_vakifbank),
    ("GARANTI", "Garanti", None, is_garanti),
    ("ENPARA", "Enpara", None, is_enpara),

    ("KUVEYT_TURK_EN", "KuveytTurk", "EN", is_kuveyt_turk_en),
    ("KUVEYT_TURK_TR", "KuveytTurk", "TR", is_kuveyt_turk_tr),

    ("QNB", "QNB", None, is_qnb),
    ("KUVEYT_TURK", "KuveytTurk", "UNKNOWN", is_kuveyt_turk),
]


def detect_bank_variant(pdf_path: Path, use_ocr_fallback: bool = False) -> dict:
    raw = extract_text(pdf_path, max_pages=2)
    text_norm = normalize_text(raw)
    method = "text"

    if (not text_norm) and use_ocr_fallback:
        try:
            from pdf2image import convert_from_path
            import pytesseract

            images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
            ocr_raw = pytesseract.image_to_string(images[0]) if images else ""
            text_norm = normalize_text(ocr_raw)
            method = "ocr" if text_norm else "none"
        except Exception:
            method = "none"
            text_norm = ""

    for key, bank_name, variant, pred in DETECTORS:
        try:
            if pred(text_norm):
                return {"key": key, "bank": bank_name, "variant": variant, "method": method}
        except Exception:
            continue

    return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": method}
