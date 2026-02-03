from pathlib import Path
from typing import Dict

from app.parsers.kuveytturk._shared import parse_kuveytturk


def parse_kuveyt_turk_en(pdf_path: Path) -> Dict:
    return parse_kuveytturk(pdf_path)
