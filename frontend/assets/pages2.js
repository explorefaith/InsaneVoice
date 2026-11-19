/* InsaneVoice — v2 pages: Changer, Isolator, Design, Transcribe,
   Dubbing, Director's Studio, Agent Studio, Connections */

import { API, state, refreshVoices, nav, render } from "./app.js";
import { abs } from "./net.js";
import {
  toast, modal, confirmModal, sk, busy, WaveBox,
  esc, fmtDur, fmtWhen, download, pageHead, iconBtn, langLabel, groupedVoiceOptions,
} from "./components.js";
import { icon } from "./icons.js";
import { inlinePlay } from "./components.js";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function head(title, sub, kicker) {
  return `
    <div class="page-head">
      ${kicker ? `<div class="kicker">${esc(kicker)}</div>` : ""}
      <h1>${esc(title)}</h1>
      ${sub ? `<p>${esc(sub)}</p>` : ""}
    </div>`;
}

function shell(html) { return `<div style="margin-top:6px">${html}</div>`; }

async function voicesSafe() {
  await refreshVoices();
  return state.voices;
}

function voiceOpts(voices, sel) {
  if (!voices.length) return `<option value="">— create a voice first —</option>`;
  return voices.map((v) => `<option value="${esc(v.id)}">${esc(v.name)}${v.verified ? " ✓" : ""}</option>`).join("")
    .replace(`value="${esc(sel)}"`, `value="${esc(sel)}" selected`);
}

function audioCard(gen) {
  const d = document.createElement("div");
  d.className = "audio-card";
  d.innerHTML = `
    <div class="spread">
      <div class="row">
        <button class="btn sm accent" data-play>${icon("play", 15)} Play</button>
        ${gen.audio_url ? `<button class="btn sm" data-dl>${icon("download", 15)} Download</button>` : ""}
      </div>
      <div class="audio-meta">
        <span class="pill acc">${esc(gen.voice_name || "voice")}</span>
        ${gen.duration ? `<span class="pill">${fmtDur(gen.duration)}</span>` : ""}
        ${gen.elapsed ? `<span class="pill">in ${fmtDur(gen.elapsed)}</span>` : ""}
      </div>
    </div>
    <div data-wave></div>`;
  if (gen.audio_url) {
    const wb = new WaveBox($("[data-wave]", d), gen.audio_url);
    wb.load();
    $("[data-play]", d).onclick = (e) => {
      wb.toggle();
      e.target.innerHTML = wb.audio.paused ? `${icon("play", 15)} Play` : `${icon("stop", 15)} Stop`;
    };
    $("[data-dl]", d).onclick = () => download(gen.audio_url, "insanevoice.wav");
  }
  return d;
}

function emptyState(icon, title, text, btnLabel, btnId) {
  return `
    <div class="empty">
      <div class="e-ico">${icon}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>
      ${btnLabel ? `<button class="btn accent" id="${btnId}">${btnLabel}</button>` : ""}
    </div>`;
}

function noVoices(page, title, kicker) {
  page.innerHTML = shell(`
    ${head(title, "", kicker)}
    ${emptyState(icon("mic", 34), "You need a voice first",
      "Record or import a 10–30 second sample to create your first cloneable voice.",
      "Create a voice now", "nv-go")}`);
  $("#nv-go", page).onclick = () => nav("recorder");
}

/* ============================================================
   Voice Changer — audio→audio performance transfer
   ============================================================ */

export async function changer(page) {
  const voices = await voicesSafe();
  if (!voices.length) return noVoices(page, "Voice Changer", "Voices");
  page.innerHTML = shell(`
    ${pageHead("Voice Changer", "Keep the performance — borrow the tone. Upload any recording (your dramatic read, a laugh, a sigh in ANY language) and it comes out in the target voice.", "Voices")}
    <div class="grid c2" style="gap:20px" id="vc-grid">
      <div class="panel">
        <div class="dropzone" id="vc-dz">
          <div class="dz-ico">${icon("mic", 26)}</div>
          <h4>Drop the guide recording here</h4>
          <p>any language — the converter only transfers tone</p>
          <input type="file" id="vc-file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm" hidden>
        </div>
        <label class="field" style="margin-top:16px"><span>Target voice</span>
          <select id="vc-voice">${groupedVoiceOptions(voices)}</select></label>
        <label class="field"><span>Clone strength</span>
          <div class="range-row">
            <input type="range" id="vc-tau" min="0.1" max="0.9" step="0.05" value="0.7">
            <output id="vc-tau-o">0.70</output>
          </div></label>
        <button class="btn accent" id="vc-go">${icon("spark", 16)} &nbsp;Convert performance</button>
        <div id="vc-prog" style="margin-top:14px"></div>
      </div>
      <div class="panel">
        <h3 style="margin:0 0 12px">Result</h3>
        <div id="vc-out">${emptyState(icon("waveform", 34), "Nothing converted yet",
          "The output keeps every rhythm and emphasis of the original — in the new voice.")}</div>
      </div>
    </div>`);
  if (innerWidth < 900) $("#vc-grid", page).style.gridTemplateColumns = "1fr";

  const dz = $("#vc-dz", page), fi = $("#vc-file", page);
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) dz.querySelector("h4").textContent = fi.files[0].name; };
  $("#vc-tau", page).oninput = (e) => $("#vc-tau-o", page).textContent = (+e.target.value).toFixed(2);

  $("#vc-go", page).onclick = async (e) => {
    if (!fi.files[0]) return toast("Pick a recording", "Drop or browse a guide audio first.", "warn");
    busy(e.currentTarget, true);
    $("#vc-prog", page).innerHTML = `<div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Transferring tone…</span><span>CPU</span></div>`;
    try {
      const fd = new FormData();
      fd.append("file", fi.files[0]);
      fd.append("voice_id", $("#vc-voice", page).value);
      fd.append("tau", (1 - +$("#vc-tau", page).value).toFixed(2));
      const res = await API.postForm("/api/changer", fd);
      $("#vc-prog", page).innerHTML = "";
      $("#vc-out", page).innerHTML = "";
      $("#vc-out", page).appendChild(audioCard(res.conversion));
      toast("Performance converted", "Same performance, new voice.");
    } catch (err) {
      $("#vc-prog", page).innerHTML = "";
      toast("Conversion failed", err.message, "err");
    } finally { busy(e.currentTarget, false); }
  };
}

/* ============================================================
   Isolator
   ============================================================ */

export async function isolate(page) {
  page.innerHTML = shell(`
    ${pageHead("Voice Isolator", "Strip room noise and hiss from any recording — useful before cloning a noisy sample.", "Tools")}
    <div class="grid c2" style="gap:20px" id="iso-grid">
      <div class="panel">
        <div class="dropzone" id="iso-dz">
          <div class="dz-ico">🧹</div><h4>Drop a noisy recording</h4>
          <p>wav, mp3, m4a, ogg, webm — up to 30MB</p>
          <input type="file" id="iso-file" accept="audio/*" hidden>
        </div>
        <button class="btn accent" style="margin-top:16px" id="iso-go">${icon("spark", 16)} &nbsp;Isolate voice</button>
        <div id="iso-prog" style="margin-top:14px"></div>
      </div>
      <div class="panel">
        <h3 style="margin:0 0 12px">Before / after</h3>
        <div id="iso-out">${emptyState("🧹", "No isolation yet", "The clean version keeps speech, drops the noise floor.")}</div>
      </div>
    </div>`);
  if (innerWidth < 900) $("#iso-grid", page).style.gridTemplateColumns = "1fr";
  const dz = $("#iso-dz", page), fi = $("#iso-file", page);
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) dz.querySelector("h4").textContent = fi.files[0].name; };
  $("#iso-go", page).onclick = async (e) => {
    if (!fi.files[0]) return toast("Pick a file", "Drop a noisy recording first.", "warn");
    busy(e.currentTarget, true);
    $("#iso-prog", page).innerHTML = `<div class="progress indet"><i></i></div>`;
    try {
      const fd = new FormData();
      fd.append("file", fi.files[0]);
      const res = await API.postForm("/api/isolate", fd);
      const iso = res.isolated;
      $("#iso-prog", page).innerHTML = "";
      $("#iso-out", page).innerHTML = `
        <div class="stack">
          <div><div class="field-label">Original</div><div id="iso-a"></div></div>
          <div><div class="field-label">Isolated</div><div id="iso-b"></div></div>
        </div>`;
      const w1 = new WaveBox($("#iso-a", page), iso.original_url, { height: 56 }); w1.load();
      const w2 = new WaveBox($("#iso-b", page), iso.url, { height: 56 }); w2.load();
      const dl = document.createElement("button");
      dl.className = "btn accent"; dl.innerHTML = `${icon("download", 15)} Download clean audio`;
      dl.onclick = () => download(iso.url, "isolated.wav");
      $("#iso-b", page).parentElement.appendChild(dl);
      toast("Isolated", "Noise floor removed.");
    } catch (err) {
      $("#iso-prog", page).innerHTML = "";
      toast("Isolation failed", err.message, "err");
    } finally { busy(e.currentTarget, false); }
  };
}

