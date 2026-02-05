from pathlib import Path
from typing import Dict, Callable, Optional

from app.parsers.tombank.parser import parse_tombank
from app.parsers.pttbank.parser import parse_pttbank
from app.parsers.qnb.parser import parse_qnb
from app.parsers.halkbank.parser import parse_halkbank
from app.parsers.isbank.parser import parse_isbank
from app.parsers.turkiyefinans.parser import parse_turkiyefinans
from app.parsers.ing.parser import parse_ing
from app.parsers.teb.parser import parse_teb
from app.parsers.vakifkatilim.parser import parse_vakifkatilim
from app.parsers.vakifbank.parser import parse_vakifbank

from app.parsers.kuveytturk.en.parser import parse_kuveyt_turk_en
from app.parsers.kuveytturk.tr.parser import parse_kuveyt_turk_tr
from app.parsers.kuveytturk.parser import parse_kuveyt_turk_unknown

from app.parsers.yapikredi.parser import parse_yapikredi_fast, parse_yapikredi_havale


ParserFn = Callable[[Path], Dict]

PARSERS: dict[str, ParserFn] = {
    "TOMBANK": parse_tombank,
    "PTTBANK": parse_pttbank,
    "QNB": parse_qnb,
    "HALKBANK": parse_halkbank,
    "ISBANK": parse_isbank,
    "TURKIYE_FINANS": parse_turkiyefinans,
    "ING": parse_ing,
    "TEB": parse_teb,
    "VAKIF_KATILIM": parse_vakifkatilim,
    "VAKIFBANK": parse_vakifbank,

    # YapıKredi variants
    "YAPIKREDI_FAST": parse_yapikredi_fast,
    "YAPIKREDI_HAVALE": parse_yapikredi_havale,

    # KuveytTurk variants
    "KUVEYT_TURK_EN": parse_kuveyt_turk_en,
    "KUVEYT_TURK_TR": parse_kuveyt_turk_tr,
    "KUVEYT_TURK": parse_kuveyt_turk_unknown,
}


def parse_by_key(key: str, pdf_path: Path) -> Optional[Dict]:
    fn = PARSERS.get(key)
    if not fn:
        return None

    try:
        return fn(pdf_path)
    except Exception as e:
        return {
            "sender_name": None,
            "receiver_name": None,
            "receiver_iban": None,
            "amount": None,
            "transaction_time": None,
            "receipt_no": None,
            "transaction_ref": None,
            "error": f"{type(e).__name__}: {e}",
        }
