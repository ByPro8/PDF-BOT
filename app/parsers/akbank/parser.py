import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).replace("\u00a0", " ").replace("\u202f", " ")


def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _iban_compact(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return re.sub(r"\s+", "", s).upper()


def _find(raw: str, pat: str) -> Optional[str]:
    m = re.search(pat, raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _clean(m.group(1))


def _pick_transfer_amount(raw: str) -> Optional[str]:
    m = re.search(
        r"^\s*ŞCH\s+[0-9\.\,]+\s*TL\s+([0-9\.\,]+)\s*TL\s*$",
        raw,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return f"{m.group(1).strip()} TL"

    nums = re.findall(r"([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\s*TL", raw)
    if not nums:
        return None

    def to_float(tr: str) -> float:
        return float(tr.replace(".", "").replace(",", "."))

    best = max(nums, key=to_float)
    return f"{best} TL"


def _detect_tr_status(raw: str) -> str:
    t = (raw or "").casefold().replace("\u0307", "")
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    t = t.translate(tr)
    if "iptal" in t:
        return "canceled"
    if "beklemede" in t or "isleniyor" in t:
        return "pending"
    if "dekont" in t and "akbank" in t:
        return "completed"
    return "unknown"


def _last_datetime(raw: str) -> Optional[str]:
    hits = re.findall(
        r"([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})", raw
    )
    return hits[-1] if hits else None


def _pick_receiver_iban(raw: str, sender_iban: Optional[str]) -> Optional[str]:
    ibans = re.findall(r"(TR[0-9][0-9\s]{18,})", raw, flags=re.IGNORECASE)
    ibans = [_iban_compact(_clean(x)) for x in ibans]
    ibans = [x for x in ibans if x and len(x) >= 26]

    sender_iban_c = _iban_compact(sender_iban) if sender_iban else None

    for ib in ibans:
        if sender_iban_c and ib == sender_iban_c:
            continue
        return ib

    return ibans[0] if ibans else None


def _looks_like_name(s: Optional[str]) -> bool:
    s = _clean(s)
    if not s:
        return False
    if len(s) < 4 or len(s) > 80:
        return False
    if "TL" in s.upper():
        return False
    if re.search(r"\d", s):
        return False
    if s.count(" ") < 1:
        return False
    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", s):
        return False
    return True


def _receiver_name_after_iban(
    raw: str, receiver_iban: Optional[str], sender_name: Optional[str]
) -> Optional[str]:
    if not receiver_iban:
        return None

    lines = raw.splitlines()
    target = receiver_iban.upper()

    for i, line in enumerate(lines):
        comp = re.sub(r"\s+", "", line).upper()
        if target in comp:
            for j in range(i + 1, min(i + 8, len(lines))):
                cand = _clean(lines[j])
                if _looks_like_name(cand) and (not sender_name or cand != sender_name):
                    return cand
            break

    return None


def _any_colon_name(raw: str, sender_name: Optional[str]) -> Optional[str]:
    for m in re.finditer(r":\s*([^\n]+)", raw):
        cand = _clean(m.group(1))
        if _looks_like_name(cand) and (not sender_name or cand != sender_name):
            return cand
    return None


def _split_receipt_pair(receipt_line: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not receipt_line:
        return None, None
    nums = re.findall(r"[0-9]{3,}", receipt_line)
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], None
    return None, None


def parse_akbank(
    pdf_path: Path,
    *,
    text_raw: Optional[str] = None,
    text_norm: Optional[str] = None,  # unused (kept for compatibility)
) -> Dict:
    raw = text_raw if (text_raw is not None and text_raw.strip()) else _extract_text(pdf_path, max_pages=2)

    names = re.findall(
        r"Adı\s+Soyadı/Unvan\s*:\s*(.+?)(?=\s+Adı\s+Soyadı/Unvan\s*:|\n|$)",
        raw,
        flags=re.IGNORECASE,
    )
    names = [_clean(n) for n in names if _clean(n)]

    sender_name = names[0] if len(names) >= 1 else None
    receiver_name = names[1] if len(names) >= 2 else None

    if not sender_name:
        sender_name = _find(raw, r"İşlemi\s+Yapan\s+Ad-?Soyad\s*:\s*([^\n]+)") or _find(
            raw, r"Islemi\s+Yapan\s+Ad-?Soyad\s*:\s*([^\n]+)"
        )

    sender_iban = _find(raw, r"\n(TR[0-9\s]{20,})\n")
    sender_iban = _iban_compact(sender_iban)

    receiver_iban = _pick_receiver_iban(raw, sender_iban)

    amount = _pick_transfer_amount(raw)

    transaction_time = _find(
        raw,
        r"İşlem\s+Tarihi/Saati\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})",
    ) or _last_datetime(raw)

    receipt_line = _find(raw, r"([0-9]{5,}\s*/\s*[0-9]{3,}\s*/)")
    receipt_no, transaction_ref = _split_receipt_pair(receipt_line)

    if not receiver_name:
        receiver_name = _receiver_name_after_iban(
            raw, receiver_iban, sender_name
        ) or _any_colon_name(raw, sender_name)

    return {
        "tr_status": _detect_tr_status(raw),
        "sender_name": sender_name,
        "sender_iban": sender_iban,
        "receiver_name": receiver_name,
        "receiver_iban": receiver_iban,
        "amount": amount,
        "transaction_time": transaction_time,
        "receipt_no": receipt_no,
        "transaction_ref": transaction_ref,
    }
