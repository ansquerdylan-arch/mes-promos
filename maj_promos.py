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


DERNIER = {"code": None}


def telecharger(url, log):
    DERNIER["code"] = None
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
        DERNIER["code"] = e.code
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


def infos_page(page):
    d = donnees_next(page)
    return (((d or {}).get("props") or {}).get("pageProps") or {}).get("pageInformation") or {}


def page_bonial(page, pi=None):
    """-> (offres, catalogues, liens magasins) depuis une page bonial « enseigne dans une ville »."""
    if pi is None:
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


# --------------------------------------------------------------------------- enseignes suivies
# nom de page bonial -> (id, nom affiché, famille)
FAMILLES = [
    (r"Super-U", "superu", "Super U", "u"),
    (r"Hyper-U", "hyperu", "Hyper U", "u"),
    (r"U-Express", "uexpress", "U Express", "u"),
    (r"Marche-U", "marcheu", "Marché U", "u"),
    (r"E-Leclerc", "leclerc", "E.Leclerc", "leclerc"),
    (r"Intermarche(-(?:Super|Hyper|Contact|Express))?", "intermarche", "Intermarché", "intermarche"),
    (r"Lidl", "lidl", "Lidl", "lidl"),
    (r"Carrefour(-(?:Market|City|Contact|Express|Proximite))?", "carrefour", "Carrefour", "carrefour"),
]


def chaine_de(nom_page):
    for motif, ident, nom, fam in FAMILLES:
        m = re.fullmatch(motif, nom_page or "")
        if m:
            suffixe = (m.group(1) or "").strip("-") if m.groups() else ""
            if suffixe:
                jolis = {"Proximite": "Proximité"}
                return {"id": ident + suffixe.lower(), "nom": nom + " " + jolis.get(suffixe, suffixe), "famille": fam}
            return {"id": ident, "nom": nom, "famille": fam}
    return None


def distance_km(a, b):
    try:
        from math import radians, sin, cos, asin, sqrt
        la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
        h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
        return 6371 * 2 * asin(sqrt(h))
    except Exception:
        return 9999


