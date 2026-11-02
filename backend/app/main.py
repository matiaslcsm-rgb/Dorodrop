from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import updater
from .cleanup import start_cleanup_thread
from .routers import downloader, pdf_tools, images, media, notes, system

app = FastAPI(title="Multiherramienta Local")

app.include_router(downloader.router)
app.include_router(pdf_tools.router)
app.include_router(images.router)
app.include_router(media.router)
app.include_router(notes.router)
app.include_router(system.router)


@app.on_event("startup")
def _start_background_tasks():
    start_cleanup_thread()
    updater.is_busy = downloader.has_active_jobs
    updater.start_auto_update_thread()


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
