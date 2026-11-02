// --- Tabs ---
const mascotImg = document.querySelector(".mascot");

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");

    if (mascotImg) {
      mascotImg.classList.remove("shake");
      void mascotImg.offsetWidth; // reinicia la animación aunque se repita rápido
      mascotImg.classList.add("shake");
    }
  });
});

// --- Parpadeo del mascote ---
if (mascotImg) {
  const OPEN_SRC = mascotImg.getAttribute("src");
  const BLINK_SRC = OPEN_SRC.replace(/mascot\.png$/, "mascot-blink.png");

  function scheduleBlink() {
    const delay = 2500 + Math.random() * 3500;
    setTimeout(() => {
      mascotImg.src = BLINK_SRC;
      setTimeout(() => {
        mascotImg.src = OPEN_SRC;
        scheduleBlink();
      }, 140);
    }, delay);
  }
  scheduleBlink();
}

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

const flameEl = document.getElementById("mascot-flame");
function celebrateSuccess() {
  if (!flameEl) return;
  flameEl.classList.remove("active");
  void flameEl.offsetWidth; // reinicia la animación aunque se repita rápido
  flameEl.classList.add("active");
}

// --- Guardar en la carpeta de Doro Drop ---
// Cada pedido a una herramienta lleva su sección; si en Opciones está
// "guardar directo en la carpeta", el servidor guarda el archivo ahí y
// responde dónde quedó en vez de mandarlo al navegador.
function sectionForUrl(url) {
  const path = String(url);
  if (path.startsWith("/api/download")) return "download";
  if (path.startsWith("/api/pdf")) return "pdf";
  if (path.startsWith("/api/image/edit")) return "editor";
  if (path.startsWith("/api/image/")) return "image";
  if (path.startsWith("/api/media")) return "media";
  return null;
}

const nativeFetch = window.fetch.bind(window);
window.fetch = (url, opts = {}) => {
  const section = typeof url === "string" ? sectionForUrl(url) : null;
  if (!section) return nativeFetch(url, opts);
  const headers = new Headers(opts.headers || {});
  headers.set("X-Doro-Save", section);
  return nativeFetch(url, { ...opts, headers });
};

let lastSavedPath = null;
let toastTimer = null;

function showSavedToast(saved) {
  lastSavedPath = saved.path;
  document.getElementById("toast-text").textContent = `Guardado: ${saved.filename}`;
  document.getElementById("toast-text").title = saved.path;
  const toast = document.getElementById("toast");
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 9000);
}

async function revealInFolder(path) {
  try {
    const res = await fetch("/api/options/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path || null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alertStatus(err.detail || "No se pudo abrir la carpeta");
    }
  } catch (err) {
    alertStatus("No se pudo abrir la carpeta");
  }
}

function alertStatus(message) {
  document.getElementById("toast-text").textContent = message;
  document.getElementById("toast-reveal").hidden = true;
  document.getElementById("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    document.getElementById("toast").hidden = true;
    document.getElementById("toast-reveal").hidden = false;
  }, 6000);
}

document.getElementById("toast-reveal").addEventListener("click", () => revealInFolder(lastSavedPath));
document.getElementById("toast-close").addEventListener("click", () => {
  document.getElementById("toast").hidden = true;
});

async function downloadBlobResponse(response, fallbackName) {
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || "Error desconocido");
  }
  if ((response.headers.get("content-type") || "").includes("application/json")) {
    const saved = await response.json();
    if (saved.saved) {
      document.getElementById("toast-reveal").hidden = false;
      showSavedToast(saved);
      return saved.filename;
    }
  }
  const disposition = response.headers.get("content-disposition") || "";
  // los nombres con acentos llegan como filename*=utf-8''... (RFC 5987)
  const encoded = disposition.match(/filename\*=utf-8''([^;]+)/i);
  const plain = disposition.match(/filename="?([^";]+)"?/);
  const filename = encoded
    ? decodeURIComponent(encoded[1])
    : plain ? plain[1] : fallbackName;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return filename;
}

