// Garde l'appli et les dernières promos en mémoire pour l'ouvrir même sans réseau (en magasin).
var CACHE = "mes-promos-v1";
var BASE = ["./", "index.html", "recettes.json", "manifest.json", "icone-192.png", "icone-512.png"];
self.addEventListener("install", function (e) { e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(BASE); })); self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  var url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  // Toujours essayer le réseau d'abord (promos fraîches), sinon la copie gardée.
  e.respondWith(fetch(e.request).then(function (r) {
    var copie = r.clone();
    var cle = url.pathname.endsWith("promos.json") ? "promos.json" : e.request;
    caches.open(CACHE).then(function (c) { c.put(cle, copie); });
    return r;
  }).catch(function () {
    return caches.match(url.pathname.endsWith("promos.json") ? "promos.json" : e.request);
  }));
});
