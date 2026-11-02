import json
import uuid
import zipfile
from pathlib import Path

import numpy as np
import rawpy
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image

from ..paths import DATA_DIR, TMP_DIR

router = APIRouter(prefix="/api/image", tags=["image"])

ALLOWED_FORMATS = {"png", "jpeg", "jpg", "webp", "bmp", "gif", "tiff"}
RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".rw2", ".orf", ".raf", ".pef", ".srw", ".raw",
}


def _is_raw(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in RAW_EXTENSIONS)


def _open_as_rgb(path, *, half_size: bool = False) -> Image.Image:
    if _is_raw(str(path)):
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, half_size=half_size, output_bps=8)
        return Image.fromarray(rgb)

    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


async def _save_upload(upload: UploadFile) -> Path:
    dest = TMP_DIR / f"{uuid.uuid4().hex}_{upload.filename}"
    with dest.open("wb") as f:
        f.write(await upload.read())
    return dest


@router.post("/convert")
async def convert_image(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    max_width: int | None = Form(None),
):
    fmt = target_format.lower().strip(".")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {fmt}")

    src_path = await _save_upload(file)

    try:
        img = _open_as_rgb(src_path) if _is_raw(file.filename) else Image.open(src_path)
        if max_width and img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)))

        save_fmt = "JPEG" if fmt in ("jpg", "jpeg") else fmt.upper()
        if save_fmt == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        out_path = TMP_DIR / f"{uuid.uuid4().hex}_convertida.{fmt}"
        img.save(out_path, format=save_fmt)
    finally:
        src_path.unlink(missing_ok=True)

    return FileResponse(out_path, filename=f"convertida.{fmt}")


@router.post("/raw-to-jpg")
async def raw_to_jpg(files: list[UploadFile] = File(...), quality: int = Form(92)):
    saved_paths = []
    out_paths = []
    try:
        for upload in files:
            saved_paths.append(await _save_upload(upload))

        for src_path, upload in zip(saved_paths, files):
            img = _open_as_rgb(src_path)
            stem = upload.filename.rsplit(".", 1)[0]
            out_path = TMP_DIR / f"{uuid.uuid4().hex}_{stem}.jpg"
            img.save(out_path, format="JPEG", quality=quality)
            out_paths.append(out_path)

        if len(out_paths) == 1:
            return FileResponse(out_paths[0], filename=out_paths[0].name.split("_", 1)[1])

        zip_path = TMP_DIR / f"{uuid.uuid4().hex}_raw_a_jpg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in out_paths:
                zf.write(p, arcname=p.name.split("_", 1)[1])
        return FileResponse(zip_path, filename="raw_a_jpg.zip", media_type="application/zip")
    except rawpy.LibRawError as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo RAW: {exc}") from exc
    finally:
        for p in saved_paths:
            p.unlink(missing_ok=True)


@router.post("/preview")
async def image_preview(file: UploadFile = File(...)):
    src_path = await _save_upload(file)
    try:
        img = _open_as_rgb(src_path, half_size=True)
        img.thumbnail((900, 900))
        out_path = TMP_DIR / f"{uuid.uuid4().hex}_preview.jpg"
        img.save(out_path, format="JPEG", quality=88)
    except rawpy.LibRawError as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}") from exc
    finally:
        src_path.unlink(missing_ok=True)

    return FileResponse(out_path, filename="preview.jpg")


def _apply_edits(img: Image.Image, exposure: float, contrast: float, saturation: float,
                  temperature: float, tint: float) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)

    arr = arr * (1 + exposure / 100)

    if contrast:
        luma = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
        mean = float(luma.mean())
        arr = mean + (arr - mean) * (1 + contrast / 100)

    if saturation:
        luma = (arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114)[..., None]
        arr = luma + (arr - luma) * (1 + saturation / 100)

    arr[..., 0] += temperature * 0.6
    arr[..., 2] -= temperature * 0.6

    arr[..., 1] -= tint * 0.5
    arr[..., 0] += tint * 0.25
    arr[..., 2] += tint * 0.25

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


@router.post("/edit")
async def edit_image(
    file: UploadFile = File(...),
    exposure: float = Form(0),
    contrast: float = Form(0),
    saturation: float = Form(0),
    temperature: float = Form(0),
    tint: float = Form(0),
    target_format: str = Form("jpg"),
):
    fmt = target_format.lower().strip(".")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {fmt}")

    src_path = await _save_upload(file)
    try:
        img = _open_as_rgb(src_path)
        edited = _apply_edits(img, exposure, contrast, saturation, temperature, tint)

        save_fmt = "JPEG" if fmt in ("jpg", "jpeg") else fmt.upper()
        save_kwargs = {"quality": 95} if save_fmt == "JPEG" else {}
        out_path = TMP_DIR / f"{uuid.uuid4().hex}_editada.{fmt}"
        edited.save(out_path, format=save_fmt, **save_kwargs)
    except rawpy.LibRawError as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}") from exc
    finally:
        src_path.unlink(missing_ok=True)

    return FileResponse(out_path, filename=f"editada.{fmt}")


@router.post("/edit-batch")
async def edit_images_batch(
    files: list[UploadFile] = File(...),
    exposure: float = Form(0),
    contrast: float = Form(0),
    saturation: float = Form(0),
    temperature: float = Form(0),
    tint: float = Form(0),
    target_format: str = Form("jpg"),
):
    fmt = target_format.lower().strip(".")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {fmt}")

    save_fmt = "JPEG" if fmt in ("jpg", "jpeg") else fmt.upper()
    save_kwargs = {"quality": 95} if save_fmt == "JPEG" else {}

    saved_paths = []
    out_paths = []
    try:
        for upload in files:
            saved_paths.append(await _save_upload(upload))

        for src_path, upload in zip(saved_paths, files):
            img = _open_as_rgb(src_path)
            edited = _apply_edits(img, exposure, contrast, saturation, temperature, tint)
            stem = upload.filename.rsplit(".", 1)[0]
            out_path = TMP_DIR / f"{uuid.uuid4().hex}_{stem}.{fmt}"
            edited.save(out_path, format=save_fmt, **save_kwargs)
            out_paths.append(out_path)

        if len(out_paths) == 1:
            return FileResponse(out_paths[0], filename=out_paths[0].name.split("_", 1)[1])

        zip_path = TMP_DIR / f"{uuid.uuid4().hex}_editadas.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in out_paths:
                zf.write(p, arcname=p.name.split("_", 1)[1])
        return FileResponse(zip_path, filename="editadas.zip", media_type="application/zip")
    except rawpy.LibRawError as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer un archivo RAW: {exc}") from exc
    finally:
        for p in saved_paths:
            p.unlink(missing_ok=True)


# --- Perfiles de color (presets) ---

PRESETS_FILE = DATA_DIR / "presets.json"


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    exposure: float = 0
    contrast: float = 0
    saturation: float = 0
    temperature: float = 0
    tint: float = 0


def _load_presets() -> list[dict]:
    if not PRESETS_FILE.exists():
        return []
    try:
        return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_presets(presets: list[dict]) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/presets")
def list_presets():
    return _load_presets()


@router.post("/presets")
def create_preset(payload: PresetIn):
    preset = {"id": uuid.uuid4().hex, **payload.model_dump()}
    presets = _load_presets()
    presets.append(preset)
    _save_presets(presets)
    return preset


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str):
    presets = _load_presets()
    remaining = [p for p in presets if p["id"] != preset_id]
    if len(remaining) == len(presets):
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    _save_presets(remaining)
    return {"deleted": preset_id}
