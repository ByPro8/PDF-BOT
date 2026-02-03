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
# Normalize
# ----------------------------


def _norm(s: str) -> str:
    if not s:
        return ""

    s = s.casefold()

    tr = str.maketrans(
        {
            "ı": "i",
            "ö": "o",
            "ü": "u",
            "ş": "s",
            "ğ": "g",
            "ç": "c",
        }
    )

    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)

    return s.strip()


# ----------------------------
# Junk filter (critical)
# ----------------------------


def _is_junk(s: str) -> bool:
    if not s:
        return True

    u = s.upper()

    if u.startswith("TR"):
        return True

    if any(
        x in u
        for x in [
            "BSMV",
            "TRY",
            "TL",
            "VERGI",
            "ÜCRET",
            "TOPLAM",
            "TUTAR",
            "FAST",
            "EFT",
            "HAVALE",
        ]
    ):
        return True

    if re.search(r"\d{3,}", u):
        return True

    return False


# ----------------------------
# Line helpers
# ----------------------------


def _lines(raw: str):
    return [l.strip() for l in raw.splitlines() if l.strip()]


def _find_inline(label: str, lines):
    for ln in lines:
        m = re.search(rf"{label}\s*:\s*(.+)", ln, re.I)
        if m:
            v = m.group(1).strip()
            if not _is_junk(v):
                return v
    return None


def _find_block(label: str, lines):
    want = _norm(label)

    for i, ln in enumerate(lines):

        if _norm(ln).startswith(want):

            j = i + 1

            while j < len(lines):

                v = lines[j].strip()

                if not v:
                    j += 1
                    continue

                if _is_junk(v):
                    return None

                return v

    return None


# ----------------------------
# Names (robust)
# ----------------------------


def _find_sender(raw: str) -> Optional[str]:

    lines = _lines(raw)

    # FAST: first real line is sender
    if len(lines) >= 2:
        first = lines[1]
        if not _is_junk(first):
            return first

    # Block
    return _find_block("Gönderici Hesap", lines)


def _find_receiver(raw: str) -> Optional[str]:

    # FAST / EFT format
    m = re.search(
        r"Alıcı Isim\\?Unvan\s*:\s*([A-ZÇĞİÖŞÜa-zçğıöşü\s\.]+)",
        raw,
    )
    if m:
        name = m.group(1)
        name = re.split(r"\b(TR|BSMV)\b", name)[0]
        return name.strip()

    # Havale format
    m = re.search(
        r"Alıcı Hesap\s*:\s*([A-ZÇĞİÖŞÜa-zçğıöşü\s\.]+)",
        raw,
    )
    if m:
        name = m.group(1)
        name = re.split(r"\b(TR|BSMV)\b", name)[0]
        return name.strip()

    return None


# ----------------------------
# IBAN
# ----------------------------


def _find_iban(raw: str) -> Optional[str]:

    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, re.I)

    if not m:
        return None

    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


# ----------------------------
# Amount
# ----------------------------


def _find_amount(raw: str) -> Optional[str]:

    m = re.search(
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*(TRY|TL)",
        raw,
        re.I,
    )

    if not m:
        return None

    return f"{m.group(1)} {m.group(2)}"


# ----------------------------
# Time
# ----------------------------


def _find_time(raw: str) -> Optional[str]:

    m = re.search(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}", raw)

    return m.group(0) if m else None


# ----------------------------
# Receipt / Ref
# ----------------------------


def _find_receipt(raw: str) -> Optional[str]:

    m = re.search(r"Sorgu Numarası\s*:\s*([A-Z0-9]+)", raw, re.I)
    if m:
        return m.group(1)

    m = re.search(r"Belge No\s*:\s*([A-Z0-9]+)", raw, re.I)
    if m:
        return m.group(1)

    return None


# ----------------------------
# Status (strict)
# ----------------------------


def _detect_status(raw: str) -> str:
    t = _norm(raw)

    # ---- STRONG COMPLETED PROOFS (only if present) ----
    COMPLETED_PATTERNS = [
        "isleminiz gerceklestirilmistir",  # strongest
        "giden fast islemi",
        "para aktarma",
        "senaryo/dekont tipi : dekont",
        "senaryo dekont tipi",
        "dekont/eft",
        "dekont/fast",
    ]

    # ---- FAILED / CANCELED ----
    CANCELED_PATTERNS = [
        "iptal",
        "basarisiz",
        "reddedildi",
        "iade edildi",
        "hata",
    ]

    # ---- PENDING ----
    PENDING_PATTERNS = [
        "beklemede",
        "isleniyor",
        "onay bekliyor",
        "pending",
        "processing",
    ]

    # Check canceled first (priority)
    for k in CANCELED_PATTERNS:
        if k in t:
            return "❌ canceled"

    # Then pending
    for k in PENDING_PATTERNS:
        if k in t:
            return "⏳ pending"

    # Then completed (ONLY if strong proof)
    for k in COMPLETED_PATTERNS:
        if k in t:
            return "✅ completed"

    # Otherwise: unknown, manual check
    return "❌ unknown — pdf does not state status, check manually"


# ----------------------------
# Main
# ----------------------------


def parse_isbank(pdf_path: Path) -> Dict:

    raw = _extract_text(pdf_path, 2)

    sender = _find_sender(raw)
    receiver = _find_receiver(raw)
    iban = _find_iban(raw)
    amount = _find_amount(raw)
    time = _find_time(raw)
    receipt = _find_receipt(raw)

    status = _detect_status(raw)

    return {
        "tr_status": status,
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": iban,
        "amount": amount,
        "transaction_time": time,
        "receipt_no": receipt,
        "transaction_ref": receipt,
    }
