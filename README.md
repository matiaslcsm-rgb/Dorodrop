# Doro Drop

Una herramienta para el equipo: descargá videos y fotos de las redes y
convertí o editá archivos, todo desde el navegador y **sin subir nada a
internet**. Corre en tu propia PC.

## Qué hace

- **Descargar**: videos y fotos de YouTube, Instagram, Facebook, TikTok y
  muchos sitios más.
  - Elegís calidad (hasta la mejor disponible) o solo audio en MP3.
  - Carruseles de Instagram completos, con las fotos en tamaño original, sin
    iniciar sesión.
  - Varios links a la vez (uno por línea) que se bajan en cola.
  - Historial para volver a buscar algo que ya bajaste.
- **PDF**: unir varios, separar páginas, pasar imágenes a PDF.
- **Imágenes**: convertir entre PNG, JPG, WEBP, BMP, GIF y TIFF, cambiar el
  tamaño, y pasar fotos RAW de cámara (CR2, CR3, NEF, ARW, DNG, etc.) a JPG.
- **Editor**: exposición, contraste, saturación y balance de blancos, con
  vista previa en vivo, perfiles guardados y edición de varias fotos juntas.
- **Audio / video**: convertir entre MP4, WEBM, MKV, MP3, WAV, FLAC y más.
- **Notas**: un tablón para dejar comentarios al equipo.

## Descargar y usar (Windows)

No hace falta instalar nada.

1. Entrá a [**Releases**](../../releases/latest) y bajá `DoroDrop.zip`.
2. Descomprimilo donde quieras (por ejemplo en Documentos).
3. Doble clic en **`Abrir Doro Drop.bat`**. Se abre el navegador con la app.
4. Para apagarla, cerrá la ventana minimizada "Doro Drop - servidor".

Si Windows muestra "Windows protegió su PC", tocá **Más información** →
**Ejecutar de todas formas**.

### Se mantiene al día sola

Las redes cambian seguido y los descargadores (`yt-dlp` y `gallery-dl`)
necesitan actualizarse. Doro Drop lo hace solo, una vez por día, y de forma
segura:

- solo baja versiones oficiales de [PyPI](https://pypi.org), y solo paquetes
  ya armados (no ejecuta código de instalación);
- espera **3 días** desde que sale una versión antes de instalarla, por si
  sale rota o comprometida;
- prueba cada versión nueva y, si no arranca, vuelve a la anterior;
- nunca actualiza en medio de una descarga.

Se puede apagar, o forzar una actualización si algo dejó de bajar, en
**Descargar → Actualizaciones**.

### Cuentas privadas

Los posts públicos se bajan sin iniciar sesión. Para contenido de una cuenta
privada, en **Descargar → Sesión de redes** se cargan las cookies del
navegador (con la extensión "Get cookies.txt LOCALLY"). Doro Drop guarda solo
las de redes sociales y descarta el resto; quedan únicamente en tu PC.

## Correrlo desde el código

Requisitos: Python 3.11 o más nuevo y [ffmpeg](https://ffmpeg.org/download.html)
en el `PATH` (en Windows: `winget install Gyan.FFmpeg`). Para todas las
calidades de YouTube conviene también [deno](https://deno.com)
(`winget install DenoLand.Deno`).

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Abrí http://localhost:8010. Para que otras PCs de la red lo usen, arrancalo
con `--host 0.0.0.0` y entran a `http://<IP-de-tu-PC>:8010` (es lo que hace
`start_doro_drop.bat`).

### Armar el .zip portable

```powershell
powershell -ExecutionPolicy Bypass -File build_portable.ps1
```

Genera `dist\DoroDrop.zip` (~255 MB) con Python embebible, todos los
paquetes, ffmpeg, ffprobe y deno (copiados de las instalaciones de winget de
la PC que lo arma) y el lanzador. Los textos del lanzador y del LEEME están en
`portable/`. La versión portable escucha solo en `127.0.0.1`.

## Cómo está hecho

Backend en Python con FastAPI, frontend en HTML, CSS y JavaScript sin
frameworks. Los archivos se procesan en la PC y los temporales se borran
solos después de 24 horas.

```
backend/app/
  main.py           arma la app y sirve el frontend
  paths.py          carpetas de datos; suma tools/ al PATH en la portable
  cleanup.py        borra data/downloads y data/tmp de más de 24 h
  updater.py        auto-actualización segura de yt-dlp y gallery-dl
  routers/
    downloader.py   videos (yt-dlp), fotos (yt-dlp para Instagram,
                    gallery-dl para el resto), cookies
    system.py       versiones y actualización manual
    pdf_tools.py    unir, dividir, imágenes a PDF
    images.py       conversión, RAW a JPG, editor, perfiles
    media.py        conversión de audio y video (ffmpeg)
    notes.py        tablón de notas
frontend/           index.html, style.css, app.js
portable/           lanzador y LEEME de la versión portable
data/               datos de cada PC (no se suben al repo)
```

## Aviso

Usalo para contenido propio o con permiso. Descargar contenido ajeno puede
ir contra los términos de uso de cada red.

## Licencia

[MIT](LICENSE)
