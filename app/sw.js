// Minimal service worker: caches the app shell so the app's UI opens
// instantly and works offline once visited. Billing data itself still
// needs whichever of Excel/Drive/Telegram/Live-Sync you've set up — this
// only makes the app *open* without internet, like a native app icon.
const CACHE = "selfsense-shell-v1";
const SHELL_FILES = ["./", "./index.html", "./manifest.json", "./insights.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL_FILES)).catch(()=>{})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Network-first for the app shell so updates are picked up quickly;
  // falls back to cache when offline. Everything else (CDN scripts, API
  // calls to Drive/Telegram/Firebase) just goes straight to the network —
  // we never want to serve a stale copy of those.
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy)).catch(()=>{});
        return res;
      })
      .catch(() => caches.match(event.request).then((r) => r || caches.match("./index.html")))
  );
});
