import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from pypdf import PdfReader


# =============================================================================
# TEXT EXTRACTION (FAST)
# =============================================================================


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
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def has_domain(text_norm: str, domain: str) -> bool:
    """Website-domain matcher that survives PDF text-layer weirdness.

    Handles:
    - spaces/newlines around dots
    - split 'www . domain . com . tr'
    - URLs that include the domain
    """
    t = text_norm or ""
    compact = re.sub(r"\s+", "", t)

    dom = (domain or "").casefold().strip()
    if not dom:
        return False

    if dom in t or dom in compact:
        return True

    # Allow both with/without www.
    dom_no_www = dom.replace("www.", "")
    parts = [re.escape(p) for p in dom_no_www.split(".") if p]
    if not parts:
        return False

    pat = r"(?:www\s*\.\s*)?" + r"\s*\.\s*".join(parts)
    return re.search(pat, t, flags=re.I) is not None


# =============================================================================
# OCR (ONLY FOR BANKS YOU ALLOWLIST BELOW)
# =============================================================================


def ocr_first_page_text(pdf_path: Path) -> str:
    """OCR the first page ONLY.

    IMPORTANT:
    - OCR is slow; we call it only when text-layer domain detection fails,
      and only to confirm domains for OCR-allowlisted banks.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
        if not images:
            return ""
        return pytesseract.image_to_string(images[0]) or ""
    except Exception:
        return ""


# =============================================================================
# BANK DETECTION (STRICT: WEBSITE DOMAIN ONLY)
# =============================================================================

# key -> (bank_name, domains...)
BANK_DOMAINS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "PTTBANK": ("PttBank", ("pttbank.ptt.gov.tr",)),
    "HALKBANK": ("Halkbank", ("halkbank.com.tr",)),
    "TOMBANK": ("TOM Bank", ("tombank.com.tr",)),
    "ISBANK": ("Isbank", ("isbank.com.tr",)),
    "TURKIYE_FINANS": ("TurkiyeFinans", ("turkiyefinans.com.tr",)),
    "ING": ("ING", ("ing.com.tr",)),
    "TEB": ("TEB", ("teb.com.tr",)),
    "VAKIF_KATILIM": ("VakifKatilim", ("vakifkatilim.com.tr",)),
    "VAKIFBANK": ("VakifBank", ("vakifbank.com.tr",)),
    "QNB": ("QNB", ("qnb.com.tr",)),
    "ZIRAAT": ("Ziraat", ("ziraatbank.com.tr",)),
    "KUVEYT_TURK": ("KuveytTurk", ("kuveytturk.com.tr",)),
    "GARANTI": ("Garanti", ("garantibbva.com.tr",)),
    "ENPARA": ("Enpara", ("enpara.com",)),
    "AKBANK": ("Akbank", ("akbank.com",)),
    "YAPIKREDI": ("YapiKredi", ("yapikredi.com.tr",)),
    "DENIZBANK": ("DenizBank", ("denizbank.com.tr", "denizbank.com")),
}

# -------------------------------------------------------------------------
# OCR allowlist (EDIT THIS IN FUTURE)
# Only these banks/domains are allowed to be detected via OCR.
#
# Example if later another bank sometimes has image-only domain:
#   OCR_DOMAIN_BANKS["SOME_BANK"] = ("Some Bank", ("somebank.com.tr",))
#
# If a key is not in OCR_DOMAIN_BANKS, OCR can NEVER detect it.
# -------------------------------------------------------------------------
OCR_DOMAIN_BANKS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "DENIZBANK": ("DenizBank", ("denizbank.com.tr", "denizbank.com")),
}


def _detect_bank_by_text_domains(text_norm: str) -> Optional[dict]:
    """Detect bank strictly by website domain in text-layer (fast path)."""
    for key, (bank_name, domains) in BANK_DOMAINS.items():
        for dom in domains:
            if has_domain(text_norm, dom):
                return {
                    "key": key,
                    "bank": bank_name,
                    "variant": None,
                    "method": "text",
                }
    return None


def _detect_bank_by_ocr_domains(pdf_path: Path) -> Optional[dict]:
    """OCR first page ONLY and detect ONLY banks in OCR_DOMAIN_BANKS by domain."""
    raw = ocr_first_page_text(pdf_path)
    if not raw:
        return None

    t = normalize_text(raw)

    for key, (bank_name, domains) in OCR_DOMAIN_BANKS.items():
        for dom in domains:
            if has_domain(t, dom):
                return {"key": key, "bank": bank_name, "variant": None, "method": "ocr"}

    return None


# =============================================================================
# VARIANT DETECTION (AFTER BANK IS KNOWN)
# =============================================================================


def _variant_ziraat(text_norm: str) -> Tuple[str, str]:
    if any(
        k in text_norm for k in ("hesaptan fast", "fast mesaj kodu", "fast sorgu no")
    ):
        return "ZIRAAT_FAST", "FAST"
    if "hesaptan hesaba havale" in text_norm:
        return "ZIRAAT_HAVALE", "HAVALE"
    return "ZIRAAT", "UNKNOWN"


def _variant_yapikredi(text_norm: str) -> Tuple[str, str]:
    if "fast gonderimi" in text_norm:
        return "YAPIKREDI_FAST", "FAST"
    if any(
        k in text_norm for k in ("havale-borc", "dekont tipi : hvl", "alacakli hesap")
    ):
        return "YAPIKREDI_HAVALE", "HAVALE"
    return "YAPIKREDI", "UNKNOWN"


def _variant_kuveytturk(text_norm: str) -> Tuple[str, str]:
    en_markers = (
        "kuveyt turk participation bank",
        "money transfer to iban",
        "outgoing",
        "transactiondate",
        "query number",
    )
    tr_markers = (
        "kuveyt turk katilim bankasi",
        "iban'a para transferi",
        "mobil sube",
        "aciklama",
        "sorgu numarasi",
        "islem tarihi",
    )
    if any(k in text_norm for k in en_markers):
        return "KUVEYT_TURK_EN", "EN"
    if any(k in text_norm for k in tr_markers):
        return "KUVEYT_TURK_TR", "TR"
    return "KUVEYT_TURK", "UNKNOWN"


def _variant_garanti(text_norm: str) -> Tuple[str, str]:
    if re.search(r"\bfast\b", text_norm) and (
        "ref" in text_norm or "referans" in text_norm
    ):
        return "GARANTI_FAST", "FAST"
    if re.search(r"\bhavale\b", text_norm):
        return "GARANTI_HAVALE", "HAVALE"
    return "GARANTI", "UNKNOWN"


VARIANT_AFTER_BANK = {
    "ZIRAAT": _variant_ziraat,
    "YAPIKREDI": _variant_yapikredi,
    "KUVEYT_TURK": _variant_kuveytturk,
    "GARANTI": _variant_garanti,
}


def _apply_variant(bank_key: str, text_norm: str) -> Tuple[str, Optional[str]]:
    fn = VARIANT_AFTER_BANK.get(bank_key)
    if not fn:
        return bank_key, None
    key, variant = fn(text_norm)
    return key, variant


# =============================================================================
# PUBLIC API
# =============================================================================


def detect_bank_variant(pdf_path: Path, use_ocr_fallback: bool = False) -> dict:
    """Detect bank strictly by website domain.

    Flow:
      1) Extract text-layer (first 2 pages) and detect bank by website domain only.
      2) If still unknown -> OCR FIRST PAGE ONLY and ONLY check OCR_DOMAIN_BANKS domains.
      3) After bank is known -> detect variant for that bank.

    NOTE:
      `use_ocr_fallback` is kept for backward compatibility, but generic OCR
      fallback is intentionally NOT used (OCR must not affect other banks).
    """
    raw = extract_text(pdf_path, max_pages=2)
    text_norm = normalize_text(raw)

    det = _detect_bank_by_text_domains(text_norm)

    # OCR is expensive -> only do it when NO domain found in text-layer.
    if not det:
        det = _detect_bank_by_ocr_domains(pdf_path)

    if not det:
        return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": "text"}

    base_bank_key = det["key"]
    parser_key, variant = _apply_variant(base_bank_key, text_norm)

    det["key"] = parser_key
    det["variant"] = variant
    return det
