// ai-detect UI: pick/drop/take a photo, optionally downscale it, POST /api/detect, draw the boxes.
// Plain JS, no dependencies, works offline.
"use strict";

const MAX_SIDE = 1280;        // client-side downscale target
const MAX_DISPLAY = 1600;     // canvas size cap for showing huge originals
const STATUS_EVERY_MS = 3000;

const $ = (id) => document.getElementById(id);
const els = {
  drop: $("drop"), file: $("file"), camera: $("camera"), cameraBtn: $("camera-btn"),
  downscale: $("downscale"), minscore: $("minscore"), minscoreOut: $("minscore-out"),
  result: $("result"), busy: $("busy"), busyText: $("busy-text"), error: $("error"),
  canvas: $("canvas"), objects: $("objects"), count: $("count"), timing: $("timing"),
  pill: $("status-pill"), pillText: $("pill-text"),
};

let current = null;   // {bitmap, res, clientMs}
let inflight = null;  // AbortController

// Hide "Take photo" on devices without a camera-ish pointer (desktop); keep it on touch devices.
if (!matchMedia("(pointer: coarse)").matches) els.cameraBtn.hidden = true;

// ---- input ------------------------------------------------------------------------------------------------

els.drop.addEventListener("click", (e) => { if (e.target === els.drop || e.target.tagName === "P") els.file.click(); });
els.drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.file.click(); } });
for (const inp of [els.file, els.camera]) {
  inp.addEventListener("change", () => { if (inp.files[0]) handleFile(inp.files[0]); inp.value = ""; });
}
["dragenter", "dragover"].forEach((t) => els.drop.addEventListener(t, (e) => { e.preventDefault(); els.drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => els.drop.addEventListener(t, (e) => { e.preventDefault(); els.drop.classList.remove("over"); }));
els.drop.addEventListener("drop", (e) => {
  const f = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
  if (f) handleFile(f); else showError("Drop an image file (JPEG or PNG).");
});
// Allow dropping anywhere on the page without the browser navigating to the file.
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => { if (!els.drop.contains(e.target)) { e.preventDefault(); const f = e.dataTransfer?.files?.[0]; if (f) handleFile(f); } });
// Paste an image from the clipboard.
window.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item) handleFile(item.getAsFile());
});

els.minscore.addEventListener("input", () => {
  els.minscoreOut.value = Number(els.minscore.value).toFixed(2);
  if (current) render();
});

// ---- upload -----------------------------------------------------------------------------------------------

async function decode(blob, orientation) {
  try { return await createImageBitmap(blob, { imageOrientation: orientation }); }
  catch { return await createImageBitmap(blob); }
}

// Returns {blob, bitmap}: the bytes to send and a bitmap whose pixels match what the detector will see.
async function prepare(file) {
  if (els.downscale.checked) {
    // Re-encode through a canvas: smaller upload, and EXIF rotation gets baked into the pixels.
    const src = await decode(file, "from-image");
    const scale = Math.min(1, MAX_SIDE / Math.max(src.width, src.height));
    const w = Math.round(src.width * scale), h = Math.round(src.height * scale);
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    c.getContext("2d").drawImage(src, 0, 0, w, h);
    src.close?.();
    const blob = await new Promise((ok, fail) => c.toBlob((b) => (b ? ok(b) : fail(new Error("encode failed"))), "image/jpeg", 0.9));
    return { blob, bitmap: await createImageBitmap(c) };
  }
  if (!/^image\/(jpeg|png)$/.test(file.type)) throw new Error(`The board only reads JPEG and PNG (this is ${file.type || "unknown"}). Turn on downscaling to convert it.`);
  // Original bytes: the detector ignores EXIF orientation, so show the image unrotated too.
  return { blob: file, bitmap: await decode(file, "none") };
}

async function handleFile(file) {
  inflight?.abort();
  const ctl = (inflight = new AbortController());
  hideError();
  els.result.hidden = false;
  setBusy("Preparing image…");
  const t0 = performance.now();
  let prep;
  try {
    prep = await prepare(file);
  } catch (e) {
    setBusy(null); showError(e.message || String(e)); return;
  }
  const tPrep = performance.now();
  // Show the image straight away, without boxes.
  current = { bitmap: prep.bitmap, res: null, client: null };
  render();
  setBusy(`Detecting… (${fmtBytes(prep.blob.size)})`);

  const form = new FormData();
  form.append("image", prep.blob, prep.blob.type === "image/png" ? "image.png" : "image.jpg");
  let res;
  try {
    const r = await fetch("api/detect", { method: "POST", body: form, signal: ctl.signal });
    res = await r.json().catch(() => ({ ok: false, error: `HTTP ${r.status}` }));
    if (!r.ok && res.ok !== false) res = { ok: false, error: `HTTP ${r.status}` };
  } catch (e) {
    if (ctl.signal.aborted) return;
    res = { ok: false, error: "Cannot reach the board: " + e.message };
  }
  if (ctl !== inflight) return;
  inflight = null;
  setBusy(null);
  const tDone = performance.now();
  if (!res.ok) {
    showError(res.error || "Detection failed");
    current.res = null;
    render();
    pollStatus();
    return;
  }
  current.res = res;
  current.client = { prepare: tPrep - t0, roundtrip: tDone - tPrep, size: prep.blob.size };
  render();
  pollStatus();
}

