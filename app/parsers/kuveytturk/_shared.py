import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from pypdf import PdfReader


def _extract_text(pdf_path: Path, max_pages: int = 2) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).replace("\u00a0", " ").replace("\u202f", " ")


def _strip_invisibles(s: str) -> str:
    """
    Removes bidi/RTL marks + zero-width chars that often break regex matching in Arabic PDFs.
    """
    if not s:
        return ""
    return re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff\u200b-\u200d]", "", s)


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.casefold().replace("\u0307", "")  # dotted-i combining mark
    tr = str.maketrans({"ı": "i", "ö": "o", "ü": "u", "ş": "s", "ğ": "g", "ç": "c"})
    s = s.translate(tr)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _clean_one_line(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.splitlines()[0].strip()
    v = re.sub(r"\s+", " ", v).strip()

    toks = v.split()
    while toks and toks[-1].upper() in {"TR", "BSMV", "TL", "TRY"}:
        toks.pop()
    v = " ".join(toks).strip()

    return v or None


def _find_line_after_label(raw: str, labels: list[str]) -> Optional[str]:
    # Label\nVALUE  (label is literal)
    for lab in labels:
        m = re.search(rf"(?:^|\n)\s*{re.escape(lab)}\s*\n\s*([^\n]+)", raw, flags=re.I)
        if m:
            return _clean_one_line(m.group(1))
    return None


def _find_line_after_label_regex(raw: str, label_patterns: list[str]) -> Optional[str]:
    # LabelRegex\nVALUE  (label is regex)
    for pat in label_patterns:
        m = re.search(rf"(?:^|\n)\s*(?:{pat})\s*\n\s*([^\n]+)", raw, flags=re.I)
        if m:
            return _clean_one_line(m.group(1))
    return None


def _find_inline_after_label_strict(raw: str, labels: list[str]) -> Optional[str]:
    """
    Inline label:value. STRICT = requires : or - so we don't capture junk like:
      "Gönderen Kişi" -> capturing "Kişi"
      "Gönderilen IBAN" -> capturing "IBAN"
    """
    for lab in labels:
        m = re.search(
            rf"(?:^|\n)\s*{re.escape(lab)}\s*[:\-]\s*([^\n]+)", raw, flags=re.I
        )
        if m:
            return _clean_one_line(m.group(1))
    return None


def _find_inline_after_label_regex_strict(
    raw: str, label_patterns: list[str]
) -> Optional[str]:
    # Inline LabelRegex : VALUE
    for pat in label_patterns:
        m = re.search(rf"(?:^|\n)\s*(?:{pat})\s*[:\-]\s*([^\n]+)", raw, flags=re.I)
        if m:
            return _clean_one_line(m.group(1))
    return None


def _find_iban(raw: str) -> Optional[str]:
    m = re.search(r"\bTR\s*(?:\d\s*){24}\b", raw, flags=re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).upper().strip()


def _find_amount(raw: str) -> Optional[str]:
    m = re.search(
        r"(?:^|\n)\s*(?:Amount|Tutar)\s*\n\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)\s*(TRY|TL)\b",
        raw,
        flags=re.I,
    )
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"

    # Arabic label: مبلغ
    m_ar = re.search(
        r"(?:^|\n)\s*(?:مبلغ)\s*\n\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)\s*(TRY|TL)\b",
        raw,
        flags=re.I,
    )
    if m_ar:
        return f"{m_ar.group(1)} {m_ar.group(2).upper()}"

    m2 = re.search(
        r"\b([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)\s*(TRY|TL)\b",
        raw,
        flags=re.I,
    )
    if m2:
        return f"{m2.group(1)} {m2.group(2).upper()}"

    return None


def _find_time(raw: str) -> Optional[str]:
    v = _find_line_after_label(
        raw,
        [
            "TransactionDate",
            "Transaction Date",
            "Transaction Date:",
            "İşlem Tarihi",
            "Islem Tarihi",
        ],
    )

    # Arabic label: تران التاريخ
    if not v:
        v = _find_line_after_label_regex(raw, [r"تران\s+التاريخ"])

    if not v:
        m = re.search(
            r"(?:TransactionDate|Transaction\s*Date|İşlem\s*Tarihi|Islem\s*Tarihi|تران\s+التاريخ)\s*[:\n ]+\s*([0-9]{2}[./][0-9]{2}[./][0-9]{4}\s+[0-9]{2}:[0-9]{2})",
            raw,
            flags=re.I,
        )
        if m:
            v = m.group(1)
        else:
            m2 = re.search(
                r"\b([0-9]{2}[./][0-9]{2}[./][0-9]{4})\s+([0-9]{2}:[0-9]{2})\b",
                raw,
            )
            if not m2:
                return None
            v = f"{m2.group(1)} {m2.group(2)}"

    v2 = v.replace("/", ".").strip()
    m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\b", v2)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    return v2


def _find_receipt(raw: str) -> Optional[str]:
    # EN/TR first
    v = _find_line_after_label(
        raw, ["Query Number", "Sorgu Numarası", "Sorgu Numarasi"]
    )
    if v:
        m = re.search(r"\b(\d{6,})\b", v)
        return m.group(1) if m else v

    v2 = _find_inline_after_label_strict(
        raw, ["Query Number", "Sorgu Numarası", "Sorgu Numarasi"]
    )
    if v2:
        m = re.search(r"\b(\d{6,})\b", v2)
        return m.group(1) if m else v2

    # Arabic (tolerant, strips invisibles)
    t = _strip_invisibles(raw)

    m = re.search(r"(?:^|\n)\s*رقم\s*طلب\s*البحث\s*\n\s*(\d{6,})\b", t, flags=re.I)
    if m:
        return m.group(1)

    m = re.search(r"(?:^|\n)\s*رقم\s*طلب\s*البحث\s*[:\-]?\s*(\d{6,})\b", t, flags=re.I)
    if m:
        return m.group(1)

    m = re.search(r"رقم.*البحث[^\d]{0,30}(\d{6,})\b", t, flags=re.I | re.DOTALL)
    if m:
        return m.group(1)

    return None


def _find_ref(raw: str) -> Optional[str]:
    def pick_ref_token(txt: str) -> Optional[str]:
        if not txt:
            return None
        m = re.search(
            r"\b(?=[A-Z0-9-]*\d)[A-Z0-9]{3,}(?:-[A-Z0-9]+)*\b", txt, flags=re.I
        )
        if m:
            return m.group(0)
        m2 = re.search(r"\b\d{8,}\b", txt)
        if m2:
            return m2.group(0)
        return None

    v = _find_line_after_label(
        raw,
        [
            "TransactionReferance",
            "TransactionReference",
            "Transaction Reference",
            "Transaction Ref",
            "İşlem Referansı",
            "Islem Referansi",
        ],
    )

    if not v:
        # Arabic: مرجع المعاملة
        v = _find_line_after_label_regex(raw, [r"مرجع\s+المعاملة"])

    if not v:
        v = _find_inline_after_label_strict(
            raw,
            [
                "TransactionReferance",
                "TransactionReference",
                "Transaction Reference",
                "Transaction Ref",
                "İşlem Referansı",
                "Islem Referansi",
            ],
        )

    if not v:
        v = _find_inline_after_label_regex_strict(raw, [r"مرجع\s+المعاملة"])

    tok = pick_ref_token(v or "")
    if tok:
        return tok

    m3 = re.search(r"\b(?=[A-Z0-9-]*\d)[A-Z0-9]{3,}-[A-Z0-9]+-\d{6}\b", raw, flags=re.I)
    if m3:
        return m3.group(0)

    m4 = re.search(r"\b(?=[A-Z0-9-]*\d)[A-Z0-9]{6,}(?:-[A-Z0-9]+)*\b", raw, flags=re.I)
    if m4:
        return m4.group(0)

    return None


def _detect_status_kuveytturk(raw: str) -> str:
    t = _norm(raw)

    if re.search(r"\biptal\b|\biade\b|\bbasarisiz\b|\breddedildi\b|\bcancel", t):
        return "canceled"

    if re.search(
        r"\bbeklemede\b|\bisleniyor\b|\bonay bekliyor\b|\bpending\b|\bprocessing\b", t
    ):
        return "pending"

    if (
        "isleminiz gerceklestirilmistir" in t
        or "transaction completed" in t
        or "successfully completed" in t
    ):
        return "completed"

    return "unknown-manually"


def _is_en_template(raw: str) -> bool:
    t = _norm(raw)
    return (
        ("transaction details" in t)
        or ("sender name" in t)
        or ("transactiondate" in t)
        or ("amount" in t)
    )


def _is_ar_template(raw: str) -> bool:
    t = _strip_invisibles(raw)
    return bool(
        re.search(
            r"(المرسلاسم|المستلماسم|اسم\s*المرسل|اسم\s*المستلم|رقم\s*طلب\s*البحث|مرجع\s*المعاملة|تران\s*التاريخ|مبلغ)",
            t,
            flags=re.I,
        )
    )


def _find_sender_en(raw: str) -> Optional[str]:
    v = _find_line_after_label(raw, ["Sender Name"])
    if not v:
        v = _find_inline_after_label_strict(raw, ["Sender Name"])
    return _clean_one_line(v)


def _find_receiver_en(raw: str) -> Optional[str]:
    v = _find_line_after_label(
        raw, ["Recipient", "Recipient Name", "Beneficiary", "Receiver"]
    )
    if not v:
        v = _find_inline_after_label_strict(
            raw, ["Recipient", "Recipient Name", "Beneficiary", "Receiver"]
        )
    return _clean_one_line(v)


def _find_sender_tr(raw: str) -> Optional[str]:
    v = _find_line_after_label(
        raw,
        [
            "Gönderen Kişi",
            "Gonderen Kisi",
            "GÖNDEREN KİŞİ",
            "GONDEREN KISI",
            "Gönderen",
            "Gonderen",
            "Gönderici",
            "Gonderici",
        ],
    )

    if not v:
        v = _find_inline_after_label_strict(
            raw,
            [
                "Gönderen Kişi",
                "Gonderen Kisi",
                "Gönderen",
                "Gonderen",
                "Gönderici",
                "Gonderici",
            ],
        )

    v = _clean_one_line(v)

    if not v:
        names = re.findall(r"(?:^|\n)\s*Müşteri Adı\s+([^\n]+)", raw, flags=re.I)
        names = [_clean_one_line(x) for x in names if _clean_one_line(x)]
        if len(names) >= 2:
            v = names[1]

    return v


def _find_receiver_tr(raw: str) -> Optional[str]:
    v = _find_line_after_label(raw, ["Alıcı", "Alici", "ALICI"])
    if not v:
        v = _find_inline_after_label_strict(raw, ["Alıcı", "Alici", "ALICI"])
    v = _clean_one_line(v)
    if v:
        return v

    v2 = _find_line_after_label(raw, ["Gönderilen", "Gonderilen"])
    if not v2:
        v2 = _find_inline_after_label_strict(raw, ["Gönderilen", "Gonderilen"])
    v2 = _clean_one_line(v2)

    if v2:
        t = _norm(v2)
        if "iban" not in t and not re.search(r"\bTR\s*\d", v2, flags=re.I):
            return v2

    names = re.findall(r"(?:^|\n)\s*Müşteri Adı\s+([^\n]+)", raw, flags=re.I)
    names = [_clean_one_line(x) for x in names if _clean_one_line(x)]
    if names:
        return names[0]

    return None


def _find_sender_ar(raw: str) -> Optional[str]:
    t = _strip_invisibles(raw)

    # Handles: "المرسلاسم" or "اسم المرسل" or "المرسل اسم"
    m = re.search(
        r"(?:^|\n)\s*(?:المرسل\s*اسم|المرسلاسم|اسم\s*المرسل)\s*\n\s*([^\n]+)",
        t,
        flags=re.I,
    )
    if m:
        return _clean_one_line(m.group(1))

    m = re.search(
        r"(?:^|\n)\s*(?:المرسل\s*اسم|المرسلاسم|اسم\s*المرسل)\s*[:\-]?\s*([^\n]+)",
        t,
        flags=re.I,
    )
    return _clean_one_line(m.group(1)) if m else None


def _find_receiver_ar(raw: str) -> Optional[str]:
    t = _strip_invisibles(raw)

    # Handles: "المستلماسم" or "اسم المستلم" or "المستلم اسم"
    m = re.search(
        r"(?:^|\n)\s*(?:المستلم\s*اسم|المستلماسم|اسم\s*المستلم)\s*\n\s*([^\n]+)",
        t,
        flags=re.I,
    )
    if m:
        return _clean_one_line(m.group(1))

    m = re.search(
        r"(?:^|\n)\s*(?:المستلم\s*اسم|المستلماسم|اسم\s*المستلم)\s*[:\-]?\s*([^\n]+)",
        t,
        flags=re.I,
    )
    return _clean_one_line(m.group(1)) if m else None


def _find_names_from_desc_ar(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Arabic PDFs include a "وصف المعاملة" block with quoted fields containing both names.
    We extract quoted fields and return (sender, receiver) from the last two meaningful values.
    """
    t = _strip_invisibles(raw)

    m = re.search(
        r"وصف\s*المعاملة\s*[:\-]?\s*([^\n]+(?:\n[^\n]+){0,2})",
        t,
        flags=re.I,
    )
    if not m:
        return (None, None)

    block = m.group(1)
    quoted = re.findall(r'"([^"]+)"', block)
    quoted = [q.strip() for q in quoted if q and q.strip()]

    if len(quoted) >= 2:
        sender = _clean_one_line(quoted[-2])
        receiver = _clean_one_line(quoted[-1])
        return (sender, receiver)

    return (None, None)


def parse_kuveytturk(pdf_path: Path) -> Dict:
    raw = _extract_text(pdf_path, 2)

    # Primary routing
    if _is_ar_template(raw):
        sender = _find_sender_ar(raw)
        receiver = _find_receiver_ar(raw)
    elif _is_en_template(raw):
        sender = _find_sender_en(raw)
        receiver = _find_receiver_en(raw)
    else:
        sender = _find_sender_tr(raw)
        receiver = _find_receiver_tr(raw)

    # Always fallback to Arabic label parsing
    if not sender:
        sender = _find_sender_ar(raw)
    if not receiver:
        receiver = _find_receiver_ar(raw)

    # Last resort: parse from وصف المعاملة
    if not sender or not receiver:
        s2, r2 = _find_names_from_desc_ar(raw)
        if not sender and s2:
            sender = s2
        if not receiver and r2:
            receiver = r2

    iban = _find_iban(raw)
    amount = _find_amount(raw)
    time = _find_time(raw)
    receipt = _find_receipt(raw)
    ref = _find_ref(raw)

    status = _detect_status_kuveytturk(raw)

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
