"""Parser registry.

`detect_bank_variant()` returns a dict with a `key`. This module maps that key to a
parser function.

Keeping all mappings here prevents 'detected but not parsed' regressions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from app.parsers.akbank.parser import parse_akbank
from app.parsers.denizbank.parser import parse_denizbank
from app.parsers.enpara.parser import parse_enpara
from app.parsers.garanti.parser import parse_garanti
from app.parsers.halkbank.parser import parse_halkbank
from app.parsers.ing.parser import parse_ing
from app.parsers.isbank.parser import parse_isbank
from app.parsers.pttbank.parser import parse_pttbank
from app.parsers.qnb.parser import parse_qnb
from app.parsers.teb.parser import parse_teb
from app.parsers.tombank.parser import parse_tombank
from app.parsers.turkiyefinans.parser import parse_turkiyefinans
from app.parsers.vakifbank.parser import parse_vakifbank
from app.parsers.vakifkatilim.parser import parse_vakifkatilim
from app.parsers.yapikredi.parser import (
    parse_yapikredi,
    parse_yapikredi_fast,
    parse_yapikredi_havale,
)
from app.parsers.ziraat.parser import parse_ziraat
from app.parsers.kuveytturk.parser import parse_kuveyt_turk_unknown

ParserFn = Callable[[Path], dict]

REGISTRY: Dict[str, ParserFn] = {
    # Garanti
    "GARANTI": parse_garanti,
    "GARANTI_FAST": parse_garanti,
    "GARANTI_HAVALE": parse_garanti,

    # Enpara / Akbank / DenizBank
    "ENPARA": parse_enpara,
    "AKBANK": parse_akbank,
    "DENIZBANK": parse_denizbank,

    # Yapı Kredi (keep variant keys as aliases too)
    "YAPIKREDI": parse_yapikredi,
    "YAPIKREDI_FAST": parse_yapikredi_fast,
    "YAPIKREDI_HAVALE": parse_yapikredi_havale,

    # Kuveyt Türk (accept all detector keys)
    "KuveytTurk": parse_kuveyt_turk_unknown,
    "KUVEYT_TURK": parse_kuveyt_turk_unknown,
    "KUVEYT_TURK_EN": parse_kuveyt_turk_unknown,
    "KUVEYT_TURK_TR": parse_kuveyt_turk_unknown,

    # Ziraat (accept all detector keys)
    "ZIRAAT": parse_ziraat,
    "ZIRAAT_FAST": parse_ziraat,
    "ZIRAAT_HAVALE": parse_ziraat,

    # Other banks (accept all detector keys)
    "ISBANK": parse_isbank,
    "TOM": parse_tombank,
    "TOMBANK": parse_tombank,
    "TEB": parse_teb,
    "PTT": parse_pttbank,
    "PTTBANK": parse_pttbank,
    "TURKIYEFINANS": parse_turkiyefinans,
    "TURKIYE_FINANS": parse_turkiyefinans,
    "VAKIFKATILIM": parse_vakifkatilim,
    "VAKIF_KATILIM": parse_vakifkatilim,
    "VAKIFBANK": parse_vakifbank,
    "HALKBANK": parse_halkbank,
    "ING": parse_ing,
    "QNB": parse_qnb,
}

def parse_by_key(key: str, pdf_path: Path) -> Optional[dict]:
    fn = REGISTRY.get(key)
    if not fn:
        return {"error": f"No parser registered for key: {key}"}
    return fn(pdf_path)
