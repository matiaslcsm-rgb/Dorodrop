import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import desktop, settings
from ..delivery import is_local

router = APIRouter(prefix="/api/options", tags=["options"])

# la ventana de la app avisa cada tanto que sigue abierta; el lanzador apaga
# el servidor si deja de recibir avisos (por si no se pudo usar Edge)
last_ping = time.time()


def _public(request: Request) -> dict:
    s = settings.load()
    return {
        **s,
        "save_dir": str(settings.save_dir()),
        "default_save_dir": str(settings.default_save_dir()),
        "is_custom_dir": bool(s["save_dir"]),
        "section_folders": settings.SECTION_FOLDERS,
        # elegir carpeta, abrir el Explorador, etc. solo tienen sentido en la
        # PC donde corre Doro Drop, no para quien entra por la red
        "is_local": is_local(request),
    }


def _require_local(request: Request) -> None:
    if not is_local(request):
        raise HTTPException(status_code=403, detail="Esto solo se puede hacer desde la PC donde corre Doro Drop")


@router.get("")
def get_options(request: Request):
    return _public(request)


class OptionsIn(BaseModel):
    save_to_folder: bool | None = None
    subfolders: bool | None = None
    show_help: bool | None = None
    save_dir: str | None = None  # "" vuelve a la carpeta por defecto


@router.post("")
def set_options(payload: OptionsIn, request: Request):
    changes = payload.model_dump(exclude_none=True)
    if "save_dir" in changes or "save_to_folder" in changes or "subfolders" in changes:
        _require_local(request)
    if changes.get("save_dir"):
        folder = Path(changes["save_dir"]).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"No se puede usar esa carpeta: {exc}") from exc
        changes["save_dir"] = str(folder)
    settings.update(**changes)
    return _public(request)


@router.post("/pick-folder")
def pick_folder(request: Request):
    _require_local(request)
    current = settings.save_dir()
    start = current if current.exists() else current.parent
    chosen = desktop.pick_folder(start)
    if chosen:
        settings.update(save_dir=chosen)
    return {**_public(request), "changed": bool(chosen)}


class RevealIn(BaseModel):
    path: str | None = None  # archivo recién guardado; vacío = la carpeta base


@router.post("/reveal")
def reveal(payload: RevealIn, request: Request):
    _require_local(request)
    base = settings.save_dir()
    target = Path(payload.path) if payload.path else base
    # solo cosas dentro de la carpeta de Doro Drop
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Esa ruta no es de Doro Drop")
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True) if target == base else None
        if not target.exists():
            raise HTTPException(status_code=404, detail="Ya no existe ese archivo")
    desktop.reveal(target)
    return {"ok": True}


@router.post("/shortcut")
def create_shortcut(request: Request):
    _require_local(request)
    try:
        path = desktop.create_desktop_shortcut()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    settings.update(shortcut_created=True)
    return {"ok": True, "path": str(path)}


@router.post("/ping")
def ping():
    global last_ping
    last_ping = time.time()
    return {"ok": True}
