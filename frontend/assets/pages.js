/* InsaneVoice — page renderers (vanilla JS, hash-routed) */

import { API, state, refreshSystem, refreshVoices, nav, render } from "./app.js";
import {
  toast, modal, confirmModal, sk, busy, WaveBox, radarChart,
  esc, fmtDur, fmtWhen, download, pageHead, iconBtn, langLabel, groupedVoiceOptions,
} from "./components.js";

/* ============================================================
   helpers
   ============================================================ */

const banners = {
  modelsMissing: `
    <div class="banner warn">!
      <div><b>Models are not downloaded yet.</b><br>
      Run <span class="kbd">python scripts/download_models.py</span> from the
      InsaneVoice folder, then reload this page.</div>
    </div>`,
  engineBusy: (s) => `
    <div class="banner">⏳
      <div><b>Engine is ${esc(s)}.</b> First load takes ~30–60s on CPU.
      This page will work once loading finishes.</div>
    </div>`,
};

function head(title, sub, kicker) {
  return `
    <div class="page-head">
      ${kicker ? `<div class="kicker">${esc(kicker)}</div>` : ""}
      <h1>${esc(title)}</h1>
      ${sub ? `<p>${esc(sub)}</p>` : ""}
    </div>`;
}

function pageShell(html) {
  return `<div style="margin-top:6px">${html}</div>`;
}

async function needVoices() {
  await refreshVoices();
  return state.voices;
}

function voiceOptions(voices, selectedId) {
  if (!voices.length) return `<option value="">— no voices yet —</option>`;
  return voices.map((v) =>
    `<option value="${esc(v.id)}" ${v.id === selectedId ? "selected" : ""}>
      ${esc(v.name)}</option>`).join("");
}

function audioCard(gen) {
  const d = document.createElement("div");
  d.className = "audio-card";
  d.innerHTML = `
    <div class="spread">
      <div class="row">
        <button class="btn sm accent" data-play>▶ Play</button>
        <button class="btn sm" data-dl>⬇ Download</button>
      </div>
      <div class="audio-meta">
        <span class="pill acc">${esc(gen.voice_name || "voice")}</span>
        <span class="pill">${fmtDur(gen.duration)}</span>
        ${gen.elapsed ? `<span class="pill">made in ${fmtDur(gen.elapsed)}</span>` : ""}
      </div>
    </div>
    <div data-wave></div>
    ${gen.text ? `<div class="small muted" style="max-height:44px;overflow:hidden">“${esc(String(gen.text).slice(0, 180))}${String(gen.text).length > 180 ? "…" : ""}”</div>` : ""}`;
  const wb = new WaveBox(d.querySelector("[data-wave]"), gen.audio_url);
  wb.load();
  d.querySelector("[data-play]").onclick = (e) => {
    wb.toggle();
    e.target.textContent = wb.audio.paused ? "▶ Play" : "■ Stop";
  };
  d.querySelector("[data-dl]").onclick = () =>
    download(gen.audio_url, `insanevoice_${gen.voice_name || "gen"}.wav`);
  return d;
}

/* analyze a File -> report object (shared by DNA / Recorder / Library) */
async function analyzeFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await API.postForm("/api/analyze", fd);
  return res.dna;
}

async function saveVoice(file, name, consent, notes) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("name", name);
  fd.append("consent", consent ? "true" : "false");
  if (notes) fd.append("notes", notes);
  const res = await API.postForm("/api/voices", fd);
  await refreshVoices();
  return res.voice;
}

/* ============================================================
   Dashboard
   ============================================================ */

export async function dashboard(page, seq, fresh) {
  await refreshSystem();
  if (!fresh()) return;
  const s = state.system;
  const hist = await API.get("/api/history?limit=6").then((r) => r.history).catch(() => []);
  if (!fresh()) return;
  const voices = state.voices.length;
  const minutes = (hist.reduce((a, h) => a + (h.duration || 0), 0) / 60).toFixed(1);
  const hour = new Date().getHours();
  const greet = hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  page.innerHTML = pageShell(`
    ${head(`${greet}.`, "Your voices, ready to speak — everything runs on this machine.", "InsaneVoice Studio")}
    ${s && !s.models_present ? banners.modelsMissing : ""}
    ${s && s.engine?.status === "error" ? `<div class="banner err">✕ <div><b>Engine failed to load.</b><br><span class="small">${esc(String(s.engine.error).split("\n")[0])}</span></div></div>` : ""}

    <div class="grid c4">
      <div class="stat"><div class="n">${voices}</div><div class="l">Voices in library</div></div>
      <div class="stat"><div class="n" id="d-gen">…</div><div class="l">Generations total</div></div>
      <div class="stat"><div class="n">${minutes}<small> min</small></div><div class="l">Audio in recent history</div></div>
      <div class="stat">
        <div class="n" style="font-size:22px;padding-top:4px">${s?.engine?.status === "ready" ? "Ready" : s?.engine?.status === "loading" ? "Loading…" : s ? "Check setup" : "…"}</div>
        <div class="l">Cloning engine (CPU)</div>
      </div>
    </div>

    <div class="grid c2" style="margin-top:20px">
      <div class="panel">
        <h3 style="margin:0 0 4px">Create</h3>
        <p class="small muted" style="margin:0 0 14px">Everything starts with a voice.</p>
        <div class="stack">
          <button class="btn primary" id="q-studio">✎ &nbsp;Open Studio — speak with a saved voice</button>
          <button class="btn" id="q-record">● &nbsp;Record a voice sample</button>
          <button class="btn" id="q-upload">⬆ &nbsp;Import an audio file</button>
        </div>
      </div>
      <div class="panel flush">
        <div class="panel-head"><h3>Latest generations</h3>
          <button class="btn ghost sm" id="q-hist">View all →</button></div>
        <div id="d-recent"></div>
      </div>
    </div>
  `);

  API.get("/api/history?limit=200").then((r) => {
    const el = document.getElementById("d-gen");
    if (el) el.textContent = r.history.length;
  });

  const recent = document.getElementById("d-recent");
  if (!hist.length) {
    recent.innerHTML = `
      <div class="empty">
        <div class="e-ico">🎙</div>
        <h3>Nothing generated yet</h3>
        <p>Create your first voice, then type anything — it will speak in that voice.</p>
        <button class="btn accent" id="q-start">Start with Voice DNA</button>
      </div>`;
    recent.querySelector("#q-start").onclick = () => nav("dna");
  } else {
    recent.innerHTML = hist.slice(0, 6).map((h) => `
      <div class="list-row">
        <span class="idx">${h.preview ? "◈" : "▸"}</span>
        <div><div class="t">${esc(String(h.text).slice(0, 64))}${String(h.text).length > 64 ? "…" : ""}</div>
        <div class="s">${esc(h.voice_name)} · ${fmtDur(h.duration)} · ${fmtWhen(h.created_at)}</div></div>
        <div class="acts"><button class="btn sm" data-go="${h.audio_url}">▶</button></div>
      </div>`).join("");
    recent.querySelectorAll("[data-go]").forEach((b) =>
      b.onclick = () => window.open(b.dataset.go, "_blank"));
  }
  page.querySelector("#q-studio").onclick = () => nav("studio");
  page.querySelector("#q-record").onclick = () => nav("recorder");
  page.querySelector("#q-upload").onclick = () => nav("dna");
  page.querySelector("#q-hist").onclick = () => nav("history");
}

