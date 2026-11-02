import shutil
import subprocess
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from ..paths import TMP_DIR

router = APIRouter(prefix="/api/media", tags=["media"])

ALLOWED_FORMATS = {"mp4", "webm", "mkv", "avi", "mov", "mp3", "wav", "ogg", "aac", "flac"}


@router.post("/convert")
async def convert_media(
    file: UploadFile = File(...),
    target_format: str = Form(...),
):
    if shutil.which("ffmpeg") is None:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg no está instalado o no está en el PATH del sistema",
        )

    fmt = target_format.lower().strip(".")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {fmt}")

    src_path = TMP_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    with src_path.open("wb") as f:
        f.write(await file.read())

    out_path = TMP_DIR / f"{uuid.uuid4().hex}_convertido.{fmt}"

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src_path), str(out_path)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500, detail=f"ffmpeg falló: {result.stderr[-800:]}"
            )
    finally:
        src_path.unlink(missing_ok=True)

    return FileResponse(out_path, filename=f"convertido.{fmt}")
