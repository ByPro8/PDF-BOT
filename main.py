import os
import tempfile
import logging
import time
import secrets
from pathlib import Path
from typing import Dict, Tuple

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
# PDF VIEW STORE (TEMP)
# -------------------------
PDF_STORE_DIR = Path(tempfile.gettempdir()) / "pdf_checker_store"
PDF_STORE_DIR.mkdir(parents=True, exist_ok=True)

# token -> (path, original_filename, created_ts)
_PDF_INDEX: Dict[str, Tuple[Path, str, float]] = {}
_PDF_TTL_SECONDS = 60 * 30  # keep for 30 minutes


def _cleanup_pdf_store() -> None:
    now = time.time()
    dead = [
        t for t, (_p, _name, ts) in _PDF_INDEX.items() if now - ts > _PDF_TTL_SECONDS
    ]
    for t in dead:
        p, _name, _ts = _PDF_INDEX.pop(t, (None, None, None))
        try:
            if p and p.exists():
                p.unlink()
        except Exception:
            pass


def _store_pdf_for_view(src_path: Path, original_name: str) -> str:
    _cleanup_pdf_store()

    token = secrets.token_urlsafe(16)
    safe_name = (original_name or "file.pdf").replace("/", "_").replace("\\", "_")
    dst = PDF_STORE_DIR / f"{token}__{safe_name}"

    # Move/copy temp file into store
    try:
        data = src_path.read_bytes()
        dst.write_bytes(data)
    except Exception as e:
        raise RuntimeError(f"Could not store PDF: {type(e).__name__}: {e}")

    _PDF_INDEX[token] = (dst, safe_name, time.time())
    return token


def _get_pdf_by_token(token: str) -> Tuple[Path, str]:
    _cleanup_pdf_store()
    item = _PDF_INDEX.get(token)
    if not item:
        raise HTTPException(status_code=404, detail="PDF not found (expired)")
    p, name, _ts = item
    if not p.exists():
        _PDF_INDEX.pop(token, None)
        raise HTTPException(status_code=404, detail="PDF file missing")
    return p, name


# -------------------------
# Upload temp helper
# -------------------------
def save_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(upload.file.read())
    finally:
        tmp.close()
    return Path(tmp.name)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# -------------------------
# View PDF (INLINE)
# -------------------------
@app.get("/pdf/{token}")
def view_pdf(token: str):
    p, name = _get_pdf_by_token(token)
    # IMPORTANT: inline so browser opens it instead of download prompt
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
async def check_pdf(file: UploadFile = File(...)):
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

        # Store for view/download BEFORE deleting temp
        token = _store_pdf_for_view(path, file.filename or "file.pdf")
        view_url = f"/pdf/{token}"
        download_url = f"/pdf/{token}/download"

        # terminal log
        try:
            log.info("---- UPLOAD ----")
            log.info("file: %s", file.filename)
            log.info("---- DETECTED ----")
            log.info("key: %s", detected.get("key"))
            log.info("bank: %s", detected.get("bank"))
            log.info("variant: %s", detected.get("variant"))
            log.info("method: %s", detected.get("method"))
            log.info("---- DATA ----")
            if isinstance(data, dict) and data is not None:
                for k in [
                    "tr_status",
                    "sender_name",
                    "receiver_name",
                    "receiver_iban",
                    "amount",
                    "transaction_time",
                    "receipt_no",
                    "transaction_ref",
                    "error",
                ]:
                    if k in data:
                        log.info("%s: %s", k, data.get(k))
        except Exception:
            pass

        return {
            "message": f"Uploaded: {file.filename}",
            "detected": detected,
            "data": data,
            "view_url": view_url,
            "download_url": download_url,
        }

    except Exception as e:
        log.error("Upload failed: %s (%s: %s)", file.filename, type(e).__name__, e)
        return {
            "message": f"Upload failed: {file.filename}",
            "error": f"{type(e).__name__}: {e}",
        }
    finally:
        # Delete only the temp upload. Stored copy remains in PDF_STORE_DIR.
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/healthz")
def health():
    return {"status": "ok"}
