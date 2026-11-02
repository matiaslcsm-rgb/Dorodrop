"""Abre Doro Drop como una app: servidor sin ventanas de consola + ventana
propia de Edge (modo app: sin pestañas ni barra de direcciones). Al cerrar la
ventana se apaga todo.

Se corre con pythonw (sin consola):
    pythonw backend/launcher.py          # solo esta PC
    pythonw backend/launcher.py --lan    # además, accesible desde la red

Si ya está abierto, solo abre otra ventana. Si no hay Edge, usa el navegador
predeterminado y se apaga solo unos minutos después de cerrar la pestaña.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
BASE = BACKEND.parent
DATA = BASE / "data"
LOG_FILE = DATA / "launcher.log"
PREFERRED_PORT = 8010
HEARTBEAT_TIMEOUT = 180  # minimizado, el navegador avisa como mucho una vez por minuto


def _hide_child_consoles() -> None:
    """Sin consola propia, cada subproceso (ffmpeg, pip, gallery-dl...) abriría
    una ventana negra. Esto los arranca a todos ocultos."""
    if os.name != "nt":
        return
    original_init = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = init


def _show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Doro Drop", 0x10)
    except Exception:
        pass


def _is_doro_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/options", timeout=1.5) as resp:
            return "save_to_folder" in json.load(resp)
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _open_window(url: str):
    """Ventana de Edge en modo app; None si no hay Edge (abre el navegador)."""
    from app import desktop

    edge = desktop.find_edge()
    if edge is None:
        webbrowser.open(url)
        return None
    return subprocess.Popen([
        str(edge),
        f"--app={url}",
        # perfil propio: la ventana es un proceso aparte (sabemos cuándo se
        # cierra) y no se mezcla con las pestañas ni extensiones del usuario
        f"--user-data-dir={DATA / 'ventana'}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--window-size=1180,900",
    ])


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    # pythonw no tiene stdout/stderr: yt-dlp y uvicorn escriben ahí
    sys.stdout = sys.stderr = log
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} abriendo Doro Drop ---")

    sys.path.insert(0, str(BACKEND))
    _hide_child_consoles()

    if _is_doro_running(PREFERRED_PORT):
        # ya está abierto (por ejemplo, doble clic de nuevo): solo otra ventana
        _open_window(f"http://localhost:{PREFERRED_PORT}")
        return

    port = next((p for p in range(PREFERRED_PORT, PREFERRED_PORT + 20) if _port_free(p)), None)
    if port is None:
        _show_error("No hay ningún puerto libre entre 8010 y 8029 para abrir Doro Drop.")
        return

    import uvicorn
    from app import settings
    from app.main import app
    from app.routers import downloader, options

    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False))
    threading.Thread(target=server.run, daemon=True, name="server").start()

    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        _show_error(f"Doro Drop no pudo arrancar. Detalles en:\n{LOG_FILE}")
        return

    # la primera vez en la versión portable, dejamos el ícono en el escritorio
    if (BASE / "python").is_dir() and not settings.load()["shortcut_created"]:
        try:
            from app import desktop

            desktop.create_desktop_shortcut()
            settings.update(shortcut_created=True)
        except Exception:
            traceback.print_exc()

    url = f"http://localhost:{port}"
    window = _open_window(url)
    options.last_ping = time.time()

    while True:
        time.sleep(2)
        window_closed = window is not None and window.poll() is not None
        no_heartbeat = time.time() - options.last_ping > HEARTBEAT_TIMEOUT
        if (window_closed or no_heartbeat) and not downloader.has_active_jobs():
            break

    print("ventana cerrada, apagando")
    server.should_exit = True
    time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        _show_error(f"Doro Drop se cerró por un error. Detalles en:\n{LOG_FILE}")