/* ============================================================
   Studio
   ============================================================ */

export async function studio(page, seq, fresh) {
  const voices = await needVoices();
  await refreshSystem();
  if (!fresh()) return;
  if (!voices.length) { emptyLibrary(page, "studio"); return; }

  page.innerHTML = pageShell(`
    ${head("Studio", "Type anything. Your voice speaks it.", "Create")}
    ${state.system && !state.system.models_present ? banners.modelsMissing : ""}
    <div class="grid balanced" id="st-grid">
      <div class="panel">
        <label class="field"><span>Voice</span>
          <select id="st-voice">${groupedVoiceOptions(voices)}</select>
        </label>
        <label class="field"><span>What should it say?</span>
          <textarea id="st-text" rows="7" placeholder="Write your script here — sentences are handled automatically."></textarea>
        </label>
        <div class="row wrap" style="margin:-6px 0 12px" id="st-chips">
          <span class="small muted">insert:</span>
          <button class="btn sm ghost" data-tag="[pause 0.5]">[pause]</button>
          <button class="btn sm ghost" data-tag="[sigh]">[sigh]</button>
          <button class="btn sm ghost" data-tag="[gasp]">[gasp]</button>
          <button class="btn sm ghost" data-tag="[breath]">[breath]</button>
          <button class="btn sm ghost" data-tag="[happy]" data-close="[/happy]">happy span</button>
          <button class="btn sm ghost" data-tag="[sad]" data-close="[/sad]">sad span</button>
          <button class="btn sm ghost" data-tag="[excited]" data-close="[/excited]">excited</button>
          <button class="btn sm ghost" data-tag="[whisper]" data-close="[/whisper]">whisper</button>
        </div>
        <label class="checkbox" style="margin-bottom:14px"><input type="checkbox" id="st-emotional">
          <span>Render emotion tags &amp; non-verbals <span class="muted">(adds a little render time)</span></span></label>
        <div class="small muted" style="margin:-4px 0 14px">
          CPU speed ≈ 3–4× the audio length. A 10s clip takes ~30–40s.
        </div>
        <div class="row wrap">
          <button class="btn accent lg" id="st-go">✦ Generate speech</button>
          <button class="btn" id="st-clear">Clear</button>
        </div>
        <div id="st-progress" style="margin-top:16px"></div>
      </div>

      <div class="stack">
        <div class="panel">
          <h3 style="margin:0 0 12px">Controls</h3>
          <label class="field"><span>Speed</span>
            <div class="range-row">
              <input type="range" id="st-speed" min="0.6" max="1.6" step="0.05" value="1">
              <output id="st-speed-o">1.00×</output>
            </div>
          </label>
          <label class="field"><span>Clone strength</span>
            <div class="range-row">
              <input type="range" id="st-tau" min="0.1" max="0.9" step="0.05" value="0.3">
              <output id="st-tau-o">0.30</output>
            </div>
          </label>
          <div class="small muted" style="margin-top:-6px">
            Higher strength = closer to the reference voice, but can add artifacts.
            0.3 is the balanced default.
          </div>
          <hr class="thin">
          <label class="field"><span>Language</span>
            <select id="st-lang">
              ${(state.system?.languages ? Object.entries(state.system.languages) : [["en", "English"]])
                .map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join("")}
            </select>
          </label>
          <label class="field" style="margin:0" id="st-accent-wrap"><span>Speaker (English)</span>
            <select id="st-accent">
              <option value="en-us">American (EN-US)</option>
              <option value="en-br">British (EN-BR)</option>
            </select>
          </label>
        </div>
        <div class="panel" id="st-result-wrap">
          <h3 style="margin:0 0 12px">Result</h3>
          <div class="empty" style="padding:26px 10px" id="st-empty">
            <div class="e-ico">🎧</div><p>Your generated audio will appear here.</p>
          </div>
          <div id="st-result"></div>
        </div>
      </div>
    </div>
  `);
  if (window.innerWidth < 900)
    page.querySelector("#st-grid").style.gridTemplateColumns = "1fr";

  const syncAccent = () => {
    page.querySelector("#st-accent-wrap").style.display =
      page.querySelector("#st-lang").value === "en" ? "" : "none";
  };
  page.querySelector("#st-lang").onchange = syncAccent;
  syncAccent();

  const txt = page.querySelector("#st-text");
  const speed = page.querySelector("#st-speed");
  const tau = page.querySelector("#st-tau");
  speed.oninput = () => page.querySelector("#st-speed-o").textContent = (+speed.value).toFixed(2) + "×";
  tau.oninput = () => page.querySelector("#st-tau-o").textContent = (+tau.value).toFixed(2);
  page.querySelector("#st-clear").onclick = () => { txt.value = ""; txt.focus(); };

  // emotion tag chips: insert at cursor, wrap when the chip has a closing tag
  page.querySelectorAll("#st-chips [data-tag]").forEach((chip) => {
    chip.onclick = () => {
      const open = chip.dataset.tag;
      const close = chip.dataset.close || "";
      const s = txt.selectionStart ?? txt.value.length;
      const e = txt.selectionEnd ?? s;
      const sel = txt.value.slice(s, e);
      const insert = sel ? `${open}${sel}${close}` : `${open}${close}`;
      txt.setRangeText(insert, s, e, "end");
      txt.focus();
      if (close && !sel) {
        const pos = s + open.length;
        txt.setSelectionRange(pos, pos);
      }
      if (!page.querySelector("#st-emotional").checked) {
        page.querySelector("#st-emotional").checked = true;
        toast("Emotional rendering on", "Tags only work with it enabled.", "warn", 2500);
      }
    };
  });

  page.querySelector("#st-go").onclick = async (e) => {
    const btn = e.currentTarget;
    const text = txt.value.trim();
    if (!text) return toast("Write something first", "The text box is empty.", "warn");
    if (!state.voices.length) return toast("No voice selected", "Create a voice in the Library first.", "warn");
    const progWrap = page.querySelector("#st-progress");
    progWrap.innerHTML = `
      <div class="progress indet"><i></i></div>
      <div class="progress-label"><span id="st-pl">Warming up the engine…</span><span>CPU</span></div>`;
    busy(btn, true);
    const t0 = Date.now();
    const tick = setInterval(() => {
      const el = page.querySelector("#st-pl");
      if (el) el.textContent = `Generating… ${Math.round((Date.now() - t0) / 1000)}s elapsed`;
    }, 500);
    try {
      const res = await API.post("/api/generate", {
        voice_id: page.querySelector("#st-voice").value,
        text,
        speed: +speed.value,
        tau: +tau.value,
        accent: page.querySelector("#st-accent").value,
        lang: page.querySelector("#st-lang").value,
        emotional: page.querySelector("#st-emotional").checked,
      });
      clearInterval(tick);
      progWrap.innerHTML = "";
      page.querySelector("#st-empty").style.display = "none";
      const rwrap = page.querySelector("#st-result");
      rwrap.innerHTML = "";
      rwrap.appendChild(audioCard(res.generation));
      toast("Speech generated", `${fmtDur(res.generation.duration)} of audio, made in ${fmtDur(res.generation.elapsed)}.`);
    } catch (err) {
      clearInterval(tick);
      progWrap.innerHTML = "";
      toast("Generation failed", err.message, "err", 7000);
    } finally {
      busy(btn, false);
    }
  };
}

