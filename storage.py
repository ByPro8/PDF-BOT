from pathlib import Path
from datetime import datetime
import os
import tempfile
import zipfile

from fastapi import UploadFile
from fastapi.responses import FileResponse

import db

BASE = Path(__file__).parent
DATA_DIR = db.DATA_DIR
UPLOADS = DATA_DIR / "uploads"

UPLOADS.mkdir(parents=True, exist_ok=True)


def save_upload(file: UploadFile) -> Path:

    name = Path(file.filename or "upload.pdf").name
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

    out = UPLOADS / f"{ts}_{name}"

    out.write_bytes(file.file.read())

    return out


def delete_file(path):

    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass


def open_file(path):

    filename = os.path.basename(path)

    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


def export_zip():

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zip_path = tmp.name
    tmp.close()

    rows = (
        db.db()
        .execute(
            """
        SELECT label, filename, stored_path FROM checks
    """
        )
        .fetchall()
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:

        for r in rows:

            src = r["stored_path"]

            if not src or not os.path.exists(src):
                continue

            label = r["label"] or "unknown"
            name = r["filename"] or os.path.basename(src)

            z.write(src, f"{label}/{name}")

    return zip_path
