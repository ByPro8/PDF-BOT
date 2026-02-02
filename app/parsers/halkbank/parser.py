import re
from pathlib import Path
from pypdf import PdfReader


def extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    out = ""

    for p in reader.pages:
        t = p.extract_text()
        if t:
            out += t + "\n"

    return out


def norm(s: str | None) -> str | None:
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def parse_halkbank(path: Path) -> dict:
    text = extract_text(path)
    t = text.upper()

    def find(rx):
        m = re.search(rx, text, flags=re.IGNORECASE)
        return norm(m.group(1)) if m else None

    sender = find(r"GÖNDEREN\s*:\s*(.+)")
    receiver = find(r"ALICI\s*:\s*(.+)")
    iban = find(r"ALICI\s+IBAN\s*:\s*(TR[\d\s]+)")
    amount = find(r"İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]+)")
    time = find(r"İŞLEM TARİHİ\s*:\s*(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}:\d{2})")
    receipt = find(r"SORGU NO\s*:\s*(\d+)")
    ref = find(r"BİMREF.*?:\s*(M-[\d\-.]+)")

    # ---- STATUS ----
    if "GİDEN FAST" in t or "GİDEN EFT" in t or "GİDEN HAVALE" in t:
        status = "completed"
    else:
        status = "unknown — check manually"

    return {
        "tr_status": status,
        "sender_name": sender,
        "receiver_name": receiver,
        "receiver_iban": iban,
        "amount": amount + " TL" if amount else None,
        "transaction_time": time.replace("-", "").strip() if time else None,
        "receipt_no": receipt,
        "transaction_ref": ref,
    }
