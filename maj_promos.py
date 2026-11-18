# -*- coding: utf-8 -*-
"""
Mise à jour des promos — sans Claude, sans clé, sans compte.

Va lire les pages publiques de catalogues (bonial.fr, anti-crise.fr) pour chaque
enseigne de config.json, en extrait les produits en promo et écrit data/promos.json.

Utilisation :
    python maj_promos.py            -> met à jour
    python maj_promos.py --debug    -> met à jour et garde les pages brutes dans data/debug/

Uniquement la bibliothèque standard de Python : rien à installer.
"""
import gzip
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser

try:  # consoles Windows : éviter un plantage sur les caractères accentués
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ICI = os.path.dirname(os.path.abspath(__file__))
DATA = ICI
FICHIER = os.path.join(DATA, "promos.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


# --------------------------------------------------------------------------- outils
def norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def prix_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for k in ("amount", "value", "price", "valeur"):
            if k in v:
                return prix_float(v[k])
        return None
    m = re.search(r"(\d{1,4})(?:[.,](\d{1,2}))?", str(v).replace(" ", "").replace(" ", ""))
    if not m:
        return None
    return float(m.group(1) + "." + (m.group(2) or "0"))


def euro(x):
    return ("%.2f €" % x).replace(".", ",") if x is not None else ""


def telecharger(url, log):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            brut = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                brut = gzip.decompress(brut)
            return brut.decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        log("   ! %s -> erreur HTTP %s" % (url, e.code))
    except Exception as e:  # réseau coupé, délai dépassé…
        log("   ! %s -> %s" % (url, e))
    return None


# --------------------------------------------------------------------------- rayons
RAYONS = {
    "Hygiène & beauté": "shampoing, gel douche, deodorant, dentifrice, brosse a dents, rasoir, maquillage, creme visage, creme mains, lingettes, demaquillant, savon, parfum, couches, protege slip, serviettes hygieniques, coton, vernis, apres shampoing, soin",
    "Entretien": "lessive, adoucissant, liquide vaisselle, pastilles lave, eponge, nettoyant, javel, essuie tout, papier toilette, sacs poubelle, desodorisant, capsules de lessive",
    "Animaux": "chat, chien, croquettes, patee, litiere, sheba, felix, whiskas, pedigree, friskies",
    "Boissons": "biere, vin, rose, champagne, cremant, whisky, rhum, vodka, jus, soda, coca, pepsi, eau minerale, eau gazeuse, sirop, ice tea, cafe, capsules cafe, dosettes, the, infusion, lait, beaujolais, aop, igp",
    "Poisson & mer": "saumon, cabillaud, crevette, crevettes, thon, sardine, maquereau, moules, huitres, coquilles saint jacques, colin, merlu, bar, dorade, poisson, surimi, crabe, langoustine, truite, rillettes de thon, calamar, seiche, delpierre, petit navire",
    "Volaille": "poulet, dinde, pintade, canard, caille, chapon, volaille, cordon bleu, cordons bleus, nuggets, aiguillettes, maitre coq, loue",
    "Charcuterie": "jambon, saucisson, lardons, rillettes, pate, terrine, chorizo, bacon, knacki, saucisse de strasbourg, foie gras, andouille, andouillette, boudin, fleury michon",
    "Viande": "boeuf, veau, porc, agneau, steak, steaks haches, hache, entrecote, cote, roti, filet mignon, echine, saucisse, saucisses, merguez, chipolatas, paupiette, paupiettes, rognons, foie de boeuf, langue, osso bucco, bavette, charal, viande",
    "Fromage": "fromage, camembert, emmental, comte, brie, raclette, mozzarella, cheddar, chevre, cabecou, roquefort, bleu d auvergne, reblochon, coulommiers, mimolette, parmesan, feta, tomme, madame loik, saint nectaire",
    "Crèmerie & œufs": "yaourt, yaourts, creme fraiche, creme liquide, beurre, oeufs, margarine, skyr, fromage blanc, dessert lacte, petits suisses, liegeois, danette, bridelice",
    "Fruits & légumes": "pomme, pommes, poire, banane, orange, clementine, mandarine, kiwi, avocat, raisin, fraise, citron, ananas, mangue, tomate, tomates, carotte, carottes, courgette, poireau, oignon, echalote, ail, salade, concombre, poivron, champignon, champignons, chou, brocoli, epinards, haricots verts, patate douce, pomme de terre, pommes de terre, potiron, courge, navet, radis, endive, pak choi, betterave, mache",
    "Surgelés": "surgele, surgeles, glace, cone, mccain, frites, pizza surgelee, poelee, noisettes, pommes noisettes",
    "Boulangerie": "pain, baguette, brioche, viennoiserie, croissant, pain de mie, pains a burger, pain a burger, wraps, tortilla, harrys, jacquet",
    "Épicerie sucrée": "chocolat, biscuit, biscuits, gateau, gateaux, bonbon, confiture, pate a tartiner, nutella, cereales, granola, cacao, sucre, miel, compote, calendrier de l avent, ferrero, kinder, madeleine, panettone, milka, flocons d avoine",
    "Épicerie salée": "pates, pates fraiches, pennette, spaghetti, riz, lentilles, semoule, couscous, quinoa, gnocchi, gnocchis, conserve, sauce, huile, vinaigre, moutarde, mayonnaise, ketchup, epices, sel, poivre, soupe, chips, aperitif, cacahuetes, olives, bouillon, farine, plat cuisine, paella, lasagnes, lustucru, panzani, barilla, rana",
}
RAYONS_ALIMENTAIRES = {"Poisson & mer", "Volaille", "Charcuterie", "Viande", "Fromage", "Crèmerie & œufs",
                       "Fruits & légumes", "Surgelés", "Boulangerie", "Épicerie sucrée", "Épicerie salée"}
_RAYONS = [(r, [k.strip() for k in mots.split(",") if k.strip()]) for r, mots in RAYONS.items()]


def rayon(nom, marque=""):
    """Rayon le plus probable : le mot-clé le plus long trouvé gagne ("fromage blanc" bat "fromage")."""
    t = " " + norm((nom or "") + " " + (marque or "")) + " "
    meilleur, long_ = "Autres", 0
    for r, cles in _RAYONS:
        for k in cles:
            if (" " + k + " ") in t and len(k) > long_:
                meilleur, long_ = r, len(k)
    return meilleur


# --------------------------------------------------------------------------- extraction JSON
CLES_NOM = ("name", "title", "productName", "product_name", "label", "nom", "offerTitle", "description")
CLES_PRIX = ("price", "priceValue", "salePrice", "currentPrice", "prix", "finalPrice", "promoPrice",
             "offerPrice", "lowPrice", "dealPrice")
CLES_AVANT = ("oldPrice", "regularPrice", "originalPrice", "strikePrice", "strikethroughPrice", "referencePrice",
              "priceBefore", "crossedOutPrice", "previousPrice", "normalPrice", "highPrice", "priceWithoutDiscount")


def _premier(d, cles):
    for k in cles:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return None


def _marque(d):
    b = d.get("brand") or d.get("brandName") or d.get("marque")
    if isinstance(b, dict):
        b = b.get("name")
    return b if isinstance(b, str) else ""


def parcourir_json(obj, sortie, profondeur=0):
    if profondeur > 40:
        return
    if isinstance(obj, dict):
        nom = _premier(obj, CLES_NOM)
        prix = _premier(obj, CLES_PRIX)
        if prix is None and isinstance(obj.get("offers"), dict):
            prix = _premier(obj["offers"], CLES_PRIX)
        if isinstance(nom, str) and prix is not None:
            p = prix_float(prix)
            if p is not None and 0.05 <= p <= 3000 and 2 <= len(nom) <= 140:
                avant = prix_float(_premier(obj, CLES_AVANT))
                sortie.append({"nom": nom.strip(), "marque": _marque(obj), "prix": p,
                               "avant": avant if avant and avant > p else None})
        for v in obj.values():
            parcourir_json(v, sortie, profondeur + 1)
    elif isinstance(obj, list):
        for v in obj:
            parcourir_json(v, sortie, profondeur + 1)


def extraire_json(page):
    trouves = []
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", page, re.S | re.I):
        attrs, corps = m.group(1), m.group(2).strip()
        if not corps or ("price" not in corps and "prix" not in corps.lower()):
            continue
        candidats = []
        if "json" in attrs.lower() or corps[:1] in "{[":
            candidats.append(corps)
        else:
            a = re.search(r"=\s*(\{.*\}|\[.*\])\s*;?\s*$", corps, re.S)
            if a:
                candidats.append(a.group(1))
        for c in candidats:
            try:
                parcourir_json(json.loads(c), trouves)
            except Exception:
                pass
    return trouves


# --------------------------------------------------------------------------- extraction bonial (texte)
RE_PRIX_LIGNE = re.compile(r"^(?:Dès\s*:?\s*)?(\d{1,4}[.,]\d{2})\s*€$", re.I)
RE_ALT = re.compile(r"Promo\s+(.{2,160}?)\s+à\s+(\d{1,4}(?:[.,]\d{1,2})?)?\s*€?\s*dans le catalogue\s+", re.I)


class Texte(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lignes, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.ignore += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.ignore:
            self.ignore -= 1

    def handle_data(self, d):
        if not self.ignore:
            d = re.sub(r"\s+", " ", d).strip()
            if d:
                self.lignes.append(d)


def lignes_texte(page):
    p = Texte()
    try:
        p.feed(page)
    except Exception:
        pass
    return p.lignes


def extraire_bonial(page, nom_enseigne):
    items = []
    cible = norm(nom_enseigne).split(" ")[0]  # "super", "e", "intermarche", "lidl", "carrefour"
    if cible == "e":
        cible = "e leclerc"
    lignes = lignes_texte(page)
    for i, l in enumerate(lignes):
        nl = norm(l)
        if not nl.startswith(cible) or len(nl) > len(cible) + 18 or i < 1 or i + 1 >= len(lignes):
            continue
        m = RE_PRIX_LIGNE.match(lignes[i + 1])
        if not m:
            continue
        nom = lignes[i - 1]
        if nom.lower().startswith("promo ") or RE_PRIX_LIGNE.match(nom) or len(nom) < 2:
            continue
        marque = ""
        if i >= 2:
            c = lignes[i - 2]
            if 1 < len(c) <= 30 and not RE_PRIX_LIGNE.match(c) and not c.lower().startswith("promo") \
                    and c.upper() == c:
                marque = c.title() if c.isupper() and len(c) > 3 else c
        prix = prix_float(m.group(1))
        avant, unite = None, ""
        for j in (i + 2, i + 3):
            if j < len(lignes):
                s = lignes[j]
                m2 = RE_PRIX_LIGNE.match(s)
                if m2 and avant is None and prix_float(m2.group(1)) > prix:
                    avant = prix_float(m2.group(1))
                elif ("kg" in s.lower() or " le l" in s.lower() or "/ l" in s.lower()) and len(s) < 40:
                    unite = s
        items.append({"nom": nom, "marque": marque, "prix": prix, "avant": avant, "unite": unite})

    # Textes alternatifs des images : « Promo X à 1,19 € dans le catalogue … » (+ bons plans sans prix)
    for m in RE_ALT.finditer(html.unescape(page)):
        nom = m.group(1).strip().strip('"')
        p = prix_float(m.group(2)) if m.group(2) else None
        items.append({"nom": nom, "marque": "", "prix": p, "avant": None,
                      "bon_plan": None if p else nom})

    validite = ""
    v = re.search(r"valables?\s+du\s+(\d{2}/\d{2})/\d{4}\s+au\s+(\d{2}/\d{2})/\d{4}", html.unescape(page), re.I)
    if v:
        validite = "du %s au %s" % (v.group(1), v.group(2))
    return items, validite


# --------------------------------------------------------------------------- anti-crise
class Tableaux(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._t, self._r, self._c = [], None, None, None

    def handle_starttag(self, tag, a):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._r = []
        elif tag in ("td", "th") and self._r is not None:
            self._c = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._c is not None and self._r is not None:
            self._r.append(re.sub(r"\s+", " ", "".join(self._c)).strip())
            self._c = None
        elif tag == "tr" and self._r is not None and self._t is not None:
            self._t.append(self._r)
            self._r = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, d):
        if self._c is not None:
            self._c.append(d)


def dates_slug(slug):
    s = norm(slug.replace("-", " "))
    m = re.search(r"du (\d{1,2})(?: (\w+))? au (\d{1,2}) (\w+) (\d{4})", s)
    if not m:
        return None
    j1, m1, j2, m2, an = m.groups()
    try:
        mo2 = MOIS[m2]
        mo1 = MOIS.get(m1, mo2) if m1 else mo2
        d1 = date(int(an) - (1 if mo1 > mo2 else 0), mo1, int(j1))
        return d1, date(int(an), mo2, int(j2))
    except (KeyError, ValueError):
        return None


def trouver_anticrise(motif, secours, log, cache):
    if "pages" not in cache:
        cache["pages"] = []
        for u in ("https://anti-crise.fr/", "https://anti-crise.fr/catalogues/"):
            p = telecharger(u, log)
            if p:
                cache["pages"].append(p)
    liens = set()
    for p in cache["pages"]:
        for m in re.finditer(r"https://anti-crise\.fr/catalogue/[^\"'#?\s<>]+", p):
            liens.add(m.group(0).rstrip("/") + "/")
    aujourd = date.today()
    for mot in (motif, secours):
        if not mot:
            continue
        bons = []
        for l in liens:
            if re.search(mot, l):
                d = dates_slug(l.rsplit("/", 2)[-2])
                if d:
                    bons.append((d, l))
        en_cours = [b for b in bons if b[0][0] <= aujourd <= b[0][1]]
        choix = sorted(en_cours or [b for b in bons if b[0][1] >= aujourd], key=lambda b: b[0][0])
        if choix:
            return choix[-1][1] if en_cours else choix[0][1], choix[-1][0] if en_cours else choix[0][0]
    return None, None


def extraire_anticrise(page):
    t = Tableaux()
    try:
        t.feed(page)
    except Exception:
        pass
    items = []
    for tab in t.tables:
        if not tab:
            continue
        ent = [norm(c) for c in tab[0]]
        if "produit" not in ent or "prix" not in ent:
            continue
        ix = {k: ent.index(k) for k in ("marque", "produit", "q", "prix", "promo", "prix final") if k in ent}
        for r in tab[1:]:
            try:
                produit = r[ix["produit"]]
                total = prix_float(r[ix["prix"]])
            except (IndexError, KeyError):
                continue
            if not produit or total is None:
                continue
            q = int(prix_float(r[ix["q"]]) or 1) if "q" in ix and ix["q"] < len(r) else 1
            promo = 0.0
            if "promo" in ix and ix["promo"] < len(r):
                promo = prix_float(r[ix["promo"]]) or 0.0
            final = prix_float(r[ix["prix final"]]) if "prix final" in ix and ix["prix final"] < len(r) else None
            marque = r[ix["marque"]] if "marque" in ix and ix["marque"] < len(r) else ""
            prix = round(total - abs(promo), 2)
            nom = produit + (" (lot de %d)" % q if q > 1 else "")
            it = {"nom": nom, "marque": marque, "prix": prix, "avant": total if promo else None}
            if final is not None and final < prix - 0.01:
                it["bon_plan"] = "%s avec bons / remboursement" % euro(final)
            items.append(it)
    return items


# --------------------------------------------------------------------------- mise à jour
def charger_config():
    with open(os.path.join(ICI, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def charger_ancien():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"enseignes": {}, "promos": []}


def nettoyer(items, ens, source, validite):
    vus, sortie = {}, []
    for it in items:
        nom = re.sub(r"\s+", " ", (it.get("nom") or "")).strip(" –:")
        if len(nom) < 2:
            continue
        cle = norm(nom)
        if cle in vus:  # garder la version la plus complète
            ancien = vus[cle]
            if not ancien.get("avant") and it.get("avant"):
                ancien["avant"] = it["avant"]
            if not ancien.get("prix") and it.get("prix"):
                ancien["prix"] = it["prix"]
            if not ancien.get("marque") and it.get("marque"):
                ancien["marque"] = it["marque"]
            continue
        p, a = it.get("prix"), it.get("avant")
        rem = round((1 - p / a) * 100) if p and a and a > p else None
        e = {
            "id": "%s-%s" % (ens["id"], cle.replace(" ", "-")[:60]),
            "enseigne": ens["id"],
            "nom": nom,
            "marque": (it.get("marque") or "").strip(),
            "prix": p,
            "avant": a,
            "remise": rem,
            "unite": it.get("unite") or "",
            "bon_plan": it.get("bon_plan") or "",
            "rayon": rayon(nom, it.get("marque")),
            "validite": validite,
            "source": source,
        }
        vus[cle] = e
        sortie.append(e)
    return sortie


def mettre_a_jour(debug=False, log=print):
    os.makedirs(DATA, exist_ok=True)
    if debug:
        os.makedirs(os.path.join(DATA, "debug"), exist_ok=True)
    cfg = charger_config()
    ancien = charger_ancien()
    resultat = {"maj": datetime.now().isoformat(timespec="seconds"), "ville": cfg.get("ville", ""),
                "enseignes": {}, "promos": []}
    cache = {}
    for ens in cfg["enseignes"]:
        if not ens.get("actif", True):
            continue
        log("→ %s" % ens["nom"])
        bruts, sources, validite = [], [], ""
        for src in ens.get("sources", []):
            if src["type"] == "bonial":
                page = telecharger(src["url"], log)
                if not page:
                    continue
                if debug:
                    with open(os.path.join(DATA, "debug", "%s-bonial.html" % ens["id"]), "w", encoding="utf-8") as f:
                        f.write(page)
                its, val = extraire_bonial(page, ens["nom"])
                its += extraire_json(page)
                log("   bonial : %d produits" % len(its))
                if its:
                    bruts += its
                    sources.append(src["url"])
                    validite = validite or val
                    break  # une page bonial suffit, la seconde est un secours
            elif src["type"] == "anticrise":
                url, dates = trouver_anticrise(src.get("motif"), src.get("secours"), log, cache)
                if not url:
                    log("   anti-crise : pas de catalogue trouvé")
                    continue
                page = telecharger(url, log)
                if not page:
                    continue
                if debug:
                    with open(os.path.join(DATA, "debug", "%s-anticrise.html" % ens["id"]), "w", encoding="utf-8") as f:
                        f.write(page)
                its = extraire_anticrise(page)
                log("   anti-crise : %d produits (%s)" % (len(its), url))
                if its:
                    bruts += its
                    sources.append(url)
                    if not validite and dates:
                        validite = "du %s au %s" % (dates[0].strftime("%d/%m"), dates[1].strftime("%d/%m"))
            time.sleep(1.0)  # politesse envers les sites

        promos = nettoyer(bruts, ens, ", ".join(sources), validite)
        if promos:
            resultat["enseignes"][ens["id"]] = {"nom": ens["nom"], "validite": validite, "nb": len(promos),
                                               "maj": resultat["maj"], "ancien": False, "sources": sources}
            resultat["promos"] += promos
            log("   ✓ %d promos gardées" % len(promos))
        else:
            # rien trouvé : on garde les promos précédentes de cette enseigne plutôt que de tout vider
            garde = [p for p in ancien.get("promos", []) if p.get("enseigne") == ens["id"]]
            info = dict(ancien.get("enseignes", {}).get(ens["id"], {"nom": ens["nom"], "validite": ""}))
            info.update({"nb": len(garde), "ancien": True})
            resultat["enseignes"][ens["id"]] = info
            resultat["promos"] += garde
            log("   ✗ rien de nouveau, %d anciennes promos conservées" % len(garde))

    if not any(not e.get("ancien") for e in resultat["enseignes"].values()):
        log("Aucune nouvelle promo trouvée (connexion internet ? sites changés ?). Les promos actuelles sont gardées.")
        return ancien

    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FICHIER)
    total = len(resultat["promos"])
    log("Terminé : %d promos enregistrées dans data/promos.json" % total)
    return resultat


if __name__ == "__main__":
    mettre_a_jour(debug="--debug" in sys.argv)
