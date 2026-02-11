from __future__ import annotations

import json
from pathlib import Path

from app.detectors.bank_detect import detect_bank_variant
from app.detectors.text_layer import extract_text, normalize_text
from app.detectors.rules import detect_bank_by_text_domains, detect_deniz_by_text_name, detect_bank_by_ocr_domains


def main():
    p = Path("tr22.pdf")
    if not p.exists():
        raise SystemExit("Put your PDF in project root as tr22.pdf (or edit this filename).")

    raw = extract_text(p, max_pages=2)
    text_norm = normalize_text(raw or "")

    out = {
        "file": str(p.resolve()),
        "text_layer": {
            "chars": len(raw or ""),
            "sample_300": (raw or "").strip().replace("\r", "")[:300],
            "detect_bank_by_text_domains": None,
            "detect_deniz_by_text_name": None,
        },
        "ocr": {
            "detect_bank_by_ocr_domains": None,
        },
        "final": None,
    }

    try:
        out["text_layer"]["detect_bank_by_text_domains"] = detect_bank_by_text_domains(text_norm)
    except Exception as e:
        out["text_layer"]["detect_bank_by_text_domains"] = f"{type(e).__name__}: {e}"

    try:
        out["text_layer"]["detect_deniz_by_text_name"] = detect_deniz_by_text_name(text_norm)
    except Exception as e:
        out["text_layer"]["detect_deniz_by_text_name"] = f"{type(e).__name__}: {e}"

    try:
        out["ocr"]["detect_bank_by_ocr_domains"] = detect_bank_by_ocr_domains(p)
    except Exception as e:
        out["ocr"]["detect_bank_by_ocr_domains"] = f"{type(e).__name__}: {e}"

    try:
        out["final"] = detect_bank_variant(p)
    except Exception as e:
        out["final"] = f"{type(e).__name__}: {e}"

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