/* ============================================================
   Voice Design
   ============================================================ */

export async function design(page) {
  page.innerHTML = shell(`
    ${pageHead("Voice Design", "Describe a voice in words — InsaneVoice sculpts it with a DSP feedback loop until the fingerprint matches, then saves it as a normal cloneable voice.", "Voices")}
    <div class="grid c2" style="gap:20px" id="vd-grid">
      <div class="panel">
        <label class="field"><span>Describe the voice</span>
          <textarea id="vd-desc" rows="4" placeholder="young warm British female, a bit breathy, medium-slow"></textarea>
        </label>
        <details><summary class="small muted" style="cursor:pointer;margin-bottom:12px">Fine-tune targets (optional)</summary>
          <div class="grid c2" style="gap:10px">
            <label class="field"><span>Pitch (Hz)</span><input type="text" id="vd-f0" placeholder="auto"></label>
            <label class="field"><span>Tempo</span>
              <div class="range-row"><input type="range" id="vd-tempo" min="0.8" max="1.25" step="0.01" value="1">
              <output id="vd-tempo-o">1.00</output></div></label>
            <label class="field"><span>Warmth</span>
              <div class="range-row"><input type="range" id="vd-warm" min="0" max="100" value="50">
              <output id="vd-warm-o">50</output></div></label>
            <label class="field"><span>Brightness</span>
              <div class="range-row"><input type="range" id="vd-bright" min="0" max="100" value="50">
              <output id="vd-bright-o">50</output></div></label>
          </div>
        </details>
        <button class="btn accent" id="vd-go">${icon("spark", 16)} &nbsp;Sculpt this voice</button>
        <div id="vd-prog" style="margin-top:14px"></div>
      </div>
      <div class="panel">
        <h3 style="margin:0 0 12px">Designed voice</h3>
        <div id="vd-out">${emptyState("✨", "No design yet",
          "The analyser loops up to 3 passes: pitch-shift + spectral tilt, then re-measures.")}</div>
      </div>
    </div>`);
  if (innerWidth < 900) $("#vd-grid", page).style.gridTemplateColumns = "1fr";
  [["vd-tempo", "vd-tempo-o"], ["vd-warm", "vd-warm-o"], ["vd-bright", "vd-bright-o"]]
    .forEach(([i, o]) => { const el = $(`#${i}`, page); el.oninput = () => $(`#${o}`, page).textContent = (+el.value).toFixed(2); });

  $("#vd-go", page).onclick = async (e) => {
    const desc = $("#vd-desc", page).value.trim();
    if (!desc) return toast("Describe it first", "e.g. warm elderly narrator, deep and slow", "warn");
    busy(e.currentTarget, true);
    $("#vd-prog", page).innerHTML = `<div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Sculpting (analyse → shape → repeat)…</span><span>CPU</span></div>`;
    try {
      const body = { description: desc };
      if ($("#vd-f0", page).value.trim()) body.f0 = parseFloat($("#vd-f0", page).value) || undefined;
      body.tempo = +$("#vd-tempo", page).value;
      body.warm = +$("#vd-warm", page).value;
      body.bright = +$("#vd-bright", page).value;
      const res = await API.post("/api/design/preview", body);
      const r = res.report;
      $("#vd-prog", page).innerHTML = "";
      $("#vd-out", page).innerHTML = `
        <div class="stack">
          <div data-wave></div>
          <div class="audio-meta">
            <span class="pill ok">pass ${r.pass}</span>
            <span class="pill">${r.f0} Hz → ${r.after} Hz</span>
            <span class="pill acc">${esc(r.archetype)}</span>
          </div>
          <div class="row">
            <button class="btn accent" id="vd-save">${icon("plus", 15)} &nbsp;Save as a voice</button>
          </div>
        </div>`;
      const wb = new WaveBox($("[data-wave]", page), res.audio_url);
      wb.load();
      $("#vd-save", page).onclick = () => {
        const bodyEl = document.createElement("div");
        bodyEl.innerHTML = `
          <label class="field"><span>Voice name</span>
            <input type="text" id="vdn" maxlength="60" value="${esc(desc.slice(0, 40))}"></label>
          <label class="checkbox"><input type="checkbox" id="vdc">
            <span>I will only use this designed voice responsibly.</span></label>
          <div id="vde"></div>`;
        const foot = document.createElement("div");
        foot.innerHTML = `<button class="btn ghost" data-a="c">Cancel</button>
          <button class="btn accent" data-a="s">${icon("plus", 14)} &nbsp;Create</button>`;
        modal({
          title: "Save designed voice", body: bodyEl, footer: foot,
          onMount: (veil, close) => {
            $('[data-a="c"]', veil).onclick = close;
            $('[data-a="s"]', veil).onclick = async (ev) => {
              if (!$("#vdc", veil).checked)
                return $("#vde", veil).innerHTML = `<div class="banner err" style="margin-top:12px">✕ <div>Consent required.</div></div>`;
              busy(ev.currentTarget, true);
              try {
                await API.post("/api/design/save", {
                  session: res.session, name: $("#vdn", veil).value, consent: true,
                  description: desc,
                });
                await refreshVoices();
                close();
                toast("Designed voice saved", "It behaves like any other voice now.");
                nav("library");
              } catch (err) {
                busy(ev.currentTarget, false);
                $("#vde", veil).innerHTML = `<div class="banner err" style="margin-top:12px">✕ <div>${esc(err.message)}</div></div>`;
              }
            };
          },
        });
      };
      toast("Voice sculpted", `${r.archetype} · ${r.f0}→${r.after} Hz`);
    } catch (err) {
      $("#vd-prog", page).innerHTML = "";
      toast("Design failed", err.message, "err");
    } finally { busy(e.currentTarget, false); }
  };
}

/* ============================================================
   Transcribe (STT)
   ============================================================ */

const STT_LANGS = [
  ["en-us", "English (US)"], ["en-in", "English (India)"], ["es", "Español"],
  ["fr", "Français"], ["de", "Deutsch"], ["it", "Italiano"], ["pt", "Português"],
  ["zh-cn", "中文"], ["ja", "日本語"], ["ko", "한국어"], ["ru", "Русский"],
  ["hi", "हिन्दी"], ["tr", "Türkçe"], ["vi", "Tiếng Việt"], ["nl", "Nederlands"],
];

