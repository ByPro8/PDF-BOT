import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.routes import router as web_router


log = logging.getLogger("pdf-checker")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

# Serve CSS/JS
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

# All endpoints (/, /check, /pdf/*, /healthz)
app.include_router(web_router)
