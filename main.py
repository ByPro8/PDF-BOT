# main.py (only the /check endpoint + helpers shown)
import os
import tempfile
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

        data = None
        try:
            data = parse_by_key(detected["key"], path)
        except Exception as e:
            data = {"error": f"{type(e).__name__}: {e}"}

        return {
            "message": f"Uploaded: {file.filename}",
            "detected": detected,
            "data": data,
        }

    except Exception as e:
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