/* ============================================================
   Voice DNA
   ============================================================ */

let dnaFile = null;   // keep the File for "save as voice"
let dnaReport = null;

export async function dna(page, seq, fresh) {
  page.innerHTML = pageShell(`
    ${head("Voice DNA", "Upload or record a sample — the analyser measures its pitch, timbre and texture, then rates the clone-ability.", "Create")}
    <div class="grid c2" style="gap:20px" id="dna-grid">
      <div class="stack">
        <div class="dropzone" id="dz">
          <div class="dz-ico">⬆</div>
          <h4>Drop an audio file here</h4>
          <p>or click to browse — wav, mp3, m4a, ogg, webm (max 30MB)</p>
          <input type="file" id="dz-file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm,.flac" hidden>
        </div>
        <div class="panel">
          <div class="spread">
            <div>
              <h3 style="margin:0">No file handy?</h3>
              <p class="small muted" style="margin:4px 0 0">Record 10–30s straight from your mic.</p>
            </div>
            <button class="btn primary" id="dna-rec">● Record</button>
          </div>
        </div>
        <div id="dna-status"></div>
      </div>
      <div class="panel" id="dna-report"><div class="empty" style="padding:40px 10px">
        <div class="e-ico">◉</div><h3>No analysis yet</h3>
        <p>10–30 seconds of clean speech gives the best fingerprint.</p>
      </div></div>
    </div>
  `);
  if (window.innerWidth < 900)
    page.querySelector("#dna-grid").style.gridTemplateColumns = "1fr";

  const dz = page.querySelector("#dz");
  const fi = page.querySelector("#dz-file");
  dz.onclick = () => fi.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = (e) => {
    e.preventDefault(); dz.classList.remove("over");
    if (e.dataTransfer.files[0]) handleDnaFile(e.dataTransfer.files[0], page);
  };
  fi.onchange = () => fi.files[0] && handleDnaFile(fi.files[0], page);
  page.querySelector("#dna-rec").onclick = () => nav("recorder");

  // restore previous report (e.g. came back from recorder)
  if (dnaReport && dnaFile) renderDnaReport(page, dnaReport, dnaFile);
}

