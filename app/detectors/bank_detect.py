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
    """Website-domain matcher that survives PDF text-layer weirdness."""
    t = text_norm or ""
    compact = re.sub(r"\s+", "", t)

    dom = (domain or "").casefold().strip()
    if not dom:
        return False

    if dom in t or dom in compact:
        return True

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
    """OCR the first page ONLY (slow path)."""
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
# BANK DEFINITIONS
# =============================================================================

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
    # Added previously
    "FIBABANKA": ("Fibabanka", ("fibabanka.com.tr",)),
    "UPT": ("UPT", ("upt.com.tr", "uption.com.tr")),
    "ZIRAATKATILIM": ("ZiraatKatilim", ("ziraatkatilim.com.tr",)),
    # ✅ NEW
    "ALBARAKA": ("Albaraka", ("albaraka.com.tr",)),
}

# OCR allowlist (only these may be detected by OCR)
OCR_DOMAIN_BANKS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "DENIZBANK": ("DenizBank", ("denizbank.com.tr", "denizbank.com")),
    "ZIRAATKATILIM": ("ZiraatKatilim", ("ziraatkatilim.com.tr",)),
    # ✅ NEW (image-based PDF)
    "ALBARAKA": ("Albaraka", ("albaraka.com.tr",)),
}

# Deniz legal-name fallback (real PDFs need this)
DENIZ_TEXT_MARKERS = (
    "denizbank a.s",
    "denizbank a.ş",
    "denizbank",
    "mobildeniz",
)


# =============================================================================
# BANK DETECTION
# =============================================================================


def _detect_bank_by_text_domains(text_norm: str) -> Optional[dict]:
    for key, (bank_name, domains) in BANK_DOMAINS.items():
        for dom in domains:
            if has_domain(text_norm, dom):
                return {
                    "key": key,
                    "bank": bank_name,
                    "variant": None,
                    "method": "text-domain",
                }
    return None


def _detect_deniz_by_text_name(text_norm: str) -> Optional[dict]:
    if any(m in text_norm for m in DENIZ_TEXT_MARKERS):
        return {
            "key": "DENIZBANK",
            "bank": "DenizBank",
            "variant": None,
            "method": "text-name",
        }
    return None


def _detect_bank_by_ocr_domains(pdf_path: Path) -> Optional[dict]:
    raw = ocr_first_page_text(pdf_path)
    if not raw:
        return None

    t = normalize_text(raw)
    for key, (bank_name, domains) in OCR_DOMAIN_BANKS.items():
        for dom in domains:
            if has_domain(t, dom):
                return {
                    "key": key,
                    "bank": bank_name,
                    "variant": None,
                    "method": "ocr-domain",
                }
    return None


# =============================================================================
# VARIANT DETECTION (AFTER BANK IS KNOWN)
# =============================================================================


def _variant_deniz(text_norm: str) -> Tuple[str, str]:
    # Keep parser key DENIZBANK (no DENIZBANK_FAST parser)
    if re.search(r"\bfast\b", text_norm):
        return "DENIZBANK", "FAST"
    return "DENIZBANK", "UNKNOWN"


def _variant_albaraka(text_norm: str) -> Tuple[str, str]:
    # Keep parser key ALBARAKA (single parser for now)
    if re.search(r"\bfast\b", text_norm) or "fast sorgu numarasi" in text_norm:
        return "ALBARAKA", "FAST"
    return "ALBARAKA", "UNKNOWN"


VARIANT_AFTER_BANK = {
    "DENIZBANK": _variant_deniz,
    "ALBARAKA": _variant_albaraka,
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
    raw = extract_text(pdf_path, max_pages=2)
    text_norm = normalize_text(raw)

    det = _detect_bank_by_text_domains(text_norm)

    # Deniz fallback (name-based) only if no domain
    if not det:
        det = _detect_deniz_by_text_name(text_norm)

    # OCR only if still nothing (and only for allowlist)
    if not det:
        det = _detect_bank_by_ocr_domains(pdf_path)

    if not det:
        return {"key": "UNKNOWN", "bank": "Unknown", "variant": None, "method": "none"}

    base_key = det["key"]
    parser_key, variant = _apply_variant(base_key, text_norm)

    det["key"] = parser_key
    det["variant"] = variant
    return det
