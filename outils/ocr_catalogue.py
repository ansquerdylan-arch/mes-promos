"""Lit le texte des pages d'un catalogue (images bonial) et montre celles qui parlent d'un mot (jeudi par défaut).
Sert à vérifier si une opération (Jeudis Plus…) est annoncée dans un catalogue papier. Lancé par diag.yml (brut=ocr).

Usage : python outils/ocr_catalogue.py MOT ID_CATALOGUE...
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import maj_promos as M  # noqa: E402

mot = M.norm(sys.argv[1]) if len(sys.argv) > 1 else "jeudi"
pos = (46.5, -1.78)
for cid in sys.argv[2:]:
    d = M.visionneuse("/brochures/%s/pages" % cid, pos, print)
    if not d:
        print(cid, ": visionneuse muette")
        continue
    pages = d.get("contents") or []
    print("== %s : %d pages" % (cid, len(pages)))
    for i, pg in enumerate(pages, 1):
        m = next((M.RE_PAGE_IMG.search(im.get("url") or "") for im in pg.get("images") or [] if M.RE_PAGE_IMG.search(im.get("url") or "")), None)
        if not m:
            continue
        url = "https://content-media.bonial.biz/%s/zoomlarge_page_%d.jpg" % (m.group(1), i)
        data = M.telecharger(url, print, binaire=True)
        if not data:
            continue
        try:
            lu = M.ocr_image(data)
        except Exception as e:  # noqa: BLE001
            print("   page %d : lecture impossible (%s)" % (i, e))
            continue
        t = lu.get("t") or ""
        if mot in M.norm(t):
            print("   page %d (%s) :" % (i, url))
            for l in t.splitlines():
                if l.strip():
                    print("      " + l.strip()[:120])