export async function transcribe(page) {
  page.innerHTML = shell(`
    ${pageHead("Transcribe", "Offline speech-to-text (Vosk models, ~50MB, downloaded on first use per language).", "Tools")}
    <div class="grid c2" style="gap:20px" id="tr-grid">
      <div class="panel">
        <div class="dropzone" id="tr-dz">
          <div class="dz-ico">📝</div><h4>Drop audio to transcribe</h4>
          <p>wav, mp3, m4a, ogg, webm — up to 200MB</p>
          <input type="file" id="tr-file" accept="audio/*,video/*" hidden>
        </div>
        <label class="field" style="margin-top:16px"><span>Language</span>
          <select id="tr-lang">${STT_LANGS.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select></label>
        <button class="btn accent" id="tr-go">${icon("spark", 16)} &nbsp;Transcribe</button>
        <div id="tr-prog" style="margin-top:14px"></div>
      </div>
      <div class="panel" id="tr-out-panel">
        <h3 style="margin:0 0 12px">Transcript</h3>
        <div id="tr-out">${emptyState("📝", "Nothing transcribed yet",
          "Word timings included — export SRT subtitles directly.")}</div>
      </div>
    </div>`);
  if (innerWidth < 900) $("#tr-grid", page).style.gridTemplateColumns = "1fr";
  const dz = $("#tr-dz", page), fi = $("#tr-file", page);
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) dz.querySelector("h4").textContent = fi.files[0].name; };

  $("#tr-go", page).onclick = async (e) => {
    if (!fi.files[0]) return toast("Pick audio", "Drop a file first.", "warn");
    busy(e.currentTarget, true);
    $("#tr-prog", page).innerHTML = `<div class="progress indet"><i></i></div>
      <div class="progress-label"><span id="tr-pl">Transcribing offline…</span><span>CPU</span></div>`;
    try {
      const fd = new FormData();
      fd.append("file", fi.files[0]);
      fd.append("lang", $("#tr-lang", page).value);
      const res = await API.postForm("/api/transcribe", fd);
      const t = res.transcript;
      $("#tr-prog", page).innerHTML = "";
      $("#tr-out", page).innerHTML = `
        <div class="stack">
          <div class="row">
            <button class="btn sm" id="tr-copy">⧉ Copy text</button>
            <button class="btn sm" id="tr-srt">${icon("download", 14)} SRT</button>
            <button class="btn sm" id="tr-txt">${icon("download", 14)} TXT</button>
            <span class="pill">${fmtDur(t.duration)}</span>
          </div>
          <div class="panel" style="max-height:300px;overflow:auto;background:var(--paper)">
            <p class="small" style="margin:0;white-space:pre-wrap">${esc(t.text)}</p>
          </div>
          <details><summary class="small muted" style="cursor:pointer">Segments (${t.segments.length})</summary>
            <div class="stack" style="margin-top:8px">
              ${t.segments.map((s) => `<div class="small"><span class="mono-num muted">${s.start.toFixed(1)}s</span> — ${esc(s.text)}</div>`).join("")}
            </div></details>
        </div>`;
      const blob = (s, type) => URL.createObjectURL(new Blob([s], { type }));
      $("#tr-copy", page).onclick = () => navigator.clipboard.writeText(t.text).then(() => toast("Copied"));
      $("#tr-srt", page).onclick = () => download(blob(t.srt, "text/plain"), "transcript.srt");
      $("#tr-txt", page).onclick = () => download(blob(t.text, "text/plain"), "transcript.txt");
      toast("Transcribed", `${t.segments.length} segments`);
    } catch (err) {
      $("#tr-prog", page).innerHTML = "";
      toast("Transcription failed", err.message, "err");
    } finally { busy(e.currentTarget, false); }
  };
}

/* ============================================================
   Dubbing
   ============================================================ */

export async function dubbing(page) {
  const voices = await voicesSafe();
  page.innerHTML = shell(`
    ${pageHead("Dubbing Studio", "Upload a video or audio track — it is transcribed with word timings, you polish the lines, pick a voice per line, and the performance timing is preserved.", "Tools")}
    <div id="db-main" class="stack">
      <div class="panel">
        <div class="dropzone" id="db-dz">
          <div class="dz-ico">🎬</div><h4>Drop a video (or audio) to dub</h4>
          <p>mp4, mov, webm, mkv · wav, mp3 — up to 600MB</p>
          <input type="file" id="db-file" accept="video/*,audio/*" hidden>
        </div>
        <div class="row wrap" style="margin-top:14px">
          <label class="field grow" style="margin:0"><span>Spoken language</span>
            <select id="db-lang">${STT_LANGS.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select></label>
          <button class="btn accent" id="db-go" style="align-self:flex-end">${icon("spark", 16)} &nbsp;Transcribe & segment</button>
        </div>
        <div id="db-prog" style="margin-top:14px"></div>
      </div>
      <div id="db-work"></div>
    </div>`);

  const dz = $("#db-dz", page), fi = $("#db-file", page);
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) dz.querySelector("h4").textContent = fi.files[0].name; };
  let dub = null;

  $("#db-go", page).onclick = async (e) => {
    if (!fi.files[0]) return toast("Pick a file", "Drop a video or audio first.", "warn");
    busy(e.currentTarget, true);
    $("#db-prog", page).innerHTML = `<div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Transcribing with word timings…</span><span>CPU</span></div>`;
    try {
      const fd = new FormData();
      fd.append("file", fi.files[0]);
      fd.append("lang", $("#db-lang", page).value);
      const res = await API.postForm("/api/dubbing/ingest", fd);
      dub = res.dub;
      $("#db-prog", page).innerHTML = "";
      renderWork();
      toast("Segments ready", `${dub.segments.length} lines detected.`);
    } catch (err) {
      $("#db-prog", page).innerHTML = "";
      toast("Ingest failed", err.message, "err");
    } finally { busy(e.currentTarget, false); }
  };

  function renderWork() {
    if (!voices.length) {
      $("#db-work", page).innerHTML = `<div class="banner warn">! <div>You need at least one voice in the Library to dub.</div></div>`;
      return;
    }
    $("#db-work", page).innerHTML = `
      <div class="panel flush">
        <div class="panel-head"><h3>Lines (${dub.segments.length})</h3>
          <span class="small muted">edit text · assign voice · revoice keeps timing</span></div>
        <div style="max-height:430px;overflow:auto">
          ${dub.segments.map((s, i) => `
            <div class="list-row" style="grid-template-columns:70px 1fr 170px">
              <span class="small mono-num muted">${s.start.toFixed(1)}–${s.end.toFixed(1)}s</span>
              <input type="text" data-txt="${i}" value="${esc(s.text)}">
              <select data-voice="${i}">
                <option value="">skip</option>
                ${groupedVoiceOptions(voices)}
              </select>
            </div>`).join("")}
        </div>
        <div class="panel-body" style="border-top:1px solid var(--line)">
          <button class="btn accent" id="db-revoice">${icon("spark", 16)} &nbsp;Revoice with cloned voices</button>
          <span class="small muted" style="margin-left:10px">takes are time-fitted (max 1.28×) to stay in sync</span>
          <div id="db-rprog" style="margin-top:14px"></div>
          <div id="db-result" class="stack" style="margin-top:14px"></div>
        </div>
      </div>`;
    $("#db-revoice", page).onclick = async (e) => {
      const assigns = [];
      $$("[data-voice]", page).forEach((sel) => {
        if (sel.value) {
          const i = +sel.dataset.voice;
          assigns.push({ index: i, voice_id: sel.value,
            text: $(`[data-txt="${i}"]`, page).value });
        }
      });
      if (!assigns.length) return toast("Assign voices", "Pick a voice for at least one line.", "warn");
      busy(e.currentTarget, true);
      const done = { n: 0 };
      $("#db-rprog", page).innerHTML = `<div class="progress"><i id="db-rbar"></i></div>
        <div class="progress-label"><span id="db-rpl">Generating lines…</span><span id="db-rc"></span></div>`;
      try {
        const res = await API.post(`/api/dubbing/${dub.id}/revoice`, { assignments: assigns });
        $("#db-rprog", page).innerHTML = "";
        $("#db-result", page).innerHTML = "";
        $("#db-result", page).appendChild(audioCard(res.audio));
        if (res.video) {
          const v = document.createElement("video");
          v.src = abs(res.video.url); v.controls = true;
          v.style.width = "100%"; v.style.borderRadius = "10px";
          $("#db-result", page).appendChild(v);
        }
        toast("Dubbing complete", `${res.report.filter((r) => r.status === "ok").length} lines re-voiced.`);
      } catch (err) {
        $("#db-rprog", page).innerHTML = "";
        toast("Revoice failed", err.message, "err");
      } finally { busy(e.currentTarget, false); }
    };
  }
}

