import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

from ..paths import DATA_DIR, DOWNLOADS_DIR

# Instagram (y algunos posts privados de Facebook) no muestran fotos sin
# sesión iniciada. Si existe este archivo (formato Netscape, exportado del
# navegador con una extensión tipo "Get cookies.txt LOCALLY"), se usa en
# yt-dlp y gallery-dl. Se carga desde la página (POST /cookies).
COOKIES_FILE = DATA_DIR / "cookies.txt"

# De lo que suban, solo guardamos las cookies de estos sitios: muchas
# extensiones exportan TODAS las sesiones del navegador por defecto, y no
# tiene sentido guardar la del banco o el mail.
COOKIE_SITES = (
    "instagram.com", "facebook.com", "tiktok.com", "youtube.com",
    "x.com", "twitter.com", "threads.net", "threads.com", "pinterest.com", "reddit.com",
)

router = APIRouter(prefix="/api/download", tags=["download"])

_jobs: dict[str, dict] = {}
JOB_MAX_AGE_SECONDS = 24 * 3600

# quality -> altura máxima de video (None = mejor disponible, sin tope)
QUALITY_HEIGHTS = {
    "best": None,
    "1080": 1080,
    "720": 720,
    "480": 480,
    "360": 360,
}

# el cliente "android" evita muchos de los 403 que tira YouTube cuando pide
# un PO token que no tenemos; "web" queda como respaldo para lo que android
# no exponga (algunos formatos de audio/subs)
_YOUTUBE_CLIENT_ARGS = {"youtube": {"player_client": ["android", "web"]}}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _clean_error(exc: Exception) -> str:
    return _ANSI_RE.sub("", str(exc)).strip()


# --- nombres de archivo legibles ---
# en disco los archivos se llaman por el id del trabajo (evita choques entre
# descargas simultáneas); al navegador se le entrega un nombre legible.

_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _safe_filename(name: str, max_len: int = 120) -> str:
    name = _BAD_FILENAME_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len].rstrip(" .") or "descarga"


def _name_from_url(url: str) -> str:
    """instagram.com/p/Detv_U3liVs/?img_index=1 -> instagram_Detv_U3liVs"""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    site = host.split(".")[0] if host else "imagenes"
    parts = [p for p in parsed.path.split("/") if p and p not in ("p", "reel", "photo", "photos", "posts")]
    tail = parts[-1] if parts else ""
    return _safe_filename(f"{site}_{tail}" if tail else site)


def has_active_jobs() -> bool:
    return any(job.get("status") not in ("done", "error", "cancelled") for job in _jobs.values())


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_MAX_AGE_SECONDS
    for job_id in [j for j, job in _jobs.items() if job.get("created", 0) < cutoff]:
        _jobs.pop(job_id, None)


# --- imágenes (gallery-dl) ---
# yt-dlp solo baja video: un post de fotos de Instagram/Facebook, un carrusel
# o un link directo a una imagen le dan "no video formats". Para eso usamos
# gallery-dl como respaldo, corriéndolo como subproceso para poder cancelarlo.

# tope por link: un post/carrusel entra de sobra; si pegan un perfil entero
# no se baja miles de fotos (ni se cuelga la vista previa)
MAX_IMAGES = 100


def _gallery_dl_cmd(*args: str) -> list[str]:
    cmd = [sys.executable, "-m", "gallery_dl", "--range", f"1-{MAX_IMAGES}"]
    if COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    return [*cmd, *args]


LOGIN_REQUIRED_MSG = (
    "Este post pide iniciar sesión para verlo. Cargá tus cookies en "
    "\"Sesión de redes\" (abajo de todo en esta sección) y probá de nuevo."
)


def _needs_login(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in ("accounts/login", "login required", "log in", "redirect to login"))


INSTAGRAM_FAILED_MSG = (
    "Instagram no dejó ver este post. Esperá unos minutos y probá de nuevo "
    "(a veces rechaza pedidos seguidos). Si es de una cuenta privada, cargá tu "
    "sesión en \"Sesión de redes\", abajo de todo en esta sección."
)


def _combined_error(
    video_exc: Exception, gallery_exc: Exception, prefix: str = "", url: str = ""
) -> str:
    gallery_msg = _clean_error(gallery_exc)
    if gallery_msg == LOGIN_REQUIRED_MSG and _is_instagram(url):
        return INSTAGRAM_FAILED_MSG
    if gallery_msg == LOGIN_REQUIRED_MSG:
        # el error de yt-dlp ("no video formats") solo confunde en este caso
        return gallery_msg
    return f"{prefix}{_clean_error(video_exc)} (imágenes: {gallery_msg})"


