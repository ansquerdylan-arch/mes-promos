"""Télécharge des pages telles quelles (pour étudier une source). Usage : python outils/aspirer.py URL... ; résultat dans brut/."""
import gzip, json, os, re, sys, time, urllib.request, urllib.error, zlib

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Mobile Safari/537.36")
os.makedirs("brut", exist_ok=True)
bilan = []
for i, url in enumerate(sys.argv[1:]):
    nom = "%02d_%s" % (i, re.sub(r"[^A-Za-z0-9]+", "_", url.split("//", 1)[-1])[:90])
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9", "Accept-Encoding": "gzip, deflate"})
    code, corps, entetes = 0, b"", {}
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            code, corps, entetes = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        code, corps, entetes = e.code, e.read(), dict(e.headers)
    except Exception as e:
        code, corps = -1, repr(e).encode()
    enc = (entetes.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip" or corps[:2] == b"\x1f\x8b":
            corps = gzip.decompress(corps)
        elif enc == "deflate":
            corps = zlib.decompress(corps)
    except Exception:
        pass
    with open(os.path.join("brut", nom), "wb") as f:
        f.write(corps)
    bilan.append({"url": url, "fichier": nom, "code": code, "taille": len(corps),
                  "type": entetes.get("Content-Type"), "finale": None})
    print(code, len(corps), url)
    time.sleep(1.2)
with open("brut/bilan.json", "w", encoding="utf-8") as f:
    json.dump(bilan, f, ensure_ascii=False, indent=1)
