// Service worker voor Staartploeg.
//
// Bewust netwerk-eerst: offline werken is geen eis, maar een verouderde
// versie serveren uit de cache is wél een probleem. De cache is er alleen
// als vangnet wanneer er even geen verbinding is.

const CACHE = "staartploeg-v1";
const SCHIL = ["./", "./index.html", "./icons/icoon-192.png", "./icons/icoon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SCHIL))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(namen.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  // Alleen eigen bestanden cachen; lettertypes van Google regelen zichzelf.
  if (new URL(req.url).origin !== self.location.origin) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const kopie = res.clone();
          caches.open(CACHE).then((c) => c.put(req, kopie)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("./")))
  );
});
