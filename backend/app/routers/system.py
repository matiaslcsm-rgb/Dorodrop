from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yt_dlp

from .. import updater

router = APIRouter(prefix="/api/system", tags=["system"])


def _versions() -> dict:
    # yt-dlp se importa dentro del servidor: una versión nueva instalada recién
    # se usa después de reiniciar. gallery-dl corre como subproceso, así que
    # la nueva versión se usa enseguida.
    installed = {pkg: updater.installed_version(pkg) for pkg in updater.PACKAGES}
    state = updater.get_state()
    return {
        "installed": installed,
        "restart_needed": installed["yt-dlp"] is not None
        and not updater.same_version(installed["yt-dlp"], yt_dlp.version.__version__),
        "auto_update": updater.auto_update_enabled(),
        "min_age_days": updater.MIN_AGE_DAYS,
        "last_check": state.get("last_check"),
        "last_results": state.get("last_results"),
    }


@router.get("/versions")
def get_versions():
    return _versions()


@router.post("/update-downloaders")
def update_downloaders():
    # manual: se usa cuando algo ya dejó de andar, así que va a la última
    # versión sin esperar los días de "cuarentena" (la prueba y la vuelta
    # atrás siguen aplicando)
    outcome = updater.check_and_update(min_age_days=0, source="manual")
    if "skipped" in outcome:
        raise HTTPException(status_code=409, detail=outcome["skipped"])
    result = _versions()
    result["results"] = outcome["results"]
    return result


class AutoUpdateIn(BaseModel):
    enabled: bool


@router.post("/auto-update")
def set_auto_update(payload: AutoUpdateIn):
    updater.set_auto_update(payload.enabled)
    return _versions()