// --- Descargar video ---
function formatBytes(n) {
  if (!n) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)}${units[i]}`;
}

function formatEta(s) {
  if (s === null || s === undefined) return "";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

let activeDownloadJobId = null;

function pollDownload(jobId, bar, status) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (activeDownloadJobId !== jobId) return; // se canceló y se abandonó el poll

      let data;
      try {
        const res = await fetch(`/api/download/progress/${jobId}`);
        data = await res.json();
      } catch (err) {
        reject(new Error("Se perdió la conexión con el servidor"));
        return;
      }

      if (data.status === "cancelled") {
        const err = new Error("Descarga cancelada");
        err.cancelled = true;
        reject(err);
        return;
      }
      if (data.status === "error") {
        reject(new Error(data.error || "Falló la descarga"));
        return;
      }
      if (data.status === "done") {
        resolve();
        return;
      }

      if (data.status === "downloading" && typeof data.percent === "number") {
        bar.className = "progress-bar";
        bar.style.width = `${data.percent}%`;
        const speed = data.speed ? ` — ${formatBytes(data.speed)}/s` : "";
        const eta = data.eta ? ` — quedan ${formatEta(data.eta)}` : "";
        setStatus(status, `Descargando ${data.percent}%${speed}${eta}`);
      } else if (data.status === "downloading_images") {
        bar.className = "progress-bar indeterminate";
        setStatus(status, `Descargando imágenes... (${data.count || 0} listas)`);
      } else if (data.status === "processing") {
        bar.className = "progress-bar indeterminate";
        setStatus(status, "Procesando (uniendo audio y video)...");
      } else if (data.status === "cancelling") {
        bar.className = "progress-bar indeterminate";
        setStatus(status, "Cancelando...");
      } else {
        bar.className = "progress-bar indeterminate";
        setStatus(status, "Preparando descarga...");
      }

      setTimeout(tick, 700);
    };
    tick();
  });
}

function formatDuration(s) {
  if (!s && s !== 0) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : m;
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

let previewedUrl = null;

const urlBox = document.getElementById("download-url");

function autoGrowUrlBox() {
  urlBox.style.height = "auto";
  urlBox.style.height = `${urlBox.scrollHeight + 4}px`;
}

function parseUrls(text) {
  const seen = new Set();
  return text
    .split(/\s+/)
    .map((u) => u.trim())
    .filter((u) => /^https?:\/\//i.test(u) && !seen.has(u) && seen.add(u));
}

urlBox.addEventListener("input", autoGrowUrlBox);
urlBox.addEventListener("keydown", (e) => {
  // Enter busca; Shift+Enter agrega otra línea para pegar más links
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    document.getElementById("download-search-btn").click();
  }
});

document.getElementById("download-search-btn").addEventListener("click", async () => {
  const searchStatus = document.getElementById("download-search-status");
  const searchBtn = document.getElementById("download-search-btn");
  const preview = document.getElementById("download-preview");
  const urls = parseUrls(urlBox.value);
  if (!urls.length) {
    setStatus(searchStatus, "Pegá un link que empiece con http:// o https://", "err");
    return;
  }

  if (urls.length > 1) {
    preview.hidden = true;
    setStatus(searchStatus, "");
    showBatch(urls);
    return;
  }
  const url = urls[0];
  document.getElementById("download-batch").hidden = true;

  preview.hidden = true;
  setStatus(document.getElementById("download-status"), "");
  searchBtn.disabled = true;
  setStatus(searchStatus, "Buscando...");

  try {
    const res = await fetch("/api/download/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo leer esa URL");

    const thumb = document.getElementById("download-thumb");
    if (data.thumbnail) {
      thumb.src = data.thumbnail;
      thumb.hidden = false;
      thumb.onerror = () => { thumb.hidden = true; };
    } else {
      thumb.hidden = true;
    }
    document.getElementById("download-title").textContent = data.title || "(sin título)";
    const parts = [];
    if (data.extractor) parts.push(data.extractor);
    if (data.duration) parts.push(formatDuration(data.duration));
    document.getElementById("download-meta").textContent = parts.join(" — ");

    previewedUrl = url;
    preview.hidden = false;
    setStatus(searchStatus, "");
  } catch (err) {
    setStatus(searchStatus, err.message, "err");
  } finally {
    searchBtn.disabled = false;
  }
});

document.getElementById("download-cancel-btn").addEventListener("click", async () => {
  if (!activeDownloadJobId) return;
  const cancelBtn = document.getElementById("download-cancel-btn");
  cancelBtn.disabled = true;
  try {
    await fetch(`/api/download/cancel/${activeDownloadJobId}`, { method: "POST" });
  } catch (err) {
    // el poll en curso va a mostrar el error si hace falta
  }
});

document.getElementById("download-confirm-btn").addEventListener("click", async () => {
  const status = document.getElementById("download-status");
  const wrap = document.getElementById("download-progress-wrap");
  const bar = document.getElementById("download-progress-bar");
  const submitBtn = document.getElementById("download-confirm-btn");
  const cancelBtn = document.getElementById("download-cancel-btn");
  const quality = document.getElementById("download-quality").value;

  if (!previewedUrl) return;

  submitBtn.disabled = true;
  cancelBtn.hidden = false;
  cancelBtn.disabled = false;
  wrap.hidden = false;
  bar.className = "progress-bar indeterminate";
  bar.style.width = "";
  setStatus(status, "Iniciando descarga...");

  try {
    const res = await fetch("/api/download/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: previewedUrl, quality }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error al descargar");

    activeDownloadJobId = data.id;
    await pollDownload(data.id, bar, status);

    bar.className = "progress-bar";
    bar.style.width = "100%";
    setStatus(status, "Descarga lista, guardando archivo...");

    const fileRes = await fetch(`/api/download/file/${data.id}`);
    const filename = await downloadBlobResponse(fileRes, "descarga");
    setStatus(status, `Listo: ${filename}`, "ok");
    addToHistory(previewedUrl, filename);
    celebrateSuccess();
  } catch (err) {
    if (err.cancelled) {
      bar.className = "progress-bar";
      bar.style.width = "0%";
      setStatus(status, "Descarga cancelada");
    } else {
      bar.className = "progress-bar error";
      setStatus(status, err.message, "err");
    }
  } finally {
    activeDownloadJobId = null;
    submitBtn.disabled = false;
    cancelBtn.hidden = true;
  }
});

// --- Descargar: cola de varios links ---
let batchUrls = [];
let batchCancelled = false;

function showBatch(urls) {
  batchUrls = urls;
  const list = document.getElementById("download-batch-list");
  list.innerHTML = "";
  for (const url of urls) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="batch-url"></span>
      <div class="progress-wrap" hidden><div class="progress-bar"></div></div>
      <div class="status hint">En espera</div>`;
    li.querySelector(".batch-url").textContent = url;
    li.querySelector(".batch-url").title = url;
    list.appendChild(li);
  }
  setStatus(document.getElementById("download-batch-status"), `${urls.length} links en la cola`);
  document.getElementById("download-batch").hidden = false;
}

