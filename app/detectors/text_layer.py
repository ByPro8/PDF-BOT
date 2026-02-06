import re
from pathlib import Path

from pypdf import PdfReader


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
