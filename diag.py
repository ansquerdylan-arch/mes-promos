# -*- coding: utf-8 -*-
"""
Diagnostic des sources : télécharge des pages et montre ce que le script y trouve.
Sert quand un site change sa présentation. Lancé par l'action « Diagnostic des sources ».

    python diag.py URL [URL ...]
"""
import json
import re
import sys

import maj_promos as m


def resume(url):
    print("=" * 100)
    print("URL :", url)
    page = m.telecharger(url, print)
    if not page:
        print("-> rien reçu")
        return
    print("taille :", len(page))
    for nom, motif in [("next_data", r"__NEXT_DATA__"), ("ld+json", r"application/ld\+json"),
                       ("nuxt", r"__NUXT__"), ("euros", r"€"), ("data-price", r"data-price"),
                       ("itemprop price", r'itemprop="price"')]:
        print("  %-15s %d" % (nom, len(re.findall(motif, page))))
    print("--- scripts JSON ---")
    for mm in re.finditer(r"<script([^>]*)>(.*?)</script>", page, re.S | re.I):
        attrs, corps = mm.group(1), mm.group(2).strip()
        if len(corps) > 200 and ("{" in corps[:5] or "json" in attrs.lower() or "__" in corps[:40]):
            print("  [%s] %d car. : %s" % (attrs.strip()[:60], len(corps), corps[:300].replace("\n", " ")))
    print("--- liens intéressants ---")
    liens = sorted(set(re.findall(r'href="([^"]*(?:/offres/|/regardez/|/p-r\d+|/Produits/)[^"]*)"', page)))
    for l in liens[:40]:
        print("  ", l)
    print("--- texte autour des prix ---")
    lignes = m.lignes_texte(page)
    debut = next((i for i, l in enumerate(lignes) if "€" in l), 0)
    for l in lignes[max(0, debut - 15): debut + 130]:
        print("  |", l[:140])
    its = m.extraire_json(page)
    print("--- extraction JSON générique : %d produits" % len(its))
    for it in its[:8]:
        print("   ", it)


if __name__ == "__main__":
    for u in sys.argv[1:]:
        resume(u)
