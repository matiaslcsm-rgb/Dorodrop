"""Limpieza periódica de data/downloads y data/tmp.

Todo lo que hay ahí es temporal: el archivo ya se le entregó al navegador
cuando terminó la descarga/conversión. Sin esto la carpeta crece sin límite.
"""
import shutil
import threading
import time

from .paths import DOWNLOADS_DIR, TMP_DIR

MAX_AGE_SECONDS = 24 * 3600
CHECK_EVERY_SECONDS = 3600


def cleanup_old_files(max_age: float = MAX_AGE_SECONDS) -> int:
    """Borra lo que tenga más de `max_age` segundos; devuelve cuántos ítems borró."""
    cutoff = time.time() - max_age
    removed = 0
    for folder in (DOWNLOADS_DIR, TMP_DIR):
        for item in folder.iterdir():
            if item.name == ".gitkeep":
                continue
            try:
                if item.stat().st_mtime > cutoff:
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                removed += 1
            except OSError:
                # un archivo en uso (descarga en curso) se intenta de nuevo la próxima
                pass
    return removed


def _loop():
    while True:
        cleanup_old_files()
        time.sleep(CHECK_EVERY_SECONDS)


def start_cleanup_thread() -> None:
    threading.Thread(target=_loop, daemon=True, name="cleanup").start()
