# -*- coding: utf-8 -*-
"""
Mise à jour des promos — sans Claude, sans clé, sans compte.

Pour chaque enseigne de config.json :
  1. lit la page bonial.fr de l'enseigne dans ta ville (données structurées : titre, marque,
     prix, ancien prix, conditions « le 2e à… », dates exactes, rayon, catalogues en cours) ;
  2. lit la même page dans les villes voisines et garde seulement les offres des catalogues
     valables dans ta ville (chaque ville montre une sélection différente) ;
  3. complète avec les tableaux d'anti-crise.fr (bons de réduction, Intermarché).
Écrit promos.json, rappels.ics (calendrier) et historique.json (prix vus au fil des semaines).

Utilisation :
    python maj_promos.py            -> met à jour
    python maj_promos.py --debug    -> met à jour et garde les pages brutes dans debug/

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
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

try:  # consoles Windows : éviter un plantage sur les caractères accentués
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ICI = os.path.dirname(os.path.abspath(__file__))
# Version PC : les données vont dans data/ ; version GitHub : à côté de la page.
DATA = os.path.join(ICI, "data") if os.path.isdir(os.path.join(ICI, "data")) else ICI
FICHIER = os.path.join(DATA, "promos.json")
HISTORIQUE = os.path.join(DATA, "historique.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


# --------------------------------------------------------------------------- outils
def norm(t):
    t = str(t or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def slug(t):
    return norm(t).replace(" ", "-")


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
        if e.code != 404:  # 404 = l'enseigne n'existe pas dans cette ville, c'est normal
            log("   ! %s -> erreur HTTP %s" % (url, e.code))
    except Exception as e:  # réseau coupé, délai dépassé…
        log("   ! %s -> %s" % (url, e))
    return None


# --------------------------------------------------------------------------- rayons
RAYONS = {
    "Maison & loisirs": "bague, collier, bracelet, pendentif, boucles d oreilles, montre, smartphone, tablette, telephone, aspirateur, balai aspirateur, lave linge, seche linge, lave vaisselle, refrigerateur, congelateur, airfryer, friteuse, expresso, cafetiere, senseo, machine a cafe, imprimante, casque, ecouteurs, enceinte, television, tv, console, jeu video, jouet, jouets, lego, playmobil, peluche, poupee, t shirt, pull, chaussures, baskets, chaussettes, pyjama, couette, oreiller, drap, plaid, boucleur, seche cheveux, lisseur, perceuse, outil, sapin, guirlande, decoration, boule, suspension, bougie, combustible, petrole, bouquet, tulipes, fleurs, vaisselle, poele, casserole, electromenager, multimedia",
    "Hygiène & beauté": "shampoing, gel douche, deodorant, dentifrice, brosse a dents, rasoir, maquillage, creme visage, creme mains, lingettes, demaquillant, savon, parfum, couches, culottes, protege slip, serviettes hygieniques, coton, vernis, apres shampoing, soin, mouchoirs, coloration, visage",
    "Entretien": "lessive, adoucissant, liquide vaisselle, pastilles lave, eponge, nettoyant, javel, essuie tout, papier toilette, sacs poubelle, desodorisant, capsules de lessive, vinaigre d alcool",
    "Animaux": "chat, chien, croquettes, patee, litiere, sheba, felix, whiskas, pedigree, friskies, ultima",
    "Boissons": "biere, vin, rose, champagne, cremant, whisky, rhum, vodka, gin, jus, soda, coca, pepsi, eau minerale, eau gazeuse, sirop, ice tea, cafe, cafe grains, capsules cafe, dosettes, the, infusion, lait, beaujolais, aop, igp, mousseux, boisson",
    "Poisson & mer": "saumon, cabillaud, crevette, crevettes, thon, sardine, maquereau, moules, huitres, coquilles saint jacques, coquilles, colin, merlu, bar, dorade, poisson, surimi, crabe, langoustine, truite, rillettes de thon, calamar, seiche, delpierre, petit navire, poissons",
    "Volaille": "poulet, dinde, pintade, canard, magret, caille, chapon, volaille, cordon bleu, cordons bleus, nuggets, aiguillettes, maitre coq, loue",
    "Charcuterie": "jambon, saucisson, lardons, rillettes, pate, terrine, chorizo, bacon, knacki, saucisse de strasbourg, foie gras, andouille, andouillette, boudin, fleury michon, fuet, rosette, charcuterie",
    "Viande": "boeuf, veau, porc, agneau, steak, steaks haches, hache, entrecote, cote, roti, filet mignon, echine, saucisse, saucisses, merguez, chipolatas, paupiette, paupiettes, rognons, foie de boeuf, langue, osso bucco, bavette, charal, viande, boulettes",
    "Fromage": "fromage, camembert, emmental, comte, brie, raclette, mozzarella, cheddar, chevre, cabecou, crottin, roquefort, bleu d auvergne, reblochon, coulommiers, mimolette, parmesan, feta, tomme, madame loik, saint nectaire, tartiflette, buche aux laits",
    "Crèmerie & œufs": "yaourt, yaourts, creme fraiche, creme liquide, beurre, oeufs, oeuf, margarine, skyr, fromage blanc, dessert lacte, petits suisses, liegeois, danette, bridelice, desserts",
    "Fruits & légumes": "pomme, pommes, poire, banane, orange, clementine, mandarine, kiwi, avocat, raisin, fraise, citron, ananas, mangue, tomate, tomates, carotte, carottes, courgette, poireau, oignon, echalote, ail, salade, concombre, poivron, champignon, champignons, chou, brocoli, epinards, haricots verts, patate douce, pomme de terre, pommes de terre, potiron, courge, navet, radis, endive, pak choi, betterave, mache, fruits, legumes",
    "Surgelés": "pommes de terre surgelees, legumes surgeles, poisson pane, poissons panes, frites surgelees, surgele, surgeles, surgelee, surgelees, glace, glaces, cone, cones, mccain, frites, pizza surgelee, poelee, noisettes, pommes noisettes, picard",
    "Boulangerie": "pain, baguette, brioche, viennoiserie, croissant, pain de mie, pains a burger, pain a burger, wraps, tortilla, harrys, jacquet, pains au chocolat, boules mais",
    "Épicerie sucrée": "chocolat, chocolats, biscuit, biscuits, gateau, gateaux, bonbon, bonbons, confiture, pate a tartiner, nutella, cereales, granola, cacao, sucre, miel, compote, calendrier de l avent, ferrero, kinder, madeleine, panettone, milka, lindor, flocons d avoine, buche, canderel, delacre, deli choc, galettes",
    "Épicerie salée": "pates, pates fraiches, pennette, spaghetti, riz, lentilles, semoule, couscous, quinoa, gnocchi, gnocchis, conserve, sauce, huile, vinaigre, moutarde, mayonnaise, ketchup, epices, sel, poivre, soupe, chips, chipster, aperitif, biscuits aperitifs, cacahuetes, olives, bouillon, farine, plat cuisine, paella, lasagnes, lustucru, panzani, barilla, rana, tuc",
}
RAYONS_ALIMENTAIRES = {"Poisson & mer", "Volaille", "Charcuterie", "Viande", "Fromage", "Crèmerie & œufs",
                       "Fruits & légumes", "Surgelés", "Boulangerie", "Épicerie sucrée", "Épicerie salée"}
_RAYONS = [(r, [k.strip() for k in mots.split(",") if k.strip()]) for r, mots in RAYONS.items()]
# catégories bonial -> rayon, quand les mots-clés ne suffisent pas
_CATS = [("electromenager", "Maison & loisirs"), ("multimedia", "Maison & loisirs"), ("maison", "Maison & loisirs"),
         ("bijou", "Maison & loisirs"), ("jouet", "Maison & loisirs"), ("vetement", "Maison & loisirs"),
         ("decoration", "Maison & loisirs"), ("jardin", "Maison & loisirs"), ("animal", "Animaux"),
         ("hygiene", "Hygiène & beauté"), ("beaute", "Hygiène & beauté"), ("entretien", "Entretien"),
         ("menage", "Entretien"), ("boisson", "Boissons"), ("alcool", "Boissons"), ("vin", "Boissons"),
         ("surgele", "Surgelés"), ("fromage", "Fromage"), ("viande", "Viande"), ("volaille", "Volaille"),
         ("poisson", "Poisson & mer"), ("fruit", "Fruits & légumes"), ("legume", "Fruits & légumes"),
         ("charcuterie", "Charcuterie"), ("produits laitiers", "Crèmerie & œufs"), ("sucre", "Épicerie sucrée"),
         ("chocolat", "Épicerie sucrée"), ("alimentation", "Épicerie salée")]


def rayon(nom, marque="", categories=""):
    """Rayon le plus probable : le mot-clé le plus long trouvé gagne ("fromage blanc" bat "fromage")."""
    t = " " + norm((nom or "") + " " + (marque or "")) + " "
    meilleur, long_ = "Autres", 0
    for r, cles in _RAYONS:
        for k in cles:
            if (" " + k + " ") in t and len(k) > long_:
                meilleur, long_ = r, len(k)
    if meilleur == "Autres" and categories:
        c = " " + norm(categories) + " "
        for r, cles in _RAYONS:  # d'abord les mots-clés dans les catégories
            for k in cles:
                if (" " + k + " ") in c and len(k) > long_:
                    meilleur, long_ = r, len(k)
        if meilleur == "Autres":
            for mot, r in _CATS:
                if mot in c:
                    return r
    return meilleur


# --------------------------------------------------------------------------- bonial : données structurées
def donnees_next(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _date_locale(iso, fin=False):
    """bonial donne des heures UTC (23:00 la veille / 22:55 le dernier jour) : on revient au jour français."""
    try:
        d = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None
    return (d + timedelta(hours=1 if fin else 2)).date()


RE_2E = re.compile(r"\b(2\s*(e|eme|ème|nd)|deuxi[eè]me|second)\b", re.I)


def offre_bonial(o):
    """Une offre bonial -> notre format. None si inutilisable."""
    titre = (o.get("title") or "").strip()
    if not titre:
        return None
    pr = o.get("prices") or {}
    p1 = prix_float(pr.get("mainPrice")) or None
    p2 = prix_float(pr.get("secondaryPrice")) or None
    conds = []
    for c in pr.get("conditions") or []:
        if isinstance(c, dict):
            conds += [str(v) for v in c.values() if isinstance(v, (str, int, float)) and str(v).strip()]
        elif isinstance(c, str):
            conds.append(c)
    texte_prix = (pr.get("description") or "").strip()
    desc = [l.strip() for l in (o.get("description") or "").splitlines() if l.strip()]
    unite = next((l for l in desc if re.search(r"\b(kg|litre|le l|la piece)\b", norm(l)) and "€" in l), "")
    detail = " · ".join(l for l in desc[:2] if l != unite and "€" not in l)[:110]
    d1, d2 = _date_locale(o.get("validFrom")), _date_locale(o.get("validUntil"), fin=True)
    cats = " ".join(n.get("name", "") for path in (o.get("categoryPaths") or []) for n in path[-3:])
    cats += " " + " ".join(o.get("categories") or [])
    it = {
        "nom": titre, "marque": (o.get("brand") or "").strip(), "prix": p1,
        "avant": p2 if (p1 and p2 and p2 > p1) else None, "unite": unite, "detail": detail,
        "debut": d1.isoformat() if d1 else "", "fin": d2.isoformat() if d2 else "",
        "categories": cats, "catalogue": str((o.get("parentContent") or {}).get("legacyId") or ""),
        "page": ((o.get("parentContent") or {}).get("page") or {}).get("number"),
    }
    tout_cond = " ".join(conds + [texte_prix])
    if p1 and it["avant"] and RE_2E.search(tout_cond):
        # « -60 % sur le 2e » : le prix affiché est celui du 2e produit, pas de chaque produit
        it["condition"] = "le 2e"
        it["remise_affichee"] = round((1 - p1 / it["avant"]) * 100)
        it["remise_effective"] = round((1 - (it["avant"] + p1) / (2 * it["avant"])) * 100)
    if not p1:
        # offre sans prix (« -50 % sur le 2e », « 34 % sur la carte U ») : le titre EST le bon plan
        it["prix"] = None
        it["bon_plan"] = texte_prix if texte_prix and norm(texte_prix) != norm(titre) else titre
        if it["marque"] and len(titre) > 30:
            it["nom"] = it["marque"].title() if it["marque"].isupper() else it["marque"]
    elif texte_prix and not it.get("condition") and len(texte_prix) < 120:
        it["bon_plan"] = texte_prix
    if conds and not it.get("condition"):
        c = " · ".join(dict.fromkeys(conds))
        if len(c) < 80 and norm(c) not in norm(it.get("bon_plan", "")):
            it["bon_plan"] = (it.get("bon_plan", "") + " · " + c).strip(" ·")
    return it


def brochures_bonial(pi):
    sortie = []
    br = pi.get("brochures") or {}
    for cle in ("viewer", "publisher"):
        for b in br.get(cle) or []:
            if not isinstance(b, dict) or not b.get("id"):
                continue
            pages = None
            for pg in b.get("pages") or []:
                alt = ((pg or {}).get("metaData") or {}).get("imageAlt") or ""
                m = re.search(r"(\d+)\s+pages?", alt)
                if m:
                    pages = int(m.group(1))
                    break
            sortie.append({"id": str(b.get("id")), "titre": (b.get("title") or "").strip(),
                           "debut": _date_locale(b.get("validFrom")), "fin": _date_locale(b.get("validUntil"), fin=True),
                           "pages": pages or len(b.get("pages") or []) or 1})
    return sortie


def page_bonial(page):
    """-> (offres, catalogues, liens magasins) depuis une page bonial « enseigne dans une ville »."""
    d = donnees_next(page)
    if not d:
        return [], [], []
    pi = ((d.get("props") or {}).get("pageProps") or {}).get("pageInformation") or {}
    offres = []
    for cle, bloc in (pi.get("offers") or {}).items():
        for o in (bloc or {}).get("items") or []:
            it = offre_bonial(o)
            if it:
                offres.append(it)
    return offres, brochures_bonial(pi), re.findall(r'href="(https://www\.bonial\.fr/Magasins/[^"]+/v-f\d+)"', page)


# --------------------------------------------------------------------------- bonial : texte (secours)
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


def extraire_bonial_texte(page, nom_enseigne):
    items = []
    for m in RE_ALT.finditer(html.unescape(page)):
        nom = m.group(1).strip().strip('"')
        p = prix_float(m.group(2)) if m.group(2) else None
        items.append({"nom": nom, "marque": "", "prix": p, "avant": None, "bon_plan": "" if p else nom})
    return items


# extraction JSON générique (utilisée par diag.py)
CLES_NOM = ("name", "title", "productName", "product_name", "label", "nom", "offerTitle")
CLES_PRIX = ("price", "priceValue", "salePrice", "currentPrice", "prix", "finalPrice", "promoPrice",
             "offerPrice", "lowPrice", "dealPrice", "mainPrice")


def extraire_json(page):
    trouves = []

    def marche(o, prof=0):
        if prof > 40:
            return
        if isinstance(o, dict):
            nom = next((o[k] for k in CLES_NOM if isinstance(o.get(k), str)), None)
            prix = next((o[k] for k in CLES_PRIX if o.get(k) not in (None, "", 0)), None)
            if prix is None and isinstance(o.get("prices"), dict):
                prix = o["prices"].get("mainPrice")
            if nom and prix is not None and prix_float(prix):
                trouves.append({"nom": nom, "prix": prix_float(prix)})
            for v in o.values():
                marche(v, prof + 1)
        elif isinstance(o, list):
            for v in o:
                marche(v, prof + 1)
    for mm in re.finditer(r"<script([^>]*)>(.*?)</script>", page, re.S | re.I):
        corps = mm.group(2).strip()
        if corps[:1] in "{[":
            try:
                marche(json.loads(corps))
            except ValueError:
                pass
    return trouves


# --------------------------------------------------------------------------- catalogues & calendrier
MOTS_OPE = ("jeudi", "vendredi", "samedi", "week", "carte", "flash", "inratable", "prix bas", "black", "foire",
            "anniversaire", "jours", "%")


def est_operation(titre, debut, fin):
    t = norm(titre)
    duree = (fin - debut).days + 1 if debut and fin else 99
    return duree <= 5 or "%" in titre or any(norm(k) in t for k in MOTS_OPE if k != "%")


def ecrire_ics(evenements, chemin, nom_cal="Mes promos", extras=()):
    """Calendrier à s'abonner sur le téléphone : un événement par catalogue / opération, avec alerte à 9 h.
    extras : événements en plus (alertes produits surveillés) : dicts uid, jour (date), resume, desc."""
    def e(t):
        return str(t).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mes promos//FR", "CALSCALE:GREGORIAN",
              "X-WR-CALNAME:" + nom_cal, "X-WR-TIMEZONE:Europe/Paris", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
              "X-PUBLISHED-TTL:PT12H"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def evt(uid, jour, resume, desc=""):
        lignes.extend(["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + stamp,
                       "DTSTART;VALUE=DATE:" + jour.strftime("%Y%m%d"),
                       "DTEND;VALUE=DATE:" + (jour + timedelta(days=1)).strftime("%Y%m%d"),
                       "SUMMARY:" + e(resume)] + (["DESCRIPTION:" + e(desc)] if desc else []) +
                      ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + e(resume),
                       "TRIGGER;RELATED=START:PT9H", "END:VALARM", "END:VEVENT"])
    for x in evenements:
        d1, d2 = date.fromisoformat(x["debut"]), date.fromisoformat(x["fin"])
        uid = slug(x["enseigne"] + " " + x["titre"] + " " + x["debut"]) + "@mes-promos"
        titre = x["titre"].title() if x["titre"].isupper() else x["titre"]
        resume = ("⚡ " if x.get("operation") else "") + "%s : %s" % (x["nom"], titre)
        evt(uid, d1, resume, "Du %s au %s. Ouvre l'appli Mes promos pour le détail." % (d1.strftime("%d/%m"), d2.strftime("%d/%m")))
        if x.get("operation") and (d2 - d1).days >= 1:
            evt("fin-" + uid, d2, "Dernier jour : " + resume)
    for x in extras:
        evt(x["uid"], x["jour"], x["resume"], x.get("desc", ""))
    lignes.append("END:VCALENDAR")
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lignes) + "\r\n")


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


def dates_slug(s):
    s = norm(s.replace("-", " "))
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
        p = telecharger("https://anti-crise.fr/", log)
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
        if en_cours:
            b = sorted(en_cours, key=lambda b: b[0][0])[-1]
            return b[1], b[0]
        futurs = sorted([b for b in bons if b[0][1] >= aujourd], key=lambda b: b[0][0])
        if futurs:
            return futurs[0][1], futurs[0][0]
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
            promo = prix_float(r[ix["promo"]]) or 0.0 if "promo" in ix and ix["promo"] < len(r) else 0.0
            final = prix_float(r[ix["prix final"]]) if "prix final" in ix and ix["prix final"] < len(r) else None
            marque = r[ix["marque"]] if "marque" in ix and ix["marque"] < len(r) else ""
            prix = round(total - abs(promo), 2)
            it = {"nom": produit + (" (lot de %d)" % q if q > 1 else ""), "marque": marque, "prix": prix,
                  "avant": total if promo else None}
            if final is not None and final < prix - 0.01:
                it["bon_plan"] = "%s avec bons / remboursement" % euro(final)
            items.append(it)
    return items


# --------------------------------------------------------------------------- configuration
def charger_config():
    with open(os.path.join(ICI, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    # compatibilité avec l'ancien format ("sources": [...])
    for e in cfg.get("enseignes", []):
        for s in e.pop("sources", []) or []:
            if s.get("type") == "bonial" and "bonial" not in e:
                m = re.match(r"https://www\.bonial\.fr/([^/]+)/(.+)$", s.get("url", ""))
                if m:
                    e["bonial"] = {"ville": m.group(1), "page": m.group(2)}
            if s.get("type") == "anticrise" and "anticrise" not in e:
                e["anticrise"] = {"motif": s.get("motif"), "secours": s.get("secours")}
    return cfg


def charger_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire_json(chemin, obj, indent=None):
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=(",", ":") if indent is None else None)
    os.replace(tmp, chemin)


# --------------------------------------------------------------------------- nettoyage
def jj_mm(iso):
    return iso[8:10] + "/" + iso[5:7] if iso else ""


def nettoyer(items, ens, validite_defaut, aujourd):
    vus, sortie = {}, []
    for it in items:
        nom = re.sub(r"\s+", " ", (it.get("nom") or "")).strip(" –:")
        if len(nom) < 2:
            continue
        if it.get("fin") and it["fin"] < aujourd.isoformat():
            continue  # offre terminée
        marque = (it.get("marque") or "").strip()
        if marque.isupper() and len(marque) > 3:
            marque = marque.title()
        cle = norm(nom) + "|" + norm(marque)
        if cle in vus:  # garder la version la plus complète
            a = vus[cle]
            for k in ("avant", "prix", "unite", "detail", "debut", "fin"):
                if not a.get(k) and it.get(k):
                    a[k] = it[k]
            continue
        p, av = it.get("prix"), it.get("avant")
        rem = it.get("remise_effective")
        if rem is None and p and av and av > p:
            rem = round((1 - p / av) * 100)
        validite = ("du %s au %s" % (jj_mm(it["debut"]), jj_mm(it["fin"]))) if it.get("debut") and it.get("fin") else validite_defaut
        e = {
            "id": "%s-%s%s" % (ens["id"], slug(nom)[:55], ("-" + slug(marque)[:18]) if marque else ""),
            "enseigne": ens["id"], "nom": nom, "marque": marque, "prix": p, "avant": av, "remise": rem,
            "unite": it.get("unite") or "", "detail": it.get("detail") or "", "bon_plan": it.get("bon_plan") or "",
            "rayon": rayon(nom, marque, it.get("categories", "")), "validite": validite,
            "debut": it.get("debut") or "", "fin": it.get("fin") or "",
        }
        if it.get("condition"):
            e["condition"] = it["condition"]
            e["remise_2e"] = it.get("remise_affichee")
        vus[cle] = e
        sortie.append(e)
    return sortie


# --------------------------------------------------------------------------- historique des prix
def mettre_historique(promos, aujourd):
    h = charger_json(HISTORIQUE, {})
    jour = aujourd.isoformat()
    limite = (aujourd - timedelta(days=400)).isoformat()
    for p in promos:
        if p.get("prix") is None:
            continue
        cle = p["enseigne"] + "|" + norm(p["nom"]) + "|" + norm(p.get("marque"))
        lst = [x for x in h.get(cle, []) if x[0] >= limite]
        # infos pour l'appli : prix vus avant cette semaine
        avant = [x for x in lst if x[0] < (aujourd - timedelta(days=6)).isoformat()]
        if avant:
            mini = min(avant, key=lambda x: x[1])
            p["histo"] = {"min": mini[1], "min_date": mini[0], "fois": len({x[0][:7] for x in avant}) + 1}
        if not lst or lst[-1][1] != p["prix"] or lst[-1][0] < (aujourd - timedelta(days=6)).isoformat():
            if not (lst and lst[-1][0] == jour):
                lst.append([jour, p["prix"]])
        h[cle] = lst[-40:]
    h = {k: v for k, v in h.items() if v and v[-1][0] >= limite}
    ecrire_json(HISTORIQUE, h)


# --------------------------------------------------------------------------- mise à jour
def mettre_a_jour(debug=False, log=print):
    os.makedirs(DATA, exist_ok=True)
    dossier_debug = os.path.join(DATA, "debug")
    if debug:
        os.makedirs(dossier_debug, exist_ok=True)
    cfg = charger_config()
    ancien = charger_json(FICHIER, {"enseignes": {}, "promos": []})
    aujourd = date.today()
    resultat = {"maj": datetime.now().isoformat(timespec="seconds"), "ville": cfg.get("ville", ""),
                "enseignes": {}, "promos": [], "evenements": []}
    voisines = cfg.get("villes_voisines", [])
    cache = {}

    for ens in cfg["enseignes"]:
        if not ens.get("actif", True):
            continue
        log("→ %s" % ens["nom"])
        bruts, sources, catalogues, magasin = [], [], [], None
        b = ens.get("bonial")
        if b:
            url = "https://www.bonial.fr/%s/%s" % (b["ville"], b["page"])
            page = telecharger(url, log)
            if page:
                if debug:
                    with open(os.path.join(dossier_debug, "%s-%s.html" % (ens["id"], b["ville"])), "w", encoding="utf-8") as f:
                        f.write(page)
                offres, catalogues, liens = page_bonial(page)
                if not offres:  # page sans données structurées : lecture du texte
                    offres = extraire_bonial_texte(page, ens["nom"])
                bruts += offres
                sources.append(url)
                magasin = next((l for l in liens if "/Magasins/%s/" % b["ville"] in l), None)
                log("   %s : %d offres, %d catalogues" % (b["ville"], len(offres), len(catalogues)))
            permis = {c["id"] for c in catalogues}
            # même enseigne dans les villes voisines : autre sélection d'offres, mêmes catalogues
            if permis:
                total = 0
                for v in voisines:
                    if v == b["ville"]:
                        continue
                    time.sleep(0.8)
                    pg = telecharger("https://www.bonial.fr/%s/%s" % (v, b["page"]), log)
                    if not pg:
                        continue
                    offres, _, _ = page_bonial(pg)
                    gardees = [o for o in offres if o.get("catalogue") in permis]
                    total += len(gardees)
                    bruts += gardees
                log("   villes voisines : %d offres de plus (catalogues valables à %s)" % (total, b["ville"]))
        a = ens.get("anticrise")
        if a:
            url, dates = trouver_anticrise(a.get("motif"), a.get("secours"), log, cache)
            if url:
                page = telecharger(url, log)
                its = extraire_anticrise(page) if page else []
                if its and dates:
                    for it in its:
                        it["debut"], it["fin"] = dates[0].isoformat(), dates[1].isoformat()
                log("   anti-crise : %d produits" % len(its))
                if its:
                    bruts += its
                    sources.append(url)
            time.sleep(0.8)

        # catalogues -> agenda
        evts = []
        for c in catalogues:
            if not c["debut"] or not c["fin"] or c["fin"] < aujourd or (c["fin"] - c["debut"]).days > 120:
                continue
            evts.append({"enseigne": ens["id"], "nom": ens["nom"], "titre": c["titre"], "pages": c["pages"],
                         "debut": c["debut"].isoformat(), "fin": c["fin"].isoformat(),
                         "operation": est_operation(c["titre"], c["debut"], c["fin"])})
        vus = set()
        for e in evts:
            k = (norm(e["titre"]), e["debut"], e["fin"])
            if k not in vus:
                vus.add(k)
                resultat["evenements"].append(e)

        principal = max((c for c in catalogues if c["debut"] and c["fin"] and c["debut"] <= aujourd <= c["fin"]),
                        key=lambda c: c["pages"] or 0, default=None)
        val_defaut = ("du %s au %s" % (principal["debut"].strftime("%d/%m"), principal["fin"].strftime("%d/%m"))) if principal else ""
        promos = nettoyer(bruts, ens, val_defaut, aujourd)
        info = {"nom": ens["nom"], "validite": val_defaut, "nb": len(promos), "maj": resultat["maj"],
                "ancien": False, "sources": sources}
        if magasin:
            info["magasin"] = magasin
            fiche = telecharger(magasin, log)
            st = ((((donnees_next(fiche) or {}).get("props") or {}).get("pageProps") or {}).get("pageInformation") or {}).get("store") or {}
            if st:
                info["adresse"] = " ".join(x for x in [str(st.get("houseNumber") or ""), st.get("street") or ""] if x).strip() + \
                    (", %s %s" % (st.get("zipCode") or "", st.get("cityName") or "")).rstrip()
                if st.get("lat") and st.get("lng"):
                    info["lat"], info["lng"] = st["lat"], st["lng"]
        if promos:
            resultat["enseignes"][ens["id"]] = info
            resultat["promos"] += promos
            log("   ✓ %d promos gardées" % len(promos))
        else:
            # rien trouvé : on garde les promos précédentes encore valables plutôt que de tout vider
            garde = [p for p in ancien.get("promos", []) if p.get("enseigne") == ens["id"]
                     and (not p.get("fin") or p["fin"] >= aujourd.isoformat())]
            info.update(ancien.get("enseignes", {}).get(ens["id"], {}))
            info.update({"nb": len(garde), "ancien": True, "nom": ens["nom"]})
            resultat["enseignes"][ens["id"]] = info
            resultat["promos"] += garde
            log("   ✗ rien de nouveau, %d anciennes promos conservées" % len(garde))
        time.sleep(0.8)

    if not any(not e.get("ancien") for e in resultat["enseignes"].values()):
        log("Aucune nouvelle promo trouvée (connexion internet ? sites changés ?). Les promos actuelles sont gardées.")
        return ancien

    resultat["evenements"].sort(key=lambda e: (e["debut"], e["nom"]))
    try:
        ecrire_ics(resultat["evenements"], os.path.join(DATA, "rappels.ics"))
    except Exception as e:
        log("Calendrier non écrit : %s" % e)
    try:
        mettre_historique(resultat["promos"], aujourd)
    except Exception as e:
        log("Historique non mis à jour : %s" % e)
    ecrire_json(FICHIER, resultat)
    log("Catalogues et opérations : %d" % len(resultat["evenements"]))
    log("Terminé : %d promos enregistrées" % len(resultat["promos"]))
    return resultat


if __name__ == "__main__":
    mettre_a_jour(debug="--debug" in sys.argv)
