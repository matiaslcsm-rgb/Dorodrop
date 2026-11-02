import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
TMP_DIR = DATA_DIR / "tmp"

DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

# la versión portable (build_portable.ps1) trae ffmpeg/ffprobe/deno en tools/;
# van primero en el PATH para no depender de lo que tenga instalado cada PC
TOOLS_DIR = BASE_DIR / "tools"
if TOOLS_DIR.is_dir():
    os.environ["PATH"] = str(TOOLS_DIR) + os.pathsep + os.environ.get("PATH", "")


def _ensure_ffmpeg_on_path() -> None:
    """winget installs ffmpeg and updates the persistent PATH, but processes
    started before that update (e.g. a desktop shortcut launched before the
    next login) won't see it. Fall back to looking in winget's known
    install location so ffmpeg-dependent features don't silently degrade."""
    if shutil.which("ffmpeg"):
        return

    winget_packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not winget_packages.is_dir():
        return

    for candidate in winget_packages.glob("Gyan.FFmpeg_*/ffmpeg-*-full_build/bin/ffmpeg.exe"):
        os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
        return


def _ensure_deno_on_path() -> None:
    """yt-dlp needs a JS runtime (deno) on PATH to extract every YouTube
    quality; same stale-PATH issue as ffmpeg above, same fix."""
    if shutil.which("deno"):
        return

    winget_packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not winget_packages.is_dir():
        return

    for candidate in winget_packages.glob("DenoLand.Deno_*/deno.exe"):
        os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
        return


_ensure_ffmpeg_on_path()
_ensure_deno_on_path()