async function handleDnaFile(file, page) {
  const status = page.querySelector("#dna-status");
  status.innerHTML = `
    <div class="panel">
      <div class="row"><b class="small">${esc(file.name)}</b>
        <span class="pill">${(file.size / 1048576).toFixed(1)} MB</span></div>
      <div style="margin-top:12px" class="progress indet"><i></i></div>
      <div class="progress-label"><span>Analysing waveform…</span><span>DSP</span></div>
    </div>`;
  page.querySelector("#dna-report").innerHTML = `<div class="stack">${sk.line()}${sk.block(240)}</div>`;
  try {
    dnaReport = await analyzeFile(file);
    dnaFile = file;
    renderDnaReport(page, dnaReport, dnaFile);
    toast("Voice analysed", dnaReport.archetype);
  } catch (err) {
    status.innerHTML = "";
    page.querySelector("#dna-report").innerHTML = `
      <div class="banner err" style="margin:0">✕ <div><b>Analysis failed.</b><br>${esc(err.message)}</div></div>`;
    toast("Analysis failed", err.message, "err");
  }
}

function renderDnaReport(page, r, file) {
  const rep = page.querySelector("#dna-report");
  const L = { pitch: "Pitch", depth: "Depth", warmth: "Warmth", brightness: "Brightness",
              roughness: "Grit", breathiness: "Air", clarity: "Clarity", energy: "Energy" };
  rep.innerHTML = `
    <div class="spread" style="margin-bottom:14px">
      <h3 style="margin:0">Fingerprint</h3>
      <span class="pill ok">${fmtDur(r.duration)} sample</span>
    </div>
    <div class="archetype" style="margin-bottom:16px">
      <span style="font-size:18px">◉</span>
      <span class="a-name">${esc(r.archetype)}</span>
    </div>
    <div data-radar style="display:grid;place-items:center"></div>
    <hr class="thin">
    <table class="stat-table">
      <tr><td>Median pitch</td><td>${r.f0_median} Hz</td></tr>
      <tr><td>Pitch range (IQR)</td><td>${r.f0_range} Hz</td></tr>
      <tr><td>Brightness (centroid)</td><td>${r.spectral_centroid} Hz</td></tr>
      <tr><td>First formant</td><td>${r.formant_f1} Hz</td></tr>
      <tr><td>Steadiness (jitter)</td><td>${(r.jitter * 100).toFixed(2)}%</td></tr>
      <tr><td>Speech density</td><td>${Math.round(r.speech_ratio * 100)}%</td></tr>
    </table>
    ${r.warnings.map((w) => `<div class="banner warn" style="margin:14px 0 0">! <div>${esc(w)}</div></div>`).join("")}
    <div style="margin-top:18px">
      <button class="btn accent" id="dna-save">＋ Save as a cloneable voice</button>
    </div>`;
  radarChart(rep.querySelector("[data-radar]"), r.radar, L, 290);
  rep.querySelector("#dna-save").onclick = () => saveVoiceModal(file, r);
  const status = page.querySelector("#dna-status");
  if (status) status.innerHTML = `
    <div class="panel">
      <div class="row"><b class="small">${esc(file.name)}</b>
        <span class="pill">${(file.size / 1048576).toFixed(1)} MB</span>
        <span class="pill ok">analysed</span></div>
    </div>`;
}

export function saveVoiceModal(file, report) {
  const body = document.createElement("div");
  body.innerHTML = `
    <label class="field"><span>Voice name</span>
      <input type="text" id="sv-name" maxlength="60" placeholder="e.g. My Narration Voice">
    </label>
    ${report ? `<div class="small muted" style="margin:-6px 0 14px">Fingerprint: ${esc(report.archetype)} · ${report.f0_median} Hz · ${fmtDur(report.duration)}</div>` : ""}
    <label class="field"><span>Notes (optional)</span>
      <input type="text" id="sv-notes" maxlength="300" placeholder="Where will you use this voice?">
    </label>
    <label class="checkbox"><input type="checkbox" id="sv-consent">
      <span>I confirm this recording is <b>my own voice</b>, or I have the
      owner's explicit permission to clone it. I will not use it to
      impersonate anyone or mislead listeners.</span>
    </label>
    <div id="sv-err"></div>`;
  const foot = document.createElement("div");
  foot.innerHTML = `
    <button class="btn ghost" data-a="cancel">Cancel</button>
    <button class="btn accent" data-a="save">＋ Create voice</button>`;
  modal({
    title: "Save voice to library",
    body, footer: foot,
    onMount: (veil, close) => {
      veil.querySelector('[data-a="cancel"]').onclick = close;
      veil.querySelector('[data-a="save"]').onclick = async (e) => {
        const name = veil.querySelector("#sv-name").value.trim();
        const consent = veil.querySelector("#sv-consent").checked;
        const errEl = veil.querySelector("#sv-err");
        if (!name) { errEl.innerHTML = `<div class="banner err" style="margin-top:14px">✕ <div>Give the voice a name.</div></div>`; return; }
        if (!consent) { errEl.innerHTML = `<div class="banner err" style="margin-top:14px">✕ <div>Consent is required — cloning a voice without permission is not allowed.</div></div>`; return; }
        const btn = e.currentTarget;
        busy(btn, true);
        try {
          const v = await saveVoice(file, name, true, veil.querySelector("#sv-notes").value.trim());
          close();
          toast("Voice created", `“${v.name}” is ready in the Library.`);
          nav("library");
        } catch (err) {
          busy(btn, false);
          errEl.innerHTML = `<div class="banner err" style="margin-top:14px">✕ <div>${esc(err.message)}</div></div>`;
        }
      };
      setTimeout(() => veil.querySelector("#sv-name").focus(), 60);
    },
  });
}

