from pathlib import Path
from typing import Dict, Callable, Optional

from app.parsers.tombank.parser import parse_tombank
from app.parsers.pttbank.parser import parse_pttbank
from app.parsers.qnb.parser import parse_qnb
from app.parsers.halkbank.parser import parse_halkbank
from app.parsers.isbank.parser import parse_isbank
from app.parsers.turkiyefinans.parser import parse_turkiyefinans
from app.parsers.ing.parser import parse_ing


ParserFn = Callable[[Path], Dict]

PARSERS: dict[str, ParserFn] = {
    "TOMBANK": parse_tombank,
    "PTTBANK": parse_pttbank,
    "QNB": parse_qnb,
    "HALKBANK": parse_halkbank,
    "ISBANK": parse_isbank,
    "TURKIYE_FINANS": parse_turkiyefinans,
    "ING": parse_ing,
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