/* ============================================================
   Director's Studio (long-form projects)
   ============================================================ */

export async function director(page) {
  const projects = await API.get("/api/projects").then((r) => r.projects).catch(() => []);
  const voices = await voicesSafe();

  page.innerHTML = shell(`
    ${head("Director's Studio", "Long-form narration as a project: chunks, three takes each, pick the best, regenerate any chunk alone, export the stitch.", "Create")}
    <div class="spread" style="margin-bottom:16px">
      <span class="small muted">${projects.length} project(s)</span>
      <button class="btn accent" id="dr-new">${icon("plus", 15)} &nbsp;New project</button>
    </div>
    <div id="dr-list" class="stack"></div>
    <div id="dr-editor"></div>`);

  $("#dr-new", page).onclick = () => {
    if (!voices.length) return toast("Create a voice first", "Projects need a voice.", "warn");
    const body = document.createElement("div");
    body.innerHTML = `
      <label class="field"><span>Title</span><input type="text" id="dr-t" placeholder="Chapter 1 — The Harbour"></label>
      <label class="field"><span>Voice</span><select id="dr-v">${voiceOpts(voices)}</select></label>
      <label class="field"><span>Script (blank line = new chunk)</span>
        <textarea id="dr-s" rows="8" placeholder="Paste the whole narration here…"></textarea></label>
      <div id="dre"></div>`;
    const foot = document.createElement("div");
    foot.innerHTML = `<button class="btn ghost" data-a="c">Cancel</button>
      <button class="btn accent" data-a="s">Create project</button>`;
    modal({
      title: "New project", body, footer: foot,
      onMount: (veil, close) => {
        $('[data-a="c"]', veil).onclick = close;
        $('[data-a="s"]', veil).onclick = async (ev) => {
          if (!$("#dr-s", veil).value.trim())
            return $("#dre", veil).innerHTML = `<div class="banner err" style="margin-top:12px">✕ <div>Script is empty.</div></div>`;
          busy(ev.currentTarget, true);
          try {
            await API.post("/api/projects", {
              title: $("#dr-t", veil).value || "Untitled",
              voice_id: $("#dr-v", veil).value,
              script: $("#dr-s", veil).value,
            });
            close(); render();
          } catch (err) {
            busy(ev.currentTarget, false);
            $("#dre", veil).innerHTML = `<div class="banner err" style="margin-top:12px">✕ <div>${esc(err.message)}</div></div>`;
          }
        };
      },
    });
  };

  const list = $("#dr-list", page);
  if (!projects.length) {
    list.innerHTML = emptyState("🎬", "No projects yet",
      "Paste a script — it gets cut into logical chunks automatically.", "New project", "dr-first");
    $("#dr-first", page).onclick = () => $("#dr-new", page).click();
  } else {
    for (const p of projects) {
      const done = p.chunks.filter((c) => c.selected).length;
      const el = document.createElement("div");
      el.className = "panel";
      el.innerHTML = `
        <div class="spread">
          <div><h3 style="margin:0">${esc(p.title)}</h3>
            <div class="small muted">${p.chunks.length} chunks · ${done} ready</div></div>
          <div class="row">
            <button class="btn sm primary" data-open>Open</button>
            <button class="btn sm danger" data-del>🗑</button>
          </div>
        </div>`;
      $("[data-open]", el).onclick = () => openProject(p.id);
      $("[data-del]", el).onclick = async () => {
        if (await confirmModal("Delete project?", `“${p.title}” and all its takes will be removed.`, "Delete")) {
          await API.del(`/api/projects/${p.id}`); render();
        }
      };
      list.appendChild(el);
    }
  }

  async function openProject(pid) {
    const res = await API.get(`/api/projects/${pid}`);
    const p = res.project;
    const ed = $("#dr-editor", page);
    ed.innerHTML = `
      <hr class="rule">
      <div class="spread"><h2 class="serif" style="margin:0;font-size:24px">${esc(p.title)}</h2>
        <div class="row">
          <button class="btn" id="dr-exp">${icon("download", 14)} Export</button>
          <button class="btn" id="dr-export-mp3">${icon("download", 14)} MP3</button>
        </div></div>
      <p class="small muted" style="margin-top:4px">Generate 3 takes per chunk (jittered speed/strength for natural variety), pick the winner, export.</p>
      <div class="stack" id="dr-chunks"></div>
      <div id="dr-exp-out" class="stack" style="margin-top:14px"></div>`;

    const wrap = $("#dr-chunks", page);
    p.chunks.forEach((c, ci) => {
      const el = document.createElement("div");
      el.className = "panel";
      el.innerHTML = `
        <div class="spread">
          <div class="row"><span class="idx serif">${String(ci + 1).padStart(2, "0")}</span>
            <textarea data-edit rows="2" style="min-height:44px">${esc(c.text)}</textarea></div>
        </div>
        <div class="row wrap" style="margin-top:10px">
          <button class="btn sm accent" data-gen3>${icon("spark", 14)} &nbsp;3 takes</button>
          <button class="btn sm" data-gen1>${icon("plus", 14)} &nbsp;1 more</button>
          <button class="btn sm ghost" data-saveedit>Save edit</button>
          <button class="btn sm danger" data-delchunk>✕</button>
          <span class="grow"></span>
          <span class="small muted" data-status>${c.takes.length ? `${c.takes.length} take(s)` : "no takes yet"}</span>
        </div>
        <div class="stack" data-takes style="margin-top:10px"></div>`;
      wrap.appendChild(el);

      const takesEl = $("[data-takes]", el);
      const renderTakes = () => {
        takesEl.innerHTML = c.takes.map((t) => `
          <div class="list-row" style="grid-template-columns:24px 1fr auto">
            <input type="radio" name="sel_${c.id}" data-pick="${t.id}" ${c.selected === t.id ? "checked" : ""}>
            <div><div class="t small">Take ${t.variant + 1} · ${fmtDur(t.duration)} · ${t.f0} Hz</div>
            <div class="row-wave" data-wave></div></div>
            <div class="acts">
              <button class="btn sm" data-play="${t.file}" title="Play here">${icon("play", 13)}</button>
              <button class="btn sm danger" data-deltake="${t.id}" title="Delete take">✕</button>
            </div>
          </div>`).join("");
        $$("[data-play]", takesEl).forEach((b) =>
          b.onclick = () => inlinePlay(b, `/api/projects/${pid}/audio/${b.dataset.play}`,
            b.closest(".list-row").querySelector("[data-wave]")));
        $$("[data-pick]", takesEl).forEach((r) => r.onchange = async () => {
          await API.patch(`/api/projects/${pid}/chunks/${c.id}`, { selected: r.dataset.pick });
          toast("Take selected");
        });
        $$("[data-deltake]", takesEl).forEach((b) => b.onclick = async () => {
          await API.del(`/api/projects/${pid}/chunks/${c.id}/takes/${b.dataset.deltake}`);
          openProject(pid);
        });
      };
      renderTakes();

      $("[data-gen3]", el).onclick = async (e) => {
        busy(e.currentTarget, true);
        $("[data-status]", el).textContent = "generating 3 takes…";
        try {
          for (const v of [0, 1, 2]) {
            await API.post(`/api/projects/${pid}/chunks/${c.id}/takes`, { variant: v });
            $("[data-status]", el).textContent = `take ${v + 1}/3 done…`;
          }
          openProject(pid);
        } catch (err) {
          toast("Take failed", err.message, "err");
          busy(e.currentTarget, false);
        }
      };
      $("[data-gen1]", el).onclick = async (e) => {
        busy(e.currentTarget, true);
        try {
          await API.post(`/api/projects/${pid}/chunks/${c.id}/takes`, { variant: c.takes.length % 3 });
          openProject(pid);
        } catch (err) { toast("Take failed", err.message, "err"); busy(e.currentTarget, false); }
      };
      $("[data-saveedit]", el).onclick = async () => {
        await API.patch(`/api/projects/${pid}/chunks/${c.id}`, { text: $("[data-edit]", el).value });
        toast("Chunk updated", "Old takes still match the old text — regenerate for the new one.");
      };
      $("[data-delchunk]", el).onclick = async () => {
        if (await confirmModal("Delete chunk?", "Its takes will be removed too.", "Delete")) {
          await API.del(`/api/projects/${pid}/chunks/${c.id}`); openProject(pid);
        }
      };
    });

    const doExport = async (fmt) => {
      const out = $("#dr-exp-out", page);
      out.innerHTML = `<div class="progress indet"><i></i></div>
        <div class="progress-label"><span>Stitching selected takes…</span><span>ffmpeg</span></div>`;
      try {
        const res = await API.post(`/api/projects/${pid}/export`, { fmt, gap: 0.45, isolate: true });
        out.innerHTML = "";
        out.appendChild(audioCard({ ...res.export, voice_name: "export", audio_url: res.export.url }));
        toast("Exported", res.export.file);
      } catch (err) {
        out.innerHTML = `<div class="banner err">✕ <div>${esc(err.message)}</div></div>`;
      }
    };
    $("#dr-exp", page).onclick = () => doExport("wav");
    $("#dr-export-mp3", page).onclick = () => doExport("mp3");
  }
}