/* ============================================================
   Recorder
   ============================================================ */

let recState = null;

export async function recorder(page, seq, fresh) {
  page.innerHTML = pageShell(`
    ${head("Recorder", "Record your reference sample. Read anything naturally for 10–30 seconds — steady distance, quiet room.", "Create")}
    <div class="panel" style="max-width:640px;margin:0 auto">
      <div class="rec-stage">
        <button class="rec-btn" id="rec-btn" title="Record / stop" aria-label="Record or stop">●</button>
        <div class="rec-timer" id="rec-timer">00:00</div>
        <canvas class="rec-live" id="rec-live"></canvas>
        <div class="small muted" id="rec-hint">Microphone permission needed on first use.</div>
      </div>
      <hr class="thin">
      <div id="rec-takes" class="stack"></div>
    </div>
  `);

  const btn = page.querySelector("#rec-btn");
  const timerEl = page.querySelector("#rec-timer");
  const canvas = page.querySelector("#rec-live");
  const hint = page.querySelector("#rec-hint");
  const takes = page.querySelector("#rec-takes");

  if (recState?.blobUrl) renderTake(recState, takes);

  let stream = null, media = null, chunks = [], raf = null, t0 = 0, timerIv = null, analyser = null;

  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      hint.textContent = "Microphone blocked — allow access in the browser bar, then try again.";
      return toast("Microphone unavailable", "Check browser permissions.", "err");
    }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    drawLive();

    chunks = [];
    media = new MediaRecorder(stream);
    media.ondataavailable = (e) => chunks.push(e.data);
    media.onstop = onStop;
    media.start();
    recState = { recording: true };
    btn.classList.add("recording");
    btn.textContent = "■";
    t0 = Date.now();
    timerIv = setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000);
      timerEl.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    }, 250);
    hint.textContent = "Recording… read a paragraph naturally.";
  }

  function drawLive() {
    const g = canvas.getContext("2d");
    const buf = new Uint8Array(analyser.frequencyBinCount);
    const loop = () => {
      if (!analyser) return;
      analyser.getByteTimeDomainData(buf);
      const dpr = devicePixelRatio || 1;
      canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr;
      g.scale(dpr, dpr);
      g.clearRect(0, 0, canvas.width, canvas.height);
      g.strokeStyle = "#C9432B"; g.lineWidth = 1.4;
      g.beginPath();
      const W = canvas.clientWidth, H = canvas.clientHeight;
      for (let i = 0; i < W; i++) {
        const v = buf[Math.floor(i / W * buf.length)] / 128 - 1;
        const y = H / 2 + v * H * 0.42;
        i ? g.lineTo(i, y) : g.moveTo(i, y);
      }
      g.stroke();
      raf = requestAnimationFrame(loop);
    };
    loop();
  }

  async function onStop() {
    clearInterval(timerIv);
    cancelAnimationFrame(raf);
    analyser = null;
    stream?.getTracks().forEach((t) => t.stop());
    btn.classList.remove("recording");
    btn.textContent = "●";
    const blob = new Blob(chunks, { type: media.mimeType || "audio/webm" });
    const secs = (Date.now() - t0) / 1000;
    const file = new File([blob], `recording_${Date.now()}.webm`, { type: blob.type });
    recState = { blobUrl: URL.createObjectURL(blob), file, secs };
    hint.textContent = `Captured ${Math.round(secs)}s.`;
    renderTake(recState, takes);
  }

  btn.onclick = () => {
    if (media?.state === "recording") media.stop();
    else start();
  };
}

function renderTake({ blobUrl, file, secs }, takes) {
  takes.innerHTML = `
    <div class="spread">
      <div class="row"><span class="pill ok">${Math.round(secs)}s captured</span>
        <span class="small muted">listen back, then analyse or save.</span></div>
      <div class="row">
        <button class="btn sm" id="tk-an">◉ Analyse DNA</button>
        <button class="btn sm accent" id="tk-save">＋ Save as voice</button>
      </div>
    </div>
    <div id="tk-wave"></div>
    <div id="tk-report"></div>`;
  const wb = new WaveBox(takes.querySelector("#tk-wave"), blobUrl, { height: 90 });
  wb.load();
  takes.querySelector("#tk-an").onclick = () => { dnaFile = null; nav("dna"); };
  takes.querySelector("#tk-save").onclick = () => saveVoiceModal(file, null);
}

/* ============================================================
   Library
   ============================================================ */