# --------------------------------------------------------------------------- exploration de la Vendée
def explorer(cfg, log, debug=False):
    """Parcourt les pages bonial « enseigne dans une ville » de proche en proche :
    chaque page donne ses promos, ses catalogues, les magasins de l'enseigne aux alentours
    (adresse, code postal, horaires) et les autres enseignes de la ville."""
    from collections import deque
    dept = str(cfg.get("departement", "85"))
    maxi = int(cfg.get("max_pages", 400))
    pause = float(cfg.get("pause", 0.7))
    file = deque(cfg.get("graines", []))
    vus, zones, magasins, catalogues, offres = set(), {}, {}, {}, []
    n, arret = 0, False
    while file and n < maxi:
        chemin = file.popleft()
        if chemin in vus:
            continue
        vus.add(chemin)
        try:
            ville, nom_page, pid = chemin.split("/")
        except ValueError:
            continue
        ch = chaine_de(nom_page)
        if not ch:
            continue
        page = telecharger("https://www.bonial.fr/" + chemin, log)
        n += 1
        time.sleep(pause)
        if not page:
            if DERNIER["code"] in (403, 429):
                log("   ! le site freine (%s) : arrêt de l'exploration, les données manquantes seront reprises de la veille" % DERNIER["code"])
                arret = True
                break
            continue
        pi = infos_page(page)
        cite = pi.get("city") or {}
        cp = str(cite.get("primaryZipCode") or "")
        if not cp.startswith(dept):
            continue  # hors Vendée
        if debug:
            with open(os.path.join(DATA, "debug", chemin.replace("/", "_") + ".html"), "w", encoding="utf-8") as f:
                f.write(page)
        its, brochures, _ = page_bonial(page, pi)
        cle = ville + "|" + ch["id"]
        zones[cle] = {"ville": cite.get("displayName") or cite.get("name") or ville, "slug": ville, "chaine": ch["id"],
                      "page": chemin, "cp": cp, "lat": cite.get("lat"), "lng": cite.get("lng"),
                      "catalogues": sorted({b["id"] for b in brochures})}
        for b in brochures:
            catalogues[b["id"]] = dict(b, chaine=ch["id"])
        for it in its:
            it["chaine"] = ch["id"]
            offres.append(it)
        cont = (pi.get("template") or {}).get("content") or {}
        # magasins de l'enseigne aux alentours
        for l in ((cont.get("StoreLogoLinkbox") or {}).get("links") or []):
            m = re.match(r"https://www\.bonial\.fr/Magasins/([^/]+)/[^/]+/v-f(\d+)", l.get("link_href") or "")
            lt = l.get("link_text") or {}
            mc = re.match(r"(\d{5})\s+(.+)", (lt.get("city") or "").strip())
            if not m or not mc or not mc.group(1).startswith(dept):
                continue
            chm = chaine_de(l.get("publisherUrl") or nom_page)
            if not chm or chm["id"] != ch["id"]:
                continue
            sid = ch["id"] + "-" + m.group(2)
            horaires = [[h.get("dayOfWeek"), h.get("minutesFrom"), h.get("minutesTo")]
                        for h in ((l.get("openingHours") or {}).get("regularOpeningHours") or []) if h.get("dayOfWeek")]
            magasins[sid] = {"id": sid, "chaine": ch["id"], "nom": ch["nom"], "adresse": (lt.get("address") or "").strip(),
                             "cp": mc.group(1), "ville": mc.group(2).strip(), "slug_ville": m.group(1),
                             "horaires": horaires, "zone_ref": cle, "fiche": l.get("link_href")}
            file.append("%s/%s/%s" % (m.group(1), nom_page, pid))
        # autres enseignes de la même ville
        for l in ((cont.get("PublisherLogoLinkbox") or {}).get("links") or []):
            m = re.match(r"https://www\.bonial\.fr/([^/]+)/([^/]+)/(p-r\d+)$", l.get("link_href") or "")
            if m and chaine_de(m.group(2)):
                file.append("%s/%s/%s" % m.groups())
    log("Exploration : %d pages lues, %d villes/enseignes, %d magasins, %d catalogues" % (n, len(zones), len(magasins), len(catalogues)))
    return zones, magasins, catalogues, offres, arret


def construire_offres(brutes, aujourd):
    """Offres dédoublonnées par enseigne + catalogue."""
    vus, sortie = {}, []
    for it in brutes:
        nom = re.sub(r"\s+", " ", (it.get("nom") or "")).strip(" –:")
        if len(nom) < 2 or (it.get("fin") and it["fin"] < aujourd.isoformat()):
            continue
        marque = (it.get("marque") or "").strip()
        if marque.isupper() and len(marque) > 3:
            marque = marque.title()
        cat = it.get("catalogue") or "*"
        cle = "%s|%s|%s|%s" % (it["chaine"], cat, norm(nom), norm(marque))
        if cle in vus:
            a = vus[cle]
            for k in ("avant", "prix", "unite", "detail", "debut", "fin"):
                if not a.get(k) and it.get(k):
                    a[k] = it[k]
            continue
        p, av = it.get("prix"), it.get("avant")
        rem = it.get("remise_effective")
        if rem is None and p and av and av > p:
            rem = round((1 - p / av) * 100)
        e = {"k": "%s-%s%s" % (it["chaine"], slug(nom)[:55], ("-" + slug(marque)[:18]) if marque else ""),
             "chaine": it["chaine"], "cat": cat, "nom": nom, "marque": marque, "prix": p, "avant": av, "remise": rem,
             "unite": it.get("unite") or "", "detail": it.get("detail") or "", "bon_plan": it.get("bon_plan") or "",
             "rayon": rayon(nom, marque, it.get("categories", "")), "debut": it.get("debut") or "", "fin": it.get("fin") or ""}
        if it.get("condition"):
            e["condition"], e["remise_2e"] = it["condition"], it.get("remise_affichee")
        vus[cle] = e
        sortie.append(e)
    return sortie


