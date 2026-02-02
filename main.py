from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    # We intentionally do NOT save anything and do NOT fingerprint anything.
    filename = (file.filename or "unknown.pdf").strip()

    # Read once so upload completes cleanly (still not saved anywhere)
    _ = await file.read()

    return {"message": f"Uploaded: {filename}"}


@app.get("/healthz")
def health():
    return {"status": "ok"}
