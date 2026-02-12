from pathlib import Path
from typing import Dict

from app.parsers.kuveytturk._shared import parse_kuveytturk


def parse_kuveyt_turk_unknown(pdf_path: Path) -> Dict:
    """
    KuveytTürk unified parser (TR + EN + AR) lives in _shared.py.
    Keep the public function name the same so your registry doesn't change.
    """
    out = parse_kuveytturk(pdf_path)

    # Keep status conservative (you handle status elsewhere / manually)
    st = str(out.get("tr_status", "")).lower()
    if not st or "unknown" in st:
        out["tr_status"] = "unknown-manually"

    return out
