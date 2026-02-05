import re
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader


def extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    """Fast text-layer extraction (first N pages)."""
    try:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    """Normalize for robust substring checks (TR letters + whitespace + dotted-i)."""
    t = (text or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    # keep line breaks as spaces, but collapse repeated whitespace
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def has_domain(text_norm: str, domain: str) -> bool:
    """
    Website-only detection that survives PDF text-layer weirdness:
    - spaces/newlines around dots
    - split "www . domain . com . tr"
    """
    t = text_norm or ""
    compact = re.sub(r"\s+", "", t)

    dom = domain.casefold().strip()
    if dom in t or dom in compact:
        return True

    # Build regex allowing whitespace around dots
    dom_no_www = dom.replace("www.", "")
    parts = [re.escape(p) for p in dom_no_www.split(".") if p]
    if not parts:
        return False

    pat = r"(?:www\s*\.\s*)?" + r"\s*\.\s*".join(parts)
    return re.search(pat, t, flags=re.I) is not None


# ----------------------------
# Bank detectors (WEBSITE-ONLY)
# ----------------------------
def is_pttbank(text_norm: str) -> bool:
    return has_domain(text_norm, "pttbank.ptt.gov.tr")


def is_halkbank(text_norm: str) -> bool:
    return has_domain(text_norm, "halkbank.com.tr")


def is_tombank(text_norm: str) -> bool:
    return has_domain(text_norm, "tombank.com.tr")


def is_isbank(text_norm: str) -> bool:
    # Website-only + extra markers to avoid collisions
    if not has_domain(text_norm, "isbank.com.tr"):
        return False
    return any(
        k in text_norm
        for k in [
            "e-dekont",
            "bilgi dekontu",
            "iscep",
            "musteri no",
            "mușteri no",
        ]
    )


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


def is_qnb(text_norm: str) -> bool:
    return has_domain(text_norm, "qnb.com.tr")


def is_ziraat(text_norm: str) -> bool:
    return has_domain(text_norm, "ziraatbank.com.tr")


def is_ziraat_fast(text_norm: str) -> bool:
    if not is_ziraat(text_norm):
        return False
    return (
        ("hesaptan fast" in text_norm)
        or ("fast mesaj kodu" in text_norm)
        or ("fast sorgu no" in text_norm)
    )


def is_ziraat_havale(text_norm: str) -> bool:
    if not is_ziraat(text_norm):
        return False
    return "hesaptan hesaba havale" in text_norm


def is_kuveyt_turk(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr")


def is_kuveyt_turk_en(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr") and any(
        k in text_norm
        for k in [
            "kuveyt turk participation bank",
            "money transfer to iban",
            "outgoing",
            "transactiondate",
            "query number",
        ]
    )


def is_kuveyt_turk_tr(text_norm: str) -> bool:
    return has_domain(text_norm, "kuveytturk.com.tr") and any(
        k in text_norm
        for k in [
            "kuveyt turk katilim bankasi",
            "iban'a para transferi",
            "mobil sube",
            "aciklama",
            "sorgu numarasi",
            "islem tarihi",
        ]
    )


# ----------------------------
# Garanti (website-only)
# ----------------------------
def is_garanti(text_norm: str) -> bool:
    # STRICT: only the website on the receipt
    return has_domain(text_norm, "garantibbva.com.tr")


# ----------------------------
# YapıKredi (variants)
# ----------------------------
def is_yapikredi_fast(text_norm: str) -> bool:
    return has_domain(text_norm, "yapikredi.com.tr") and ("fast gonderimi" in text_norm)


def is_yapikredi_havale(text_norm: str) -> bool:
    return has_domain(text_norm, "yapikredi.com.tr") and (
        ("havale-borc" in text_norm)
        or ("dekont tipi : hvl" in text_norm)
        or ("alacakli hesap" in text_norm)
    )


def is_yapikredi(text_norm: str) -> bool:
    return has_domain(text_norm, "yapikredi.com.tr")


Detector = tuple[str, str, Optional[str], Callable[[str], bool]]

# Order matters: put lookalikes/variants before generic website checks
DETECTORS: list[Detector] = [
    ("PTTBANK", "PttBank", None, is_pttbank),
    ("HALKBANK", "Halkbank", None, is_halkbank),
    ("TOMBANK", "TOM Bank", None, is_tombank),
    ("ISBANK", "Isbank", None, is_isbank),
    ("TURKIYE_FINANS", "TurkiyeFinans", None, is_turkiye_finans),
    ("ING", "ING", None, is_ing),
    ("TEB", "TEB", None, is_teb),
    ("VAKIF_KATILIM", "VakifKatilim", None, is_vakif_katilim),
    ("VAKIFBANK", "VakifBank", None, is_vakifbank),
    # Garanti (website-only)
    ("GARANTI", "Garanti", None, is_garanti),
    # YapıKredi variants
    ("YAPIKREDI_FAST", "YapiKredi", "FAST", is_yapikredi_fast),
    ("YAPIKREDI_HAVALE", "YapiKredi", "HAVALE", is_yapikredi_havale),
    ("YAPIKREDI", "YapiKredi", "UNKNOWN", is_yapikredi),
    # KuveytTurk variants
    ("KUVEYT_TURK_EN", "KuveytTurk", "EN", is_kuveyt_turk_en),
    ("KUVEYT_TURK_TR", "KuveytTurk", "TR", is_kuveyt_turk_tr),
    ("ZIRAAT_FAST", "Ziraat", "FAST", is_ziraat_fast),
    ("ZIRAAT_HAVALE", "Ziraat", "HAVALE", is_ziraat_havale),
    ("ZIRAAT", "Ziraat", "UNKNOWN", is_ziraat),
    ("QNB", "QNB", None, is_qnb),
    # Kuveyt fallback
    ("KUVEYT_TURK", "KuveytTurk", "UNKNOWN", is_kuveyt_turk),
]


def detect_bank_variant(pdf_path: Path, use_ocr_fallback: bool = False) -> dict:
    raw = extract_text(pdf_path, max_pages=2)
    text_norm = normalize_text(raw)

    method = "text"

    # Optional OCR fallback (if you ever enable it)
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
                return {
                    "key": key,
                    "bank": bank_name,
                    "variant": variant,
                    "method": method,
                }
        except Exception:
            continue

    return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": method}
