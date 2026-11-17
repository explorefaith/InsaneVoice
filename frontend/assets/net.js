/* InsaneVoice — engine connection layer.
   The UI is static (hostable anywhere); the engine is a local FastAPI server.
   apiBase() is "" when the UI is served by the engine itself, or
   "http://127.0.0.1:8177" when this UI is hosted remotely (e.g. Vercel). */

const KEY = "ivApiBase";

let base = "";
try { base = (localStorage.getItem(KEY) || "").replace(/\/+$/, ""); } catch { /* no storage */ }

export function apiBase() { return base; }

export function setApiBase(url) {
  base = String(url || "").trim().replace(/\/+$/, "");
  try {
    if (base) localStorage.setItem(KEY, base);
    else localStorage.removeItem(KEY);
  } catch { /* no storage */ }
}

/* Resolve a server-relative path ("/api/...") against the engine base. */
export function abs(path) {
  if (!path) return path;
  if (/^[a-z]+:\/\//i.test(path) || path.startsWith("data:")) return path;
  return base + path;
}
