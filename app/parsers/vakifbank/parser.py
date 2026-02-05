import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple

from pypdf import PdfReader

TR_UPPER = "A-ZÇĞİÖŞÜ"


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    raw = "\n".join(parts)

    raw = raw.replace("\u00a0", " ").replace("\u202f", " ")
    raw = unicodedata.normalize("NFC", raw)
    raw = raw.replace("I\u0307", "İ").replace("i\u0307", "i")
    return raw


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _match_text(raw: str) -> str:
    """
    For numeric fields: normalize Turkish letters -> ASCII, uppercase,
    and join ALL-CAPS splits (Skia/Chromium produces 'ISL EM', 'S ORGU', etc).
    """
    t = (raw or "").replace("\u0307", "")
    tr = str.maketrans(
        {
            "ı": "i",
            "İ": "i",
            "ö": "o",
            "Ö": "o",
            "ü": "u",
            "Ü": "u",
            "ş": "s",
            "Ş": "s",
            "ğ": "g",
            "Ğ": "g",
            "ç": "c",
            "Ç": "c",
        }
    )
    t = unicodedata.normalize("NFKC", t.translate(tr)).upper()

    # join caps split by spaces: "ISL EM" -> "ISLEM", "S ORGU" -> "SORGU"
    t = re.sub(r"(?<=[A-Z])\s+(?=[A-Z])", "", t)
    return _collapse_ws(t)


def _fix_name_splits(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    s = _collapse_ws(name)
    for _ in range(10):
        before = s
        s = re.sub(rf"\b([{TR_UPPER}])\s+([{TR_UPPER}]{{2,}})\b", r"\1\2", s)
        if s == before:
            break
    return s


def _detect_status(raw: str) -> str:
    t = (raw or "").casefold()
    if re.search(r"\biptal\b|\biade\b|\bbasarisiz\b|\breddedildi\b|\bcancel", t):
        return "canceled"
    if re.search(
        r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b|\bpending\b|\bprocessing\b", t
    ):
        return "pending"
    return "unknown-manually"


# ---------------------------
# Numeric fields (from MATCH text)
# ---------------------------
def _find_time(match: str) -> Optional[str]:
    m = re.search(
        r"ISLEMTARIHI\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}):(\d{2})(?::\d{2})?",
        match,
        flags=re.I,
    )
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)}:{m.group(3)}"


def _find_receipt_no(match: str) -> Optional[str]:
    m = re.search(r"SORGUNO\s+(\d{6,})", match, flags=re.I)
    return m.group(1) if m else None


def _find_transaction_ref(match: str) -> Optional[str]:
    m = re.search(r"ISLEMNO\s+(\d{8,})", match, flags=re.I)
    return m.group(1) if m else None


def _find_amount(match: str) -> Optional[str]:
    # IMPORTANT: currency may be glued to next word like "TLMASRAFTUTARI"
    m = re.search(
        r"ISLEMTUTARI\s+([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)\s*(TL|TRY)",
        match,
        flags=re.I,
    )
    if not m:
        return None
    val = m.group(1).strip()
    cur = m.group(2).upper()
    if "," not in val:
        val += ",00"
    return f"{val} {cur}"


# ---------------------------
# Names + IBAN (from RAW text)
# ---------------------------
def _find_sender_receiver(raw: str) -> Tuple[Optional[str], Optional[str]]:
    # Sender between "... UNVAN" and "ALICI AD SOYAD/UNVAN"
    m1 = re.search(
        r"G[ÖO]NDEREN\s*AD\s*S\s*OYAD\s*/\s*UNVAN\s*(?P<sender>.*?)\s+AL\s*ICI\s+AD\s*S\s*OYAD\s*/?\s*UNVAN",
        raw,
        flags=re.I | re.S,
    )
    sender = _fix_name_splits(m1.group("sender")) if m1 else None

    # Receiver: NOTE UNVAN may be glued to name (UNVANMurat)
    m2 = re.search(
        r"AL\s*ICI\s+AD\s*S\s*OYAD\s*/?\s*UNVAN\s*(?P<receiver>.*?)\s+AL\s*ICI\s+HES\s*AP\s+NO\s*/\s*IBAN",
        raw,
        flags=re.I | re.S,
    )
    receiver = _fix_name_splits(m2.group("receiver")) if m2 else None

    return sender, receiver


def _find_receiver_iban(raw: str) -> Optional[str]:
    m = re.search(
        r"AL\s*ICI\s+HES\s*AP\s+NO\s*/\s*IBAN\s*(.*?)(?:İŞL\s*EM\s*NO|İŞLEM\s*NO|ISLEM\s*NO|FİŞ\s*NO|FIS\s*NO|İŞL\s*EM\s*AÇIKL|İŞLEM\s*AÇIKL|ISLEM\s*AÇIKL|İNTERNET\s+S|INTERNET\s+S|$)",
        raw,
        flags=re.I | re.S,
    )
    block = m.group(1) if m else raw
    iban = re.search(r"\bTR\s*(?:\d\s*){24}\b", block, flags=re.I)
    if not iban:
        return None
    return re.sub(r"\s+", " ", iban.group(0)).upper().strip()


def parse_vakifbank(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, max_pages=2)
    match = _match_text(raw)

    sender, receiver = _find_sender_receiver(raw)

    return {
        "tr_status": _detect_status(raw),
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": _find_receiver_iban(raw),
        "amount": _find_amount(match),
        "transaction_time": _find_time(match),
        "receipt_no": _find_receipt_no(match),
        "transaction_ref": _find_transaction_ref(match),
    }