export async function library(page, seq, fresh) {
  const voices = await needVoices();
  if (!fresh()) return;
  page.innerHTML = pageShell(`
    ${pageHead("Voice Library",
      "Every saved voice keeps its fingerprint, its reference audio and its own speaker embedding.",
      "Voices",
      `<span class="pill" id="lib-count"></span>
       <button class="btn accent" id="lib-add">＋ New voice</button>`)}
    <div class="row wrap" style="margin-bottom:16px">
      <input type="search" id="lib-q" placeholder="Search voices…" style="max-width:280px">
      <select id="lib-lang" style="max-width:220px">
        <option value="">All languages</option>
        ${[...new Set(voices.map((v) => v.language || "other"))]
          .sort((a, b) => langLabel(a).localeCompare(langLabel(b)))
          .map((l) => `<option value="${esc(l)}">${esc(langLabel(l))}</option>`).join("")}
      </select>
      <span class="grow"></span>
    </div>
    <div id="lib-grid" class="grid c3"></div>
  `);
  page.querySelector("#lib-add").onclick = () => addVoiceFlow();
  const grid = page.querySelector("#lib-grid");

  const draw = () => {
    const q = (page.querySelector("#lib-q").value || "").toLowerCase();
    const lang = page.querySelector("#lib-lang").value;
    const shown = voices.filter((v) =>
      (!lang || (v.language || "other") === lang) &&
      (!q || (v.name || "").toLowerCase().includes(q) ||
             (v.dna?.archetype || "").toLowerCase().includes(q)));
    page.querySelector("#lib-count").textContent = `${shown.length} of ${voices.length} voices`;
    grid.innerHTML = "";
    if (!voices.length) {
      grid.innerHTML = `
        <div class="empty" style="grid-column:1/-1">
          <div class="e-ico">☰</div>
          <h3>No voices yet</h3>
          <p>Record or import 10–30 seconds of speech. InsaneVoice turns it into a cloneable voice.</p>
          <button class="btn accent" id="lib-first">Create your first voice</button>
        </div>`;
      grid.querySelector("#lib-first").onclick = () => addVoiceFlow();
      return;
    }
    if (!shown.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <div class="e-ico">🔍</div><h3>No match</h3><p>Try a different search or language.</p></div>`;
      return;
    }
    for (const v of shown) {
      const card = document.createElement("div");
      card.className = "voice-card";
      const r = v.dna || { radar: {} };
      const hot = (k) => Math.round(r.radar?.[k] ?? 0);
      card.innerHTML = `
        <div class="v-head">
          <div class="v-ava">${esc((v.name || "?")[0].toUpperCase())}</div>
          <div class="grow">
            <h4>${esc(v.name)} ${v.verified ? `<span class="pill ok" title="Ownership verified by voice-match">✓ verified</span>` : ""}</h4>
            <div class="v-sub">${esc(langLabel(v.language || "other"))} · ${esc(r.archetype || "unanalysed")} · ${fmtDur(v.duration)}</div>
          </div>
        </div>
        <div class="dna-bars">
          ${[["pitch", hot("pitch")], ["warmth", hot("warmth")], ["brightness", hot("brightness")], ["grit", hot("roughness")]]
          .map(([k, val]) => `
            <div class="dna-bar ${k === "pitch" ? "hot" : ""}">
              <span>${k}</span>
              <span class="bar"><i style="width:${val}%"></i></span>
            </div>`).join("")}
        </div>
        <div class="row">
          <button class="btn sm accent" data-act="preview" title="Generate a greeting in this voice">✦ Preview</button>
          <button class="btn sm" data-act="sample" title="Listen to the reference sample">▶ Sample</button>
          ${v.verified ? "" : `<button class="btn sm" data-act="verify" title="Prove ownership: read 5 random words, we compare voice metrics">✓ Verify</button>`}
          <span class="grow"></span>
          ${iconBtn("trash", "Delete this voice", "btn sm icon")}
        </div>
        <div data-out></div>`;
      card.querySelector('[data-act="preview"]').onclick = async (e) => {
        const out = card.querySelector("[data-out]");
        out.innerHTML = `<div class="progress indet" style="margin-top:10px"><i></i></div>
          <div class="progress-label"><span>Generating greeting…</span><span>CPU</span></div>`;
        busy(e.currentTarget, true);
        try {
          const res = await API.post(`/api/voices/${v.id}/preview`, {});
          out.innerHTML = "";
          out.appendChild(audioCard(res.generation));
        } catch (err) {
          out.innerHTML = "";
          toast("Preview failed", err.message, "err");
        } finally { busy(e.currentTarget, false); }
      };
      card.querySelector('[data-act="sample"]').onclick = (e) => {
        const out = card.querySelector("[data-out]");
        out.innerHTML = "";
        const wb = new WaveBox(out, v.sample_url, { height: 56 });
        wb.load();
        e.currentTarget.textContent = "■ Stop";
        wb.onPlayState = (playing) => {
          e.currentTarget.textContent = playing ? "■ Stop" : "▶ Sample";
        };
        wb.toggle();
      };
      const verifyBtn = card.querySelector('[data-act="verify"]');
      if (verifyBtn) verifyBtn.onclick = () => verifyModal(v);

      card.querySelector(".btn.icon").onclick = async () => {
        if (await confirmModal("Delete voice?", `“${v.name}” and its fingerprint will be removed from this machine. Generated audio stays in History.`, "Delete")) {
          try {
            await API.del(`/api/voices/${v.id}`);
            toast("Voice deleted", v.name);
            render();
          } catch (err) { toast("Delete failed", err.message, "err"); }
        }
      };
      grid.appendChild(card);
    }
  };
  page.querySelector("#lib-q").oninput = draw;
  page.querySelector("#lib-lang").onchange = draw;
  draw();
}

/* ============================================================
   Batch Studio
   ============================================================ */

export async function batch(page, seq, fresh) {
  const voices = await needVoices();
  await refreshSystem();
  if (!fresh()) return;
  if (!voices.length) { emptyLibrary(page, "batch"); return; }

  page.innerHTML = pageShell(`
    ${head("Batch Studio", "Paste one line per clip — intro, hook, body, outro — and render the whole queue in order.", "Voices")}
    ${state.system && !state.system.models_present ? banners.modelsMissing : ""}
    <div class="grid c2" style="gap:20px" id="bt-grid">
      <div class="panel">
        <label class="field"><span>Voice</span>
          <select id="bt-voice">${groupedVoiceOptions(voices)}</select>
        </label>
        <label class="field"><span>Lines — one clip per line</span>
          <textarea id="bt-text" rows="10"></textarea>
        </label>
        <div class="row wrap">
          <button class="btn accent" id="bt-go">✦ Render queue</button>
          <button class="btn" id="bt-clear">Clear</button>
          <span class="small muted" id="bt-count"></span>
        </div>
        <div id="bt-progress" style="margin-top:16px"></div>
      </div>
      <div class="panel flush">
        <div class="panel-head"><h3>Queue output</h3><span class="small muted" id="bt-stat"></span></div>
        <div id="bt-out"></div>
      </div>
    </div>
  `);
  if (window.innerWidth < 900) page.querySelector("#bt-grid").style.gridTemplateColumns = "1fr";
  const ta = page.querySelector("#bt-text");
  ta.placeholder = "Welcome back to the channel.\nToday we are talking about…\nLike and subscribe — see you next week.";
  const countEl = page.querySelector("#bt-count");
  const recount = () => {
    const n = ta.value.split("\n").map((s) => s.trim()).filter(Boolean).length;
    countEl.textContent = n ? `${n} clip${n > 1 ? "s" : ""}` : "";
  };
  ta.oninput = recount; recount();
  page.querySelector("#bt-clear").onclick = () => { ta.value = ""; recount(); };

  page.querySelector("#bt-go").onclick = async (e) => {
    const lines = ta.value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return toast("Nothing to render", "Add at least one line.", "warn");
    const btn = e.currentTarget;
    busy(btn, true);
    const out = page.querySelector("#bt-out");
    const prog = page.querySelector("#bt-progress");
    const stat = page.querySelector("#bt-stat");
    out.innerHTML = lines.map((l, i) => `
      <div class="list-row" id="bt-row-${i}">
        <span class="idx">${i + 1}</span>
        <div><div class="t">${esc(l.slice(0, 70))}${l.length > 70 ? "…" : ""}</div>
        <div class="s" id="bt-s-${i}">queued</div></div>
        <div class="acts" id="bt-a-${i}"></div>
      </div>`).join("");
    let done = 0;
    const setProg = (label) => {
      prog.innerHTML = `
        <div class="progress"><i style="width:${Math.round(done / lines.length * 100)}%"></i></div>
        <div class="progress-label"><span>${label}</span><span>${done}/${lines.length}</span></div>`;
    };
    setProg("Rendering…");
    for (let i = 0; i < lines.length; i++) {
      const s = page.querySelector(`#bt-s-${i}`);
      s.textContent = "generating…";
      s.style.color = "var(--amber)";
      try {
        const res = await API.post("/api/generate", {
          voice_id: page.querySelector("#bt-voice").value,
          text: lines[i], speed: 1.0, tau: 0.3, accent: "en-us",
        });
        done++;
        s.textContent = `${fmtDur(res.generation.duration)} · in ${fmtDur(res.generation.elapsed)}`;
        s.style.color = "var(--green)";
        const acts = page.querySelector(`#bt-a-${i}`);
        acts.innerHTML = `
          <button class="btn sm" data-u="${res.generation.audio_url}">▶</button>
          <button class="btn sm" data-d="${res.generation.audio_url}" data-n="clip_${String(i + 1).padStart(2, "0")}.wav">⬇</button>`;
        acts.querySelector("[data-u]").onclick = (ev) => window.open(ev.currentTarget.dataset.u, "_blank");
        acts.querySelector("[data-d]").onclick = (ev) => download(ev.currentTarget.dataset.d, ev.currentTarget.dataset.n);
      } catch (err) {
        done++;
        s.textContent = "failed — " + err.message.slice(0, 60);
        s.style.color = "var(--verm)";
      }
      setProg("Rendering…");
    }
    stat.textContent = `${done} finished`;
    busy(btn, false);
    toast("Queue finished", `${done}/${lines.length} clips rendered.`);
  };
}