def vue_magasins(donnees, ids):
    """Ce que voit l'appli pour une sélection de magasins : promos, enseignes, agenda.
    (même logique que dans la page, utilisée ici pour le calendrier et les alertes)"""
    mags = {m["id"]: m for m in donnees.get("magasins", [])}
    zones, cats = donnees.get("zones", {}), donnees.get("catalogues", {})
    aujourd = date.today().isoformat()
    enseignes, promos, evts = {}, [], []
    for sid in ids:
        m = mags.get(sid)
        if not m:
            continue
        z = zones.get(m.get("zone") or "", {})
        ok = set(z.get("catalogues", []))
        nom = "%s %s" % (m["nom"], m["ville"])
        mes = [o for o in donnees.get("offres", []) if o["chaine"] == m["chaine"] and (o["cat"] == "*" or o["cat"] in ok)]
        for o in mes:
            q = dict(o, id=sid + "|" + o["k"], enseigne=sid,
                     validite=("du %s au %s" % (jj_mm(o["debut"]), jj_mm(o["fin"]))) if o.get("debut") and o.get("fin") else "")
            promos.append(q)
        enseignes[sid] = {"nom": nom, "chaine": m["chaine"], "nb": len(mes)}
        for c in ok:
            x = cats.get(c)
            if x and x.get("fin", "") >= aujourd:
                evts.append({"enseigne": sid, "nom": nom, "titre": x["titre"], "pages": x.get("pages"),
                             "debut": x["debut"], "fin": x["fin"], "operation": x.get("operation")})
    evts.sort(key=lambda e: (e["debut"], e["nom"]))
    return enseignes, promos, evts


