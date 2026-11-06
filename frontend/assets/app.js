/* InsaneVoice — app shell: state, api, router, navigation */

import { toast, sk, esc } from "./components.js";
import * as pages from "./pages.js";
import * as pages2 from "./pages2.js";

/* ---------- api ---------- */

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
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
  dashboard:  { title: "Dashboard",        render: pages.dashboard,  group: "Overview" },
  studio:     { title: "Studio",           render: pages.studio,     group: "Create" },
  director:   { title: "Director's Studio",render: pages2.director,  group: "Create" },
  dna:        { title: "Voice DNA",        render: pages.dna,        group: "Create" },
  recorder:   { title: "Recorder",         render: pages.recorder,   group: "Create" },
  library:    { title: "Voice Library",    render: pages.library,    group: "Voices" },
  design:     { title: "Voice Design",     render: pages2.design,    group: "Voices" },
  changer:    { title: "Voice Changer",    render: pages2.changer,   group: "Voices" },
  batch:      { title: "Batch Studio",     render: pages.batch,      group: "Voices" },
  isolate:    { title: "Voice Isolator",   render: pages2.isolate,   group: "Tools" },
  transcribe: { title: "Transcribe",       render: pages2.transcribe,group: "Tools" },
  dubbing:    { title: "Dubbing Studio",   render: pages2.dubbing,   group: "Tools" },
  agent:      { title: "Agent Studio",     render: pages2.agent,     group: "Agent" },
  connections:{ title: "Connections",      render: pages2.connections,group: "Agent" },
  history:    { title: "History",          render: pages.history,    group: "System" },
  settings:   { title: "Settings",         render: pages.settings,   group: "System" },
  help:       { title: "Help",             render: pages.help,       group: "System" },
};

function buildNav() {
  const nav = document.getElementById("nav");
  const groups = [];
  for (const [id, r] of Object.entries(ROUTES)) {
    let g = groups.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, items: [] }; groups.push(g); }
    g.items.push([id, r.title]);
  }
  const ICONS = {
    dashboard: "⌂", studio: "✎", director: "▦", dna: "◉", recorder: "●",
    library: "☰", design: "✦", changer: "⇄", batch: "≡",
    isolate: "◌", transcribe: "✐", dubbing: "▷",
    agent: "★", connections: "⊕",
    history: "↺", settings: "⚙", help: "?",
  };
  nav.innerHTML = groups.map((g) => `
    <div class="group">${esc(g.name)}</div>
    ${g.items.map(([id, title]) => `
      <button data-route="${id}" title="${esc(title)}">
        <span class="ico">${ICONS[id] || "•"}</span>
        <span class="grow">${esc(title)}</span>
        <span class="badge" data-badge="${id}" hidden></span>
      </button>`).join("")}`).join("");
  nav.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => location.hash = `#/${b.dataset.route}`);
  });
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
  return ROUTES[h] ? h : "dashboard";
}

export function nav(route) {
  location.hash = `#/${route}`;
}

let renderSeq = 0;

export async function render() {
  const route = currentRoute();
  state.route = route;
  document.querySelectorAll(".nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === route));
  const page = document.getElementById("page");
  const seq = ++renderSeq;
  page.innerHTML = `<div style="margin-top:6px">${sk.page()}</div>`;
  window.scrollTo(0, 0);
  const def = ROUTES[route];
  document.title = `${def.title} — InsaneVoice`;
  try {
    await def.render(page, seq, () => seq === renderSeq);
  } catch (e) {
    if (seq !== renderSeq) return;
    page.innerHTML = `
      <div class="banner err">✕ <div><b>${esc(def.title)} failed to load.</b><br>${esc(e.message)}</div></div>`;
  }
  updateNavBadges();
}

window.addEventListener("hashchange", render);

/* ---------- boot ---------- */

async function boot() {
  buildNav();
  render();
  await refreshSystem();
  await refreshVoices();
  render();
  // poll engine status while it loads
  const poll = setInterval(async () => {
    const s = state.system;
    const need = !s || s.engine?.status === "loading";
    if (need) {
      await refreshSystem();
      if (state.system?.engine?.status !== "loading") {
        renderFoot();
        if (state.route === "dashboard" || state.route === "settings") render();
      }
    }
  }, 2500);
  setTimeout(() => clearInterval(poll), 120000);
}

boot();
