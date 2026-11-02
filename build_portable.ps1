# Arma dist\DoroDrop (carpeta portable, con Python y ffmpeg adentro) y
# dist\DoroDrop.zip para compartir. Uso, desde esta carpeta:
#   powershell -ExecutionPolicy Bypass -File build_portable.ps1
#
# No copia nada de data\ (cookies, notas, presets, descargas): eso es de esta PC.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dist = Join-Path $root "dist"
$out = Join-Path $dist "DoroDrop"
$venvPy = Join-Path $root "backend\venv\Scripts\python.exe"

# Python embebible: tiene que ser la misma versión menor que el venv, porque
# los paquetes compilados (numpy, rawpy) se instalan para esa versión
$pyVersion = (& $venvPy -c "import platform; print(platform.python_version())").Trim()
$pyTag = (& $venvPy -c "import sys; print(f'python{sys.version_info.major}{sys.version_info.minor}')").Trim()
Write-Host "Python $pyVersion"

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force $out | Out-Null

# 1. Python embebible (de python.org, se cachea en dist\)
$embedZip = Join-Path $dist "python-$pyVersion-embed-amd64.zip"
if (-not (Test-Path $embedZip)) {
    Write-Host "Bajando Python embebible..."
    Invoke-WebRequest "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-embed-amd64.zip" -OutFile $embedZip
}
Expand-Archive $embedZip (Join-Path $out "python")

# el ._pth reemplaza a sys.path: sumamos site-packages y el backend
Set-Content (Join-Path $out "python\$pyTag._pth") -Encoding ascii -Value @(
    "$pyTag.zip", ".", "Lib\site-packages", "..\backend", "import site"
)

# 2. Paquetes (más pip, para que funcione "Actualizar descargadores")
Write-Host "Instalando paquetes..."
$site = Join-Path $out "python\Lib\site-packages"
& $venvPy -m pip install --disable-pip-version-check --quiet --target $site `
    -r (Join-Path $root "backend\requirements.txt") pip
if ($LASTEXITCODE -ne 0) { throw "pip falló" }
Remove-Item (Join-Path $site "bin") -Recurse -Force -ErrorAction SilentlyContinue

# 3. Código de la app
Write-Host "Copiando la app..."
New-Item -ItemType Directory -Force (Join-Path $out "backend") | Out-Null
Copy-Item (Join-Path $root "backend\app") (Join-Path $out "backend\app") -Recurse
Copy-Item (Join-Path $root "backend\requirements.txt") (Join-Path $out "backend")
Copy-Item (Join-Path $root "frontend") (Join-Path $out "frontend") -Recurse
Get-ChildItem $out -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force (Join-Path $out "data\downloads"), (Join-Path $out "data\tmp") | Out-Null

# 4. ffmpeg, ffprobe y deno (de las instalaciones de winget de esta PC)
Write-Host "Copiando ffmpeg y deno..."
$tools = Join-Path $out "tools"
New-Item -ItemType Directory -Force $tools | Out-Null
$winget = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
foreach ($exe in "ffmpeg.exe", "ffprobe.exe", "deno.exe") {
    $found = Get-ChildItem $winget -Recurse -Filter $exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) {
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if ($cmd) { $found = Get-Item $cmd.Source }
    }
    if (-not $found) { throw "No encontré $exe (instalalo con winget: Gyan.FFmpeg / DenoLand.Deno)" }
    Copy-Item $found.FullName $tools
}

# 5. Lanzador e instrucciones (el .bat con CRLF: cmd se confunde con LF)
$bat = (Get-Content (Join-Path $root "portable\Abrir Doro Drop.bat") -Raw) -replace "`r?`n", "`r`n"
[IO.File]::WriteAllText((Join-Path $out "Abrir Doro Drop.bat"), $bat, [Text.Encoding]::ASCII)
$leeme = (Get-Content (Join-Path $root "portable\LEEME.txt") -Raw -Encoding utf8) -replace "`r?`n", "`r`n"
[IO.File]::WriteAllText((Join-Path $out "LEEME.txt"), $leeme, (New-Object Text.UTF8Encoding $true))
Copy-Item (Join-Path $root "LICENSE") (Join-Path $out "LICENSE.txt")

# 6. Zip
Write-Host "Comprimiendo..."
$zip = Join-Path $dist "DoroDrop.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
tar.exe -a -c -f $zip -C $dist DoroDrop
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el zip" }

$sizeDir = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
$sizeZip = (Get-Item $zip).Length / 1MB
Write-Host ("Listo: {0} ({1:N0} MB, carpeta {2:N0} MB)" -f $zip, $sizeZip, $sizeDir)
