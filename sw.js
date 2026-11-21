// Garde l'appli et les dernières promos en mémoire pour l'ouvrir même sans réseau (en magasin).
var CACHE = "mes-promos-v12";
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

// Notifications de Mogette : la mise à jour du matin envoie { titre, texte, url, tag } à chaque téléphone abonné.
self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { texte: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.titre || "Mogette", {
    body: d.texte || "Des promos t'attendent.", icon: "icone-192.png", badge: "icone-192.png",
    tag: d.tag || "mogette", data: { url: d.url || "./" }
  }));
});
// toucher la notification : ouvre Mogette (ou la ramène devant) sur la bonne page
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = new URL((e.notification.data && e.notification.data.url) || "./", self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (l) {
    for (var i = 0; i < l.length; i++) {
      if (l[i].url.indexOf(self.registration.scope) === 0 && "focus" in l[i]) {
        if ("navigate" in l[i] && l[i].url !== url) l[i].navigate(url).catch(function () {});
        return l[i].focus();
      }
    }
    return self.clients.openWindow ? self.clients.openWindow(url) : null;
  }));
});
