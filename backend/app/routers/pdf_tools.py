import uuid
from pathlib import Path

import img2pdf
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter

from ..paths import TMP_DIR

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _save_upload(upload: UploadFile) -> Path:
    dest = TMP_DIR / f"{uuid.uuid4().hex}_{upload.filename}"
    with dest.open("wb") as f:
        f.write(upload.file.read())
    return dest


@router.post("/merge")
async def merge_pdfs(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Subí al menos 2 archivos PDF")

    writer = PdfWriter()
    saved_paths = []
    try:
        for upload in files:
            path = _save_upload(upload)
            saved_paths.append(path)
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)

        out_path = TMP_DIR / f"{uuid.uuid4().hex}_merged.pdf"
        with out_path.open("wb") as f:
            writer.write(f)
    finally:
        for p in saved_paths:
            p.unlink(missing_ok=True)

    return FileResponse(out_path, filename="unido.pdf", media_type="application/pdf")


@router.post("/split")
async def split_pdf(file: UploadFile = File(...)):
    path = _save_upload(file)
    try:
        reader = PdfReader(str(path))
        out_dir = TMP_DIR / uuid.uuid4().hex
        out_dir.mkdir()
        page_paths = []
        for i, page in enumerate(reader.pages, start=1):
            writer = PdfWriter()
            writer.add_page(page)
            page_path = out_dir / f"pagina_{i}.pdf"
            with page_path.open("wb") as f:
                writer.write(f)
            page_paths.append(page_path)

        import zipfile

        zip_path = TMP_DIR / f"{uuid.uuid4().hex}_paginas.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in page_paths:
                zf.write(p, arcname=p.name)
    finally:
        path.unlink(missing_ok=True)

    return FileResponse(zip_path, filename="paginas.zip", media_type="application/zip")


@router.post("/images-to-pdf")
async def images_to_pdf(files: list[UploadFile] = File(...)):
    saved_paths = []
    try:
        for upload in files:
            saved_paths.append(_save_upload(upload))

        out_path = TMP_DIR / f"{uuid.uuid4().hex}_imagenes.pdf"
        with out_path.open("wb") as f:
            f.write(img2pdf.convert([str(p) for p in saved_paths]))
    finally:
        for p in saved_paths:
            p.unlink(missing_ok=True)

    return FileResponse(out_path, filename="imagenes.pdf", media_type="application/pdf")
