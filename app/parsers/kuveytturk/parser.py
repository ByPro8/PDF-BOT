from pathlib import Path
from typing import Dict

from app.parsers.kuveytturk.en.parser import parse_kuveyt_turk_en
from app.parsers.kuveytturk.tr.parser import parse_kuveyt_turk_tr


def _score(d: Dict) -> int:
    keys = (
        "sender_name",
        "receiver_name",
        "receiver_iban",
        "amount",
        "transaction_time",
        "receipt_no",
        "transaction_ref",
    )
    return sum(1 for k in keys if d.get(k))


def parse_kuveyt_turk_unknown(pdf_path: Path) -> Dict:
    # Try both and pick the one that extracts more fields.
    tr = parse_kuveyt_turk_tr(pdf_path)
    en = parse_kuveyt_turk_en(pdf_path)
    best = tr if _score(tr) >= _score(en) else en

    # Keep status conservative
    st = str(best.get("tr_status", "")).lower()
    if "completed" in st:
        # Only keep completed if parser explicitly set it
        return best

    if not st or "unknown" in st:
        best["tr_status"] = "unknown-manually"
    return best