// ---- drawing ----------------------------------------------------------------------------------------------

function colour(cls, alpha = 1) {
  const hue = (cls * 137.508 + 200) % 360; // golden angle: neighbouring classes get distant hues
  return `hsla(${hue.toFixed(0)}, 85%, 52%, ${alpha})`;
}

function visibleObjects() {
  const min = Number(els.minscore.value);
  return (current?.res?.objects || []).map((o, i) => ({ ...o, i, show: o.score >= min }));
}

function render() {
  const { bitmap, res } = current;
  const scale = Math.min(1, MAX_DISPLAY / Math.max(bitmap.width, bitmap.height));
  const W = Math.round(bitmap.width * scale), H = Math.round(bitmap.height * scale);
  const cv = els.canvas;
  cv.width = W; cv.height = H;
  const g = cv.getContext("2d");
  g.drawImage(bitmap, 0, 0, W, H);
  renderList();
  renderTiming();
  if (!res) return;

  // Boxes are in the detector's image coordinates (res.width x res.height).
  const sx = W / (res.width || bitmap.width), sy = H / (res.height || bitmap.height);
  // Keep lines and labels readable on screen: k = canvas pixels per CSS pixel (large on phones).
  const k = W / Math.max(1, Math.min(W, cv.parentElement.clientWidth || W));
  const lw = Math.max(2, Math.round(2 * k));
  const fs = Math.max(13, Math.round(13 * k));
  g.font = `600 ${fs}px system-ui, sans-serif`;
  g.textBaseline = "top";
  const objs = visibleObjects().filter((o) => o.show).reverse(); // draw best last (on top)
  for (const o of objs) {
    const [x1, y1, x2, y2] = o.box;
    const x = x1 * sx, y = y1 * sy, w = (x2 - x1) * sx, h = (y2 - y1) * sy;
    g.lineWidth = lw;
    g.strokeStyle = colour(o.class);
    g.fillStyle = colour(o.class, 0.12);
    g.fillRect(x, y, w, h);
    g.strokeRect(x, y, w, h);
    const text = `${o.label} ${(o.score * 100).toFixed(0)}%`;
    const tw = g.measureText(text).width + fs * 0.6, th = fs * 1.35;
    const ty = y - th >= 0 ? y - th : y; // above the box if there is room
    const tx = Math.min(Math.max(0, x - lw / 2), W - tw);
    g.fillStyle = colour(o.class);
    g.fillRect(tx, ty, tw, th);
    g.fillStyle = "#fff";
    g.fillText(text, tx + fs * 0.3, ty + fs * 0.18);
  }
}

function renderList() {
  const ul = els.objects;
  ul.textContent = "";
  if (!current.res) { els.count.textContent = ""; return; }
  const objs = visibleObjects();
  const shown = objs.filter((o) => o.show).length;
  els.count.textContent = objs.length === shown ? `(${shown})` : `(${shown} of ${objs.length})`;
  if (!objs.length) {
    const li = document.createElement("li");
    li.innerHTML = `<span></span><span class="muted">Nothing detected</span>`;
    ul.append(li);
    return;
  }
  for (const o of objs) {
    const li = document.createElement("li");
    if (!o.show) li.className = "dim";
    const sw = document.createElement("span"); sw.className = "sw"; sw.style.background = colour(o.class);
    const name = document.createElement("span"); name.textContent = o.label;
    const [x1, y1, x2, y2] = o.box;
    name.title = `box ${x1},${y1} – ${x2},${y2} (${x2 - x1}×${y2 - y1} px)`;
    const sc = document.createElement("span"); sc.className = "score"; sc.textContent = (o.score * 100).toFixed(1) + "%";
    const bar = document.createElement("span"); bar.className = "bar";
    const fill = document.createElement("i"); fill.style.width = (o.score * 100).toFixed(1) + "%"; fill.style.background = colour(o.class);
    bar.append(fill);
    li.append(sw, name, sc, bar);
    ul.append(li);
  }
}

const STAGES = [
  ["decode", "Decode", "#8b5cf6"],
  ["preprocess", "Preprocess", "#06b6d4"],
  ["npu", "NPU", "#f59e0b"],
  ["postprocess", "Postprocess", "#10b981"],
];