/* ============================================================
   Agent Studio
   ============================================================ */

export async function agent(page) {
  const voices = await voicesSafe();
  const conns = await API.get("/api/connections").then((r) => r.connections).catch(() => null);
  page.innerHTML = shell(`
    ${pageHead("Agent Studio", "One prompt → script → scenes → cloned narration → rendered video. Every stage streams live feedback and waits for your approval when asked.", "Agent")}
    ${!conns?.text?.base_url ? `<div class="banner warn">! <div><b>No text provider connected.</b> The Agent needs one LLM for scriptwriting — connect it below first.</div></div>` : ""}
    <div class="grid c2" style="gap:20px" id="ag-grid">
      <div class="panel">
        <label class="field"><span>Video prompt</span>
          <textarea id="ag-prompt" rows="4" placeholder="A 60-second explainer about why faceless creators should own their voice — warm, confident tone."></textarea></label>
        <div class="grid c2" style="gap:12px">
          <label class="field"><span>Target duration (seconds)</span>
            <input type="text" id="ag-dur" value="60"></label>
          <label class="field"><span>Narration voice</span>
            <select id="ag-voice">${groupedVoiceOptions(voices)}</select></label>
          <label class="field"><span>Audio source</span>
            <select id="ag-audio"><option value="local">Local cloned voice (free)</option>
              <option value="provider">Connected audio model</option></select></label>
          <label class="field"><span>Timing fit</span>
            <select id="ag-fit"><option value="natural">Natural (visuals follow audio)</option>
              <option value="strict">Strict (fit to target duration)</option></select></label>
        </div>
        <label class="field"><span>Attachments — images / video (optional, needs vision model)</span>
          <input type="file" id="ag-att" multiple accept="image/*,video/*"></label>
        <label class="checkbox"><input type="checkbox" id="ag-confirm" checked>
          <span>Ask me to approve the script and the audio before rendering</span></label>
        <div class="row" style="margin-top:14px">
          <button class="btn accent lg" id="ag-go">${icon("spark", 17)} &nbsp;Start agent run</button>
        </div>
      </div>
      <div class="panel flush" style="display:flex;flex-direction:column">
        <div class="panel-head"><h3>Live pipeline</h3><span class="pill" id="ag-state">idle</span></div>
        <div id="ag-log" class="small" style="padding:14px 18px;overflow:auto;flex:1;max-height:430px;background:var(--paper)"></div>
        <div id="ag-progress" style="padding:12px 18px;border-top:1px solid var(--line)"></div>
        <div id="ag-result" style="padding:0 18px 16px"></div>
      </div>
    </div>`);
  if (innerWidth < 900) $("#ag-grid", page).style.gridTemplateColumns = "1fr";

  const log = $("#ag-log", page);
  const addLog = (msg, cls = "muted") => {
    const div = document.createElement("div");
    div.className = cls;
    div.style.marginBottom = "6px";
    div.innerHTML = `<span class="mono-num">${new Date().toLocaleTimeString()}</span> — ${esc(msg)}`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  };

  $("#ag-go", page).onclick = async (e) => {
    const prompt = $("#ag-prompt", page).value.trim();
    if (!prompt) return toast("Write a prompt", "What should the video be about?", "warn");
    // upload attachments first
    const atts = [];
    const files = [...($("#ag-att", page).files || [])];
    if (files.length) {
      addLog(`Uploading ${files.length} attachment(s)…`);
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await API.postForm("/api/agent/upload", fd);
        atts.push(r.path);
      }
    }
    busy(e.currentTarget, true);
    addLog("Starting agent run…", "");
    try {
      const res = await API.post("/api/agent/start", {
        prompt, duration: parseFloat($("#ag-dur", page).value) || 60,
        voice_id: $("#ag-voice", page).value,
        audio_source: $("#ag-audio", page).value,
        fit: $("#ag-fit", page).value,
        confirm: $("#ag-confirm", page).checked,
        attachments: atts,
      });
      listen(res.job.id, e.currentTarget);
    } catch (err) {
      busy(e.currentTarget, false);
      toast("Could not start", err.message, "err");
    }
  };

  function setProgress(stage, pct, label) {
    $("#ag-progress", page).innerHTML = `
      <div class="progress ${pct >= 1 ? "" : "indet"}"><i style="width:${Math.round(pct * 100)}%"></i></div>
      <div class="progress-label"><span>${esc(label || stage)}</span><span>${Math.round(pct * 100)}%</span></div>`;
  }

  function listen(jid, btn) {
    $("#ag-state", page).textContent = "running";
    setProgress("start", 0, "Starting…");
    const es = new EventSource(abs(`/api/agent/${jid}/events`));
    es.onmessage = (m) => {
      let ev; try { ev = JSON.parse(m.data); } catch { return; }
      switch (ev.type) {
        case "stage_start":
          addLog(`${icon("play", 11)} ${ev.stage}: ${ev.message || ""}`, "");
          setProgress(ev.stage, 0, ev.message);
          break;
        case "stage_progress":
          addLog(ev.message);
          setProgress(ev.stage, ev.pct || 0, ev.message);
          break;
        case "stage_done":
          addLog(`✓ ${ev.stage}: ${ev.message || ""}`, "");
          setProgress(ev.stage, 1, ev.message);
          if (ev.data?.scenes) ev._scenes = ev.data.scenes;
          if (ev.stage === "script" || ev.stage === "audio") lastScenes(ev, jid);
          break;
        case "info": addLog(ev.message); break;
        case "warning": addLog(`⚠ ${ev.message}`, "muted"); toast("Heads up", ev.message, "warn"); break;
        case "awaiting_confirmation": askConfirm(jid, ev); break;
        case "done":
          addLog(`✓ DONE — ${ev.message}`, "");
          es.close();
          $("#ag-state", page).textContent = "done";
          setProgress("done", 1, "Video ready");
          busy(btn, false);
          const r = ev.result;
          $("#ag-result", page).innerHTML = `
            <div class="stack" style="padding-top:12px">
              <video src="${abs(r.video_url)}" controls style="width:100%;border-radius:10px"></video>
              <div class="row">
                <a class="btn accent" href="${abs(r.video_url)}" download="${esc(r.file)}">${icon("download", 15)} Download video</a>
                <span class="pill ok">${esc(r.title || "")}</span>
                <span class="pill">${r.scenes} scenes · ${r.duration}s</span>
              </div>
            </div>`;
          toast("Video ready", r.file);
          break;
        case "error":
          addLog(`✕ ${ev.message}`, "");
          es.close();
          $("#ag-state", page).textContent = "error";
          busy(btn, false);
          toast("Agent failed", ev.message, "err");
          break;
      }
    };
    es.onerror = () => { /* keep-alive pings; ignore */ };
  }

  let pendingScenes = null;
  function lastScenes(ev, jid) {
    pendingScenes = ev.data?.scenes || null;
    _jid = jid;
  }
  let _jid = null;

  function askConfirm(jid, ev) {
    $("#ag-state", page).textContent = "awaiting you";
    addLog(`⏸ Waiting for your approval — ${ev.stage}`, "");
    const isScript = ev.stage === "script";
    const payload = ev.payload || {};
    const body = document.createElement("div");
    if (isScript) {
      body.innerHTML = `<p class="small muted" style="margin-top:0">Edit narration freely — visuals follow. Then approve.</p>
        <div class="stack" data-scenes>
        ${(payload.scenes || []).map((s, i) => `
          <div class="panel" style="padding:12px 14px">
            <div class="small muted">#${i + 1} · ${esc(s.visual?.type || "")}</div>
            <label class="field" style="margin:6px 0 0"><span>Narration</span>
              <textarea rows="2" data-nar="${i}">${esc(s.narration || "")}</textarea></label>
          </div>`).join("")}
        </div>`;
    } else {
      body.innerHTML = `<p class="small" style="margin-top:0">Audio is ready for all scenes. Approve to render the video.</p>`;
    }
    const foot = document.createElement("div");
    foot.innerHTML = `<button class="btn danger" data-a="cancel">Cancel run</button>
      <button class="btn accent" data-a="ok">✓ Approve & continue</button>`;
    modal({
      title: isScript ? "Approve the script" : "Approve the audio",
      body, footer: foot,
      onMount: (veil) => {
        $("[data-a='cancel']", veil).onclick = () => {
          API.post(`/api/agent/${jid}/confirm`, { cancel: true });
          veil.remove();
          addLog("✕ Cancelled by user.", "");
        };
        $("[data-a='ok']", veil).onclick = () => {
          let payloadOut = null;
          if (isScript && payload.scenes) {
            const scenes = payload.scenes.map((s, i) => ({
              ...s,
              narration: $(`[data-nar="${i}"]`, veil)?.value ?? s.narration,
            }));
            payloadOut = { title: payload.title, scenes };
          }
          API.post(`/api/agent/${jid}/confirm`, { payload: payloadOut });
          veil.remove();
          $("#ag-state", page).textContent = "running";
          addLog("✓ Approved — continuing…", "");
        };
      },
    });
  }
}