/* ============================================================
   History
   ============================================================ */

export async function history(page, seq, fresh) {
  const items = await API.get("/api/history?limit=200").then((r) => r.history).catch(() => []);
  if (!fresh()) return;
  page.innerHTML = pageShell(`
    ${pageHead("History", "Every generation stays on this machine until you delete it.", "System")}
    <div class="panel flush" id="h-list"></div>
  `);
  const list = page.querySelector("#h-list");
  if (!items.length) {
    list.innerHTML = `
      <div class="empty"><div class="e-ico">↺</div><h3>History is empty</h3>
      <p>Generate something in the Studio and it will show up here.</p>
      <button class="btn accent" id="h-go">Open Studio</button></div>`;
    list.querySelector("#h-go").onclick = () => nav("studio");
    return;
  }
  list.innerHTML = items.map((h, i) => `
    <div class="list-row">
      <span class="idx">${h.preview ? "◈" : String(items.length - i).padStart(2, "0")}</span>
      <div>
        <div class="t">${esc(String(h.text).slice(0, 90))}${String(h.text).length > 90 ? "…" : ""}</div>
        <div class="s">${esc(h.voice_name)} · ${fmtDur(h.duration)} · ${fmtWhen(h.created_at)}${h.preview ? " · preview" : ""}</div>
      </div>
      <div class="acts">
        <button class="btn sm" data-act="play" data-u="${h.audio_url}">▶</button>
        <button class="btn sm" data-act="dl" data-u="${h.audio_url}" data-n="${esc(h.voice_name)}_${h.id}.wav">⬇</button>
        ${iconBtn("trash", "Delete this entry", "btn sm icon")}
      </div>
    </div>`).join("");
  list.querySelectorAll('[data-act="play"]').forEach((b) =>
    b.onclick = () => window.open(b.dataset.u, "_blank"));
  list.querySelectorAll('[data-act="dl"]').forEach((b) =>
    b.onclick = () => download(b.dataset.u, b.dataset.n));
  list.querySelectorAll('[data-act="del"]').forEach((b) =>
    b.onclick = async () => {
      try {
        await API.del(`/api/history/${b.dataset.id}`);
        toast("Removed", "Deleted from history and disk.");
        render();
      } catch (err) { toast("Delete failed", err.message, "err"); }
    });
}

