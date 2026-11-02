"""Actualización automática y segura de yt-dlp y gallery-dl.

Las redes cambian seguido y los descargadores sacan versiones casi todas las
semanas, así que conviene actualizarlos solos. Para hacerlo seguro:

- Solo desde PyPI, vía pip (HTTPS + verificación de hashes).
- Solo se instalan versiones publicadas hace al menos MIN_AGE_DAYS días: si
  sale una versión rota o comprometida, suele retirarse antes de eso.
  (El botón manual ignora la espera: se usa cuando algo ya dejó de andar.)
- Después de instalar se prueba que cada paquete arranque; si no, se vuelve
  a la versión anterior.
- No se actualiza con una descarga en curso.
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version

from . import settings
from .paths import DATA_DIR

PACKAGES = ("yt-dlp", "gallery-dl")
MIN_AGE_DAYS = 3
CHECK_EVERY_SECONDS = 24 * 3600
FIRST_CHECK_DELAY_SECONDS = 60

STATE_FILE = DATA_DIR / "update_state.json"

# downloader.py registra acá una función que dice si hay descargas en curso
is_busy = lambda: False  # noqa: E731

_lock = threading.Lock()

# lo que prueba cada paquete después de instalarlo (en un proceso aparte, así
# no importa la versión que ya está cargada en el servidor)
_SMOKE_TESTS = {
    "yt-dlp": [sys.executable, "-c", "import yt_dlp; yt_dlp.YoutubeDL({'quiet': True})"],
    "gallery-dl": [sys.executable, "-m", "gallery_dl", "--version"],
}


# --- ajustes y estado ---

def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def auto_update_enabled() -> bool:
    return settings.load()["auto_update"]


def set_auto_update(enabled: bool) -> None:
    settings.update(auto_update=bool(enabled))


def get_state() -> dict:
    return _read_json(STATE_FILE, {})


def _save_state(**fields) -> None:
    state = get_state()
    state.update(fields)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# --- versiones ---

def installed_version(pkg: str) -> str | None:
    try:
        return version(pkg)
    except PackageNotFoundError:
        return None


def _vtuple(v: str) -> tuple[int, ...] | None:
    """'2026.10.26' -> (2026, 10, 26). None para pre-releases (rc, dev, b1...),
    que nunca se instalan solas."""
    parts = v.split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def same_version(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and _vtuple(a) == _vtuple(b)


def _latest_safe_version(pkg: str, min_age_days: int) -> str | None:
    """La versión estable más nueva publicada hace al menos `min_age_days`."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=30) as resp:
        data = json.load(resp)
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    candidates = []
    for ver, files in data.get("releases", {}).items():
        vt = _vtuple(ver)
        live = [f for f in files if not f.get("yanked")]
        if vt is None or not live:
            continue
        uploaded = min(datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00")) for f in live)
        if uploaded <= cutoff:
            candidates.append((vt, ver))
    return max(candidates)[1] if candidates else None


# --- instalación ---

def _pip_install(specs: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "--no-input", "--only-binary", ":all:", *specs],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if proc.returncode != 0:
        lines = [l for l in proc.stderr.splitlines() if l.strip()]
        raise RuntimeError(lines[-1] if lines else "pip falló sin dar detalles")


def _smoke_test(pkg: str) -> bool:
    try:
        return subprocess.run(_SMOKE_TESTS[pkg], capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def check_and_update(min_age_days: int = MIN_AGE_DAYS, source: str = "auto") -> dict:
    """Busca versiones nuevas y las instala. Devuelve qué pasó con cada paquete."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "Ya hay una actualización en curso"}
    try:
        if is_busy():
            return {"skipped": "Hay una descarga en curso; se reintenta más tarde"}

        results = {}
        for pkg in PACKAGES:
            current = installed_version(pkg)
            try:
                target = _latest_safe_version(pkg, min_age_days)
            except Exception as exc:
                results[pkg] = {"status": "error", "detail": f"No se pudo consultar PyPI: {exc}"}
                continue
            if target is None or (current and _vtuple(current) >= _vtuple(target)):
                results[pkg] = {"status": "up_to_date", "version": current}
                continue
            try:
                _pip_install([f"{pkg}=={target}"])
            except Exception as exc:
                results[pkg] = {"status": "error", "detail": str(exc)}
                continue
            if _smoke_test(pkg):
                results[pkg] = {"status": "updated", "before": current, "after": target}
            else:
                # la versión nueva no arranca: volver a la que andaba
                if current:
                    try:
                        _pip_install([f"{pkg}=={current}"])
                    except Exception:
                        pass
                results[pkg] = {
                    "status": "rolled_back",
                    "detail": f"La versión {target} no arrancó; se mantuvo la {current}",
                }

        _save_state(
            last_check=datetime.now().isoformat(timespec="seconds"),
            last_source=source,
            last_results=results,
        )
        return {"results": results}
    finally:
        _lock.release()


def _loop():
    time.sleep(FIRST_CHECK_DELAY_SECONDS)
    while True:
        if auto_update_enabled():
            try:
                outcome = check_and_update(source="auto")
                if "skipped" in outcome:
                    time.sleep(15 * 60)  # había una descarga: reintentar pronto
                    continue
            except Exception:
                pass  # sin internet, etc.: se reintenta en el próximo ciclo
        time.sleep(CHECK_EVERY_SECONDS)


def start_auto_update_thread() -> None:
    threading.Thread(target=_loop, daemon=True, name="auto-update").start()
