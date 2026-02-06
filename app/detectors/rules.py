import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.detectors.ocr_utils import ocr_first_page_text
from app.detectors.text_layer import has_domain, normalize_text


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
    "FIBABANKA": ("Fibabanka", ("fibabanka.com.tr",)),
    "UPT": ("UPT", ("upt.com.tr", "uption.com.tr")),
    "ZIRAATKATILIM": ("ZiraatKatilim", ("ziraatkatilim.com.tr",)),
    "ALBARAKA": ("Albaraka", ("albaraka.com.tr",)),
}

# OCR allowlist (only these may be detected by OCR)
OCR_DOMAIN_BANKS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "DENIZBANK": ("DenizBank", ("denizbank.com.tr", "denizbank.com")),
    "ZIRAATKATILIM": ("ZiraatKatilim", ("ziraatkatilim.com.tr",)),
    "ALBARAKA": ("Albaraka", ("albaraka.com.tr",)),
}

DENIZ_TEXT_MARKERS = (
    "denizbank a.s",
    "denizbank a.ş",
    "denizbank",
    "mobildeniz",
)


def detect_bank_by_text_domains(text_norm: str) -> Optional[dict]:
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


def detect_deniz_by_text_name(text_norm: str) -> Optional[dict]:
    if any(m in text_norm for m in DENIZ_TEXT_MARKERS):
        return {
            "key": "DENIZBANK",
            "bank": "DenizBank",
            "variant": None,
            "method": "text-name",
        }
    return None


def detect_bank_by_ocr_domains(pdf_path: Path) -> Optional[dict]:
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


def _variant_deniz(text_norm: str) -> Tuple[str, str]:
    if re.search(r"\bfast\b", text_norm):
        return "DENIZBANK", "FAST"
    return "DENIZBANK", "UNKNOWN"


def _variant_albaraka(text_norm: str) -> Tuple[str, str]:
    if re.search(r"\bfast\b", text_norm) or "fast sorgu numarasi" in text_norm:
        return "ALBARAKA", "FAST"
    return "ALBARAKA", "UNKNOWN"


VARIANT_AFTER_BANK = {
    "DENIZBANK": _variant_deniz,
    "ALBARAKA": _variant_albaraka,
}


def _is_parser_key_registered(key: str) -> bool:
    try:
        from app.parsers.registry import REGISTRY

        return key in REGISTRY
    except Exception:
        return False


def apply_variant(bank_key: str, text_norm: str) -> Tuple[str, Optional[str]]:
    """Return (parser_key, variant).

    Rule: never switch parser key unless it exists in registry.
    """
    fn = VARIANT_AFTER_BANK.get(bank_key)
    if not fn:
        return bank_key, None

    proposed_key, variant = fn(text_norm)
    if proposed_key != bank_key and not _is_parser_key_registered(proposed_key):
        proposed_key = bank_key

    return proposed_key, variant
