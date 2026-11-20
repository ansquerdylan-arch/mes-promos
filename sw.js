// Garde l'appli et les dernières promos en mémoire pour l'ouvrir même sans réseau (en magasin).
var CACHE = "mes-promos-v11";
var BASE = ["./", "index.html", "recettes.json", "manifest.json", "icone-192.png", "icone-512.png", "icone-maskable-512.png",
  "polices/lilita-one-400.ttf", "polices/patrick-hand-400.woff"];
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
  // promos.json, offres/<catalogue>.json et pages/<catalogue>.json : une seule copie par fichier, quel que soit le ?v=
  var cle = url.pathname.endsWith("promos.json") ? "promos.json" : (/\/(offres|pages)\/[\w-]+\.json$/.test(url.pathname) ? url.origin + url.pathname : e.request);
  e.respondWith(fetch(e.request).then(function (r) {
    if (r.ok) { var copie = r.clone(); caches.open(CACHE).then(function (c) { c.put(cle, copie); }); }
    return r;
  }).catch(function () {
    return caches.match(cle);
  }));
});
