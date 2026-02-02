import os
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
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


@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    path = save_temp(file)
    try:
        detected = detect_bank_variant(path, use_ocr_fallback=USE_OCR)

        try:
            data = parse_by_key(detected["key"], path)
        except Exception as e:
            data = {"error": f"{type(e).__name__}: {e}"}

        # Ensure tr_status always exists (parsers decide; if missing -> unknown)
        if isinstance(data, dict) and data is not None:
            data.setdefault("tr_status", "unknown")
        else:
            data = {"tr_status": "unknown"}

        # --- Pretty terminal log ---
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
