"""Entrega de archivos: al navegador o directo a la carpeta de Doro Drop.

Cada herramienta devuelve su resultado con `deliver(...)` en vez de
`FileResponse(...)`. Si el pedido viene de esta misma PC, trae el header
`X-Doro-Save: <sección>` (lo agrega la página) y está activado "guardar en
carpeta", el archivo se copia a la carpeta elegida y se responde un JSON con
dónde quedó. Si no (por ejemplo alguien que entra por la red), se manda al
navegador como siempre.
"""
import contextvars
import shutil
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse

from . import settings

_current_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar(
    "current_request", default=None
)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


async def remember_request(request: Request, call_next):
    """Middleware: deja el pedido a mano para `deliver`."""
    token = _current_request.set(request)
    try:
        return await call_next(request)
    finally:
        _current_request.reset(token)


def is_local(request: Request | None) -> bool:
    return bool(request and request.client and request.client.host in LOCAL_HOSTS)


def _unique_path(folder: Path, filename: str) -> Path:
    """'foto.jpg' -> 'foto (2).jpg' si ya existe: nunca pisar nada."""
    dest = folder / filename
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while dest.exists():
        dest = folder / f"{stem} ({n}){suffix}"
        n += 1
    return dest


def save_to_folder(path: Path, filename: str, section: str | None) -> Path:
    folder = settings.folder_for(section)
    folder.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(folder, filename)
    shutil.copy2(path, dest)
    return dest


def deliver(path, filename: str | None = None, media_type: str | None = None):
    path = Path(path)
    filename = filename or path.name
    request = _current_request.get()
    section = request.headers.get("x-doro-save") if request else None
    if section and is_local(request) and settings.load()["save_to_folder"]:
        dest = save_to_folder(path, filename, section)
        return JSONResponse(
            {"saved": True, "filename": dest.name, "path": str(dest), "folder": str(dest.parent)}
        )
    return FileResponse(path, filename=filename, media_type=media_type)
