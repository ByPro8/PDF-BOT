import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pdf_logic import fingerprint

BASE = Path(__file__).parent

# IMPORTANT: Render disk mount is an ABSOLUTE path (example: /var/data)
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE / "data")))
UPLOADS = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "checks.db"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE / "templates"))

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,              -- good/bad
            template_hash TEXT NOT NULL,
            filename TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON checks(template_hash)")
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def save_upload(file: UploadFile) -> Path:
    name = Path(file.filename or "upload.pdf").name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    out = UPLOADS / f"{ts}_{name}"
    out.write_bytes(file.file.read())
    return out

def get_matches(template_hash: str):
    conn = db()
    rows = conn.execute(
        "SELECT label, filename FROM checks WHERE template_hash=?",
        (template_hash,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_record(label: str, template_hash: str, filename: str):
    conn = db()
    conn.execute(
        "INSERT INTO checks(label, template_hash, filename, created_at) VALUES(?,?,?,?)",
        (label, template_hash, filename, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    path = save_upload(file)
    fp = fingerprint(path)
    matches = get_matches(fp["template_hash"])

    if any(m["label"] == "bad" for m in matches):
        return {"message": "WE FOUND A MATCH: FAKE (matches BAD database)"}
    if any(m["label"] == "good" for m in matches):
        return {"message": "WE FOUND A MATCH: GOOD (known good template)"}
    return {"message": "NO MATCH FOUND (unknown template)"}

@app.post("/add")
async def add_pdf(label: str = Form(...), file: UploadFile = File(...)):
    label = (label or "").strip().lower()
    if label not in {"good", "bad"}:
        return {"message": "ERROR: label must be good or bad"}

    path = save_upload(file)
    fp = fingerprint(path)
    add_record(label, fp["template_hash"], file.filename or "")
    return {"message": f"ADDED TO DATABASE: {label.upper()}"}
