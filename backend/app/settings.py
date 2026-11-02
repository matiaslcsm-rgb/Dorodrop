"""Ajustes de Doro Drop, guardados en data/settings.json (uno por PC)."""
import json
import os
import threading
from pathlib import Path

from .paths import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULTS = {
    "auto_update": True,     # actualizar yt-dlp y gallery-dl solos
    "save_to_folder": True,  # guardar los resultados directo en save_dir
    "save_dir": "",          # vacío = Descargas\Doro Drop
    "subfolders": True,      # una subcarpeta por sección (PDF, Imágenes...)
    "show_help": True,       # explicación breve arriba de cada sección
    "shortcut_created": False,
}

# nombre de la subcarpeta para cada pestaña de la interfaz
SECTION_FOLDERS = {
    "download": "Descargas",
    "pdf": "PDF",
    "image": "Imágenes",
    "media": "Audio y video",
    "editor": "Editor",
}

_lock = threading.Lock()


def load() -> dict:
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def update(**changes) -> dict:
    with _lock:
        current = load()
        current.update({k: v for k, v in changes.items() if k in DEFAULTS})
        SETTINGS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        return current


def _windows_downloads_dir() -> Path:
    """La carpeta Descargas real (el usuario puede haberla movido a otro disco)."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
        return Path(os.path.expandvars(value))
    except (ImportError, OSError):
        return Path.home() / "Downloads"


def default_save_dir() -> Path:
    return _windows_downloads_dir() / "Doro Drop"


def save_dir() -> Path:
    custom = load()["save_dir"]
    return Path(custom) if custom else default_save_dir()


def folder_for(section: str | None) -> Path:
    base = save_dir()
    if section and load()["subfolders"] and section in SECTION_FOLDERS:
        return base / SECTION_FOLDERS[section]
    return base