# --------------------------------------------------------------------------- historique des prix
# --------------------------------------------------------------------------- historique des prix
def mettre_historique(promos, aujourd):
    h = charger_json(HISTORIQUE, {})
    jour = aujourd.isoformat()
    limite = (aujourd - timedelta(days=400)).isoformat()
    for p in promos:
        if p.get("prix") is None:
            continue
        cle = p.get("chaine", p.get("enseigne")) + "|" + norm(p["nom"]) + "|" + norm(p.get("marque"))
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
def mettre_a_jour(debug=False, log=print, essai=False):
    os.makedirs(DATA, exist_ok=True)
    if debug:
        os.makedirs(os.path.join(DATA, "debug"), exist_ok=True)
    cfg = charger_config()
    ancien = charger_json(FICHIER, {})
    aujourd = date.today()
    jour = aujourd.isoformat()

    zones, magasins, catalogues, brutes, arret = explorer(cfg, log, debug)

    # promos nationales d'anti-crise : valables dans tous les magasins de l'enseigne
    cache = {}
    for ident, a in (cfg.get("anticrise") or {}).items():
        url, dates = trouver_anticrise(a.get("motif"), a.get("secours"), log, cache)
        if not url:
            continue
        page = telecharger(url, log)
        its = extraire_anticrise(page) if page else []
        for it in its:
            it["chaine"] = ident
            it["catalogue"] = "*"
            if dates:
                it["debut"], it["fin"] = dates[0].isoformat(), dates[1].isoformat()
        brutes += its
        log("   anti-crise %s : %d produits" % (ident, len(its)))
        time.sleep(0.7)

    # si l'exploration a été coupée : on garde ce qu'on avait la veille pour les villes non relues
    if ancien.get("v") == 2:
        for k, z in (ancien.get("zones") or {}).items():
            if k not in zones:
                zones[k] = z
        for k, mg in {m["id"]: m for m in ancien.get("magasins", [])}.items():
            magasins.setdefault(k, mg)
        for k, c in (ancien.get("catalogues") or {}).items():
            if c.get("fin", "") >= jour:
                catalogues.setdefault(k, c)
        lus = {(o["chaine"], o.get("catalogue")) for o in brutes}
        for o in ancien.get("offres", []):
            if (o["chaine"], o["cat"]) not in lus and o["cat"] in catalogues and (not o.get("fin") or o["fin"] >= jour):
                brutes.append(dict(o, catalogue=o["cat"]))

    # magasins -> zone (page de leur ville, sinon celle où on les a trouvés), position
    for m in magasins.values():
        z = m["slug_ville"] + "|" + m["chaine"]
        m["zone"] = z if z in zones else m.get("zone_ref")
        zz = zones.get(m["zone"]) or {}
        zv = next((x for k, x in zones.items() if k.startswith(m["slug_ville"] + "|")), None) or zz
        m["lat"], m["lng"] = zv.get("lat"), zv.get("lng")
    magasins = {k: m for k, m in magasins.items() if m.get("zone") in zones}

    # catalogues : dates françaises, opérations courtes repérées
    cats = {}
    for k, c in catalogues.items():
        d1, d2 = c.get("debut"), c.get("fin")
        if isinstance(d1, date):
            d1, d2 = d1.isoformat(), d2.isoformat()
        if not d1 or not d2 or d2 < jour:
            continue
        if (date.fromisoformat(d2) - date.fromisoformat(d1)).days > 120:
            continue
        cats[k] = {"chaine": c["chaine"], "titre": c["titre"], "debut": d1, "fin": d2, "pages": c.get("pages"),
                   "operation": est_operation(c["titre"], date.fromisoformat(d1), date.fromisoformat(d2))}
    for z in zones.values():
        z["catalogues"] = [c for c in z["catalogues"] if c in cats]

    offres = construire_offres(brutes, aujourd)
    offres = [o for o in offres if o["cat"] == "*" or o["cat"] in cats]

    # magasins proposés par défaut : le plus proche de chez toi pour chaque enseigne de config
    dom = cfg.get("domicile") or {}
    pos = (dom.get("lat"), dom.get("lng"))
    defaut = []
    for ident in cfg.get("enseignes_defaut", []):
        cand = [m for m in magasins.values() if m["chaine"] == ident or (ident.endswith("*") and m["chaine"].startswith(ident[:-1]))]
        cand = [m for m in cand if m.get("lat")]
        if cand and pos[0]:
            defaut.append(min(cand, key=lambda m: distance_km(pos, (m["lat"], m["lng"])))["id"])

    chaines = {}
    for m in magasins.values():
        ch = chaine_de_id(m["chaine"])
        chaines[m["chaine"]] = {"nom": m["nom"], "famille": ch}
    resultat = {"v": 2, "maj": datetime.now().isoformat(timespec="seconds"), "ville": dom.get("ville", ""),
                "departement": str(cfg.get("departement", "85")), "domicile": dom, "chaines": chaines,
                "zones": zones, "magasins": sorted(magasins.values(), key=lambda m: (m["ville"], m["nom"])),
                "catalogues": cats, "offres": offres, "defaut": defaut}

    if not offres:
        log("Aucune promo trouvée (connexion internet ? site changé ?). Les promos actuelles sont gardées.")
        return ancien
    try:
        mettre_historique(offres, aujourd)
    except Exception as e:
        log("Historique non mis à jour : %s" % e)
    # vue « magasins par défaut » (anciennes versions de l'appli + calendrier de base)
    ens, promos, evts = vue_magasins(resultat, defaut)
    resultat["enseignes"], resultat["promos"], resultat["evenements"] = ens, promos, evts
    if essai:
        log("ESSAI : rien n'est enregistré.")
        return resultat
    try:
        ecrire_ics(evts, os.path.join(DATA, "rappels.ics"))
    except Exception as e:
        log("Calendrier non écrit : %s" % e)
    ecrire_json(FICHIER, resultat)
    log("Terminé : %d magasins, %d catalogues, %d offres" % (len(magasins), len(cats), len(offres)))
    return resultat


def chaine_de_id(ident):
    for motif, i, nom, fam in FAMILLES:
        if ident.startswith(i):
            return fam
    return ident


if __name__ == "__main__":
    r = mettre_a_jour(debug="--debug" in sys.argv, essai="--essai" in sys.argv)
    if "--essai" in sys.argv and r:
        from collections import Counter
        print("Magasins par enseigne :", dict(Counter(m["chaine"] for m in r.get("magasins", []))))
        print("Offres par enseigne :", dict(Counter(o["chaine"] for o in r.get("offres", []))))
        print("Villes :", sorted({m["ville"] for m in r.get("magasins", [])}))
        print("Par défaut :", [(m["nom"], m["ville"]) for m in r.get("magasins", []) if m["id"] in r.get("defaut", [])])
        print("Exemple magasin :", json.dumps(r.get("magasins", [{}])[0], ensure_ascii=False)[:400])
