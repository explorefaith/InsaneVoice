/* InsaneVoice — page renderers (vanilla JS, hash-routed) */

import { API, state, refreshSystem, refreshVoices, nav, render } from "./app.js";
import {
  toast, modal, confirmModal, sk, busy, WaveBox, radarChart, audioCtx,
  esc, fmtDur, fmtWhen, download, pageHead, iconBtn, langLabel, groupedVoiceOptions,
} from "./components.js";
import { icon } from "./icons.js";
import { apiBase, setApiBase } from "./net.js";
import { inlinePlay } from "./components.js";

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
        <button class="btn sm accent" data-play>${icon("play", 15)} Play</button>
        <button class="btn sm" data-dl>${icon("download", 15)} Download</button>
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
    e.target.innerHTML = wb.audio.paused ? `${icon("play", 15)} Play` : `${icon("stop", 15)} Stop`;
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

/* 3D waveform orb — the hero visual. A ring of signal bars spinning in
   perspective, transparent background, amber phosphor trace. */
function startOrb(canvas) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const g = canvas.getContext("2d");
  let raf, t = Math.random() * 1000;
  const N = 64;
  const fit = () => {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = w * dpr; canvas.height = h * dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  const draw = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    g.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2;
    const R = Math.min(w, h) * 0.31;
    const tilt = 0.58;
    const rot = t * 0.0055;
    const pts = [];
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2;
      const amp = 0.5 + 0.5 * Math.sin(t * 0.017 + i * 0.9) * Math.sin(t * 0.0043 + i * 0.37);
      const x = Math.cos(a), y = Math.sin(a);
      const rx = x * Math.cos(rot) - y * Math.sin(rot);
      const rz = x * Math.sin(rot) + y * Math.cos(rot);
      const depth = (rz + 1) / 2;
      const px = cx + rx * R;
      const py = cy + y * R * tilt;
      const barH = h * 0.05 + amp * h * 0.15 * (0.45 + depth * 0.55);
      pts.push({ px, py, barH, depth });
    }
    pts.sort((a, b) => a.depth - b.depth);
    for (const p of pts) {
      g.fillStyle = `rgba(232, 130, 12, ${(0.18 + p.depth * 0.82).toFixed(3)})`;
      if (p.depth > 0.78) { g.shadowColor = "rgba(232,130,12,.4)"; g.shadowBlur = 9; }
      const bw = 3;
      g.beginPath();
      g.roundRect(p.px - bw / 2, p.py - p.barH / 2, bw, p.barH, bw / 2);
      g.fill();
      g.shadowBlur = 0;
    }
    t += 16;
  };
  const loop = () => {
    if (!canvas.isConnected) return;   // route changed — stop silently
    draw();
    raf = requestAnimationFrame(loop);
  };
  fit();
  canvas._orbResize = fit;
  window.addEventListener("resize", canvas._orbResize);
  if (reduce) draw(); else loop();
  canvas._orbStop = () => { cancelAnimationFrame(raf); window.removeEventListener("resize", canvas._orbResize); };
}

/* ============================================================
   Landing — "The Living Wave"
   ============================================================ */

/* A canvas wave that feels alive: ambient speech-like motion, follows the
   cursor, pulses on click, can dance to the microphone, and morphs its
   "accent" per language. */
class LandingWave {
  constructor(canvas) {
    this.c = canvas;
    this.g = canvas.getContext("2d");
    this.N = 120;
    this.t = Math.random() * 500;
    this.raf = 0;
    this.mouseX = -1;
    this.mic = null;
    this.micData = null;
    this.cur = { freq: 1, amp: 1, speed: 1 };
    this.tgt = { freq: 1, amp: 1, speed: 1 };
    this.ripples = [];
    this.running = false;
    this._onMove = (e) => {
      const r = this.c.getBoundingClientRect();
      this.mouseX = e.clientX - r.left;
    };
    this._onLeave = () => { this.mouseX = -1; };
    this._onClick = (e) => {
      const r = this.c.getBoundingClientRect();
      this.ripples.push({ x: e.clientX - r.left, age: 0 });
    };
    canvas.addEventListener("pointermove", this._onMove);
    canvas.addEventListener("pointerleave", this._onLeave);
    canvas.addEventListener("click", this._onClick);
    this._fit = () => this.fit();
    window.addEventListener("resize", this._fit);
    this.fit();
  }