async function downloadOne(url, quality, li) {
  const wrap = li.querySelector(".progress-wrap");
  const bar = li.querySelector(".progress-bar");
  const status = li.querySelector(".status");
  wrap.hidden = false;
  bar.className = "progress-bar indeterminate";
  setStatus(status, "Iniciando...");

  const res = await fetch("/api/download/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, quality }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Error al descargar");

  activeDownloadJobId = data.id;
  await pollDownload(data.id, bar, status);
  const fileRes = await fetch(`/api/download/file/${data.id}`);
  const filename = await downloadBlobResponse(fileRes, "descarga");
  bar.className = "progress-bar";
  bar.style.width = "100%";
  setStatus(status, `Listo: ${filename}`, "ok");
  addToHistory(url, filename);
}

document.getElementById("download-batch-btn").addEventListener("click", async () => {
  const startBtn = document.getElementById("download-batch-btn");
  const cancelBtn = document.getElementById("download-batch-cancel-btn");
  const summary = document.getElementById("download-batch-status");
  const quality = document.getElementById("download-batch-quality").value;
  const items = document.querySelectorAll("#download-batch-list li");

  batchCancelled = false;
  startBtn.disabled = true;
  cancelBtn.hidden = false;
  cancelBtn.disabled = false;

  let ok = 0;
  let failed = 0;
  for (let i = 0; i < batchUrls.length; i++) {
    const li = items[i];
    if (batchCancelled) {
      setStatus(li.querySelector(".status"), "Cancelado");
      continue;
    }
    setStatus(summary, `Descargando ${i + 1} de ${batchUrls.length}...`);
    try {
      await downloadOne(batchUrls[i], quality, li);
      ok++;
    } catch (err) {
      const bar = li.querySelector(".progress-bar");
      if (err.cancelled) {
        bar.className = "progress-bar";
        bar.style.width = "0%";
        setStatus(li.querySelector(".status"), "Cancelado");
      } else {
        bar.className = "progress-bar error";
        setStatus(li.querySelector(".status"), err.message, "err");
        failed++;
      }
    } finally {
      activeDownloadJobId = null;
    }
  }

  const parts = [`${ok} descargados`];
  if (failed) parts.push(`${failed} con error`);
  if (batchCancelled) parts.push("cola cancelada");
  setStatus(summary, parts.join(" — "), failed || batchCancelled ? "" : "ok");
  if (ok) celebrateSuccess();
  startBtn.disabled = false;
  cancelBtn.hidden = true;
});

document.getElementById("download-batch-cancel-btn").addEventListener("click", async () => {
  batchCancelled = true;
  document.getElementById("download-batch-cancel-btn").disabled = true;
  if (activeDownloadJobId) {
    try {
      await fetch(`/api/download/cancel/${activeDownloadJobId}`, { method: "POST" });
    } catch (err) {
      // el poll en curso va a mostrar el error si hace falta
    }
  }
});

// --- Descargar: historial (solo en este navegador) ---
const HISTORY_KEY = "doro-drop-history";
const HISTORY_MAX = 30;

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch (err) {
    return [];
  }
}

function saveHistory(items) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
  } catch (err) {
    // navegador sin almacenamiento: el historial simplemente no persiste
  }
}

function addToHistory(url, filename) {
  const items = loadHistory().filter((h) => h.url !== url);
  items.unshift({ url, filename, date: new Date().toISOString() });
  saveHistory(items.slice(0, HISTORY_MAX));
  renderHistory();
}

