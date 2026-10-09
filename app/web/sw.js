// Service worker: de app-schil werkt ook met een haperende verbinding.
// Netwerk eerst (dan zie je altijd de nieuwste versie), cache als terugval.
// /api/ blijft altijd buiten de cache: verouderde cijfers zijn erger dan een foutmelding.

const CACHE = "thuis-v3";
const SCHIL = [
  "./",
  "index.html",
  "style.css",
  "manifest.webmanifest",
  "icons/icon.svg",
  "js/app.js",
  "js/basis.js",
  "js/grafiek.js",
  "js/onderdelen.js",
  "js/paginas/overzicht.js",
  "js/paginas/energie.js",
  "js/paginas/prijzen.js",
  "js/paginas/laden.js",
  "js/paginas/auto.js",
  "js/paginas/inzichten.js",
  "js/paginas/bronnen.js",
];
const ECHARTS = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll([...SCHIL, ECHARTS])).catch(() => {}).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(namen.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.includes("/api/")) return;
  if (url.href === ECHARTS) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
    return;
  }
  if (url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok && r.type === "basic") {
          const kopie = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, kopie));
        }
        return r;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true })),
  );
});
