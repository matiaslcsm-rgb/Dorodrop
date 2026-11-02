# Multiherramienta Local

App local tipo "iLovePDF + descargador de video", pensada para correr en un
equipo o servidor de la oficina y que el resto del equipo la use desde el
navegador dentro de la misma red.

## Funciones

- **Descargar**: videos (vía `yt-dlp`) y fotos/carruseles (vía `gallery-dl`) de
  YouTube, Instagram, Facebook, TikTok y más. Vista previa, calidad o MP3,
  progreso real, cancelar, cola de varios links, historial, carga de cookies
  para Instagram ("Sesión de redes") y botón para actualizar los descargadores.
- **PDF**: unir varios PDFs, dividir un PDF en páginas, convertir imágenes a PDF.
- **Imágenes**: convertir entre PNG/JPG/WEBP/BMP/GIF/TIFF, redimensionar, y
  convertir RAW de cámara (CR2, CR3, NEF, ARW, DNG, RW2, ORF, RAF, PEF, SRW) a JPG.
- **Editor**: mini editor de exposición/contraste/saturación/temperatura/tinte
  con vista previa en vivo, para JPG/PNG y RAW.
- **Audio/Video**: convertir formatos (MP4, WEBM, MP3, WAV, etc.) vía `ffmpeg`.
- **Notas**: tablón simple de comentarios/feedback para el equipo.

## Requisitos

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) instalado y en el `PATH`
  (en Windows: `winget install Gyan.FFmpeg`, después reabrir la terminal)
- Para RAW/editor: `rawpy` y `numpy` (se instalan solos con `requirements.txt`,
  requieren una wheel prearmada para tu versión de Python — si falla la
  instalación, probar con una versión de Python un poco más vieja)

## Instalación

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows (PowerShell: venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

## Ejecutar

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Abrí `http://localhost:8010` en el navegador. Para que otros equipos de la
misma red lo usen, entran a `http://<IP-de-esta-máquina>:8010`.

(Se usa el puerto 8010 en vez del 8000 porque esa máquina ya tiene otra
app corriendo en el 8000.)

## Estructura

```
multiherramienta/
  backend/
    app/
      main.py          # arma la app y sirve el frontend
      paths.py          # carpetas de datos temporales/descargas
      cleanup.py        # borra data/downloads y data/tmp de más de 24 h
      updater.py        # auto-actualización segura de yt-dlp/gallery-dl
      routers/
        downloader.py   # descarga de video e imágenes, cookies
        system.py        # versiones y actualización de yt-dlp/gallery-dl
        pdf_tools.py     # unir/dividir/convertir PDF
        images.py        # conversión de imágenes, RAW a JPG, editor
        media.py          # conversión de audio/video
        notes.py           # tablón de notas
    requirements.txt
  frontend/
    index.html
    style.css
    app.js
  data/
    downloads/   # videos descargados
    tmp/         # archivos temporales de conversión
```

## Notas

- `data/downloads` y `data/tmp` se limpian solos: al arrancar y cada hora se
  borra lo que tenga más de 24 h.
- Instagram: los posts públicos se bajan sin sesión (yt-dlp con
  `process=False` trae las fotos del carrusel como thumbnails; se elige la
  original). gallery-dl queda como respaldo para otros sitios.
- Auto-actualización (`updater.py`): una vez por día, solo desde PyPI, solo
  wheels (`--only-binary`), solo versiones con 3+ días de publicadas; prueba
  cada paquete y vuelve a la versión anterior si no arranca. No corre con
  descargas en curso. Se apaga desde la página (`data/settings.json`).
- `data/cookies.txt` (sesión de redes) se carga desde la página y solo guarda
  cookies de redes sociales. Nunca se incluye en la versión portable.
- Descargar contenido de redes sociales puede chocar con los términos de
  uso de cada plataforma; usarlo para fines internos/personales, no para
  redistribuir contenido ajeno públicamente.

## Versión portable (para compartir)

```powershell
powershell -ExecutionPolicy Bypass -File build_portable.ps1
```

Genera `dist\DoroDrop.zip` (~255 MB): Python embebible, todos los paquetes,
ffmpeg/ffprobe/deno (copiados de las instalaciones de winget de esta PC), la
app y `Abrir Doro Drop.bat`. Quien lo recibe lo descomprime y hace doble clic;
no necesita instalar nada. La portable escucha solo en `127.0.0.1` (no queda
expuesta a la red). Los textos del lanzador y del LEEME están en `portable/`.