function renderHistory() {
  const items = loadHistory();
  const card = document.getElementById("download-history-card");
  const list = document.getElementById("download-history");
  card.hidden = items.length === 0;
  list.innerHTML = "";
  for (const h of items) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = h.filename;
    a.title = h.url;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      urlBox.value = h.url;
      autoGrowUrlBox();
      document.getElementById("download-search-btn").click();
      window.scrollTo({ top: document.getElementById("download").offsetTop, behavior: "smooth" });
    });
    const date = document.createElement("span");
    date.className = "history-date";
    date.textContent = new Date(h.date).toLocaleString("es-AR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
    li.append(a, date);
    list.appendChild(li);
  }
}

document.getElementById("download-history-clear").addEventListener("click", () => {
  saveHistory([]);
  renderHistory();
});

renderHistory();

// --- Descargar: sesión de redes (cookies) ---
function renderCookies(data) {
  const el = document.getElementById("cookies-status");
  el.textContent = data.loaded && data.sites.length
    ? `Sesión cargada para: ${data.sites.join(", ")}`
    : "No hay ninguna sesión cargada.";
  document.getElementById("cookies-delete-btn").hidden = !data.loaded;
}

async function refreshCookies() {
  try {
    const res = await fetch("/api/download/cookies");
    renderCookies(await res.json());
  } catch (err) {
    // sin servidor no hay nada que mostrar
  }
}

