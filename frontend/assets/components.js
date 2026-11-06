/* InsaneVoice — UI components: toasts, modals, skeletons, waveform, radar */

/* ---------- toasts ---------- */

export function toast(title, msg = "", kind = "ok", ms = 4200) {
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  const ico = kind === "ok" ? "✓" : kind === "err" ? "✕" : kind === "warn" ? "!" : "i";
  el.innerHTML = `
    <span class="t-ico">${ico}</span>
    <span>
      <div class="t-title"></div>
      <div class="t-msg"></div>
    </span>
    <button class="t-x" aria-label="Dismiss">✕</button>`;
  el.querySelector(".t-title").textContent = title;
  el.querySelector(".t-msg").textContent = msg;
  const kill = () => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 220);
  };
  el.querySelector(".t-x").onclick = kill;
  box.appendChild(el);
  if (ms) setTimeout(kill, ms);
  return kill;
}

/* ---------- modal ---------- */

export function modal({ title, body, footer, onMount }) {
  const veil = document.createElement("div");
  veil.className = "modal-veil";
  veil.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-label="">
      <div class="m-head">
        <h3></h3>
        <button class="m-x" aria-label="Close">✕</button>
      </div>
      <div class="m-body"></div>
      <div class="m-foot"></div>
    </div>`;
  veil.querySelector("h3").textContent = title;
  veil.querySelector(".modal").setAttribute("aria-label", title);
  const bodyEl = veil.querySelector(".m-body");
  if (typeof body === "string") bodyEl.innerHTML = body;
  else bodyEl.appendChild(body);
  const footEl = veil.querySelector(".m-foot");
  if (footer) {
    if (typeof footer === "string") footEl.innerHTML = footer;
    else footEl.appendChild(footer);
  } else footEl.remove();

  const close = () => veil.remove();
  veil.addEventListener("click", (e) => { if (e.target === veil) close(); });
  veil.querySelector(".m-x").onclick = close;
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });
  document.body.appendChild(veil);
  if (onMount) onMount(veil, close);
  return { veil, close };
}

export function confirmModal(title, message, confirmLabel = "Delete") {
  return new Promise((resolve) => {
    const foot = document.createElement("div");
    foot.innerHTML = `
      <button class="btn ghost" data-a="no">Cancel</button>
      <button class="btn danger" data-a="yes"></button>`;
    foot.querySelector('[data-a="yes"]').textContent = confirmLabel;
    const { close } = modal({
      title,
      body: `<p style="margin:0;color:var(--ink-2)"></p>`,
      footer: foot,
      onMount: (veil, c) => {
        veil.querySelector(".m-body p").textContent = message;
        veil.querySelector('[data-a="no"]').onclick = () => { c(); resolve(false); };
        veil.querySelector('[data-a="yes"]').onclick = () => { c(); resolve(true); };
      },
    });
  });
}

/* ---------- skeletons ---------- */

export const sk = {
  line: (w = "") => `<div class="sk sk-line ${w}"></div>`,
  title: () => `<div class="sk sk-title"></div>`,
  block: (h = 110) => `<div class="sk sk-block" style="height:${h}px"></div>`,
  stat: () => `<div class="sk sk-stat"></div>`,
  page() {
    return `
      ${this.title()}
      ${this.line("w60")}
      <div class="grid c4" style="margin-top:22px">${this.stat()}${this.stat()}${this.stat()}${this.stat()}</div>
      <div style="margin-top:18px">${this.block(180)}</div>`;
  },
};

/* ---------- busy buttons ---------- */

export function busy(btn, on = true) {
  if (!btn) return;
  if (on) {
    btn.dataset.label = btn.innerHTML;
    btn.classList.add("busy");
    if (!btn.querySelector(".spinner")) {
      const s = document.createElement("span");
      s.className = "spinner";
      btn.appendChild(s);
    }
  } else {
    btn.classList.remove("busy");
    if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
  }
}

/* ---------- audio ---------- */

let actx = null;
export function audioCtx() {
  if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === "suspended") actx.resume();
  return actx;
}

export class WaveBox {
  /* canvas waveform + play control bound to one audio URL */
  constructor(container, url, { height = 72, onPlayState } = {}) {
    this.url = url;
    this.onPlayState = onPlayState;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "wave";
    this.canvas.style.height = height + "px";
    container.appendChild(this.canvas);
    this.audio = new Audio(url);
    this.audio.preload = "metadata";
    this.peaks = null;
    this.progress = 0;
    this.raf = null;
    this.audio.addEventListener("ended", () => this.stop());
    this.canvas.addEventListener("click", () => this.toggle());
  }

  async load() {
    const buf = await fetch(this.url).then((r) => r.arrayBuffer());
    const decoded = await audioCtx().decodeAudioData(buf);
    const ch = decoded.getChannelData(0);
    const N = 240;
    this.peaks = [];
    const step = Math.floor(ch.length / N) || 1;
    for (let i = 0; i < N; i++) {
      let max = 0;
      for (let j = i * step; j < (i + 1) * step && j < ch.length; j += 8) {
        const v = Math.abs(ch[j]);
        if (v > max) max = v;
      }
      this.peaks.push(max);
    }
    this.duration = decoded.duration;
    this.draw();
  }

  toggle() {
    if (this.audio.paused) this.play();
    else this.stop();
  }

  play() {
    this.audio.play();
    this.canvas.classList.add("playing");
    const tick = () => {
      this.progress = this.audio.currentTime / (this.duration || 1);
      this.draw();
      if (!this.audio.paused) this.raf = requestAnimationFrame(tick);
    };
    tick();
    this.onPlayState?.(true);
  }

  stop() {
    this.audio.pause();
    this.audio.currentTime = 0;
    this.progress = 0;
    this.canvas.classList.remove("playing");
    cancelAnimationFrame(this.raf);
    this.draw();
    this.onPlayState?.(false);
  }

  draw() {
    const c = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d");
    g.scale(dpr, dpr);
    g.clearRect(0, 0, W, H);
    if (!this.peaks) {
      g.fillStyle = "#7A7263";
      g.font = "12px Segoe UI";
      g.textAlign = "center";
      g.fillText("loading waveform…", W / 2, H / 2 + 4);
      return;
    }
    const mid = H / 2;
    const N = this.peaks.length;
    const bw = W / N;
    const cut = Math.floor(this.progress * N);
    for (let i = 0; i < N; i++) {
      const h = Math.max(2, this.peaks[i] * (H * 0.86));
      g.fillStyle = i <= cut && this.progress > 0 ? "#C9432B" : "#1A1712";
      const x = i * bw + bw * 0.22;
      const w = bw * 0.56;
      g.beginPath();
      g.roundRect(x, mid - h / 2, w, h, w / 2);
      g.fill();
    }
  }
}

/* ---------- radar chart ---------- */

export function radarChart(container, scores, labels, size = 300) {
  const keys = Object.keys(labels);
  const canvas = document.createElement("canvas");
  canvas.width = size * 2; canvas.height = size * 2;
  canvas.style.width = size + "px";
  canvas.style.height = size + "px";
  canvas.style.maxWidth = "100%";
  container.appendChild(canvas);
  const g = canvas.getContext("2d");
  g.scale(2, 2);
  const cx = size / 2, cy = size / 2, R = size * 0.36;
  const n = keys.length;
  const pt = (i, r) => {
    const a = -Math.PI / 2 + i * 2 * Math.PI / n;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  // grid rings
  for (let ring = 1; ring <= 4; ring++) {
    g.beginPath();
    for (let i = 0; i <= n; i++) {
      const [x, y] = pt(i % n, R * ring / 4);
      i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
    }
    g.strokeStyle = ring === 4 ? "#B9AE97" : "#D8CFBE";
    g.lineWidth = 1;
    g.stroke();
  }
  // spokes + labels
  g.font = "11px Segoe UI";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, R);
    g.beginPath();
    g.moveTo(cx, cy);
    g.lineTo(x, y);
    g.strokeStyle = "#D8CFBE";
    g.stroke();
    const [lx, ly] = pt(i, R + 17);
    g.fillStyle = "#4A4438";
    g.textAlign = lx > cx + 4 ? "left" : lx < cx - 4 ? "right" : "center";
    g.fillText(labels[keys[i]], lx, ly + 3);
  }
  // value polygon
  g.beginPath();
  keys.forEach((k, i) => {
    const v = Math.max(4, Math.min(100, scores[k] || 0)) / 100;
    const [x, y] = pt(i, R * v);
    i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
  });
  g.closePath();
  g.fillStyle = "rgba(201, 67, 43, .16)";
  g.fill();
  g.strokeStyle = "#C9432B";
  g.lineWidth = 1.6;
  g.stroke();
  keys.forEach((k, i) => {
    const v = Math.max(4, Math.min(100, scores[k] || 0)) / 100;
    const [x, y] = pt(i, R * v);
    g.beginPath();
    g.arc(x, y, 3, 0, 7);
    g.fillStyle = "#C9432B";
    g.fill();
  });
}

/* ---------- misc ---------- */

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtDur(s) {
  if (s == null) return "—";
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return m ? `${m}m ${sec}s` : `${sec}s`;
}

export function fmtWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function download(url, name) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name || "audio.wav";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