/* ============================================================
   Settings
   ============================================================ */

export async function settings(page, seq, fresh) {
  const s = await refreshSystem();
  if (!fresh()) return;
  const e = s?.engine || {};
  const rows = [
    ["App version", `${s?.version || "?"} (v1.0)`],
    ["Python", s?.python || "—"],
    ["Cloning engine", e.status || "unknown"],
    ["Engine detail", e.detail || "—"],
    ["Models downloaded", s?.models_present ? "yes" : "NO — run scripts/download_models.py"],
    ["ffmpeg", s?.ffmpeg ? "found" : "missing — audio import will fail"],
    ["Voices stored", String(s?.voices ?? "—")],
    ["Data folder", s?.data_dir || "—"],
  ];
  page.innerHTML = pageShell(`
    ${pageHead("Settings", "InsaneVoice is fully local — no account, no cloud, no API keys.", "System")}
    <div class="panel">
      <h3 style="margin:0 0 10px">System</h3>
      <table class="stat-table">
        ${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td style="font-weight:400">${esc(v)}</td></tr>`).join("")}
      </table>
    </div>
    <div class="panel" style="margin-top:18px">
      <h3 style="margin:0 0 8px">Voice cloning consent</h3>
      <p class="small" style="margin:0;color:var(--ink-2)">
        Every voice in your library stores a consent record made at creation time.
        Clone only voices you own or have explicit written permission to use.
        Generated audio carries an inaudible watermark. Impersonating real people
        without consent is illegal in many places — don't.
      </p>
    </div>
    <div class="panel" style="margin-top:18px">
      <h3 style="margin:0 0 8px">Where things live</h3>
      <p class="small" style="margin:0;color:var(--ink-2)">
        Models, voice embeddings and generated audio all stay inside the InsaneVoice
        data folder on this machine. Deleting a voice removes its embedding and
        reference sample; history items remove their audio too.
      </p>
    </div>
  `);
}

/* ============================================================
   Help
   ============================================================ */

export async function help(page, seq, fresh) {
  page.innerHTML = pageShell(`
    ${pageHead("How InsaneVoice works", "Three moves from your real voice to a synthetic one — all offline, all free.", "System")}
    <div class="grid c2" style="gap:20px">
      <div class="panel">
        <div class="steps">
          <div class="step"><span class="no"></span>
            <div><h4>Feed it a sample</h4><p>10–30 seconds of you reading naturally. Record in-app or import a file.</p></div>
          </div>
          <div class="step"><span class="no"></span>
            <div><h4>Read the fingerprint</h4><p>Voice DNA measures pitch, warmth, brightness and grit — you'll see exactly what makes the voice yours.</p></div>
          </div>
          <div class="step"><span class="no"></span>
            <div><h4>Generate</h4><p>Type any script. The base speaker says it, then the tone converter paints it with your voice's colour.</p></div>
          </div>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3 style="margin:0 0 8px">Better clones</h3>
          <table class="stat-table">
            <tr><td>Length</td><td>10–30s</td></tr>
            <tr><td>Room</td><td>quiet, no echo</td></tr>
            <tr><td>Mic distance</td><td>one fist, steady</td></tr>
            <tr><td>Delivery</td><td>match your target tone</td></tr>
            <tr><td>Silence</td><td>trim dead air</td></tr>
          </table>
        </div>
        <div class="panel">
          <h3 style="margin:0 0 8px">Expectations on CPU</h3>
          <p class="small" style="margin:0;color:var(--ink-2)">
            Generation runs at roughly 3–4× real time on a laptop CPU — a 10-second
            clip takes about 30–40 seconds. It's free and private; that's the trade.
          </p>
        </div>
      </div>
    </div>
    <div class="panel" style="margin-top:20px">
      <h3 style="margin:0 0 10px">Troubleshooting</h3>
      <table class="stat-table">
        <tr><td>“Models are not downloaded”</td><td style="font-weight:400">Run <span class="kbd">python scripts/download_models.py</span></td></tr>
        <tr><td>Import fails on m4a/webm</td><td style="font-weight:400">Install ffmpeg and restart the server</td></tr>
        <tr><td>First generation is slow</td><td style="font-weight:400">The engine warms up once — later runs are faster</td></tr>
        <tr><td>Clone sounds distant</td><td style="font-weight:400">Raise clone strength, use a longer sample</td></tr>
        <tr><td>Clone sounds rough</td><td style="font-weight:400">Lower clone strength toward 0.2, re-record cleaner</td></tr>
      </table>
    </div>
  `);
}

/* ============================================================
   shared empty state
   ============================================================ */

function emptyLibrary(page, from) {
  page.innerHTML = pageShell(`
    ${head(from === "studio" ? "Studio" : "Batch Studio", "", "Create")}
    <div class="empty">
      <div class="e-ico">🎙</div>
      <h3>You need a voice first</h3>
      <p>Record or import a 10–30 second sample — InsaneVoice turns it into a cloneable voice in seconds.</p>
      <div class="row" style="justify-content:center">
        <button class="btn accent" id="e-rec">● Record now</button>
        <button class="btn" id="e-imp">⬆ Import a file</button>
      </div>
    </div>`);
  page.querySelector("#e-rec").onclick = () => nav("recorder");
  page.querySelector("#e-imp").onclick = () => addVoiceFlow();
}