  fit() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.c.clientWidth, h = this.c.clientHeight;
    if (!w || !h) return;
    this.c.width = w * dpr;
    this.c.height = h * dpr;
    this.g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      this.draw();
      this.raf = requestAnimationFrame(loop);
    };
    loop();
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this._fit);
  }

  setMic(node) {
    this.mic = node;
    this.micData = node ? new Uint8Array(node.frequencyBinCount) : null;
  }

  morph(params) { Object.assign(this.tgt, params); }

  draw() {
    const W = this.c.clientWidth, H = this.c.clientHeight;
    if (!W || !H) return;
    for (const k of ["freq", "amp", "speed"]) {
      this.cur[k] += (this.tgt[k] - this.cur[k]) * 0.055;
    }
    this.t += this.cur.speed;
    const g = this.g;
    g.clearRect(0, 0, W, H);
    const mid = H / 2;
    const bw = W / this.N;
    if (this.mic) this.mic.getByteFrequencyData(this.micData);
    this.ripples = this.ripples.filter((r) => r.age < 80);
    for (const r of this.ripples) r.age += 1;
    for (let i = 0; i < this.N; i++) {
      const x = i * bw + bw / 2;
      // ambient: layered sines that drift like speech
      let e = (0.42 * Math.sin(i * 0.55 * this.cur.freq + this.t * 0.014)
             + 0.3 * Math.sin(i * 0.13 + this.t * 0.031)
             + 0.28 * Math.sin(i * 1.71 * this.cur.freq + this.t * 0.007)) * 0.5 + 0.5;
      e = Math.max(0.04, e * this.cur.amp);
      if (this.mic) {
        const bin = Math.floor(Math.pow(i / this.N, 1.35) * (this.micData.length - 1));
        const mv = (this.micData[bin] / 255);
        e = Math.max(e * 0.16, mv * 0.92 * this.cur.amp);
      }
      // cursor attraction
      if (this.mouseX >= 0) {
        const d = (x - this.mouseX) / (W / 14);
        e += Math.exp(-d * d) * 0.6;
      }
      // click pulses
      for (const r of this.ripples) {
        const radius = r.age * 7;
        const d = (Math.abs(x - r.x) - radius) / 30;
        e += Math.exp(-d * d) * Math.max(0, 1 - r.age / 80) * 0.85;
      }
      e = Math.min(1, e);
      const barH = 4 + e * H * 0.44;
      const hot = e > 0.62;
      g.fillStyle = hot ? "#E8820C" : "rgba(23, 26, 32, .82)";
      if (hot) { g.shadowColor = "rgba(232,130,12,.45)"; g.shadowBlur = 8; }
      g.beginPath();
      g.roundRect(x - bw * 0.28, mid - barH / 2, bw * 0.56, barH, bw * 0.28);
      g.fill();
      g.shadowBlur = 0;
    }
  }
}

const LP_LANGS = [
  ["English", { freq: 1, amp: 1, speed: 1 }, "melo EN · 2 speakers · offline"],
  ["বাংলা", { freq: 1.6, amp: 1.18, speed: 0.8 }, "facebook/mms-tts-ben · 36M params"],
  ["हिन्दी", { freq: 1.35, amp: 1.05, speed: 1.15 }, "facebook/mms-tts-hin"],
  ["中文", { freq: 2.1, amp: 0.8, speed: 1.35 }, "melo ZH · offline"],
  ["العربية", { freq: 1.25, amp: 0.95, speed: 0.9 }, "facebook/mms-tts-ara"],
  ["Español", { freq: 0.85, amp: 1.1, speed: 1.2 }, "melo ES · offline"],
  ["Deutsch", { freq: 1.1, amp: 0.9, speed: 0.85 }, "facebook/mms-tts-deu"],
  ["日本語", { freq: 1.8, amp: 0.85, speed: 1.3 }, "melo JP · offline"],
];

