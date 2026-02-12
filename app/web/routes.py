import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from starlette.requests import Request

from app.detectors.bank_detect import detect_bank_variant
from app.parsers.registry import parse_by_key
from app.services.pdf_context import PDFContext
from app.services.pdf_meta import extract_metadata_logs
from app.services.pdf_store import get_pdf_by_token, store_pdf_for_view
from app.services.pdf_view import build_pdf_wrapper_html
from app.services.upload import save_upload_to_temp
from app.web.templates import templates

router = APIRouter()
log = logging.getLogger("pdf-checker")


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/pdf/{token}", response_class=HTMLResponse)
def view_pdf(token: str):
    _p, name = get_pdf_by_token(token)
    html = build_pdf_wrapper_html(token=token, filename=name)
    return HTMLResponse(content=html)


@router.get("/pdf/{token}/raw")
def view_pdf_raw(token: str):
    p, name = get_pdf_by_token(token)
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=name,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@router.get("/pdf/{token}/download")
def download_pdf(token: str):
    p, name = get_pdf_by_token(token)
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=name,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/check")
def check_pdf(file: UploadFile = File(...)):
    path = save_upload_to_temp(file)
    display_name = file.filename or "file.pdf"

    try:
        # Per-request cache (bytes + reader + first pages text)
        ctx = PDFContext(path=path, display_name=display_name, max_pages_text=2)

        # Detection: reuse normalized text
        detected = detect_bank_variant(path, text_norm=ctx.text_norm)

        # Parsing: Phase 2B — pass cached text to parsers that support it
        try:
            data = parse_by_key(
                detected.get("key", ""),
                path,
                text_raw=ctx.text_raw,
                text_norm=ctx.text_norm,
            )
        except Exception as e:
            data = {"error": f"{type(e).__name__}: {e}"}

        if isinstance(data, dict) and data is not None:
            data.setdefault("tr_status", "unknown")
        else:
            data = {"tr_status": "unknown"}

        # Metadata: reuse cached bytes/reader
        meta = extract_metadata_logs(
            path,
            display_name=display_name,
            pdf_bytes=ctx.pdf_bytes,
            pdf_reader=ctx.reader,
        )

        token = store_pdf_for_view(path, display_name)
        return {
            "message": f"Uploaded: {display_name}",
            "detected": detected,
            "data": data,
            "meta": meta,
            "view_url": f"/pdf/{token}",
            "download_url": f"/pdf/{token}/download",
        }

    except Exception as e:
        log.error(
            "Upload failed: %s (%s: %s)",
            getattr(file, "filename", None),
            type(e).__name__,
            e,
        )
        return {
            "message": f"Upload failed: {getattr(file, 'filename', None)}",
            "error": f"{type(e).__name__}: {e}",
        }

    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@router.get("/healthz")
def health():
    return {"status": "ok"}
