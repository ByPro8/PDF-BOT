import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile


def save_upload_to_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)
    try:
        upload.file.seek(0)
        shutil.copyfileobj(upload.file, tmp)
    finally:
        tmp.close()
    return tmp_path
