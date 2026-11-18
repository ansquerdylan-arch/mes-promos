// Garde l'appli et les dernières promos en mémoire pour l'ouvrir même sans réseau (en magasin).
var CACHE = "mes-promos-v7";
var BASE = ["./", "index.html", "recettes.json", "manifest.json", "icone-192.png", "icone-512.png", "icone-maskable-512.png"];
self.addEventListener("install", function (e) { e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(BASE); })); self.skipWaiting(); });
self.addEventListener("activate", function (e) {
  // anciennes versions du cache : on les supprime
  e.waitUntil(caches.keys().then(function (n) { return Promise.all(n.filter(function (x) { return x !== CACHE; }).map(function (x) { return caches["delete"](x); })); }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  var url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  // Toujours essayer le réseau d'abord (promos fraîches), sinon la copie gardée.
  // promos.json et offres/<catalogue>.json : une seule copie par fichier, quel que soit le ?v=
  var cle = url.pathname.endsWith("promos.json") ? "promos.json" : (/\/offres\/\d+\.json$/.test(url.pathname) ? url.origin + url.pathname : e.request);
  e.respondWith(fetch(e.request).then(function (r) {
    if (r.ok) { var copie = r.clone(); caches.open(CACHE).then(function (c) { c.put(cle, copie); }); }
    return r;
  }).catch(function () {
    return caches.match(cle);
  }));
});
