import os
import tempfile
import logging
import time
import secrets
import shutil
from pathlib import Path
from typing import Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.detectors.bank_detect import detect_bank_variant
from app.parsers.registry import parse_by_key

app = FastAPI()
templates = Jinja2Templates(directory="templates")

USE_OCR = os.getenv("USE_OCR", "0") == "1"

log = logging.getLogger("pdf-checker")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

# -------------------------
# PDF VIEW STORE (DISK, MULTI-WORKER SAFE)
# -------------------------
PDF_STORE_DIR = Path(tempfile.gettempdir()) / "pdf_checker_store"
PDF_STORE_DIR.mkdir(parents=True, exist_ok=True)

_PDF_TTL_SECONDS = 60 * 30  # keep for 30 minutes


def _cleanup_pdf_store() -> None:
    """Delete stored PDFs older than TTL (safe across multiple workers)."""
    now = time.time()
    try:
        for p in PDF_STORE_DIR.glob("*__*.pdf"):
            try:
                if (now - p.stat().st_mtime) > _PDF_TTL_SECONDS:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def _store_pdf_for_view(src_path: Path, original_name: str) -> str:
    _cleanup_pdf_store()

    token = secrets.token_urlsafe(16)
    safe_name = (original_name or "file.pdf").replace("/", "_").replace("\\", "_")

    # store as: <token>__<originalfilename>.pdf
    dst = PDF_STORE_DIR / f"{token}__{safe_name}"

    try:
        with src_path.open("rb") as r, dst.open("wb") as w:
            shutil.copyfileobj(r, w)
    except Exception as e:
        raise RuntimeError(f"Could not store PDF: {type(e).__name__}: {e}")

    return token


def _get_pdf_by_token(token: str) -> Tuple[Path, str]:
    _cleanup_pdf_store()

    matches = list(PDF_STORE_DIR.glob(f"{token}__*"))
    if not matches:
        raise HTTPException(status_code=404, detail="PDF not found (expired)")

    # if duplicates exist, newest wins
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    p = matches[0]
    name = p.name.split("__", 1)[1] if "__" in p.name else "file.pdf"
    return p, name


# -------------------------
# Upload temp helper (STREAM TO DISK)
# -------------------------
def save_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)
    try:
        upload.file.seek(0)
        shutil.copyfileobj(upload.file, tmp)
    finally:
        tmp.close()
    return tmp_path


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# -------------------------
# View PDF (INLINE)
# -------------------------
@app.get("/pdf/{token}")
def view_pdf(token: str):
    p, name = _get_pdf_by_token(token)
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=name,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


# -------------------------
# Download PDF (ATTACHMENT)
# -------------------------
@app.get("/pdf/{token}/download")
def download_pdf(token: str):
    p, name = _get_pdf_by_token(token)
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=name,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.post("/check")
def check_pdf(file: UploadFile = File(...)):
    path = save_temp(file)
    try:
        detected = detect_bank_variant(path, use_ocr_fallback=USE_OCR)

        try:
            data = parse_by_key(detected["key"], path)
        except Exception as e:
            data = {"error": f"{type(e).__name__}: {e}"}

        if isinstance(data, dict) and data is not None:
            data.setdefault("tr_status", "unknown")
        else:
            data = {"tr_status": "unknown"}

        token = _store_pdf_for_view(path, file.filename or "file.pdf")
        return {
            "message": f"Uploaded: {file.filename}",
            "detected": detected,
            "data": data,
            "view_url": f"/pdf/{token}",
            "download_url": f"/pdf/{token}/download",
        }

    except Exception as e:
        log.error("Upload failed: %s (%s: %s)", file.filename, type(e).__name__, e)
        return {
            "message": f"Upload failed: {file.filename}",
            "error": f"{type(e).__name__}: {e}",
        }
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/healthz")
def health():
    return {"status": "ok"}
