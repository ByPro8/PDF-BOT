import re
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


# ----------------------------
# Extract
# ----------------------------


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


# ----------------------------
# Normalize (for status scanning only)
# ----------------------------


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold()
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ----------------------------
# Helpers
# ----------------------------


def _cleanup_name(s: str) -> str:
    s = (s or "").strip()
    # remove junk tokens that sometimes land on the next line
    s = re.sub(r"\b(?:TR|BSMV|TRY|TL)\b", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_iban(raw: str) -> Optional[str]:
    # allow both spaced and unspaced IBAN
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


def _find_sender(raw: str) -> Optional[str]:
    # Example: KULLANILAN HESAP : DÖNMEZ EMRE
    m = re.search(r"KULLANILAN\s+HESAP\s*:\s*([^\n]+)", raw, re.I)
    if m:
        return _cleanup_name(m.group(1))
    # Fallback: Sayın <name>
    m = re.search(r"Say[ıi]n\s+([^\n]+)", raw, re.I)
    return _cleanup_name(m.group(1)) if m else None


def _find_amount(raw: str) -> Optional[str]:
    # Example: FAST TUTARI : 25,718.00 TL
    m = re.search(r"FAST\s+TUTARI\s*:\s*([0-9][0-9,\.]*)\s*(TL|TRY)\b", raw, re.I)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    # Fallback generic
    m = re.search(r"\b([0-9][0-9,\.]*)\s*(TL|TRY)\b", raw, re.I)
    return f"{m.group(1)} {m.group(2).upper()}" if m else None


def _find_time(raw: str) -> Optional[str]:
    # Prefer Basım Tarihi which includes time
    # Example: Basım Tarihi : 22/01/2026 - 15:39:25
    m = re.search(
        r"Bas[ıi]m\s+Tarihi\s*:\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}):(\d{2})(?::\d{2})?",
        raw,
        re.I,
    )
    if m:
        dd, mm, yyyy, hh, mi = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        return f"{dd}.{mm}.{yyyy} {hh}:{mi}"
    # Fallback: İşlem Tarihi (date-only) => return date with 00:00? better None than guessing
    return None


def _find_receipt_no(raw: str) -> Optional[str]:
    # Example: Dekont No : 591756
    m = re.search(r"Dekont\s+No\s*:\s*([0-9]+)", raw, re.I)
    return m.group(1) if m else None


def _find_transaction_ref(raw: str) -> Optional[str]:
    # Prefer Sorgu No inside Açıklama (FAST query number)
    m = re.search(r"Sorgu\s*No\s*[:\-]?\s*([0-9]{6,})", raw, re.I)
    if m:
        return m.group(1)

    # Fallback: Fiş Bilgileri : 22/01/2026-202-48202-21638
    m = re.search(
        r"Fi[sş]\s+Bilgileri\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4}[-0-9]+)", raw, re.I
    )
    return m.group(1) if m else None


def _find_receiver_name(raw: str) -> Optional[str]:
    """
    ING file packs receiver into the Açıklama line:
    Açıklama : Giden FAST Sorgu No:... TR.... <Bank Name> <Receiver Name>
    We'll:
      1) take the Açıklama line
      2) cut everything up to the receiver IBAN
      3) remove common bank tail like 'A.Ş.' and keep last name chunk
    """
    m = re.search(r"A[cç]ıklama\s*:\s*([^\n]+)", raw, re.I)
    if not m:
        return None

    desc = m.group(1).strip()

    iban = _find_iban(desc) or _find_iban(raw)
    if not iban:
        return None

    # cut to the right of iban
    idx = desc.upper().find(re.sub(r"\s+", "", iban).upper())
    if idx == -1:
        # try spaced version
        idx = desc.upper().find(iban.upper())

    tail = desc
    if idx != -1:
        tail = desc[idx + len(iban) :].strip()

    # remove known bank words (best-effort)
    tail = re.sub(
        r"\b(T[üu]rkiye|Cumhuriyeti|Bankas[ıi]|Bankasi|A\.?S\.?|A\.?Ş\.?|A\.?S)\b",
        " ",
        tail,
        flags=re.I,
    )
    tail = re.sub(r"\s+", " ", tail).strip()

    # receiver name is usually the remaining text; keep it as-is but cleaned
    return _cleanup_name(tail) if tail else None


# ----------------------------
# Status (STRICT: only if explicitly written)
# ----------------------------


def _detect_status(raw: str) -> str:
    t = _norm(raw)

    # If it explicitly says canceled/failed/pending, catch it.
    if re.search(r"\biptal\b|\biade\b|\bbasarisiz\b|\breddedildi\b|\bfail(ed)?\b", t):
        return "canceled"

    if re.search(
        r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b|\bprocessing\b|\bpending\b", t
    ):
        return "pending"

    # STRICT RULE: only mark completed if the PDF explicitly says so.
    if re.search(
        r"\bislem(.*?)basarili\b|\bisleminiz(.*?)gerceklestirilmistir\b|\bsuccessful\b|\bcompleted\b",
        t,
    ):
        return "completed"

    return "unknown — PDF does not state status; check manually"


# ----------------------------
# Main
# ----------------------------


def parse_ing(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, 2)

    sender = _find_sender(raw)
    receiver = _find_receiver_name(raw)
    iban = _find_iban(raw)
    amount = _find_amount(raw)
    time = _find_time(raw)
    receipt = _find_receipt_no(raw)
    ref = _find_transaction_ref(raw)

    status = _detect_status(raw)

    return {
        "tr_status": status,
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": iban,
        "amount": amount,
        "transaction_time": time,
        "receipt_no": receipt,
        "transaction_ref": ref,
    }
