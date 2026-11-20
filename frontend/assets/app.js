/* InsaneVoice — app shell: state, api, router, navigation */

import { toast, sk, esc, stopAllPlayers } from "./components.js";
import { icon } from "./icons.js";
import * as pages from "./pages.js";
import * as pages2 from "./pages2.js";
import { abs, apiBase, setApiBase } from "./net.js";
import { t, lang, toggle as langToggle } from "./i18n.js";

/* ---------- api ---------- */

async function api(path, opts = {}) {
  const res = await fetch(abs(path), opts);
  let data = null;
  try { data = await res.json(); } catch { /* non-json */ }
  if (!res.ok || (data && data.ok === false)) {
    const msg = data?.error || `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const API = {
  get: (p) => api(p),
  post: (p, body) => api(p, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }),
  patch: (p, body) => api(p, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }),
  postForm: (p, form) => api(p, { method: "POST", body: form }),
  del: (p) => api(p, { method: "DELETE" }),
};

/* ---------- global state ---------- */

export const state = {
  system: null,
  voices: [],
  route: "dashboard",
};

export async function refreshSystem() {
  try {
    state.system = await API.get("/api/system");
  } catch {
    state.system = null;
  }
  renderFoot();
  return state.system;
}

export async function refreshVoices() {
  try {
    state.voices = (await API.get("/api/voices")).voices;
  } catch {
    state.voices = [];
  }
  updateNavBadges();
}

function footState() {
  const s = state.system;
  if (!s) return ["err", "Backend unreachable"];
  if (!s.models_present) return ["warn", "Models not downloaded"];
  const st = s.engine?.status;
  if (st === "ready") return ["ok", "Engine ready · CPU"];
  if (st === "loading") return ["load", "Engine loading…"];
  if (st === "error") return ["err", "Engine error"];
  return ["load", "Engine idle"];
}

function renderFoot() {
  const [cls, text] = footState();
  const dot = document.querySelector("#side-foot .dot");
  const t = document.getElementById("foot-text");
  if (dot) dot.className = `dot ${cls}`;
  if (t) t.textContent = text;
}

/* ---------- router ---------- */

const ROUTES = {
  landing:    { title: "Welcome",              render: pages.landing,   landing: true },
  dashboard:  { title: "Dashboard",        render: pages.dashboard,  group: "Overview" },
  gallery:    { title: "Gallery",          render: pages2.gallery,   group: "Overview" },
  /* Create — every studio that makes something */
  studio:     { title: "Studio",           render: pages.studio,     group: "Create" },
  director:   { title: "Director's Studio",render: pages2.director,  group: "Create" },
  batch:      { title: "Batch Studio",     render: pages.batch,      group: "Create" },
  cartoon:    { title: "Cartoon Studio",   render: pages2.cartoon,   group: "Create" },
  agent:      { title: "Agent Studio",     render: pages2.agent,     group: "Create" },
  /* Voices — clone, design, transform */
  dna:        { title: "Voice DNA",        render: pages.dna,        group: "Voices" },
  recorder:   { title: "Recorder",         render: pages.recorder,   group: "Voices" },
  library:    { title: "Voice Library",    render: pages.library,    group: "Voices" },
  design:     { title: "Voice Design",     render: pages2.design,    group: "Voices" },
  changer:    { title: "Voice Changer",    render: pages2.changer,   group: "Voices" },
  /* Tools */
  isolate:    { title: "Voice Isolator",   render: pages2.isolate,   group: "Tools" },
  transcribe: { title: "Transcribe",       render: pages2.transcribe,group: "Tools" },
  dubbing:    { title: "Dubbing Studio",   render: pages2.dubbing,   group: "Tools" },
  dubhub:     { title: "DubHub",           render: pages2.dubhub,    group: "Tools" },
  /* System */
  connections:{ title: "Connections",      render: pages2.connections,group: "System" },
  admin:      { title: "Admin",            render: pages2.admin,     group: "System" },
  history:    { title: "History",          render: pages.history,    group: "System" },
  settings:   { title: "Settings",         render: pages.settings,   group: "System" },
  help:       { title: "Help",             render: pages.help,       group: "System" },
};

function buildNav() {
  const nav = document.getElementById("nav");
  const groups = [];
  for (const [id, r] of Object.entries(ROUTES)) {
    if (r.landing) continue;
    let g = groups.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, items: [] }; groups.push(g); }
    g.items.push([id, r.title]);
  }
  const NAV_ICONS = {
    dashboard: "grid", studio: "type", director: "rows", dna: "radar",
    recorder: "record", library: "stack", design: "wand", changer: "swap",
    batch: "list", isolate: "isolate", transcribe: "doc", dubbing: "video",
    agent: "bolt", connections: "nodes", history: "clock", settings: "sliders",
    help: "help", dubhub: "globe", gallery: "grid", admin: "doc",
  };
  const T = (k, fb) => t(k) || fb;
  const GROUPS = { Overview: "nav_overview", Create: "nav_create", Voices: "nav_voices",
                   Tools: "nav_tools", System: "nav_system" };
  const TITLES = {
    dashboard: "title_dashboard", gallery: "title_gallery", studio: "title_studio",
    director: "title_director", batch: "title_batch", cartoon: "title_cartoon",
    agent: "title_agent", dna: "title_dna", recorder: "title_recorder",
    library: "title_library", design: "title_design", changer: "title_changer",
    isolate: "title_isolate", transcribe: "title_transcribe", dubbing: "title_dubbing",
    dubhub: "title_dubhub", connections: "title_connections", admin: "title_admin",
    history: "title_history", settings: "title_settings", help: "title_help",
  };
  nav.innerHTML = groups.map((g) => `
    <div class="group">${esc(T(GROUPS[g.name], g.name))}</div>
    ${g.items.map(([id, title]) => `
      <button data-route="${id}" title="${esc(T(TITLES[id], title))}">
        <span class="ico">${icon(NAV_ICONS[id] || "grid", 17)}</span>
        <span class="grow">${esc(T(TITLES[id], title))}</span>
        <span class="badge" data-badge="${id}" hidden></span>
      </button>`).join("")}`).join("")
    + `<div class="group">·</div>
       <button id="lang-toggle" title="Language / ভাষা">
         <span class="ico">🌐</span><span class="grow">${lang() === "bn" ? "English" : "বাংলা"}</span>
       </button>`;
  nav.querySelectorAll("button[data-route]").forEach((b) => {
    b.addEventListener("click", () => location.hash = `#/${b.dataset.route}`);
  });
  const lt = document.getElementById("lang-toggle");
  if (lt) lt.addEventListener("click", langToggle);
}

