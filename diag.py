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
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if nd:
        data = json.loads(nd.group(1))
        chemins = []

        def marche(o, chemin, prof=0):
            if prof > 30 or len(chemins) > 60:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    if re.search(r"price|prix|offer|validity|valid|brochure|publisher", k, re.I):
                        apercu = json.dumps(v, ensure_ascii=False)[:220]
                        chemins.append(chemin + "." + k + " = " + apercu)
                    marche(v, chemin + "." + k, prof + 1)
            elif isinstance(o, list):
                for i, v in enumerate(o[:3]):
                    marche(v, chemin + "[%d]" % i, prof + 1)
        marche(data, "")
        pi = data.get("props", {}).get("pageProps", {}).get("pageInformation", {})
        br = pi.get("brochures", {})
        if br:
            print("--- brochures : clés", {k: len(v) if isinstance(v, list) else type(v).__name__ for k, v in br.items()})
            for k, v in br.items():
                if isinstance(v, list) and v:
                    print("  exemple", k, ":", json.dumps(v[0], ensure_ascii=False)[:1500])
                    lid = str(v[0].get("id"))
                    for mm in list(re.finditer(re.escape(lid), page))[:4]:
                        print("  ... contexte HTML :", page[max(0, mm.start() - 160): mm.end() + 80].replace("\n", " "))
                    break
        of = pi.get("offers", {})
        if of:
            print("--- offers : clés", {k: (len(v.get("items", [])) if isinstance(v, dict) else type(v).__name__) for k, v in of.items()})
        plb = pi.get("template", {}).get("content", {}).get("PublisherLogoLinkbox", {})
        if plb:
            print("--- enseignes de la ville :", [l.get("link_href") for l in plb.get("links", [])])
        if pi.get("city"):
            print("--- ville :", json.dumps(pi["city"], ensure_ascii=False)[:900])
        cont = (pi.get("template") or {}).get("content") or {}
        for nom in ("StoreLogoLinkbox", "StoreLinkbox", "NearbyStores", "StoreList"):
            if cont.get(nom):
                print("--- %s :" % nom, json.dumps(cont[nom], ensure_ascii=False)[:1500])
        for k, v in (pi or {}).items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and any(x in json.dumps(v[0])[:600] for x in ("zipCode", "street", "lat")):
                print("--- liste magasins %s (%d) :" % (k, len(v)), json.dumps(v[:2], ensure_ascii=False)[:1200])
        if pi.get("store"):
            print("--- magasin :", json.dumps(pi["store"], ensure_ascii=False)[:2500])
        print("--- pageInformation : clés ---")
        for k, v in pi.items():
            taille = len(v) if isinstance(v, (list, dict, str)) else ""
            print("   %-28s %-6s %s" % (k, type(v).__name__, taille))
        def listes_offres(o, chemin, prof=0):
            if prof > 12:
                return
            if isinstance(o, list) and o and isinstance(o[0], dict) and any(re.search("price", kk, re.I) for kk in json.dumps(o[0])[:4000].split('"')):
                print("--- liste avec prix : %s (%d éléments) ---" % (chemin, len(o)))
                print("   exemple complet :", json.dumps(o[0], ensure_ascii=False)[:1600])
                for it in o[:40]:
                    pr = it.get("prices") or {}
                    print("   · %-45s %-12s %7s %7s  %s → %s  %s" % (
                        (it.get("title") or "")[:45], (it.get("brand") or "")[:12], pr.get("mainPrice"), pr.get("secondaryPrice"),
                        (it.get("validFrom") or "")[:10], (it.get("validUntil") or "")[:10], (it.get("publisherName") or "")))
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    if k != "_nextI18Next":
                        listes_offres(v, chemin + "." + k, prof + 1)
            elif isinstance(o, list):
                for i, v in enumerate(o[:2]):
                    listes_offres(v, chemin + "[%d]" % i, prof + 1)
        listes_offres(data.get("props", {}).get("pageProps", {}), "pageProps")
        print("--- __NEXT_DATA__ : clés prix / offres ---")
        for c in chemins[:60]:
            print("  ", c)
    print("--- tous les liens (échantillon) ---")
    tous = sorted(set(re.findall(r'href="(https://www\.bonial\.fr/[^"]+)"', page)))
    for l in [x for x in tous if re.search(r"\d{6,}|/b/|Promos/|Apercu|Catalogue", x)][:50]:
        print("  ", l)
    print("--- liens catalogues ---")
    for l in sorted(set(re.findall(r'href="([^"]*(?:brochure|catalogue|/b-|/Magasins/)[^"]*)"', page)))[:30]:
        print("  ", l)
    its = m.extraire_json(page)
    print("--- extraction JSON générique : %d produits" % len(its))
    for it in its[:8]:
        print("   ", it)


if __name__ == "__main__":
    for u in sys.argv[1:]:
        resume(u)
