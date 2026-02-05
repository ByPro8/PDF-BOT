import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _clean_spaces(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip()


def _norm(s: str) -> str:
    if not s:
        return ""
    t = s.casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _find_one(pattern: str, text: str, flags: int = 0) -> Optional[str]:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    g = m.group(1) if m.lastindex else m.group(0)
    return _clean_spaces(g)


def _strip_leading_minus(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    v2 = v.strip()
    if v2.startswith("-"):
        v2 = v2[1:].strip()
    return v2


def _trim_sender_name(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    parts = re.split(r"ÖDEMENİN\s+KAYNAĞI\s*:", v, flags=re.I)
    v = parts[0].strip()
    v = re.sub(r"\s*/\s*$", "", v).strip()
    return _clean_spaces(v)


def _detect_variant(text_norm: str) -> str:
    if "fast gonderimi" in text_norm:
        return "FAST"
    if "havale-borc" in text_norm or "dekont tipi : hvl" in text_norm or "alacakli hesap" in text_norm:
        return "HAVALE"
    return "UNKNOWN"


def _detect_tr_status(raw: str) -> str:
    n = _norm(raw)
    if "tamamlanmistir" in n or "isleminiz an itibariyle" in n:
        return "completed"
    if "hesabiniza borc/alacak kaydedilmistir" in n:
        return "completed"
    if "beklemede" in n or "onay bekliyor" in n or "pending" in n:
        return "pending"
    if "iptal" in n or "canceled" in n or "cancelled" in n:
        return "canceled"
    return "unknown"


def _sender_from_aciklama_block(raw: str) -> Optional[str]:
    """
    HAVALE PDFs: sender name is usually an unlabeled standalone line after 'AÇIKLAMA:...'
    Example shows AÇIKLAMA line then name (e.g., 'ALİ IŞIKSOY'). :contentReference[oaicite:2]{index=2}
    """
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]

    # Find first line that starts with AÇIKLAMA:
    idx = None
    for i, ln in enumerate(lines):
        if _norm(ln).startswith("aciklama:"):
            idx = i
            break
    if idx is None:
        return None

    # candidate: first "clean" line after it
    bad_starts = (
        "e-dekont",
        "ticari unvan",
        "buyuk mukellefler",
        "web adresi",
        "ticaret sicil",
        "plaza",
        "mersis no",
        "mobil",
        "sistem",
    )

    for j in range(idx + 1, min(idx + 8, len(lines))):
        ln = lines[j]
        n = _norm(ln)

        if any(n.startswith(bs) for bs in bad_starts):
            continue

        # skip obvious non-name lines
        if "havale ucreti" in n or "giden havale" in n:
            continue
        if "iban" in n or "tr" in n and any(ch.isdigit() for ch in ln):
            continue
        if len(ln) < 3:
            continue

        return ln

    return None


def parse_yapikredi_fast(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    transaction_time = _find_one(
        r"İŞLEM TARİHİ\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
        raw,
    )

    sender = _find_one(r"GÖNDEREN ADI\s*:\s*(.+)", raw)
    sender = _trim_sender_name(sender)

    receiver = _find_one(r"ALICI ADI\s*:\s*(.+)", raw)

    receiver_iban = _find_one(r"ALICI HESAP\s*:\s*(TR[0-9 ]{10,})", raw)
    if receiver_iban:
        receiver_iban = receiver_iban.replace(" ", "")

    amount = _find_one(r"GİDEN FAST TUTARI\s*:\s*([-\s]*[0-9][0-9\.\,]*)", raw)
    amount = _strip_leading_minus(amount)
    if amount and "tl" not in _norm(amount):
        amount = f"{amount} TL"

    receipt_no = _find_one(r"SIRA NO/ID\s*:\s*([0-9\- ]+\s*/\s*[0-9]+)", raw)
    transaction_ref = _find_one(r"İŞLEM REF\s*:\s*([0-9]+)", raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }


def parse_yapikredi_havale(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)

    transaction_time = _find_one(
        r"İŞLEM TARİHİ\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
        raw,
    )

    receiver = _find_one(r"ALACAKLI ADI\s*:\s*(.+)", raw)

    receiver_iban = _find_one(r"ALACAKLI HESAP\s*:\s*(?:[0-9]+/IBAN:)?\s*(TR[0-9 ]{10,})", raw)
    if receiver_iban:
        receiver_iban = receiver_iban.replace(" ", "")

    amount = _find_one(r"ISLEM TUTARI\s*:\s*([-\s]*[0-9][0-9\.\,]*)", raw)
    amount = _strip_leading_minus(amount)
    if amount and "tl" not in _norm(amount):
        amount = f"{amount} TL"

    # HAVALE receipt number is the BELGE NUMARASI (MOA...)
    receipt_no = _find_one(r"BELGE NUMARASI\s*:\s*([A-Z0-9]+)", raw)
    transaction_ref = _find_one(r"İŞLEM REF\s*:\s*([0-9]+)", raw)

    sender = _sender_from_aciklama_block(raw)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }


def parse_yapikredi(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    v = _detect_variant(_norm(raw))

    if v == "FAST":
        return parse_yapikredi_fast(pdf_path)
    if v == "HAVALE":
        return parse_yapikredi_havale(pdf_path)

    # fallback: try FAST first, then HAVALE
    try:
        return parse_yapikredi_fast(pdf_path)
    except Exception:
        return parse_yapikredi_havale(pdf_path)