def _gallery_error(stderr: str) -> str:
    if _needs_login(stderr):
        return LOGIN_REQUIRED_MSG
    lines = [l.strip() for l in _ANSI_RE.sub("", stderr).splitlines() if l.strip()]
    errors = [l for l in lines if "error" in l.lower()]
    return (errors or lines or ["gallery-dl no encontró imágenes"])[-1]


def _gallery_urls(url: str, time_limit: float = 20) -> tuple[list[str], bool]:
    """Lista las URLs de imágenes para la vista previa. Algunos sitios
    (Facebook) resuelven foto por foto, así que cortamos a los `time_limit`
    segundos y devolvemos lo encontrado; el bool indica si quedaron más."""
    proc = subprocess.Popen(
        _gallery_dl_cmd("-g", url),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    urls: list[str] = []
    stderr_chunks: list[str] = []

    def read_stdout():
        for line in proc.stdout:
            # las líneas "| url" son alternativas de respaldo, no imágenes distintas
            if line.strip().startswith("http"):
                urls.append(line.strip())

    out_reader = threading.Thread(target=read_stdout, daemon=True)
    err_reader = threading.Thread(
        target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True
    )
    out_reader.start()
    err_reader.start()

    truncated = False
    try:
        proc.wait(timeout=time_limit)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        truncated = True
    out_reader.join(timeout=5)
    err_reader.join(timeout=5)

    if not urls:
        if truncated:
            raise RuntimeError("gallery-dl tardó demasiado en responder")
        raise RuntimeError(_gallery_error("".join(stderr_chunks)))
    return urls, truncated


def _run_gallery_download(job_id: str, url: str) -> Path:
    """Baja todas las imágenes de la URL; devuelve el archivo a servir
    (la imagen sola, o un zip si son varias)."""
    job = _jobs[job_id]
    out_dir = DOWNLOADS_DIR / job_id
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    job.update({"status": "downloading_images", "percent": None, "count": 0})
    proc = subprocess.Popen(
        _gallery_dl_cmd("-D", str(out_dir), url),
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    stderr_chunks: list[str] = []
    reader = threading.Thread(
        target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True
    )
    reader.start()

    while proc.poll() is None:
        if job.get("cancel_requested"):
            proc.kill()
            proc.wait()
            shutil.rmtree(out_dir, ignore_errors=True)
            raise Exception("Descarga cancelada por el usuario")
        job["count"] = sum(1 for f in out_dir.iterdir() if not f.name.endswith(".part"))
        time.sleep(0.5)
    reader.join(timeout=5)

    files = sorted(f for f in out_dir.iterdir() if f.is_file() and not f.name.endswith(".part"))
    if not files:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise RuntimeError(_gallery_error("".join(stderr_chunks)))

    return _package_files(job_id, url, out_dir, files)


def _package_files(job_id: str, url: str, out_dir: Path, files: list[Path]) -> Path:
    """Un archivo se entrega tal cual; varios, en un zip con nombre legible."""
    job = _jobs[job_id]
    job["count"] = len(files)
    if len(files) == 1:
        job["download_name"] = files[0].name
        return files[0]

    job["download_name"] = f"{_name_from_url(url)}.zip"
    zip_path = DOWNLOADS_DIR / f"{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for f in files:
            zf.write(f, f.name)
    shutil.rmtree(out_dir, ignore_errors=True)
    return zip_path


# --- Instagram sin iniciar sesión ---
# gallery-dl necesita cuenta para Instagram, pero yt-dlp lee los posts sin
# sesión y trae cada ítem del carrusel: los videos con sus formatos y las
# fotos como "thumbnails" en varios tamaños. Si pedimos el post sin procesar
# (process=False) en vez de fallar por "no video formats", tenemos todo.

def _is_instagram(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "instagram.com" or host.endswith(".instagram.com")


def _best_image_url(entry: dict) -> str | None:
    """De las variantes de una foto, la original: sin tamaño fijo (s640x640,
    p1080x1080) ni recorte (c0.360...) en el parámetro stp de la URL."""
    urls = [t["url"] for t in entry.get("thumbnails") or [] if t.get("url")]
    if not urls:
        return entry.get("thumbnail")

    def score(u: str) -> int:
        m = re.search(r"[?&]stp=([^&]+)", u)
        stp = m.group(1) if m else ""
        size = re.search(r"(?:^|_)[sp](\d+)x\d+", stp)
        cropped = re.match(r"c[\d.]+", stp)
        if not size and not cropped:
            return 10**6
        return (int(size.group(1)) if size else 0) - (5000 if cropped else 0)

    return max(urls, key=score)


def _instagram_items(url: str, attempts: int = 3) -> list[dict]:
    opts = {"quiet": True, "no_warnings": True, "no_color": True}
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    # sin sesión, Instagram a veces rechaza un pedido y acepta el siguiente
    for attempt in range(attempts):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
            break
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(3 * (attempt + 1))
    entries = list(info.get("entries") or [info])
    items = []
    for entry in entries:
        if entry.get("formats"):
            items.append({"kind": "video", "entry": entry})
        else:
            image = _best_image_url(entry)
            if image:
                items.append({"kind": "image", "url": image, "id": entry.get("id") or ""})
    if not items:
        raise RuntimeError("Instagram no devolvió fotos ni videos para este link")
    return items


def _run_instagram_download(job_id: str, url: str) -> Path:
    job = _jobs[job_id]
    out_dir = DOWNLOADS_DIR / job_id
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    job.update({"status": "downloading_images", "percent": None, "count": 0})

    items = _instagram_items(url)
    has_ffmpeg = shutil.which("ffmpeg") is not None
    files: list[Path] = []
    for n, item in enumerate(items, start=1):
        if job.get("cancel_requested"):
            shutil.rmtree(out_dir, ignore_errors=True)
            raise Exception("Descarga cancelada por el usuario")
        prefix = f"{n:02d}"
        if item["kind"] == "image":
            dest = out_dir / f"{prefix}_{item['id']}.jpg"
            req = urllib.request.Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            files.append(dest)
        else:
            opts = {
                "quiet": True, "no_warnings": True, "no_color": True,
                "outtmpl": str(out_dir / f"{prefix}_%(id)s.%(ext)s"),
                "format": "bv*+ba/b" if has_ffmpeg else "b",
                "merge_output_format": "mp4",
            }
            if COOKIES_FILE.exists():
                opts["cookiefile"] = str(COOKIES_FILE)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.process_ie_result(item["entry"], download=True)
            files.extend(sorted(out_dir.glob(f"{prefix}_*")))
        job["count"] = len(files)

    if not files:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise RuntimeError("No se pudo bajar nada de este post")
    return _package_files(job_id, url, out_dir, sorted(files))


class UrlIn(BaseModel):
    url: str


class StartIn(BaseModel):
    url: str
    quality: str = "best"  # "best" | "1080" | "720" | "480" | "360" | "audio"


@router.post("/info")
def get_info(payload: UrlIn):
    opts = {
        "quiet": True,
        "no_color": True,
        "skip_download": True,
        "noplaylist": True,
    }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(payload.url, download=False)
    except Exception as exc:
        # sin video: puede ser un post de fotos o una imagen suelta
        if _is_instagram(payload.url):
            try:
                items = _instagram_items(payload.url)
            except Exception:
                items = None  # probamos con gallery-dl
            if items:
                photos = sum(1 for i in items if i["kind"] == "image")
                videos = len(items) - photos
                parts = []
                if photos:
                    parts.append("1 foto" if photos == 1 else f"{photos} fotos")
                if videos:
                    parts.append("1 video" if videos == 1 else f"{videos} videos")
                title = " y ".join(parts) + (" en un .zip" if len(items) > 1 else "")
                first_image = next((i["url"] for i in items if i["kind"] == "image"), None)
                return {
                    "title": title,
                    "duration": None,
                    "thumbnail": first_image,
                    "extractor": "Instagram",
                    "kind": "images",
                }
        try:
            urls, truncated = _gallery_urls(payload.url)
        except Exception as gallery_exc:
            raise HTTPException(
                status_code=400,
                detail=_combined_error(exc, gallery_exc, "No se pudo leer la URL: ", payload.url),
            ) from exc
        n = len(urls)
        if truncated or n >= MAX_IMAGES:
            title = f"{n}+ imágenes en un .zip (máximo {MAX_IMAGES} por link)"
        else:
            title = "1 imagen" if n == 1 else f"{n} imágenes en un .zip"
        return {
            "title": title,
            "duration": None,
            "thumbnail": urls[0],
            "extractor": "Imágenes",
            "kind": "images",
        }

    return {
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key"),
        "kind": "video",
    }


def _make_progress_hook(job_id: str):
    def hook(d: dict):
        job = _jobs.get(job_id)
        if job is None:
            return
        if job.get("cancel_requested"):
            raise Exception("Descarga cancelada por el usuario")
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            percent = round(downloaded / total * 100, 1) if total else None
            job.update(
                {
                    "status": "downloading",
                    "percent": percent,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                }
            )
        elif status == "finished":
            # esta pista terminó; si hay que unir video+audio o convertir a mp3
            # todavía falta el post-procesado (ffmpeg), así que no es 100% real
            job.update({"status": "processing", "percent": 99})
        elif status == "error":
            job.update({"status": "error", "error": "Falló la descarga"})

    return hook


def _build_opts(job_id: str, payload: "StartIn", *, simple_format: bool) -> dict:
    has_ffmpeg = shutil.which("ffmpeg") is not None
    out_template = str(DOWNLOADS_DIR / f"{job_id}.%(ext)s")

    opts = {
        "quiet": True,
        "no_color": True,
        "noplaylist": True,
        "outtmpl": out_template,
        "progress_hooks": [_make_progress_hook(job_id)],
        "retries": 5,
        "fragment_retries": 5,
    }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)

    if simple_format:
        # último recurso: forzar el cliente "android" evita muchos de los 403
        # que tira YouTube, a costa de perder acceso a los formatos de mayor
        # calidad (que solo exponen otros clientes)
        opts["extractor_args"] = _YOUTUBE_CLIENT_ARGS

    if payload.quality == "audio":
        opts["format"] = "ba/b"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
        opts["keepvideo"] = False
    else:
        height = QUALITY_HEIGHTS[payload.quality]
        height_filter = f"[height<={height}]" if height else ""
        if simple_format or not has_ffmpeg:
            # formato progresivo único: más lento de conseguir en alta calidad
            # pero mucho menos propenso a los 403 que tira YouTube en algunos
            # formatos separados de video/audio
            opts["format"] = f"b{height_filter}"
        else:
            opts["format"] = f"bv*{height_filter}+ba/b{height_filter}"
            opts["merge_output_format"] = "mp4"

    return opts


def _run_download(job_id: str, payload: "StartIn"):
    job = _jobs[job_id]
    job["status"] = "downloading"

    info = None
    filename = None
    last_error = None

    for attempt, simple_format in enumerate((False, True)):
        if job.get("cancel_requested"):
            break
        if attempt > 0:
            # el intento anterior dejó pistas parciales; limpiar antes de reintentar
            # con un formato progresivo único (menos propenso a los 403 de YouTube)
            for leftover in DOWNLOADS_DIR.glob(f"{job_id}.*"):
                leftover.unlink(missing_ok=True)
            job.update({"status": "downloading", "percent": 0})

        opts = _build_opts(job_id, payload, simple_format=simple_format)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(payload.url, download=True)
                filename = ydl.prepare_filename(info)
            last_error = None
            break
        except Exception as exc:
            last_error = exc

    if job.get("cancel_requested"):
        job.update({"status": "cancelled", "error": "Descarga cancelada"})
        for leftover in DOWNLOADS_DIR.glob(f"{job_id}.*"):
            leftover.unlink(missing_ok=True)
        return

    if last_error is not None:
        for leftover in DOWNLOADS_DIR.glob(f"{job_id}.*"):
            leftover.unlink(missing_ok=True)
        if payload.quality != "audio":
            # yt-dlp no encontró video: probar como imágenes
            try:
                final_path = None
                if _is_instagram(payload.url):
                    try:
                        final_path = _run_instagram_download(job_id, payload.url)
                    except Exception:
                        if job.get("cancel_requested"):
                            raise
                if final_path is None:
                    final_path = _run_gallery_download(job_id, payload.url)
            except Exception as gallery_exc:
                if job.get("cancel_requested"):
                    job.update({"status": "cancelled", "error": "Descarga cancelada"})
                    return
                job.update(
                    {
                        "status": "error",
                        "error": _combined_error(last_error, gallery_exc, url=payload.url),
                    }
                )
                return
            download_name = job.get("download_name", final_path.name)
            job.update(
                {
                    "status": "done",
                    "percent": 100,
                    "path": final_path,
                    "title": Path(download_name).stem,
                    "filename": download_name,
                }
            )
            return
        job.update({"status": "error", "error": _clean_error(last_error)})
        return

    final_path = Path(filename)
    if not final_path.exists():
        candidates = list(DOWNLOADS_DIR.glob(f"{job_id}.*"))
        if not candidates:
            job.update({"status": "error", "error": "No se encontró el archivo descargado"})
            return
        final_path = candidates[0]

    title = info.get("title") or _name_from_url(payload.url)
    download_name = f"{_safe_filename(title)}{final_path.suffix}"
    job.update(
        {
            "status": "done",
            "percent": 100,
            "path": final_path,
            "title": title,
            "filename": download_name,
            "download_name": download_name,
        }
    )


@router.post("/start")
def start_download(payload: StartIn):
    if payload.quality not in QUALITY_HEIGHTS and payload.quality != "audio":
        raise HTTPException(status_code=400, detail=f"Calidad inválida: {payload.quality}")
    if payload.quality == "audio" and shutil.which("ffmpeg") is None:
        raise HTTPException(
            status_code=400,
            detail="Descargar como MP3 necesita ffmpeg instalado en el servidor",
        )

    _prune_jobs()
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "queued", "percent": 0, "created": time.time()}

    thread = threading.Thread(target=_run_download, args=(job_id, payload), daemon=True)
    thread.start()

    return {"id": job_id}


@router.post("/cancel/{job_id}")
def cancel_download(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.get("status") in ("done", "error", "cancelled"):
        return {"status": job["status"]}
    job["cancel_requested"] = True
    job["status"] = "cancelling"
    return {"status": "cancelling"}


@router.get("/progress/{job_id}")
def get_progress(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {k: v for k, v in job.items() if k != "path"}


@router.get("/file/{job_id}")
def get_file(job_id: str):
    job = _jobs.get(job_id)
    if not job or not job.get("path") or not job["path"].exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(job["path"], filename=job.get("download_name", job["path"].name))


# --- cookies (sesión de redes) ---

def _cookie_domain(line: str) -> str:
    return line.removeprefix("#HttpOnly_").split("\t", 1)[0].lstrip(".").lower()


def _is_cookie_site(domain: str) -> bool:
    return any(domain == site or domain.endswith("." + site) for site in COOKIE_SITES)


def _cookie_sites_in_file() -> list[str]:
    if not COOKIES_FILE.exists():
        return []
    sites = set()
    for line in COOKIES_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.count("\t") >= 6:
            domain = _cookie_domain(line)
            sites.update(s for s in COOKIE_SITES if domain == s or domain.endswith("." + s))
    return sorted(sites)


@router.get("/cookies")
def cookies_status():
    return {"loaded": COOKIES_FILE.exists(), "sites": _cookie_sites_in_file()}


@router.post("/cookies")
async def upload_cookies(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    cookie_lines = [l for l in raw.splitlines() if l.count("\t") >= 6]
    if not cookie_lines:
        raise HTTPException(
            status_code=400,
            detail="Ese archivo no parece un cookies.txt (formato Netscape). "
            "Exportalo con la extensión \"Get cookies.txt LOCALLY\".",
        )
    kept = [l for l in cookie_lines if _is_cookie_site(_cookie_domain(l))]
    if not kept:
        raise HTTPException(
            status_code=400,
            detail="El archivo no tiene cookies de Instagram, Facebook, TikTok, "
            "YouTube ni otras redes. ¿Exportaste estando en el sitio con la sesión iniciada?",
        )
    # sumamos a lo que ya había: así se pueden cargar las redes de a una
    existing = []
    if COOKIES_FILE.exists():
        new_domains = {_cookie_domain(l) for l in kept}
        existing = [
            l for l in COOKIES_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            if l.count("\t") >= 6 and _cookie_domain(l) not in new_domains
        ]
    COOKIES_FILE.write_text(
        "# Netscape HTTP Cookie File\n\n" + "\n".join(existing + kept) + "\n", encoding="utf-8"
    )
    return {
        "loaded": True,
        "sites": _cookie_sites_in_file(),
        "kept": len(kept),
        "discarded": len(cookie_lines) - len(kept),
        "warnings": _logged_out_sites(kept),
    }


# cookie que solo existe con la sesión iniciada; sin ella, exportar no sirve
_SESSION_COOKIES = {"instagram.com": "sessionid", "facebook.com": "c_user", "tiktok.com": "sessionid"}


def _logged_out_sites(lines: list[str]) -> list[str]:
    names_by_site: dict[str, set[str]] = {}
    for line in lines:
        domain = _cookie_domain(line)
        for site in _SESSION_COOKIES:
            if domain == site or domain.endswith("." + site):
                names_by_site.setdefault(site, set()).add(line.split("\t")[5])
    return sorted(
        site for site, names in names_by_site.items() if _SESSION_COOKIES[site] not in names
    )


@router.delete("/cookies")
def delete_cookies():
    COOKIES_FILE.unlink(missing_ok=True)
    return {"loaded": False, "sites": []}
