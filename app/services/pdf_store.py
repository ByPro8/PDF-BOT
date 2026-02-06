import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException


PDF_STORE_DIR = Path(tempfile.gettempdir()) / "pdf_checker_store"
PDF_STORE_DIR.mkdir(parents=True, exist_ok=True)

PDF_TTL_SECONDS = 60 * 30  # 30 minutes


def cleanup_pdf_store(now: Optional[float] = None) -> None:
    now_ts = now if now is not None else time.time()
    try:
        for p in PDF_STORE_DIR.glob("*__*"):
            try:
                if (now_ts - p.stat().st_mtime) > PDF_TTL_SECONDS:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def store_pdf_for_view(src_path: Path, original_name: str) -> str:
    cleanup_pdf_store()

    token = secrets.token_urlsafe(16)
    safe_name = (original_name or "file.pdf").replace("/", "_").replace("\\", "_")
    dst = PDF_STORE_DIR / f"{token}__{safe_name}"

    try:
        with src_path.open("rb") as r, dst.open("wb") as w:
            shutil.copyfileobj(r, w)
    except Exception as e:
        raise RuntimeError(f"Could not store PDF: {type(e).__name__}: {e}")

    return token


def get_pdf_by_token(token: str) -> Tuple[Path, str]:
    cleanup_pdf_store()

    matches = list(PDF_STORE_DIR.glob(f"{token}__*"))
    if not matches:
        raise HTTPException(status_code=404, detail="PDF not found (expired)")

    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    p = matches[0]
    name = p.name.split("__", 1)[1] if "__" in p.name else "file.pdf"
    return p, name
