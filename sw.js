// Opruimer voor de service worker van de vroegere Staartploeg-app.
// Browsers die de app ooit installeerden halen dit bestand op als update:
// het wist de oude cache en meldt zichzelf af, daarna is de pagina weer gewoon.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(namen.map((n) => caches.delete(n))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll())
      .then((tabs) => tabs.forEach((t) => t.navigate(t.url)))
  );
});