function updateNavBadges() {
  const set = (route, n, show) => {
    const b = document.querySelector(`[data-badge="${route}"]`);
    if (!b) return;
    b.hidden = !show || !n;
    b.textContent = n ?? "";
  };
  set("library", state.voices.length, true);
}

function currentRoute() {
  const h = location.hash.replace(/^#\//, "");
  return ROUTES[h] ? h : "landing";
}

export function nav(route) {
  location.hash = `#/${route}`;
}

let renderSeq = 0;

/* route-change top progress bar */
function topProgress(mode) {
  let el = document.querySelector(".top-progress");
  if (!el) {
    el = document.createElement("div");
    el.className = "top-progress";
    document.body.appendChild(el);
  }
  if (mode === "start") {
    el.style.transition = "none";
    el.style.width = "0";
    void el.offsetWidth;
    el.style.transition = "";
    el.style.width = "38%";
    el.classList.add("on");
  } else {
    el.style.width = "100%";
    setTimeout(() => {
      el.classList.remove("on");
      setTimeout(() => { el.style.width = "0"; }, 400);
    }, 220);
  }
}

/* one staggered reveal pass per route render */
function observeReveals(page) {
  const els = [...page.querySelectorAll(".panel, .banner, .list-row, .voice-card, .stat, .lp-section, .lp-clip, .lp-tool")]
    .filter((el) => !el.closest(".hero"));   // hero runs its own load sequence
  els.forEach((el, i) => {
    el.classList.add("reveal");
    el.style.setProperty("--d", Math.min(i * 45, 270) + "ms");
  });
  if (!("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver((ents) => {
    ents.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    });
  }, { threshold: .06 });
  els.forEach((el) => io.observe(el));
}