function renderTiming() {
  const t = els.timing;
  t.textContent = "";
  const res = current.res;
  if (!res) return;
  const m = res.ms || {}, s = res.server || {}, c = current.client || {};
  const row = (label, val, cls, swatch) => {
    const tr = t.insertRow();
    if (cls) tr.className = cls;
    const a = tr.insertCell(), b = tr.insertCell();
    if (swatch) a.innerHTML = `<span class="sw" style="display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:${swatch}"></span>`;
    a.append(label);
    b.textContent = val == null ? "–" : `${Number(val).toFixed(1)} ms`;
  };
  // Stacked bar of the detector stages.
  const total = STAGES.reduce((a, [k]) => a + (m[k] || 0), 0);
  if (total > 0) {
    const tr = t.insertRow(), td = tr.insertCell(); td.colSpan = 2; td.style.borderBottom = "0";
    const bar = document.createElement("div"); bar.className = "tbar";
    for (const [k, , col] of STAGES) {
      const seg = document.createElement("span");
      seg.style.width = ((m[k] || 0) / total * 100) + "%"; seg.style.background = col; seg.title = k;
      bar.append(seg);
    }
    td.append(bar);
  }
  for (const [k, label, col] of STAGES) row(label, m[k], "", col);
  row("Detector total", m.total, "total");
  const sep = t.insertRow(); sep.className = "sep"; const sc = sep.insertCell(); sc.colSpan = 2; sc.textContent = "End to end";
  row("Prepare in browser", c.prepare);
  row("Upload to board", s.upload_ms);
  row("Server (upload + queue + detect)", s.total_ms);
  row("Round trip", c.roundtrip, "total");
}

// ---- status -----------------------------------------------------------------------------------------------

let statusTimer = null;
async function pollStatus() {
  clearTimeout(statusTimer);
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    showStatus(await r.json());
  } catch {
    setPill("offline", "board offline");
  }
  statusTimer = setTimeout(tick, STATUS_EVERY_MS);
}
function tick() { if (document.hidden) statusTimer = setTimeout(tick, STATUS_EVERY_MS); else pollStatus(); }
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollStatus(); });

function setPill(state, text) {
  els.pill.className = "pill " + state;
  els.pillText.textContent = text;
}

function showStatus(st) {
  const d = st.detector || {}, sys = st.system || {};
  const state = d.state || "unknown";
  setPill(state, (st.mock ? "mock · " : "") + state);
  const stateEl = $("s-state");
  stateEl.textContent = state + (d.restarts ? ` (${d.restarts} restart${d.restarts > 1 ? "s" : ""})` : "");
  stateEl.className = state === "ready" ? "ok" : state === "error" ? "bad" : "warn";
  $("s-model").textContent = (st.model || "–") + (d.input ? ` · ${d.input.join("×")}` : "");
  const temp = $("s-temp");
  if (sys.temp_c != null) {
    temp.textContent = sys.temp_c.toFixed(1) + " °C";
    temp.className = sys.temp_c >= 85 ? "bad" : sys.temp_c >= 70 ? "warn" : "";
  } else { temp.textContent = "n/a"; temp.className = "muted"; }
  const mem = $("s-mem");
  if (sys.mem_available_kb != null && sys.mem_total_kb) {
    mem.textContent = `${(sys.mem_available_kb / 1024).toFixed(0)} / ${(sys.mem_total_kb / 1024).toFixed(0)} MB`;
    mem.className = sys.mem_available_kb / sys.mem_total_kb < 0.1 ? "bad" : "";
  } else { mem.textContent = "n/a"; mem.className = "muted"; }
  $("s-load").textContent = sys.load?.length ? sys.load.map((x) => x.toFixed(2)).join(" ") : "n/a";
  $("s-uptime").textContent = fmtDuration(sys.uptime_s ?? st.server_uptime_s);
  const sv = st.served || {};
  $("s-served").textContent = `${sv.detections ?? 0} (${sv.objects ?? 0} objects${sv.failures ? `, ${sv.failures} failed` : ""})`;
  $("s-last").textContent = st.last_inference ? `${st.last_inference.total_ms.toFixed(1)} ms (NPU ${st.last_inference.npu_ms.toFixed(1)})` : "–";
  const err = $("s-error");
  err.hidden = !(d.last_error && state !== "ready");
  err.textContent = d.last_error ? "Last error: " + d.last_error : "";
}

// ---- helpers ----------------------------------------------------------------------------------------------

function setBusy(text) {
  els.busy.hidden = !text;
  if (text) els.busyText.textContent = text;
}
function showError(msg) { els.result.hidden = false; els.error.hidden = false; els.error.textContent = msg; }
function hideError() { els.error.hidden = true; }
function fmtBytes(n) { return n < 1024 * 1024 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
function fmtDuration(s) {
  if (s == null) return "–";
  s = Math.floor(s);
  const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60;
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
}

pollStatus();