/* ============================================================
   Connections
   ============================================================ */

export async function connections(page) {
  const res = await API.get("/api/connections").catch(() => null);
  const c = res?.connections || {};
  const modelsState = {};
  for (const k of ["text", "audio", "visual"]) {
    modelsState[k] = [...(c[k]?.models || [])];
  }

  const chipsHTML = (kind, v) => `
    <label class="field"><span>Model IDs — failover order (add one or many)</span>
      <div class="chips" data-chips="${kind}" data-empty="No models yet — add the first one below">
        ${(v.models || []).map((m) => `
          <span class="chip">${esc(m)}<button class="x" data-rm="${esc(m)}" title="Remove">✕</button></span>`).join("")}
      </div>
      <div class="chip-add">
        <input type="text" data-newmodel="${kind}" placeholder="model id, e.g. gpt-4o-mini / gemini-2.0-flash / deepseek-chat">
        <button class="btn sm" data-add="${kind}">${icon("plus", 14)} &nbsp;Add</button>
      </div>
    </label>`;

  const card = (kind, label, extra = "") => {
    const v = c[kind] || {};
    return `
      <div class="panel" data-kind="${kind}">
        <div class="spread"><h3 style="margin:0">${esc(label)}</h3>
          <span class="pill ${v.has_key ? "ok" : ""}" data-state>${v.has_key ? "key saved" : "not configured"}</span></div>
        <label class="field"><span>Base URL (OpenAI-compatible)</span>
          <input type="url" data-f="base_url" value="${esc(v.base_url || "")}" placeholder="https://api.openai.com/v1"></label>
        <label class="field"><span>API key ${v.has_key ? "(saved — type to replace)" : ""}</span>
          <input type="password" data-f="api_key" placeholder="${v.has_key ? "•••••••• (leave empty to keep)" : "sk-…"}"></label>
        ${chipsHTML(kind, v)}
        ${extra}
        <div class="row" style="margin-top:14px"><button class="btn sm" data-test>Test connection</button>
          <span class="small muted" data-testmsg></span></div>
      </div>`;
  };

  page.innerHTML = shell(`
    ${pageHead("Connections", "Bring your own OpenAI-compatible endpoints. Keys stay in a local file on this machine — never in the cloud. If a model id fails, the agent retries the next one with the same context.", "Agent")}
    <div class="stack">
      ${card("text", "Text model — script writing",
        `<label class="checkbox"><input type="checkbox" data-f="vision" ${c.text?.vision ? "checked" : ""}>
          <span>This model accepts images (vision) — needed for attachments</span></label>`)}
      ${card("audio", "Audio model — narration (optional)",
        `<label class="field"><span>Voice name for /audio/speech (e.g. alloy)</span>
          <input type="text" data-f="voice" value="${esc(c.audio?.voice || "")}"></label>`)}
      ${card("visual", "Visual model — scene images (optional)")}
    </div>
    <div class="row" style="margin-top:18px">
      <button class="btn accent" id="cn-save">Save connections</button>
      <span class="small muted" id="cn-msg"></span>
    </div>`);

  const wireChips = () => {
    $$("[data-add]", page).forEach((b) => {
      b.onclick = () => {
        const kind = b.dataset.add;
        const input = $(`[data-newmodel="${kind}"]`, page);
        const val = (input.value || "").trim();
        if (!val) return;
        for (const m of val.split(",").map((x) => x.trim()).filter(Boolean)) {
          if (!modelsState[kind].includes(m)) modelsState[kind].push(m);
        }
        input.value = "";
        renderChips(kind);
      };
    });
    $$("[data-chips] .x", page).forEach((x) => {
      x.onclick = () => {
        const kind = x.closest("[data-chips]").dataset.chips;
        modelsState[kind] = modelsState[kind].filter((m) => m !== x.dataset.rm);
        renderChips(kind);
      };
    });
  };

  const renderChips = (kind) => {
    const box = $(`[data-chips="${kind}"]`, page);
    box.innerHTML = modelsState[kind].map((m) =>
      `<span class="chip">${esc(m)}<button class="x" data-rm="${esc(m)}" title="Remove">✕</button></span>`).join("");
    wireChips();
  };
  wireChips();

  const gather = () => {
    const out = {};
    $$(".panel[data-kind]", page).forEach((p) => {
      const kind = p.dataset.kind;
      const g = (f) => $(`[data-f="${f}"]`, p)?.value?.trim();
      out[kind] = {
        base_url: g("base_url"),
        api_key: g("api_key") || "",
        models: modelsState[kind] || [],
      };
      if (kind === "text") out[kind].vision = $('[data-f="vision"]', p)?.checked || false;
      if (kind === "audio") out[kind].voice = g("voice") || "";
    });
    return out;
  };

  $$("[data-test]", page).forEach((b) => {
    b.onclick = async () => {
      await API.post("/api/connections", { connections: gather() });
      const kind = b.closest(".panel").dataset.kind;
      const msg = $("[data-testmsg]", b.closest(".panel"));
      msg.textContent = "testing…";
      const r = await API.post("/api/connections/test", { kind });
      msg.textContent = r.test.ok ? "✓ reachable" : `✕ ${r.test.error || r.test.status}`;
      msg.style.color = r.test.ok ? "var(--green)" : "var(--verm)";
    };
  });

  $("#cn-save", page).onclick = async (e) => {
    busy(e.currentTarget, true);
    try {
      await API.post("/api/connections", { connections: gather() });
      $("#cn-msg", page).textContent = "Saved. Keys live in the local data folder only.";
      toast("Connections saved");
      render();
    } catch (err) { toast("Save failed", err.message, "err"); }
    finally { busy(e.currentTarget, false); }
  };
}

/* ============================================================
   DubHub — any-language media, dubbed into your language
   ============================================================ */