export async function render() {
  const route = currentRoute();
  state.route = route;
  document.body.classList.toggle("route-landing", route === "landing");
  if (window.__lpCleanup) { try { window.__lpCleanup(); } catch { /* page gone */ } window.__lpCleanup = null; }
  document.querySelectorAll(".nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === route));
  const page = document.getElementById("page");
  const seq = ++renderSeq;
  stopAllPlayers();              // audio from the previous page stops here
  topProgress("start");
  page.innerHTML = `<div style="margin-top:6px">${sk.page()}</div>`;
  window.scrollTo(0, 0);
  const def = ROUTES[route];
  document.title = route === "landing"
    ? "InsaneVoice — Type. It speaks."
    : `${def.title} — InsaneVoice`;
  try {
    await def.render(page, seq, () => seq === renderSeq);
  } catch (e) {
    if (seq !== renderSeq) return;
    page.innerHTML = `
      <div class="banner err">✕ <div><b>${esc(def.title)} failed to load.</b><br>${esc(e.message)}</div></div>`;
  }
  if (seq === renderSeq) observeReveals(page);
  topProgress("done");
  updateNavBadges();
}

window.addEventListener("hashchange", render);

/* ---------- boot ---------- */

/* Hosted-UI mode: this static site isn't served by the engine, so if the
   same-origin API is missing, try the default local engine once and remember it. */
/* Find an engine to connect to. Order: same-origin (UI served by the engine
   itself) -> the site's published public engine (engine.json — e.g. a
   cloudflared tunnel; works from phones and anywhere) -> a local engine on
   this machine (desktop case). */
async function autodetectEngine() {
  if (apiBase()) return false;
  // 1. same-origin API — UI served by the engine itself
  try {
    const res = await fetch("/api/system", { signal: AbortSignal.timeout(1500) });
    if (res.ok) { setApiBase(""); return true; }
  } catch { /* not engine-served */ }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  if (!local) {
    // 2. published public engine for this site (mobile / remote visitors)
    try {
      const cfg = await fetch("/engine.json", { signal: AbortSignal.timeout(1500) })
        .then((r) => (r.ok ? r.json() : null));
      const url = (cfg?.engineUrl || "").replace(/\/+$/, "");
      if (url) {
        const res = await fetch(url + "/api/system", { signal: AbortSignal.timeout(6000) });
        if (res.ok) { setApiBase(url); return true; }
      }
    } catch { /* no public engine published */ }
  }
  // 3. local engine on this machine
  if (!local) return false;
  try {
    const res = await fetch("http://127.0.0.1:8177/api/system", { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return false;
    setApiBase("http://127.0.0.1:8177");
    return true;
  } catch { return false; }
}

async function boot() {
  buildNav();
  render();
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
  await refreshSystem();
  if (!state.system && await autodetectEngine()) {
    toast(apiBase() ? "Connected to the InsaneVoice engine" : "Connected to your local InsaneVoice engine", "ok");
    await refreshSystem();
  }
  await refreshVoices();
  render();
  // poll engine status while it loads — only re-render on a real
  // loading → ready transition; intermittent network failures must NOT
  // re-render the whole page (that was the dashboard "constant refresh" bug)
  let lastEng = state.system?.engine?.status ?? null;
  const poll = setInterval(async () => {
    await refreshSystem();
    const eng = state.system?.engine?.status ?? null;
    renderFoot();
    if (lastEng === "loading" && eng && eng !== "loading") {
      if (state.route === "dashboard" || state.route === "settings") render();
    }
    lastEng = eng;
  }, 2500);
  setTimeout(() => clearInterval(poll), 180000);
}

boot();
