from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import db
import storage
import admin

from pdf_logic import fingerprint

app = FastAPI()
templates = Jinja2Templates(directory="templates")

db.init_db()


# ---------- ROUTES ----------


@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):

    path = storage.save_upload(file)

    fp = fingerprint(path)

    matches = db.get_matches(fp["template_hash"])

    if matches:

        m = matches[0]

        return {
            "message": "WE FOUND A MATCH: FAKE ❌",
            "matched_with": {
                "id": m["id"],
                "filename": m["filename"],
                "url": f"/open/{m['id']}",
            },
        }

    return {"message": "NO MATCH FOUND ⚠️"}


@app.post("/add")
async def add_pdf(label: str = Form(...), file: UploadFile = File(...)):

    admin.log("ADD_START", file.filename or "")

    label = label.lower().strip()

    if label not in ["real", "fake"]:

        admin.log("ADD_FAIL", "invalid label")

        return {"message": "ERROR: label must be real or fake"}

    filename = (file.filename or "").strip()

    existing = db.find_by_filename(filename)

    if existing:

        admin.log("DUPLICATE_ADD", f"{filename} (id={existing['id']})")

        return {
            "error": "DUPLICATE",
            "message": f"❌ DUPLICATE NAME: {filename}",
            "existing": {
                "id": existing["id"],
                "filename": existing["filename"],
                "label": existing["label"],
                "url": f"/open/{existing['id']}",
            },
        }

    path = storage.save_upload(file)

    fp = fingerprint(path)

    db.add_record(label, fp["template_hash"], filename, str(path))

    admin.log("ADD_OK", f"{filename} ({label})")

    return {"message": f"ADDED AS {label.upper()} ✅"}


@app.get("/files")
def list_files():

    return db.list_files()


@app.post("/admin/delete")
async def admin_delete(file_id: str = Form(...), password: str = Form(...)):

    admin.log("DELETE_START", f"id={file_id}")

    if not password:
        return {"error": "Password missing"}

    if not file_id.isdigit():
        return {"error": "Invalid ID"}

    if not admin.check_admin(password):
        return {"error": "Wrong password"}

    file_id = int(file_id)

    path = db.get_file_path(file_id)

    if not path:

        admin.log("DELETE_FAIL", f"id={file_id} not found")

        return {"error": "File not found"}

    storage.delete_file(path)

    db.delete_record(file_id)

    admin.log("DELETE_OK", f"id={file_id}")

    return {"message": "Deleted"}


@app.post("/admin/label")
async def admin_label(
    file_id: str = Form(...), label: str = Form(...), password: str = Form(...)
):

    admin.log("LABEL_START", f"id={file_id}")

    if not file_id.isdigit():
        return {"error": "Invalid ID"}

    if not admin.check_admin(password):
        return {"error": "Wrong password"}

    if label not in ["real", "fake"]:
        return {"error": "Invalid label"}

    file_id = int(file_id)

    updated = db.update_label(file_id, label)

    if not updated:

        admin.log("LABEL_FAIL", f"id={file_id}")

        return {"error": "File not found"}

    admin.log("LABEL_OK", f"id={file_id} -> {label}")

    return {"message": "Updated"}


@app.get("/search")
def search(q: str):

    return db.search_files(q)


@app.get("/admin/reset_db")
def reset_db():

    db.reset_db()

    admin.log("RESET_DB")

    return {"message": "Database reset"}


@app.get("/admin/logs")
def logs():

    conn = db.db()

    rows = conn.execute("""
        SELECT action, details, created_at
        FROM admin_log
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return [dict(r) for r in rows]


@app.get("/admin/export")
def export_db():

    path = storage.export_zip()

    return storage.open_file(path)


@app.get("/healthz")
def health():

    return {"status": "ok"}