export async function dubhub(page) {
  const voices = await voicesSafe();
  let dub = null;          // ingest result (state.json mirror)
  let lines = [];          // translated lines, editable
  let src = "en-us";
  let target = "bn";

  const SRC_LABELS = {
    "en-us": "English", "es": "Español", "fr": "Français", "zh-cn": "中文",
    "ja": "日本語", "ko": "한국어", "de": "Deutsch", "it": "Italiano",
    "pt": "Português", "ru": "Русский", "hi": "हिन्दी", "tr": "Türkçe",
    "vi": "Tiếng Việt", "nl": "Nederlands",
  };

  page.innerHTML = shell(`
    ${pageHead("DubHub", "Feed it any video or audio. Every spoken line gets translated into the language you pick, then re-voiced by your cloned voice — timing preserved.", "Tools")}
    <div class="grid balanced" id="dh-grid">
      <div class="panel">
        <label class="field"><span>Media — video or audio, any language</span>
          <div class="dropzone" id="dh-dz">
            <div class="dz-ico">${icon("upload", 26)}</div>
            <h4>Drop the file here</h4>
            <p>mp4 · mov · mkv · webm · wav · mp3 · m4a</p>
            <input type="file" id="dh-file" accept="audio/*,video/*,.wav,.mp3,.m4a,.mp4,.mov,.mkv,.webm" hidden>
          </div>
        </label>
        <label class="field"><span>Spoken language (source)</span>
          <select id="dh-src">
            ${Object.entries(SRC_LABELS).map(([k, l]) => `<option value="${k}" ${k === "en-us" ? "selected" : ""}>${l}</option>`).join("")}
          </select>
        </label>
        <button class="btn accent" id="dh-ingest">${icon("waveform", 16)} &nbsp;Transcribe media</button>
        <div id="dh-ingest-progress" style="margin-top:var(--s4)"></div>
      </div>

      <div class="panel" id="dh-step2" style="display:none">
        <h3 style="margin:0 0 var(--s2)">Translate</h3>
        <div class="row wrap" style="margin-bottom:var(--s3)">
          <span class="small muted" id="dh-src-line"></span>
        </div>
        <label class="field"><span>Dub into</span>
          <select id="dh-target"></select>
        </label>
        <button class="btn accent" id="dh-translate">${icon("globe", 16)} &nbsp;Translate lines</button>
        <div class="small muted" style="margin-top:var(--s2)">First use of a language pair downloads the local NLLB model (~1.2 GB), then everything stays offline.</div>
        <div id="dh-translate-progress" style="margin-top:var(--s4)"></div>
      </div>
    </div>

    <section class="dash-section" id="dh-lines-section" style="display:none">
      <h2 class="dash-h2">Lines. <span class="lp-dim">Fix any translation before dubbing.</span></h2>
      <div class="dh-lines" id="dh-lines"></div>
    </section>

    <section class="dash-section" id="dh-render-section" style="display:none">
      <h2 class="dash-h2">Dub it. <span class="lp-dim">Your voice, new language, original timing.</span></h2>
      <div class="grid c2">
        <div class="panel">
          <label class="field"><span>Dub voice</span>
            <select id="dh-voice">${groupedVoiceOptions(voices)}</select>
          </label>
          <button class="btn accent lg" id="dh-go">${icon("play", 17)} &nbsp;Render dub</button>
          <div class="small muted" style="margin-top:var(--s2)">CPU renders every line, fits it into the original timing, then muxes the video.</div>
        </div>
        <div class="panel" id="dh-result">
          <h3 style="margin:0 0 var(--s2)">Result</h3>
          <div id="dh-out">${emptyStateHTML()}</div>
        </div>
      </div>
    </section>
  `);

  function emptyStateHTML() {
    return `<div class="empty"><div class="e-ico">${icon("video", 34)}</div>
      <p style="margin:0">The dubbed track will land here.</p></div>`;
  }

  const dz = $("#dh-dz", page), fi = $("#dh-file", page);
  dz.onclick = () => fi.click();
  fi.onchange = () => {
    if (fi.files[0]) dz.querySelector("h4").textContent = fi.files[0].name;
  };
  ["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) { const dt = new DataTransfer(); dt.items.add(f); fi.files = dt.files; dz.querySelector("h4").textContent = f.name; }
  });

  // ---- step 1: transcribe ----
  $("#dh-ingest", page).onclick = async (e) => {
    if (!fi.files[0]) return toast("Pick a file", "Drop a video or audio first.", "warn");
    src = $("#dh-src", page).value;
    const btn = e.currentTarget;
    busy(btn, true);
    $("#dh-ingest-progress", page).innerHTML = `
      <div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Transcribing with word timings…</span><span>CPU</span></div>`;
    try {
      const fd = new FormData();
      fd.append("file", fi.files[0]);
      fd.append("lang", src);
      const res = await API.postForm("/api/dubbing/ingest", fd);
      dub = res.dub;
      lines = [];
      $("#dh-src-line", page).textContent =
        `${dub.segments.length} lines · ${fmtDur(dub.duration)} · ${SRC_LABELS[src] || src}`;
      $("#dh-step2", page).style.display = "";
      $("#dh-step2", page).scrollIntoView({ behavior: "smooth", block: "center" });
      $("#dh-ingest-progress", page).innerHTML = "";
      toast("Transcribed", `${dub.segments.length} spoken lines found.`);
    } catch (err) {
      $("#dh-ingest-progress", page).innerHTML = "";
      toast("Transcribe failed", err.message, "err", 7000);
    } finally { busy(btn, false); }
  };

  // ---- step 2: translate ----
  API.get("/api/dubhub/langs").then((r) => {
    const sel = $("#dh-target", page);
    if (!sel) return;
    sel.innerHTML = r.targets.map((k) =>
      `<option value="${k}" ${k === target ? "selected" : ""}>${esc(langLabel(k))}</option>`).join("");
    sel.value = target;
  }).catch(() => {});

  $("#dh-translate", page).onclick = async (e) => {
    if (!dub) return toast("Transcribe first", "Analyze the media before translating.", "warn");
    target = $("#dh-target", page).value;
    const btn = e.currentTarget;
    busy(btn, true);
    $("#dh-translate-progress", page).innerHTML = `
      <div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Translating locally (first run downloads the model)…</span><span>CPU</span></div>`;
    try {
      const res = await API.post(`/api/dubhub/${dub.id}/translate`, { target });
      lines = res.lines;
      $("#dh-lines", page).innerHTML = dub.segments.map((s, i) => `
        <div class="dh-line">
          <div class="dh-line-src"><span class="mono-num">${String(i + 1).padStart(2, "0")}</span> ${esc(s.text)}</div>
          <textarea data-line="${i}" rows="2">${esc(lines[i] || "")}</textarea>
        </div>`).join("");
      $("#dh-lines-section", page).style.display = "";
      $("#dh-render-section", page).style.display = "";
      $("#dh-translate-progress", page).innerHTML = "";
      toast("Translated", `${res.count} lines → ${langLabel(target)}.`);
    } catch (err) {
      $("#dh-translate-progress", page).innerHTML = "";
      toast("Translation failed", err.message, "err", 7000);
    } finally { busy(btn, false); }
  };

  // ---- step 3: render ----
  $("#dh-go", page).onclick = async (e) => {
    if (!dub) return;
    // pick up manual edits
    $$("#dh-lines textarea", page).forEach((t) => { lines[+t.dataset.line] = t.value; });
    const btn = e.currentTarget;
    busy(btn, true);
    $("#dh-out", page).innerHTML = `
      <div class="progress indet"><i></i></div>
      <div class="progress-label"><span>Dubbing every line — this renders one clip per line…</span><span>CPU</span></div>`;
    try {
      const res = await API.post(`/api/dubhub/${dub.id}/render`,
        { voice_id: $("#dh-voice", page).value, tau: 0.3, speed: 1.0 });
      const out = $("#dh-out", page);
      out.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.innerHTML = `
        <div class="dash-clip" style="grid-template-columns:auto 1fr">
          <button class="btn sm accent" data-play>${icon("play", 14)}</button>
          <div data-wave></div>
        </div>
        <div class="row wrap" style="margin-top:var(--s3)">
          <a class="btn sm" href="${abs(res.audio.url)}" download="${res.audio.file}">${icon("download", 14)} Dubbed audio</a>
          ${res.video ? `<a class="btn sm accent" href="${abs(res.video.url)}" download="${esc(res.video.file)}">${icon("video", 14)} Dubbed video</a>` : ""}
        </div>`;
      out.appendChild(wrap);
      const wb = new WaveBox(wrap.querySelector("[data-wave]"), res.audio.url, { height: 56 });
      wb.load();
      const pb = wrap.querySelector("[data-play]");
      wb.onPlayState = (playing) => { pb.innerHTML = playing ? icon("stop", 13) : icon("play", 13); };
      pb.onclick = () => wb.toggle();
      $("#dh-render-section", page).scrollIntoView({ behavior: "smooth", block: "center" });
      toast("Dub rendered", `${langLabel(target)} audio${res.video ? " + muxed video" : ""} ready.`);
    } catch (err) {
      $("#dh-out", page).innerHTML = emptyStateHTML();
      toast("Dub failed", err.message, "err", 8000);
    } finally { busy(btn, false); }
  };
}