const LP_TOOLS = [
  ["studio", "Studio", "Type anything — it speaks in any saved voice."],
  ["dna", "Voice DNA", "Pitch, warmth, brightness, grit — your voice, measured."],
  ["changer", "Voice Changer", "Any recording's performance, any voice's tone."],
  ["design", "Voice Design", "Describe a voice in words — the engine builds it."],
  ["dubbing", "Dubbing Studio", "Re-voice a whole video, timing preserved."],
  ["agent", "Agent Studio", "One prompt in, a finished video out."],
];

let lpWaves = [];        // live canvases on this route
let lpMicStream = null;  // active mic, if the visitor enabled it

async function lpEnableMic(wave, btn) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = audioCtx();
  const src = ctx.createMediaStreamSource(stream);
  const an = ctx.createAnalyser();
  an.fftSize = 256;
  an.smoothingTimeConstant = 0.82;
  src.connect(an);
  wave.setMic(an);
  wave.morph({ freq: 1, amp: 1.05, speed: 1 });
  lpMicStream = stream;
  return stream;
}

export async function landing(page, seq, fresh) {
  // stop previous wave loop / mic if the route is being re-entered
  lpWaves.forEach((w) => w.stop());
  lpWaves = [];
  if (lpMicStream) { lpMicStream.getTracks().forEach((t) => t.stop()); lpMicStream = null; }

  page.innerHTML = pageShell(`
    <div class="lp">
      <div class="lp-top">
        <div class="lp-brand">
          <img src="/static/assets/logo.svg" alt="">
          <span class="lp-brand-name">Insane<b>Voice</b></span>
        </div>
        <button class="btn accent sm" id="lp-top-enter">Enter the studio</button>
      </div>

      <section class="lp-hero">
        <div class="eyebrow lp-eyebrow">local · free · <b>no cloud</b></div>
        <h1 class="lp-title">Type. It speaks.<br>In your voice.</h1>
        <p class="lp-sub">Ten seconds of audio is enough. InsaneVoice clones the voice, speaks
        30+ languages, renders emotion — entirely on this machine. No account. No keys. No cost.</p>
        <div class="lp-cta">
          <button class="btn accent lg" id="lp-enter">Enter the studio</button>
          <button class="btn lg" id="lp-mic">${icon("mic", 17)} Speak to the wave</button>
        </div>
        <canvas class="lp-wave" id="lp-wave" aria-hidden="true"></canvas>
        <div class="lp-hint">move across the wave · click to drop a pulse · or let it hear you</div>
      </section>

      <section class="lp-section">
        <h2 class="lp-h2">Hear it. <span class="lp-dim">Real clips, rendered on a CPU.</span></h2>
        <div class="lp-clips" id="lp-clips"></div>
      </section>

      <section class="lp-section">
        <h2 class="lp-h2">One voice. <span class="lp-dim">Every tongue.</span></h2>
        <div class="lp-langs">
          <canvas class="lp-wave lp-wave-sm" id="lp-wave2" aria-hidden="true"></canvas>
          <div class="lp-chips" id="lp-chips"></div>
          <div class="lp-spec" id="lp-spec">hover a language — the wave changes its tongue</div>
        </div>
      </section>

      <section class="lp-section">
        <h2 class="lp-h2">Nothing leaves <span class="lp-dim">this machine.</span></h2>
        <div class="lp-specrows">
          <div class="lp-specrow"><span class="n">0</span><span class="l">API keys</span></div>
          <div class="lp-specrow"><span class="n">0</span><span class="l">Uploads</span></div>
          <div class="lp-specrow"><span class="n">0</span><span class="l">Cost, forever</span></div>
          <div class="lp-specrow"><span class="n">30+</span><span class="l">Languages</span></div>
        </div>
      </section>

      <section class="lp-section">
        <h2 class="lp-h2">The toolkit.</h2>
        <div class="lp-tools" id="lp-tools"></div>
      </section>

      <section class="lp-final">
        <h2 class="lp-final-title">Ready to sound insane?</h2>
        <button class="btn accent lg" id="lp-enter2">Open InsaneVoice</button>
        <div class="lp-foot">runs on your CPU · MIT licensed · your audio never uploads</div>
      </section>
    </div>
  `);

  // the living wave
  const w1 = new LandingWave(page.querySelector("#lp-wave"));
  w1.start();
  lpWaves.push(w1);
  const w2 = new LandingWave(page.querySelector("#lp-wave2"));
  w2.morph(LP_LANGS[0][1]);
  w2.start();
  lpWaves.push(w2);
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    lpWaves.forEach((w) => { w.stop(); w.draw(); });
  }

  // mic moment
  const micBtn = page.querySelector("#lp-mic");
  micBtn.onclick = async () => {
    if (lpMicStream) {
      lpMicStream.getTracks().forEach((t) => t.stop());
      lpMicStream = null;
      w1.setMic(null);
      micBtn.innerHTML = `${icon("mic", 17)} Speak to the wave`;
      return;
    }
    try {
      await lpEnableMic(w1);
      micBtn.innerHTML = `${icon("stop", 15)} Stop listening`;
      toast("Wave is listening", "The hero wave now dances to your microphone.", "ok");
    } catch (err) {
      toast("Mic declined", "No problem — the wave keeps imagining on its own.", "warn");
    }
  };

  // language morphs
  const chips = page.querySelector("#lp-chips");
  const spec = page.querySelector("#lp-spec");
  chips.innerHTML = LP_LANGS.map(([name], i) =>
    `<button class="lp-chip ${i === 0 ? "on" : ""}" data-i="${i}">${esc(name)}</button>`).join("");
  chips.querySelectorAll(".lp-chip").forEach((ch) => {
    ch.onclick = () => {
      chips.querySelectorAll(".lp-chip").forEach((c) => c.classList.remove("on"));
      ch.classList.add("on");
      const [name, params, text] = LP_LANGS[+ch.dataset.i];
      w2.morph(params);
      spec.textContent = `${name} — ${text}`;
    };
  });

  // real demo clips from history
  API.get("/api/history?limit=200").then((r) => {
    const el = page.querySelector("#lp-clips");
    if (!el) return;
    const seen = new Set();
    const picks = [];
    for (const h of r.history || []) {
      if (h.preview || (h.duration || 0) > 14 || seen.has(h.voice_name)) continue;
      seen.add(h.voice_name);
      picks.push(h);
      if (picks.length >= 3) break;
    }
    if (!picks.length) { el.closest(".lp-section").style.display = "none"; return; }
    el.innerHTML = picks.map((h) => `
      <div class="lp-clip">
        <button class="btn sm accent" data-play>${icon("play", 14)}</button>
        <div class="lp-clip-wave" data-wave></div>
        <div class="lp-clip-meta">
          <b>${esc(h.voice_name)}</b>
          <span class="mono-num">${fmtDur(h.duration)} · CPU</span>
        </div>
      </div>`).join("");
    el.querySelectorAll(".lp-clip").forEach((row, i) => {
      const wb = new WaveBox(row.querySelector("[data-wave]"), picks[i].audio_url, { height: 46 });
      wb.load();
      const btn = row.querySelector("[data-play]");
      btn.onclick = () => {
        wb.toggle();
        btn.innerHTML = wb.audio.paused ? icon("play", 14) : icon("stop", 14);
      };
      wb.onPlayState = (playing) => { btn.innerHTML = playing ? icon("stop", 14) : icon("play", 14); };
    });
  }).catch(() => {});

  // toolkit
  const tools = page.querySelector("#lp-tools");
  tools.innerHTML = LP_TOOLS.map(([route, name, desc]) => `
    <button class="lp-tool" data-route="${route}">
      <span class="lp-tool-name">${esc(name)}</span>
      <span class="lp-tool-desc">${esc(desc)}</span>
      <span class="lp-tool-arrow">→</span>
    </button>`).join("");
  tools.querySelectorAll(".lp-tool").forEach((b) => {
    b.onclick = () => { window.__lpCleanup = null; nav(b.dataset.route); };
  });

  // CTAs
  for (const id of ["lp-enter", "lp-enter2", "lp-top-enter"]) {
    page.querySelector(`#${id}`).onclick = () => { window.__lpCleanup = null; nav("dashboard"); };
  }

  // cleanup when the route changes away
  window.__lpCleanup = () => {
    lpWaves.forEach((w) => w.stop());
    lpWaves = [];
    if (lpMicStream) { lpMicStream.getTracks().forEach((t) => t.stop()); lpMicStream = null; }
  };
}

