import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.detectors.bank_detect import detect_bank_variant

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# later you can set USE_OCR=1 on Render if you add OCR deps
USE_OCR = os.getenv("USE_OCR", "0") == "1"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    if not file.filename:
        return {"error": "Missing filename"}

    suffix = Path(file.filename).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    try:
        tmp.write(await file.read())
        tmp.flush()
        tmp_path = Path(tmp.name)

        hit = detect_bank_variant(tmp_path, use_ocr_fallback=USE_OCR)

        return {
            "message": "Uploaded ✅",
            "filename": file.filename,
            "bank": hit["bank"],
            "variant": hit["variant"],
            "method": hit["method"],
        }

    finally:
        try:
            tmp.close()
            os.unlink(tmp.name)
        except Exception:
            pass


@app.get("/healthz")
def health():
    return {"status": "ok"}