/* ============================================================
   Cartoon Studio — one free 2D cartoon per day (cloud pipeline)
   ============================================================ */

const CARTOON_CLIENT = (() => {
  try {
    let id = localStorage.getItem("ivClientId");
    if (!id) { id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)); localStorage.setItem("ivClientId", id); }
    return id;
  } catch { return "anon"; }
})();

async function cApi(path, opts = {}) {
  const res = await fetch(abs(path), {
    ...opts,
    headers: { "X-IV-Client-Id": CARTOON_CLIENT, ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || (data && data.ok === false)) {
    throw new Error(data?.error || `Request failed (${res.status})`);
  }
  return data;
}

export async function cartoon(page, seq, fresh) {
  const $ = (sel) => page.querySelector(sel);
  if (window.__ctPoll) { clearInterval(window.__ctPoll); window.__ctPoll = null; }

  let quotaData = null;
  try { quotaData = await cApi("/api/cartoon/quota"); } catch { /* engine offline */ }
  if (!fresh()) return;
  const active = quotaData?.active;
  const quota = quotaData?.quota;
  const configured = quotaData?.configured;

  page.innerHTML = shell(`
    ${pageHead("Cartoon Studio", "Type a story idea — a full cartoon (script, scenes, narration, music) is generated for you. One free cartoon per day.", "Agent")}
    ${!state.system ? `<div class="banner err">✕ <div><b>Engine unreachable.</b><br>Cartoons are generated by your local InsaneVoice engine — start it, then connect (see Settings).</div></div>` : ""}
    ${state.system && !configured ? `<div class="banner err">✕ <div><b>Cartoon providers not configured.</b><br>Add <code>data/cartoon_providers.json</code> in the engine's data folder.</div></div>` : ""}
    ${quota && quota.remaining <= 0 && !active ? `
      <div class="banner warn">◍ <div><b>Today's free cartoon is used.</b><br>The counter resets at midnight — come back tomorrow.</div></div>` : ""}
    <div class="panel">
      <label class="field"><span>Story idea (optional — leave blank for the classic Pip story)</span>
        <textarea id="ct-idea" maxlength="400" placeholder="e.g. a little cat who dreams of flying, or a robot learning to dance"></textarea>
      </label>
      <div class="row wrap" style="margin-top:var(--s2);gap:8px" id="ct-mode">
        <button class="chip ok" data-mode="motion">✦ Motion cartoon — animated scenes, frame-by-frame</button>
        <button class="chip" data-mode="storybook">▢ Storybook — illustrated stills</button>
      </div>
      <div class="row wrap" style="margin-top:var(--s2);align-items:center">
        <button class="btn accent" id="ct-go" ${(!configured || (quota && quota.remaining <= 0 && !active)) ? "disabled" : ""}>
          ${icon("video", 15)} Generate my cartoon
        </button>
        <span class="pill ${quota && quota.remaining > 0 ? "ok" : ""}">${quota ? `Today: ${quota.used}/${quota.limit} · ${quota.remaining > 0 ? `${quota.remaining} left` : "used up"}` : "Quota unknown"}</span>
      </div>
      <div id="ct-progress" style="margin-top:14px"></div>
    </div>
    <div id="ct-result"></div>
    <div class="panel" style="margin-top:18px" id="ct-lib-panel">
      <h3 style="margin:0 0 8px">Recent cartoons on this engine</h3>
      <div id="ct-lib" class="small muted">Loading…</div>
    </div>
  `);
  let ctMode = "motion";
  page.querySelectorAll("#ct-mode .chip").forEach((ch) => ch.addEventListener("click", () => {
    ctMode = ch.dataset.mode;
    page.querySelectorAll("#ct-mode .chip").forEach((c) => c.classList.toggle("ok", c === ch));
  }));

  const setProgress = (pct, label) => {
    $("#ct-progress").innerHTML = `
      <div class="progress ${pct >= 1 ? "" : "indet"}"><i style="width:${Math.round(pct * 100)}%"></i></div>
      <div class="progress-label"><span>${esc(label || "")}</span><span>${Math.round(pct * 100)}%</span></div>`;
  };

  const showDone = (job) => {
    const url = abs(`/api/cartoon/${job.id}/video`);
    $("#ct-progress").innerHTML = "";
    $("#ct-result").innerHTML = `
      <div class="panel">
        <h3 style="margin:0 0 10px">${icon("video", 15)} ${esc(job.title || "Your cartoon")}</h3>
        <video src="${url}" controls style="width:100%;border-radius:10px"></video>
        <div class="row wrap" style="margin-top:12px">
          <a class="btn accent" href="${url}" download="insanevoice_cartoon.mp4">${icon("download", 15)} Download MP4</a>
          <span class="pill ok">Done · ${job.duration || "?"}s · 1080p</span>
        </div>
      </div>`;
  };

  const showJob = (job) => {
    setProgress(job.progress || 0, job.message || job.stage);
    if (job.status === "done") {
      clearInterval(window.__ctPoll); window.__ctPoll = null;
      showDone(job);
      refreshLibrary();
    } else if (job.status === "error") {
      clearInterval(window.__ctPoll); window.__ctPoll = null;
      $("#ct-progress").innerHTML = `<div class="banner err">✕ <div><b>Generation failed.</b><br>${esc(job.error || job.message || "")}</div></div>`;
    }
  };

  const listen = (job) => {
    const btn = $("#ct-go");
    if (btn) { btn.disabled = true; btn.innerHTML = `${icon("video", 15)} Generating…`; }
    showJob(job);
    window.__ctPoll = setInterval(async () => {
      try {
        const r = await cApi(`/api/cartoon/${job.id}`);
        if (!fresh()) { clearInterval(window.__ctPoll); window.__ctPoll = null; return; }
        showJob(r.job);
      } catch { /* transient */ }
    }, 2500);
  };

  async function refreshLibrary() {
    try {
      const r = await cApi("/api/cartoon/library");
      const vids = r.videos || [];
      $("#ct-lib").innerHTML = vids.length ? vids.map((v) => `
        <div class="stack" style="margin-bottom:14px">
          <div class="row"><b>${esc(v.title)}</b><span class="pill">${v.duration || "?"}s</span></div>
          <video src="${abs(`/api/cartoon/${v.id}/video`)}" controls preload="metadata" style="width:100%;max-width:520px;border-radius:10px"></video>
        </div>`).join("") : "No cartoons yet — generate your first one above.";
    } catch { $("#ct-lib").textContent = "Library unavailable."; }
  }
  refreshLibrary();

  if (active) listen(active);

  $("#ct-go")?.addEventListener("click", async (e) => {
    const idea = $("#ct-idea").value.trim();
    busy(e.currentTarget, true);
    try {
      const r = await cApi("/api/cartoon", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea, mode: ctMode }),
      });
      toast("Cartoon started", "Script → scenes → narration → render. Takes a few minutes.", "ok");
      listen(r.job);
    } catch (err) {
      toast("Could not start", err.message, "err", 8000);
      busy(e.currentTarget, false);
    }
  });
}
