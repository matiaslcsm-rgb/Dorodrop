"""Cosas de escritorio de Windows: elegir carpeta, abrir el Explorador,
crear el acceso directo. Todo corre en la PC donde está el servidor, así que
solo se ofrece cuando la página se abre desde esa misma PC."""
import os
import subprocess
import sys
from pathlib import Path

from .paths import BASE_DIR

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ICON = BASE_DIR / "frontend" / "assets" / "icon.ico"
LAUNCHER = BASE_DIR / "backend" / "launcher.py"


def _powershell(script: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=NO_WINDOW,
    )


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def pick_folder(start: Path) -> str | None:
    """Abre el diálogo de Windows para elegir carpeta. None si se cancela."""
    script = f"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{{TopMost = $true}}
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Elegí dónde guarda Doro Drop lo que descargás y convertís'
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = {_ps_quote(str(start))}
if ($dialog.ShowDialog($owner) -eq 'OK') {{ $dialog.SelectedPath }}
"""
    result = _powershell(script, timeout=600)
    chosen = result.stdout.strip()
    return chosen or None


def reveal(path: Path) -> None:
    """Abre el Explorador: con el archivo seleccionado, o la carpeta."""
    if path.is_file():
        subprocess.Popen(["explorer", f"/select,{path}"], creationflags=NO_WINDOW)
    else:
        subprocess.Popen(["explorer", str(path)], creationflags=NO_WINDOW)


def pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def create_desktop_shortcut() -> Path:
    """Acceso directo 'Doro Drop' en el escritorio que abre la ventana de la app."""
    script = f"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'Doro Drop.lnk'
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($path)
$lnk.TargetPath = {_ps_quote(str(pythonw()))}
$lnk.Arguments = '"' + {_ps_quote(str(LAUNCHER))} + '"'
$lnk.WorkingDirectory = {_ps_quote(str(BASE_DIR))}
$lnk.IconLocation = {_ps_quote(str(ICON))}
$lnk.Description = 'Doro Drop: descargá y convertí archivos'
$lnk.Save()
$path
"""
    result = _powershell(script, timeout=60)
    created = result.stdout.strip()
    if result.returncode != 0 or not created:
        raise RuntimeError(result.stderr.strip() or "No se pudo crear el acceso directo")
    return Path(created)


def find_edge() -> Path | None:
    candidates = []
    try:
        import winreg

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
                candidates.append(Path(winreg.QueryValueEx(key, "")[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return next((c for c in candidates if c.exists()), None)