document.getElementById("cookies-upload-btn").addEventListener("click", async () => {
  const msg = document.getElementById("cookies-msg");
  const input = document.getElementById("cookies-file");
  if (!input.files.length) {
    setStatus(msg, "Elegí primero el archivo .txt que exportó la extensión", "err");
    return;
  }
  const formData = new FormData();
  formData.append("file", input.files[0]);
  try {
    const res = await fetch("/api/download/cookies", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo cargar");
    renderCookies(data);
    const extra = data.discarded ? ` (se descartaron ${data.discarded} de otros sitios)` : "";
    if (data.warnings && data.warnings.length) {
      setStatus(
        msg,
        `Ojo: en ${data.warnings.join(", ")} no había una sesión iniciada. ` +
          "Entrá con tu cuenta, recargá la página y exportá de nuevo.",
        "err"
      );
    } else {
      setStatus(msg, `Listo, sesión guardada${extra}.`, "ok");
    }
    input.value = "";
  } catch (err) {
    setStatus(msg, err.message, "err");
  }
});

document.getElementById("cookies-delete-btn").addEventListener("click", async () => {
  const msg = document.getElementById("cookies-msg");
  try {
    const res = await fetch("/api/download/cookies", { method: "DELETE" });
    renderCookies(await res.json());
    setStatus(msg, "Sesión borrada.", "ok");
  } catch (err) {
    setStatus(msg, "No se pudo borrar", "err");
  }
});

refreshCookies();

// --- Descargar: actualizar descargadores ---
function describeUpdateResults(results) {
  const lines = [];
  for (const [pkg, r] of Object.entries(results || {})) {
    if (r.status === "updated") lines.push(`${pkg} actualizado a ${r.after}`);
    else if (r.status === "rolled_back") lines.push(`${pkg}: ${r.detail}`);
    else if (r.status === "error") lines.push(`${pkg}: error (${r.detail})`);
  }
  return lines;
}

function renderVersions(data) {
  const v = data.installed || {};
  let text = `Versiones instaladas: yt-dlp ${v["yt-dlp"] || "?"} · gallery-dl ${v["gallery-dl"] || "?"}`;
  if (data.restart_needed) text += " — cerrá y volvé a abrir Doro Drop para usar la versión nueva.";
  document.getElementById("updater-versions").textContent = text;

  document.getElementById("updater-auto").checked = data.auto_update !== false;
  if (data.min_age_days !== undefined) {
    document.getElementById("updater-min-age").textContent = data.min_age_days;
  }

  const last = document.getElementById("updater-last");
  if (data.last_check) {
    const when = new Date(data.last_check).toLocaleString("es-AR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
    const changes = describeUpdateResults(data.last_results);
    last.textContent = `Última revisión: ${when}. ` + (changes.length ? changes.join("; ") + "." : "Todo al día.");
  } else {
    last.textContent = data.auto_update === false ? "" : "Todavía no revisó (lo hace al minuto de abrir la app).";
  }
}

document.getElementById("updater-auto").addEventListener("change", async (e) => {
  try {
    const res = await fetch("/api/system/auto-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: e.target.checked }),
    });
    renderVersions(await res.json());
  } catch (err) {
    setStatus(document.getElementById("updater-status"), "No se pudo guardar el ajuste", "err");
  }
});

async function refreshVersions() {
  try {
    const res = await fetch("/api/system/versions");
    renderVersions(await res.json());
  } catch (err) {
    // sin servidor no hay nada que mostrar
  }
}

document.getElementById("updater-btn").addEventListener("click", async () => {
  const btn = document.getElementById("updater-btn");
  const status = document.getElementById("updater-status");
  btn.disabled = true;
  setStatus(status, "Buscando actualizaciones (puede tardar un minuto)...");
  try {
    const res = await fetch("/api/system/update-downloaders", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo actualizar");
    renderVersions(data);
    const changes = describeUpdateResults(data.results);
    let text = changes.length ? changes.join("; ") + "." : "Ya tenías la última versión.";
    if (data.restart_needed) text += " Cerrá y volvé a abrir Doro Drop para terminar.";
    const failed = Object.values(data.results || {}).some((r) => r.status !== "updated" && r.status !== "up_to_date");
    setStatus(status, text, failed ? "err" : "ok");
  } catch (err) {
    setStatus(status, err.message, "err");
  } finally {
    btn.disabled = false;
  }
});

refreshVersions();

// --- PDF: unir ---
document.getElementById("pdf-merge-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("pdf-status");
  const files = document.getElementById("pdf-merge-files").files;
  const formData = new FormData();
  for (const f of files) formData.append("files", f);

  setStatus(status, "Uniendo PDFs...");
  try {
    const res = await fetch("/api/pdf/merge", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, "unido.pdf");
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- PDF: dividir ---
document.getElementById("pdf-split-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("pdf-status");
  const file = document.getElementById("pdf-split-file").files[0];
  const formData = new FormData();
  formData.append("file", file);

  setStatus(status, "Dividiendo PDF...");
  try {
    const res = await fetch("/api/pdf/split", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, "paginas.zip");
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- PDF: imágenes a PDF ---
document.getElementById("pdf-img2pdf-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("pdf-status");
  const files = document.getElementById("pdf-img2pdf-files").files;
  const formData = new FormData();
  for (const f of files) formData.append("files", f);

  setStatus(status, "Convirtiendo imágenes a PDF...");
  try {
    const res = await fetch("/api/pdf/images-to-pdf", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, "imagenes.pdf");
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- Imágenes ---
document.getElementById("image-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("image-status");
  const file = document.getElementById("image-file").files[0];
  const targetFormat = document.getElementById("image-format").value;
  const maxWidth = document.getElementById("image-maxwidth").value;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_format", targetFormat);
  if (maxWidth) formData.append("max_width", maxWidth);

  setStatus(status, "Convirtiendo imagen...");
  try {
    const res = await fetch("/api/image/convert", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, `convertida.${targetFormat}`);
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- RAW a JPG ---
document.getElementById("raw2jpg-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("image-status");
  const files = document.getElementById("raw2jpg-files").files;
  const formData = new FormData();
  for (const f of files) formData.append("files", f);

  setStatus(status, "Convirtiendo RAW a JPG... puede tardar un poco.");
  try {
    const res = await fetch("/api/image/raw-to-jpg", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, "raw_a_jpg.zip");
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- Audio / Video ---
document.getElementById("media-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("media-status");
  const file = document.getElementById("media-file").files[0];
  const targetFormat = document.getElementById("media-format").value;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_format", targetFormat);

  setStatus(status, "Convirtiendo... esto puede tardar unos minutos.");
  try {
    const res = await fetch("/api/media/convert", { method: "POST", body: formData });
    const filename = await downloadBlobResponse(res, `convertido.${targetFormat}`);
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// --- Notas ---
function formatNoteDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function loadNotes() {
  const list = document.getElementById("notes-list");
  try {
    const res = await fetch("/api/notes");
    const notes = await res.json();
    list.innerHTML = "";

    if (notes.length === 0) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "Todavía no hay notas. Sé el primero en dejar una.";
      list.appendChild(empty);
      return;
    }

    for (const note of notes) {
      const card = document.createElement("div");
      card.className = "note-card";

      const header = document.createElement("div");
      header.className = "note-header";

      const author = document.createElement("span");
      author.className = "note-author";
      author.textContent = note.author;

      const date = document.createElement("span");
      date.className = "note-date";
      date.textContent = formatNoteDate(note.created_at);

      header.appendChild(author);
      header.appendChild(date);

      const text = document.createElement("div");
      text.className = "note-text";
      text.textContent = note.text;

      const del = document.createElement("button");
      del.className = "note-delete";
      del.textContent = "Eliminar";
      del.addEventListener("click", async () => {
        del.disabled = true;
        try {
          await fetch(`/api/notes/${note.id}`, { method: "DELETE" });
          loadNotes();
        } catch (err) {
          del.disabled = false;
        }
      });

      card.appendChild(header);
      card.appendChild(text);
      card.appendChild(del);
      list.appendChild(card);
    }
  } catch (err) {
    list.innerHTML = "";
    const errEl = document.createElement("p");
    errEl.className = "status err";
    errEl.textContent = "No se pudieron cargar las notas.";
    list.appendChild(errEl);
  }
}

document.getElementById("note-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("note-status");
  const authorInput = document.getElementById("note-author");
  const textInput = document.getElementById("note-text");
  const submitBtn = document.getElementById("note-form").querySelector("button[type=submit]");

  const text = textInput.value.trim();
  if (!text) return;

  submitBtn.disabled = true;
  setStatus(status, "Publicando...");

  try {
    const res = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: authorInput.value.trim(), text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo publicar la nota");

    textInput.value = "";
    setStatus(status, "");
    celebrateSuccess();
    loadNotes();
  } catch (err) {
    setStatus(status, err.message, "err");
  } finally {
    submitBtn.disabled = false;
  }
});

loadNotes();

// --- Editor ---
const RAW_EXTS = [".cr2", ".cr3", ".nef", ".arw", ".dng", ".rw2", ".orf", ".raf", ".pef", ".srw"];
function isRawFilename(name) {
  const lower = name.toLowerCase();
  return RAW_EXTS.some((ext) => lower.endsWith(ext));
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("No se pudo cargar la imagen"));
    img.src = url;
  });
}

// misma matemática que _apply_edits en el backend (images.py), para que la
// vista previa del canvas coincida con lo que se descarga al final
function applyEditsToImageData(srcData, exposure, contrast, saturation, temperature, tint) {
  const out = new Uint8ClampedArray(srcData);
  const n = out.length / 4;

  const expFactor = 1 + exposure / 100;
  if (expFactor !== 1) {
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      out[o] = srcData[o] * expFactor;
      out[o + 1] = srcData[o + 1] * expFactor;
      out[o + 2] = srcData[o + 2] * expFactor;
    }
  }

  if (contrast) {
    let sum = 0;
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      sum += out[o] * 0.299 + out[o + 1] * 0.587 + out[o + 2] * 0.114;
    }
    const mean = sum / n;
    const cFactor = 1 + contrast / 100;
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      out[o] = mean + (out[o] - mean) * cFactor;
      out[o + 1] = mean + (out[o + 1] - mean) * cFactor;
      out[o + 2] = mean + (out[o + 2] - mean) * cFactor;
    }
  }

  if (saturation) {
    const sFactor = 1 + saturation / 100;
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      const luma = out[o] * 0.299 + out[o + 1] * 0.587 + out[o + 2] * 0.114;
      out[o] = luma + (out[o] - luma) * sFactor;
      out[o + 1] = luma + (out[o + 1] - luma) * sFactor;
      out[o + 2] = luma + (out[o + 2] - luma) * sFactor;
    }
  }

  if (temperature || tint) {
    const rShift = temperature * 0.6 + tint * 0.25;
    const gShift = -tint * 0.5;
    const bShift = -temperature * 0.6 + tint * 0.25;
    for (let i = 0; i < n; i++) {
      const o = i * 4;
      out[o] += rShift;
      out[o + 1] += gShift;
      out[o + 2] += bShift;
    }
  }

  return out;
}

const EDITOR_SLIDERS = ["exposure", "contrast", "saturation", "temperature", "tint"];
let editorFiles = [];       // [{id, file, selected, previewUrl}]
let editorActiveId = null;
let editorBaseImageData = null;
let editorCanvas = null;
let editorCtx = null;
let editorRAF = null;

function resetEditorSliders() {
  for (const id of EDITOR_SLIDERS) {
    document.getElementById(`editor-${id}`).value = 0;
    document.getElementById(`editor-${id}-val`).textContent = "0";
  }
}

function redrawEditor() {
  if (editorRAF) cancelAnimationFrame(editorRAF);
  editorRAF = requestAnimationFrame(() => {
    if (!editorBaseImageData) return;
    const values = {};
    for (const id of EDITOR_SLIDERS) {
      values[id] = Number(document.getElementById(`editor-${id}`).value);
    }
    const out = applyEditsToImageData(
      editorBaseImageData.data,
      values.exposure, values.contrast, values.saturation, values.temperature, values.tint
    );
    editorCtx.putImageData(
      new ImageData(out, editorCanvas.width, editorCanvas.height), 0, 0
    );
  });
}

function renderEditorFileList() {
  const list = document.getElementById("editor-file-list");
  list.innerHTML = "";
  for (const ef of editorFiles) {
    const card = document.createElement("div");
    card.className = "editor-file-card" + (ef.id === editorActiveId ? " active" : "");
    card.dataset.id = ef.id;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = ef.selected;
    checkbox.addEventListener("click", (evt) => evt.stopPropagation());
    checkbox.addEventListener("change", () => { ef.selected = checkbox.checked; });

    const img = document.createElement("img");
    img.src = ef.previewUrl;
    img.alt = ef.file.name;

    const fname = document.createElement("div");
    fname.className = "fname";
    fname.textContent = ef.file.name;

    card.appendChild(checkbox);
    card.appendChild(img);
    card.appendChild(fname);
    card.addEventListener("click", () => selectEditorFile(ef.id));
    list.appendChild(card);
  }
}

async function selectEditorFile(id) {
  const ef = editorFiles.find((f) => f.id === id);
  if (!ef) return;
  editorActiveId = id;

  const img = await loadImage(ef.previewUrl);
  editorCanvas = document.getElementById("editor-canvas");
  editorCtx = editorCanvas.getContext("2d");
  const maxW = 700;
  const scale = Math.min(1, maxW / img.width);
  editorCanvas.width = Math.round(img.width * scale);
  editorCanvas.height = Math.round(img.height * scale);
  editorCtx.drawImage(img, 0, 0, editorCanvas.width, editorCanvas.height);
  editorBaseImageData = editorCtx.getImageData(0, 0, editorCanvas.width, editorCanvas.height);

  redrawEditor(); // reaplica los sliders actuales a la foto que se acaba de abrir

  document.querySelectorAll(".editor-file-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === id);
  });
}

document.getElementById("editor-file").addEventListener("change", async (e) => {
  const files = Array.from(e.target.files);
  if (!files.length) return;
  const status = document.getElementById("editor-status");
  const workspace = document.getElementById("editor-workspace");

  workspace.hidden = true;
  setStatus(status, "Cargando...");

  for (const ef of editorFiles) URL.revokeObjectURL(ef.previewUrl);
  editorFiles = [];
  editorActiveId = null;
  editorBaseImageData = null;

  try {
    for (const file of files) {
      let previewUrl;
      if (isRawFilename(file.name)) {
        const formData = new FormData();
        formData.append("file", file);
        const res = await fetch("/api/image/preview", { method: "POST", body: formData });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(`${file.name}: ${err.detail || "no se pudo leer"}`);
        }
        previewUrl = URL.createObjectURL(await res.blob());
      } else {
        previewUrl = URL.createObjectURL(file);
      }
      editorFiles.push({ id: crypto.randomUUID(), file, selected: true, previewUrl });
    }

    resetEditorSliders();
    renderEditorFileList();
    await selectEditorFile(editorFiles[0].id);

    workspace.hidden = false;
    setStatus(status, "");
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

for (const id of EDITOR_SLIDERS) {
  document.getElementById(`editor-${id}`).addEventListener("input", (e) => {
    document.getElementById(`editor-${id}-val`).textContent = e.target.value;
    redrawEditor();
  });
}

document.getElementById("editor-reset-btn").addEventListener("click", () => {
  resetEditorSliders();
  redrawEditor();
});

document.getElementById("editor-download-btn").addEventListener("click", async () => {
  if (!editorFiles.length) return;
  const status = document.getElementById("editor-status");
  const btn = document.getElementById("editor-download-btn");
  const fmt = document.getElementById("editor-format").value;
  const scope = document.querySelector('input[name="editor-apply-scope"]:checked').value;

  const targets = scope === "selected" ? editorFiles.filter((f) => f.selected) : editorFiles;
  if (!targets.length) {
    setStatus(status, "No hay fotos seleccionadas", "err");
    return;
  }

  const formData = new FormData();
  for (const ef of targets) formData.append("files", ef.file);
  for (const id of EDITOR_SLIDERS) {
    formData.append(id, document.getElementById(`editor-${id}`).value);
  }
  formData.append("target_format", fmt);

  btn.disabled = true;
  setStatus(status, `Procesando ${targets.length} foto${targets.length > 1 ? "s" : ""}...`);
  try {
    const res = await fetch("/api/image/edit-batch", { method: "POST", body: formData });
    const fallback = targets.length > 1 ? "editadas.zip" : `editada.${fmt}`;
    const filename = await downloadBlobResponse(res, fallback);
    setStatus(status, `Listo: ${filename}`, "ok");
    celebrateSuccess();
  } catch (err) {
    setStatus(status, err.message, "err");
  } finally {
    btn.disabled = false;
  }
});

// --- Perfiles de color (presets) ---
async function loadPresetsList() {
  const select = document.getElementById("editor-preset-select");
  select.innerHTML = '<option value="">— Perfil guardado —</option>';
  try {
    const res = await fetch("/api/image/presets");
    const presets = await res.json();
    for (const p of presets) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    }
  } catch (err) {
    // no bloquea el resto del editor si esto falla
  }
}

document.getElementById("editor-preset-load-btn").addEventListener("click", async () => {
  const id = document.getElementById("editor-preset-select").value;
  if (!id) return;
  try {
    const res = await fetch("/api/image/presets");
    const presets = await res.json();
    const preset = presets.find((p) => p.id === id);
    if (!preset) return;
    for (const key of EDITOR_SLIDERS) {
      document.getElementById(`editor-${key}`).value = preset[key];
      document.getElementById(`editor-${key}-val`).textContent = preset[key];
    }
    redrawEditor();
  } catch (err) {
    setStatus(document.getElementById("editor-status"), "No se pudo cargar el perfil", "err");
  }
});

document.getElementById("editor-preset-save-btn").addEventListener("click", async () => {
  const name = window.prompt("Nombre del perfil:");
  if (!name || !name.trim()) return;
  const status = document.getElementById("editor-status");

  const values = {};
  for (const key of EDITOR_SLIDERS) values[key] = Number(document.getElementById(`editor-${key}`).value);

  try {
    const res = await fetch("/api/image/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), ...values }),
    });
    if (!res.ok) throw new Error("No se pudo guardar el perfil");
    await loadPresetsList();
    setStatus(status, `Perfil "${name.trim()}" guardado`, "ok");
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

document.getElementById("editor-preset-delete-btn").addEventListener("click", async () => {
  const select = document.getElementById("editor-preset-select");
  const id = select.value;
  if (!id) return;
  await fetch(`/api/image/presets/${id}`, { method: "DELETE" });
  await loadPresetsList();
});

loadPresetsList();

// --- Opciones ---
let options = null;

function shortFolder(path) {
  // "C:\Users\Ana\Downloads\Doro Drop\PDF" -> "Downloads\Doro Drop\PDF"
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 3 ? "…\\" + parts.slice(-3).join("\\") : path;
}

function folderForSection(section) {
  const base = options.save_dir;
  const sub = options.subfolders && options.section_folders[section];
  return sub ? `${base}\\${sub}` : base;
}

function renderSaveLines() {
  document.querySelectorAll(".save-line").forEach((el) => {
    el.innerHTML = "";
    if (!options) return;
    if (!options.is_local || !options.save_to_folder) {
      el.textContent = "Se guarda en las descargas del navegador.";
      return;
    }
    const folder = folderForSection(el.dataset.section);
    el.append("Se guarda en ");
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = shortFolder(folder);
    a.title = `${folder}\nTocá para abrir la carpeta`;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      revealInFolder(folder);
    });
    el.append(a, " · ");
    const change = document.createElement("a");
    change.href = "#";
    change.textContent = "cambiar";
    change.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelector('[data-tab="options"]').click();
    });
    el.append(change);
  });
}

function renderOptions(data) {
  options = data;
  document.body.classList.toggle("hide-help", !data.show_help);
  document.body.classList.toggle("remote", !data.is_local);
  document.getElementById("opt-folder").textContent = data.save_dir;
  document.getElementById("opt-folder-reset").hidden = !data.is_custom_dir;
  document.getElementById("opt-subfolders").checked = data.subfolders;
  document.getElementById("opt-save-to-folder").checked = data.save_to_folder;
  document.getElementById("opt-show-help").checked = data.show_help;
  renderSaveLines();
}

async function saveOptions(changes, statusEl) {
  try {
    const res = await fetch("/api/options", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo guardar");
    renderOptions(data);
    if (statusEl) setStatus(statusEl, "");
  } catch (err) {
    if (statusEl) setStatus(statusEl, err.message, "err");
    loadOptions();
  }
}

async function loadOptions() {
  try {
    const res = await fetch("/api/options");
    renderOptions(await res.json());
  } catch (err) {
    // sin servidor no hay nada que mostrar
  }
}

const folderStatus = document.getElementById("opt-folder-status");

document.getElementById("opt-folder-open").addEventListener("click", () => revealInFolder(null));

document.getElementById("opt-folder-pick").addEventListener("click", async () => {
  const btn = document.getElementById("opt-folder-pick");
  btn.disabled = true;
  setStatus(folderStatus, "Elegí la carpeta en la ventana que se abrió (puede quedar detrás de esta).");
  try {
    const res = await fetch("/api/options/pick-folder", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo abrir el selector");
    renderOptions(data);
    setStatus(folderStatus, data.changed ? "Listo, de ahora en más se guarda ahí." : "", data.changed ? "ok" : "");
  } catch (err) {
    setStatus(folderStatus, err.message, "err");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("opt-folder-reset").addEventListener("click", () =>
  saveOptions({ save_dir: "" }, folderStatus)
);
document.getElementById("opt-subfolders").addEventListener("change", (e) =>
  saveOptions({ subfolders: e.target.checked }, folderStatus)
);
document.getElementById("opt-save-to-folder").addEventListener("change", (e) =>
  saveOptions({ save_to_folder: e.target.checked }, folderStatus)
);
document.getElementById("opt-show-help").addEventListener("change", (e) =>
  saveOptions({ show_help: e.target.checked })
);

document.getElementById("opt-shortcut").addEventListener("click", async () => {
  const status = document.getElementById("opt-shortcut-status");
  try {
    const res = await fetch("/api/options/shortcut", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo crear");
    setStatus(status, "Listo, ya está el ícono de Doro Drop en el escritorio.", "ok");
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

loadOptions();

// la ventana avisa que sigue abierta y se despide al cerrarse: el lanzador
// apaga el servidor cuando no queda ninguna ventana de Doro Drop
const PAGE_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
const pageBody = () => JSON.stringify({ page: PAGE_ID });

function sendPing() {
  nativeFetch("/api/options/ping", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: pageBody(),
  }).catch(() => {});
}

sendPing();
setInterval(sendPing, 10000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") sendPing();
});
window.addEventListener("pagehide", () => {
  navigator.sendBeacon("/api/options/bye", new Blob([pageBody()], { type: "application/json" }));
});
