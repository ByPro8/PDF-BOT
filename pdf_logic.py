import re
import hashlib
from pathlib import Path
from pypdf import PdfReader

REMOVE_LINE_PREFIXES = [
    "sayin","güvenli̇k","guvenlik","şube kodu/adi","sube kodu/adi","iban",
    "hesap numarasi","hesap numarası","vergi̇ dai̇resi̇","vergi dairesi",
    "vergi̇ ki̇mli̇k no","vergi kimlik no","i̇şlem tari̇hi","islem tarihi",
    "valör","valor","alacaklı şube","alacakli sube","alacaklı hesap","alacakli hesap",
    "alacaklı iban","alacakli iban","alacaklı adı soyadı","alacakli adi soyadi",
    "alacaklı vergi","alacakli vergi","komi̇syon","komisyon","havale tutarı",
    "havale tutari","hesabınızdan","hesabinizdan",
]

def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)

def normalize_for_template(text: str) -> str:
    s = text.lower().replace("\u00a0", " ")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in s.splitlines()]
    kept = []
    for ln in lines:
        if not ln:
            continue
        if any(ln.startswith(pref) for pref in REMOVE_LINE_PREFIXES):
            continue
        if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}[- ]\d{1,2}:\d{2}:\d{2}\b", ln):
            continue
        ln = re.sub(r"\d+", "#", ln)
        ln = re.sub(r"[^\w\s#]", " ", ln)
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            kept.append(ln)
    return "\n".join(kept)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def anomaly_flags(raw_text: str) -> list[str]:
    t = (raw_text or "").strip()
    flags = []
    if len(t) < 300:
        flags.append("LOW_TEXT")
    weird_ratio = len(re.findall(r"[^\w\s]", t)) / max(1, len(t))
    if weird_ratio > 0.25:
        flags.append("WEIRD_ENCODING")
    return flags

def fingerprint(pdf_path: Path) -> dict:
    raw = extract_text(pdf_path)
    norm = normalize_for_template(raw)
    return {
        "raw_len": len(raw),
        "anomaly": anomaly_flags(raw) or ["OK"],
        "template_hash": sha256(norm),
        "norm_preview": norm[:300],
    }
