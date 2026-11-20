/* InsaneVoice service worker — static shell cache, network-first */
const CACHE = "iv-shell-v1";
const SHELL = [
  "/", "/static/assets/logo.svg", "/static/assets/styles.css",
  "/static/assets/app.js", "/static/assets/net.js", "/static/assets/icons.js",
  "/static/assets/components.js", "/static/assets/pages.js", "/static/assets/pages2.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(e.request).then((m) => m || Response.error())),
  );
});