/* ============================================================
   Dashboard
   ============================================================ */

export async function dashboard(page, seq, fresh) {
  await refreshSystem();
  if (!fresh()) return;
  const s = state.system;
  const hist = await API.get("/api/history?limit=8").then((r) => r.history).catch(() => []);
  if (!fresh()) return;
  const voices = state.voices.length;
  const minutes = (hist.reduce((a, h) => a + (h.duration || 0), 0) / 60).toFixed(1);
  const hour = new Date().getHours();
  const greet = hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const eng = s?.engine?.status;
  const engText = eng === "ready" ? "Ready" : eng === "loading" ? "Loading…" : s ? "Check setup" : "…";
  const engClass = eng === "ready" ? "live" : eng === "loading" ? "sig" : "";
  const recentVoices = state.voices.slice(0, 8);

  page.innerHTML = pageShell(`
    <div class="hero">
      <div class="hero-copy">
        <div class="eyebrow">InsaneVoice · <b>local</b> cloning studio</div>
        <h1 class="hero-title">${greet}.</h1>
        <p class="hero-sub">Your voices, ready to speak — everything runs on this machine, offline and free.</p>
        <div class="hero-stats">
          <div class="stat"><div class="n">${voices}</div><div class="l">Voices in library</div></div>
          <div class="stat"><div class="n" id="d-gen">…</div><div class="l">Generations</div></div>
          <div class="stat"><div class="n">${minutes}<small> min</small></div><div class="l">Audio rendered</div></div>
          <div class="stat"><div class="n ${engClass}" id="d-eng">${engText}</div><div class="l">Engine · CPU</div></div>
        </div>
      </div>
      <div class="orb-wrap"><canvas class="orb" aria-hidden="true"></canvas></div>
    </div>

    ${s && !s.models_present ? banners.modelsMissing : ""}
    ${s && eng === "error" ? `<div class="banner err">✕ <div><b>Engine failed to load.</b><br><span class="small">${esc(String(s.engine.error).split("\n")[0])}</span></div></div>` : ""}

    <section class="dash-section">
      <h2 class="dash-h2">Your demos. <span class="lp-dim">Fresh renders from this machine.</span></h2>
      <div class="dash-clips" id="d-clips"></div>
    </section>

    <section class="dash-section">
      <h2 class="dash-h2">Your voices. <span class="lp-dim">${voices} cloned and ready.</span></h2>
      <div class="dash-voices" id="d-voices"></div>
    </section>
  `);

  startOrb(page.querySelector(".orb"));

  API.get("/api/history?limit=200").then((r) => {
    const el = document.getElementById("d-gen");
    if (el) el.textContent = r.history.length;
  });

  // demos: the newest renders, playable in place
  const clips = page.querySelector("#d-clips");
  const demos = hist.filter((h) => !h.preview).slice(0, 4);
  if (!demos.length) {
    clips.innerHTML = `
      <div class="empty">
        <div class="e-ico">${icon("waveform", 34)}</div>
        <h3>Nothing rendered yet</h3>
        <p>Open the Studio, pick a voice and type — your first demo will live here.</p>
      </div>`;
  } else {
    clips.innerHTML = demos.map((h) => `
      <div class="dash-clip">
        <button class="btn sm accent" data-play title="Play this render">${icon("play", 14)}</button>
        <div class="dash-clip-wave" data-wave></div>
        <div class="dash-clip-meta">
          <b title="${esc(String(h.text).slice(0, 120))}">${esc(String(h.text).slice(0, 56))}${String(h.text).length > 56 ? "…" : ""}</b>
          <span class="mono-num">${esc(h.voice_name)} · ${fmtDur(h.duration)} · ${fmtWhen(h.created_at)}</span>
        </div>
      </div>`).join("");
    clips.querySelectorAll(".dash-clip").forEach((row, i) => {
      const wb = new WaveBox(row.querySelector("[data-wave]"), demos[i].audio_url, { height: 44 });
      wb.load();
      const btn = row.querySelector("[data-play]");
      wb.onPlayState = (playing) => { btn.innerHTML = playing ? icon("stop", 13) : icon("play", 13); };
      btn.onclick = () => wb.toggle();
    });
  }

  // voices snapshot: display only
  const strip = page.querySelector("#d-voices");
  if (!recentVoices.length) {
    strip.innerHTML = `<div class="empty"><div class="e-ico">${icon("stack", 34)}</div>
      <h3>No voices yet</h3><p>Your cloned voices will gather here.</p></div>`;
  } else {
    strip.innerHTML = recentVoices.map((v) => `
      <div class="dv-chip" title="${esc(v.name)}">
        <span class="v-ava">${esc((v.name || "?")[0].toUpperCase())}</span>
        <span class="dv-meta">
          <b>${esc(v.name)}</b>
          <span>${esc(langLabel(v.language || "other"))} · ${fmtDur(v.duration)}</span>
        </span>
      </div>`).join("");
  }
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
          <button class="btn accent lg" id="st-go">${icon("spark", 17)} &nbsp;Generate speech</button>
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
              <input type="range" id="st-tau" min="0.1" max="0.9" step="0.05" value="0.7">
              <output id="st-tau-o">0.70</output>
            </div>
          </label>
          <div class="small muted" style="margin-top:-6px">
            Higher strength = closer to the reference voice, but can add artifacts.
            0.7 is the balanced default.
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
            <div class="e-ico">${icon("waveform", 34)}</div><p>Your generated audio will appear here.</p>
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
  // the engine's tau is a noise temperature: LOWER tau = closer to the
  // reference tone. The slider is "clone strength", so invert on the way out.
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
        tau: +(1 - tau.value).toFixed(2),
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
        <div class="e-ico">${icon("radar", 34)}</div><h3>No analysis yet</h3>
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
      <button class="btn accent" id="dna-save">${icon("plus", 15)} &nbsp;Save as a cloneable voice</button>
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
    <button class="btn accent" data-a="save">${icon("plus", 15)} &nbsp;Create voice</button>`;
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
    btn.innerHTML = icon("stop", 14);
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
        <button class="btn sm accent" id="tk-save">${icon("plus", 14)} &nbsp;Save as voice</button>
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
       <button class="btn accent" id="lib-add">${icon("plus", 15)} &nbsp;New voice</button>`)}
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
          <div class="e-ico">${icon("stack", 34)}</div>
          <h3>No voices yet</h3>
          <p>Record or import 10–30 seconds of speech. InsaneVoice turns it into a cloneable voice.</p>
          <button class="btn accent" id="lib-first">Create your first voice</button>
        </div>`;
      grid.querySelector("#lib-first").onclick = () => addVoiceFlow();
      return;
    }
    if (!shown.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <div class="e-ico">${icon("search", 34)}</div><h3>No match</h3><p>Try a different search or language.</p></div>`;
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
          <button class="btn sm accent" data-act="preview" title="Generate a greeting in this voice">${icon("spark", 14)} &nbsp;Preview</button>
          <button class="btn sm" data-act="sample" title="Listen to the reference sample">${icon("play", 14)} &nbsp;Sample</button>
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
      const sampleBtn = card.querySelector('[data-act="sample"]');
      sampleBtn.onclick = () => {
        const out = card.querySelector("[data-out]");
        // one WaveBox per card: toggle() handles BOTH play and stop.
        // (creating a new one per click made "Stop" restart the audio and
        // overlap takes.)
        if (!sampleBtn._wb) {
          out.innerHTML = "";
          const wb = new WaveBox(out, v.sample_url, { height: 56 });
          wb.load();
          wb.onPlayState = (playing) => {
            sampleBtn.innerHTML = playing ? `${icon("stop", 13)} Stop` : `${icon("play", 13)} Sample`;
          };
          sampleBtn._wb = wb;
        }
        sampleBtn._wb.toggle();
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
          <button class="btn accent" id="bt-go">${icon("spark", 16)} &nbsp;Render queue</button>
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
          <button class="btn sm" data-u="${res.generation.audio_url}">${icon("play", 14)}</button>
          <button class="btn sm" data-d="${res.generation.audio_url}" data-n="clip_${String(i + 1).padStart(2, "0")}.wav">${icon("download", 14)}</button>`;
        const row = page.querySelector(`#bt-row-${i} > div`);
        row.insertAdjacentHTML("beforeend", `<div class="row-wave" data-wave></div>`);
        acts.querySelector("[data-u]").onclick = (ev) =>
          inlinePlay(ev.currentTarget, ev.currentTarget.dataset.u, row.querySelector("[data-wave]"));
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
      <div class="empty"><div class="e-ico">${icon("clock", 34)}</div><h3>History is empty</h3>
      <p>Generate something in the Studio and it will show up here.</p>
      <button class="btn accent" id="h-go">Open Studio</button></div>`;
    list.querySelector("#h-go").onclick = () => nav("studio");
    return;
  }
  list.innerHTML = items.map((h, i) => `
    <div class="list-row">
      <span class="idx">${h.preview ? icon("waveform", 12) : String(items.length - i).padStart(2, "0")}</span>
      <div>
        <div class="t">${esc(String(h.text).slice(0, 90))}${String(h.text).length > 90 ? "…" : ""}</div>
        <div class="s">${esc(h.voice_name)} · ${fmtDur(h.duration)} · ${fmtWhen(h.created_at)}${h.preview ? " · preview" : ""}</div>
        <div class="row-wave" data-wave></div>
      </div>
      <div class="acts">
        <button class="btn sm" data-act="play" data-u="${h.audio_url}" title="Play here">${icon("play", 14)}</button>
        <button class="btn sm" data-act="dl" data-u="${h.audio_url}" data-n="${esc(h.voice_name)}_${h.id}.wav" title="Download">${icon("download", 14)}</button>
        <button class="btn sm icon" data-act="del" data-id="${h.id}" title="Delete this entry" aria-label="Delete this entry">${icon("trash", 15)}</button>
      </div>
    </div>`).join("");
  list.querySelectorAll('[data-act="play"]').forEach((b) =>
    b.onclick = () => inlinePlay(b, b.dataset.u, b.closest(".list-row").querySelector("[data-wave]")));
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
      <h3 style="margin:0 0 8px">Engine connection</h3>
      <p class="small" style="margin:0 0 12px;color:var(--ink-2)">
        ${state.system
          ? `Connected${apiBase() ? ` to <b>${esc(apiBase())}</b>` : " to the built-in local engine"}.`
          : `No engine reachable. The InsaneVoice engine runs on your machine —
             start it with <code>scripts/start_windows.bat</code> (Windows) or
             <code>uvicorn main:app --port 8177</code> (macOS/Linux), then connect below.`}
      </p>
      <div class="row wrap">
        <label class="field" style="flex:1;min-width:240px">
          <span>Engine URL</span>
          <input type="text" id="set-engine-url" placeholder="http://127.0.0.1:8177"
                 value="${esc(apiBase())}">
        </label>
        <button class="btn accent" id="set-engine-save" style="align-self:flex-end">${icon("check", 15)} Connect</button>
      </div>
      ${apiBase() ? `<button class="btn sm" id="set-engine-reset" style="margin-top:10px">Use built-in engine (same origin)</button>` : ""}
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
  page.querySelector("#set-engine-save")?.addEventListener("click", async (e) => {
    const url = page.querySelector("#set-engine-url").value.trim();
    if (!/^https?:\/\/.+/.test(url)) { toast("Enter a full URL like http://127.0.0.1:8177", "", "err"); return; }
    const prev = apiBase();
    setApiBase(url);
    const sys = await refreshSystem();
    if (sys) { toast("Connected to engine", url, "ok"); render(); }
    else { setApiBase(prev); toast("Engine unreachable", `${url} didn't respond — is the server running?`, "err"); }
  });
  page.querySelector("#set-engine-reset")?.addEventListener("click", () => {
    setApiBase("");
    location.reload();
  });
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
      <div class="e-ico">${icon("mic", 34)}</div>
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
