import os
import sqlite3
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pdf_logic import fingerprint


ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

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

    # main table
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

    # admin log table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON checks(template_hash)")

    conn.commit()
    conn.close()



init_db()

def check_admin(pw: str):
    return pw == ADMIN_PASSWORD

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

def log_admin(action: str, details: str = ""):

    conn = db()

    conn.execute("""
        INSERT INTO admin_log(action, details, created_at)
        VALUES(?,?,?)
    """, (
        action,
        details,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()

def find_by_filename(name: str):

    if not name:
        return None

    conn = db()

    row = conn.execute("""
        SELECT id, filename
        FROM checks
        WHERE lower(filename)=lower(?)
        LIMIT 1
    """, (name.strip(),)).fetchone()

    conn.close()

    return dict(row) if row else None    


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

        m = matches[0]

        return {
            "message": "WE FOUND A MATCH: FAKE ❌",
            "matched_with": {
                "id": m["id"],
                "filename": m["filename"],
                "url": f"/open/{m['id']}"
            }
        }

    return {
        "message": "NO MATCH FOUND ⚠️"
    }



@app.post("/add")
async def add_pdf(label: str = Form(...), file: UploadFile = File(...)):

    label = label.lower().strip()

    if label not in ["real", "fake"]:
        return {"message": "ERROR: label must be real or fake"}

    filename = (file.filename or "").strip()

    # ---- CHECK DUPLICATE ----
    existing = find_by_filename(filename)

    if existing:

        log_admin("DUPLICATE_ADD", f"{filename} (id={existing['id']})")

        return {
            "error": "DUPLICATE",
            "message": f"❌ DUPLICATE NAME: {filename}",
            "existing": {
                "id": existing["id"],
                "filename": existing["filename"],
                "url": f"/open/{existing['id']}"
            }
        }

    # ---- SAVE NEW ----
    path = save_upload(file)

    fp = fingerprint(path)

    add_record(
        label,
        fp["template_hash"],
        filename,
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

@app.post("/admin/delete")
async def admin_delete(
    file_id: int = Form(...),
    password: str = Form(...)
):

    if not check_admin(password):
        return {"error": "Wrong password"}

    conn = db()

    row = conn.execute(
        "SELECT stored_path FROM checks WHERE id=?",
        (file_id,)
    ).fetchone()

    if not row:
        conn.close()
        return {"error": "Not found"}

    # delete file
    try:
        os.remove(row["stored_path"])
    except:
        pass

    conn.execute("DELETE FROM checks WHERE id=?", (file_id,))
    log_admin("DELETE", f"id={file_id}")
    conn.commit()
    conn.close()

    return {"ok": True, "message": "Deleted"}


@app.post("/admin/label")
async def admin_label(
    file_id: int = Form(...),
    label: str = Form(...),
    password: str = Form(...)
):

    if not check_admin(password):
        return {"error": "Wrong password"}

    if label not in ["real", "fake"]:
        return {"error": "Invalid label"}

    conn = db()

    conn.execute("""
        UPDATE checks SET label=? WHERE id=?
    """, (label, file_id))

    conn.commit()
    conn.close()

    log_admin("LABEL", f"id={file_id} -> {label}")

    return {"ok": True, "message": "Updated"}

@app.get("/search")
def search(q: str):

    conn = db()

    rows = conn.execute("""
        SELECT id, label, filename, created_at
        FROM checks
        WHERE filename LIKE ?
        ORDER BY id DESC
    """, (f"%{q}%",)).fetchall()

    conn.close()

    return [dict(r) for r in rows]


# ----------- DATABASE reset/ delete -----------

@app.get("/admin/reset_db")
def reset_db():

    if DB_PATH.exists():
        DB_PATH.unlink()

    init_db()

    log_admin("RESET_DB", "database wiped")

    return {
        "ok": True,
        "message": "Database reset",
        "link": "/admin/reset_db"
    }



@app.get("/admin/logs")
def get_logs():

    conn = db()

    rows = conn.execute("""
        SELECT action, details, created_at
        FROM admin_log
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return [dict(r) for r in rows]



@app.get("/admin/export")
def export_database():

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zip_path = tmp.name
    tmp.close()

    conn = db()

    rows = conn.execute("""
        SELECT label, filename, stored_path
        FROM checks
    """).fetchall()

    conn.close()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:

        for r in rows:

            label = r["label"] or "unknown"
            src = r["stored_path"]

            if not src or not os.path.exists(src):
                continue

            name = r["filename"] or os.path.basename(src)

            # put into real/ or fake/
            dest = f"{label}/{name}"

            z.write(src, dest)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="pdf_database_backup.zip"
    )

@app.get("/healthz")
def health_check():
    return {"status": "ok"}
