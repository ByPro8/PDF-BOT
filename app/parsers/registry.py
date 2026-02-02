from pathlib import Path
from typing import Dict, Callable, Optional

from app.parsers.tombank.parser import parse_tombank
from app.parsers.pttbank.parser import parse_pttbank

ParserFn = Callable[[Path], Dict]

PARSERS: dict[str, ParserFn] = {
    "TOMBANK": parse_tombank,
    "PTTBANK": parse_pttbank,
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
