import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pdf_logic import fingerprint


# ---------------- CONFIG ----------------

BASE = Path(__file__).parent

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE / "data")))
UPLOADS = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "checks.db"

UPLOADS.mkdir(parents=True, exist_ok=True)


# ---------------- APP ----------------

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE / "templates"))


# ---------------- DATABASE ----------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            template_hash TEXT NOT NULL,
            filename TEXT,
            stored_path TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON checks(template_hash)")
    conn.commit()
    conn.close()


init_db()


# ---------------- HELPERS ----------------

def save_upload(file: UploadFile) -> Path:
    name = Path(file.filename or "upload.pdf").name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    out = UPLOADS / f"{ts}_{name}"
    out.write_bytes(file.file.read())
    return out


def get_matches(template_hash: str):
    conn = db()
    rows = conn.execute("""
        SELECT id, filename
        FROM checks
        WHERE template_hash=?
    """, (template_hash,)).fetchall()

    conn.close()

    return [dict(r) for r in rows]


def add_record(label, template_hash, filename, path):
    conn = db()
    conn.execute("""
        INSERT INTO checks(label, template_hash, filename, stored_path, created_at)
        VALUES(?,?,?,?,?)
    """, (
        label,
        template_hash,
        filename,
        path,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()


# ---------------- ROUTES ----------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    path = save_upload(file)

    fp = fingerprint(path)
    matches = get_matches(fp["template_hash"])

    if matches:

        m = matches[0]   # first match

        return {
        "message": "WE FOUND A MATCH: FAKE ❌",
        "matched_with": {
            "id": m["id"],
            "filename": m["filename"],
            "url": f"/open/{m['id']}"
        }
    }

    return {"message": "NO MATCH FOUND ⚠️"}



@app.post("/add")
async def add_pdf(label: str = Form(...), file: UploadFile = File(...)):

    label = label.lower().strip()

    if label not in ["good", "bad"]:
        return {"message": "ERROR: label must be good or bad"}

    path = save_upload(file)

    fp = fingerprint(path)

    add_record(
        label,
        fp["template_hash"],
        file.filename or "",
        str(path)
    )

    return {"message": f"ADDED AS {label.upper()} ✅"}


# ----------- DATABASE VIEW -----------

@app.get("/files")
def list_files():

    conn = db()
    rows = conn.execute("""
        SELECT id, label, filename, created_at
        FROM checks
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    return [dict(r) for r in rows]


@app.get("/open/{file_id}")
def open_file(file_id: int):

    conn = db()
    row = conn.execute("""
        SELECT stored_path FROM checks WHERE id=?
    """, (file_id,)).fetchone()
    conn.close()

    if not row:
        return {"error": "File not found"}

    return FileResponse(
        row["stored_path"],
        media_type="application/pdf"
    )
