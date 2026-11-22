#!/usr/bin/env python3
"""Producteurs locaux et marchés de Vendée, pour l'onglet « Local » de Mogette.

Sources ouvertes, relues une fois par semaine (les autres jours, rien n'est téléchargé) :
- Vendée Expansion : fiches « Producteurs locaux et découverte de savoir-faire » et marchés de l'agenda
  (flux Tourinsoft publiés sur data.gouv.fr, Licence Ouverte 2.0) ;
- Agence Bio : producteurs bio qui vendent aux particuliers (API Professionnels du bio, Licence Ouverte 2.0) ;
- OpenStreetMap : vente à la ferme, brasseries, vignerons, apiculteurs, distributeurs, marchés
  (© contributeurs OpenStreetMap, licence ODbL) ;
- noms officiels des communes (geo.api.gouv.fr).
Si une source ne répond pas, ses fiches de la semaine précédente sont gardées.
Écrit producteurs.json à côté des promos.

    python producteurs.py            mise à jour si la dernière a plus de 6 jours
    python producteurs.py --forcer   mise à jour tout de suite
    python producteurs.py --essai    mise à jour tout de suite et détails dans le journal
"""
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from maj_promos import DATA, OSM_API, charger_json, distance_km, ecrire_json, horaires_osm, norm

FICHIER = os.path.join(DATA, "producteurs.json")
UA = "Mogette/1.0 (appli de promos, github.com/ansquerdylan-arch/mes-promos)"
FLUX_PRODUCTEURS = "https://www.data.gouv.fr/api/1/datasets/r/81fa2a94-d788-4a2f-85d0-800ba3fb5e96"
FLUX_AGENDA = "https://www.data.gouv.fr/api/1/datasets/r/5121010c-cdf4-40e9-8a49-64efd41f3fce"
API_BIO = "https://opendata.agencebio.org/api/gouv/operateurs/?departements=85&nb=1000&debut=%d"
API_COMMUNES = "https://geo.api.gouv.fr/departements/85/communes?fields=nom,code,centre&format=json&geometry=centre"
TOUS_LES = 6        # jours entre deux lectures des sources
HORIZON = 35        # jours de marchés gardés à l'avance
JOURS_BONIAL = [2, 3, 4, 5, 6, 7, 1]  # lundi … dimanche -> 1 = dimanche … 7 = samedi (comme les magasins)

# familles de produits (les mêmes clés dans l'appli)
FAMILLES = ["fl", "viande", "vo", "lait", "miel", "vin", "biere", "cidre", "mer", "sel", "pain", "sucre", "epicerie", "fleurs"]

# mots qui rangent un producteur dans une famille (texte sans accents, en minuscules)
MOTS = [
    ("fl", r"maraich|legume|potager|pomme de terre|patate|arboricult|verger|fruit|fraise|framboise|kiwi|melon|tomate|salade|mache|asperge|champignon|abricot|cerise|prune|poire|noix|chataign|courge|potiron|carotte|oignon|echalote"),
    ("vo", r"volaille|poulet|\bpoules?\b|pondeuse|oeuf|canard|pintade|dinde|\boie\b|chair\b|aviculture"),
    ("viande", r"viande|boeuf|\bveau|porc|agneau|ovins? viande|mouton|lapin|charcut|rillette|foie gras|salaison|betail|cochon|allaitant|caprins? viande"),
    ("lait", r"lait|fromag|chevre|brebis lait|laitier|yaourt|beurre|creme|creamerie|tomme"),
    ("miel", r"miel|apicult|rucher|abeille|pollen"),
    ("vin", r"viticult|vigne|vignoble|vigneron|\bvins?\b|\bchai\b|\bcaves?\b|spiritueu|distill|whisky|rhum|cognac|pineau"),
    ("biere", r"biere|brass|houblon"),
    ("cidre", r"cidre|cidricole|\bjus\b"),
    ("mer", r"huitre|ostrei|conchyl|\bmoules?\b|mytilicult|palourde|coquillage|poisson|pecheur|fruits de mer|crustace|langoustine"),
    ("sel", r"\bsel\b|saunier|salicult|marais salant|salorge|fleur de sel"),
    ("pain", r"\bpain|boulang|brioche|viennois|fouace|gache"),
    ("sucre", r"biscuit|confiserie|chocolat|confiture|glace|caramel|galette|gateau|patisserie|sorbet|bonbon|nougat"),
    ("epicerie", r"farine|cereal|\bble\b|sarrasin|oleagin|huile|legumineuse|lentille|pois chiche|mogette|haricot|\bpates\b|epice|condiment|\bthe\b|\bcafe\b|tisane|aromatique|ppam|plantes a parfum|medicinal|spiruline|conserve|safran|vinaigre|moutarde"),
    ("fleurs", r"fleur|horticult|pepinier|plants\b|bulbe|rosier"),
]
MOTS = [(f, re.compile(r)) for f, r in MOTS]

# types des fiches de Vendée Expansion (sans accents) -> familles
TYPES_VT = {
    "fruits / legumes": ["fl"], "viande": ["viande"], "elevage": ["viande"], "betail": ["viande"], "rillettes": ["viande"],
    "foie gras": ["viande"], "salaisons": ["viande"], "conserves": ["epicerie"], "volailles / oeufs": ["vo"],
    "fromage et produit laitier": ["lait"], "glace": ["sucre"], "produits apicoles": ["miel"], "vins": ["vin"],
    "spiritueux": ["vin"], "bieres": ["biere"], "produits cidricoles / jus de fruit": ["cidre"], "huitres": ["mer"],
    "poisson": ["mer"], "fruits de mer": ["mer"], "spiruline": ["epicerie"], "sel": ["sel"], "pain / patisserie": ["pain"],
    "brioche et viennoiserie": ["pain"], "biscuit": ["sucre"], "confiserie / chocolat": ["sucre"], "confiture": ["sucre"],
    "farine": ["epicerie"], "cereales": ["epicerie"], "legumes secs": ["epicerie"], "pates": ["epicerie"], "huile": ["epicerie"],
    "epices / condiment": ["epicerie"], "the": ["epicerie"], "cafe": ["epicerie"], "plantes et fleurs": ["fleurs"],
    "produits du terroir (boutique)": [],
}
TYPES_VT = {norm(k): v for k, v in TYPES_VT.items()}
SECTEURS_EXCLUS = ("artisanat", "industrie", "loisirs")

PETITS = {"de", "du", "des", "la", "le", "les", "et", "a", "à", "au", "aux", "en", "sur", "sous", "d", "l", "chez", "pour", "par"}
SIGLES = {"EARL", "GAEC", "SCEA", "SARL", "SAS", "SASU", "EURL", "EI", "SCI", "AB", "HVE", "GFA", "SA", "SCA", "CUMA", "AOP", "IGP",
          "SCL", "SNC", "EIRL", "SC"}


# --------------------------------------------------------------------------- petits outils
def lire(url, data=None, essais=2, delai=90):
    derniere = None
    for _ in range(essais):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=delai) as r:
                return r.read()
        except Exception as e:
            derniere = e
    raise derniere


def jolie(nom):
    """« LES FROMAGES DE PERRURE » -> « Les Fromages de Perrure » ; un nom déjà en casse normale n'est pas touché."""
    nom = re.sub(r"\s+", " ", (nom or "").strip().strip(",;-"))
    lettres = [c for c in nom if c.isalpha()]
    if not lettres or sum(c.isupper() for c in lettres) / len(lettres) < 0.75:
        return nom
    out, debut, avant = [], True, ""
    for m in re.split(r"([ \-'’/()])", nom):
        if not m:
            continue
        if m in " -'’/()":
            if (m == "-" and avant == " ") or m == "(":
                debut = True
            out.append(m)
            avant = m
            continue
        avant = m
        if m.upper() in SIGLES and not (debut and m.upper() in ("AB", "SA", "SC")):
            out.append(m.upper())
        elif m.lower() in PETITS and not debut:
            out.append(m.lower())
        elif m.lower() in ("st", "ste"):
            out.append(m.capitalize())
        else:
            out.append(m[:1].upper() + m[1:].lower())
        debut = False
    s = "".join(out)
    m = re.match(r"^(.*?)\s*\((la|le|les|l')\)$", s, re.I)
    if m:
        art = m.group(2).capitalize()
        s = art + ("" if art.endswith("'") else " ") + m.group(1)
    return s


def tel(t):
    """« 0761148660 », « +33 2 51 … » -> « 07 61 14 86 60 »."""
    c = re.sub(r"\D", "", t or "")
    if c.startswith("33") and len(c) == 11:
        c = "0" + c[2:]
    if len(c) != 10 or not c.startswith("0"):
        return ""
    return " ".join(c[i:i + 2] for i in range(0, 10, 2))


def site(u):
    u = (u or "").strip()
    if not u or " " in u:
        return ""
    if not re.match(r"^https?://", u):
        u = "https://" + u
    return u[:200]


def minutes(hhmm):
    m = re.match(r"^\s*(\d{1,2})[:h](\d{2})\s*$", hhmm or "")
    if not m:
        return None
    v = int(m.group(1)) * 60 + int(m.group(2))
    return v if 0 <= v <= 1440 else None


def date_fr(t):
    try:
        return datetime.strptime((t or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def familles_texte(*textes):
    t = " " + norm(" ".join(x for x in textes if x)) + " "
    return [f for f, r in MOTS if r.search(t)]


def ranger(fams):
    return [f for f in FAMILLES if f in set(fams)]


def mots_nom(n):
    vides = {"earl", "gaec", "scea", "sarl", "sas", "sasu", "eurl", "ei", "sci", "scl", "ferme", "la", "le", "les", "de", "du", "des",
             "d", "l", "et", "a", "au", "aux", "domaine", "chez", "maison", "brasserie", "vergers", "verger", "jardins", "jardin"}
    return {w for w in norm(n).split() if w not in vides and len(w) > 2}


# --------------------------------------------------------------------------- horaires des fiches Vendée Expansion
def horaires_vt(granule, aujourd):
    """Ouvertures des fiches « producteurs » : des périodes séparées par « ## », chacune
    « début||fin||note||jours fermés||lun ouv1||lun ferm1||lun ouv2||lun ferm2||mar… ||dim ferm2 ».
    Rend (horaires de la période en cours ou à venir, au format des magasins, note, [début, fin] si période limitée)."""
    periodes = []
    for g in (granule or "").split("##"):
        p = g.split("||")
        if len(p) < 4:
            continue
        d1, d2 = date_fr(p[0]), date_fr(p[1])
        cases = (p[4:32] + [""] * 28)[:28]
        h = []
        for j in range(7):
            c = cases[j * 4:(j + 1) * 4]
            for a, b in ((c[0], c[1]), (c[2], c[3])):
                ma, mb = minutes(a), minutes(b)
                if ma is not None and mb is not None and mb > ma:
                    h.append([JOURS_BONIAL[j], ma, mb])
        periodes.append((d1, d2, h, re.sub(r"\s+", " ", p[2]).strip()))
    if not periodes:
        return [], "", None
    en_cours = [x for x in periodes if (x[0] is None or x[0] <= aujourd) and (x[1] is None or x[1] >= aujourd)]
    a_venir = sorted([x for x in periodes if x[0] and x[0] > aujourd], key=lambda x: x[0])
    choix = en_cours[0] if en_cours else (a_venir[0] if a_venir else None)
    if not choix:
        return [], "", None
    d1, d2, h, note = choix
    limite = None
    # période qui commence plus tard, ou qui finit dans moins de 10 mois sans période juste après : on la montre
    # (« ouvre le 1er avril », « jusqu'au 31 mai »)
    suite = d2 and any(x[0] and d2 < x[0] <= d2 + timedelta(days=2) for x in periodes)
    if d1 and d2 and (d1 > aujourd or ((d2 - aujourd).days < 300 and not suite)):
        limite = [d1.isoformat(), d2.isoformat()]
    return h, note[:160], limite


def dates_marche(granule, aujourd):
    """Dates de l'agenda : « début||fin||heure début||heure fin||… », séparées par « ## ».
    Rend les dates des HORIZON prochains jours : [[début, fin, minute début, minute fin], …]."""
    fin_horizon = aujourd + timedelta(days=HORIZON)
    out = []
    for g in (granule or "").split("##"):
        p = (g.split("||") + [""] * 4)[:4]
        d1, d2 = date_fr(p[0]), date_fr(p[1]) or date_fr(p[0])
        if not d1 or not d2 or d2 < aujourd or d1 > fin_horizon:
            continue
        out.append([max(d1, aujourd).isoformat(), d2.isoformat(), minutes(p[2]), minutes(p[3])])
    out.sort()
    return out[:40]


# --------------------------------------------------------------------------- flux Tourinsoft (Vendée Expansion)
def atom(brut):
    """Flux Atom (OData v2) de Tourinsoft -> liste de dictionnaires {propriété: texte}."""
    ns = {"a": "http://www.w3.org/2005/Atom", "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
    out = []
    for e in ET.fromstring(brut).findall("a:entry", ns):
        props = e.find(".//m:properties", ns)
        if props is None:
            continue
        it = {}
        for p in props:
            val = "".join(p.itertext()).strip()
            if val:
                it[p.tag.split("}")[-1]] = val
        out.append(it)
    return out


def coord(it, cle_la="GmapLatitude", cle_lo="GmapLongitude"):
    try:
        la, lo = float(it.get(cle_la)), float(it.get(cle_lo))
    except (TypeError, ValueError):
        return None
    return (la, lo) if 46.2 < la < 47.1 and -2.6 < lo < -0.5 else None


def adresse_vt(it):
    """Morceaux d'adresse sans répétition (« 3 le Fief Pacaud » et « 3, Le Fief Pacaud » : un seul)."""
    garde = []
    for x in (it.get("Adresse1"), it.get("Adresse1Suite"), it.get("Adresse2"), it.get("Adresse3")):
        n = norm(x)
        if n and not any(n in norm(g) or norm(g) in n for g in garde):
            garde.append(x.strip())
    return ", ".join(garde)[:120]


def producteurs_vt(brut, communes, aujourd, journal):
    lieux, ecartes = [], {"artisanat": 0, "pas de vente": 0, "sans produit": 0, "sans position": 0}
    for it in atom(brut):
        if not it.get("ObjectTypeName", "").startswith("Producteurs"):
            continue
        secteur = norm(it.get("DegSecteurActivite"))
        if any(s in secteur for s in SECTEURS_EXCLUS):
            ecartes["artisanat"] += 1
            continue
        if norm(it.get("DegVente")) == "non":
            ecartes["pas de vente"] += 1
            continue
        types = [t.strip() for t in (it.get("Type") or "").split("##") if t.strip()]
        fams, boutique = [], False
        for t in types:
            if "terroir" in norm(t):
                boutique = True
            fams += TYPES_VT.get(norm(t), [])
        if not fams:
            fams = familles_texte(it.get("SyndicObjectName"), " ".join(types))
        if not fams and not boutique:
            ecartes["sans produit"] += 1
            continue
        pos = coord(it)
        if not pos:
            ecartes["sans position"] += 1
            continue
        h, note, periode = horaires_vt(it.get("OuvertureGranule"), aujourd)
        c = communes.get(it.get("CodeInseeCommune") or "")
        e = {"id": "vt:" + it.get("SyndicObjectID", ""), "n": jolie(it.get("SyndicObjectName")), "c": ranger(fams),
             "v": c["nom"] if c else jolie(it.get("Commune")), "a": jolie(adresse_vt(it)), "la": round(pos[0], 5), "lo": round(pos[1], 5),
             "s": ["vt"]}
        if boutique:
            e["bq"] = 1
        if h:
            e["h"] = h
        if note:
            e["hn"] = note
        if periode:
            e["per"] = periode
        elif not h and norm(it.get("OuvertureALAnnee")) == "oui":
            e["hn"] = e.get("hn") or "Ouvert toute l'année"
        if "biolog" in norm(it.get("Labels")):
            e["bio"] = 1
        if "bienvenue a la ferme" in norm(it.get("Labels")):
            e["baf"] = 1
        if tel(it.get("CommTel")):
            e["tel"] = tel(it.get("CommTel"))
        if site(it.get("CommWeb")):
            e["web"] = site(it.get("CommWeb"))
        lieux.append(e)
    journal("   Vendée Expansion : %d producteurs (écartés : %s)" % (len(lieux), ", ".join("%s %d" % kv for kv in ecartes.items())))
    return lieux


def marches_vt(brut, communes, aujourd, journal):
    out = []
    for it in atom(brut):
        if norm(it.get("Type")) != "marche":
            continue
        dates = dates_marche(it.get("OuvertureGranule"), aujourd)
        pos = coord(it)
        if not dates or not pos:
            continue
        c = communes.get(it.get("CodeInseeCommune") or "")
        nom = jolie(it.get("SyndicObjectName"))
        texte = norm(" ".join((nom, it.get("EvenementFma") or "", it.get("DescriptifSynthetique") or "")))
        m = {"id": "vt:" + it.get("SyndicObjectID", ""), "n": nom, "v": c["nom"] if c else jolie(it.get("Commune")),
             "a": jolie(adresse_vt(it)), "la": round(pos[0], 5), "lo": round(pos[1], 5), "d": dates, "s": ["vt"]}
        if re.search(r"\bnoel\b|\bavent\b|lutin|cadeaux", texte):
            m["noel"] = 1
        if "producteur" in texte:
            m["prod"] = 1
        ds = re.sub(r"\s+", " ", it.get("DescriptifSynthetique") or "").strip()
        if ds and len(ds) <= 140:
            m["ds"] = ds
        out.append(m)
    journal("   Vendée Expansion : %d marchés dans les %d prochains jours (dont %d de Noël)" % (
        len(out), HORIZON, sum(1 for m in out if m.get("noel"))))
    return out


# --------------------------------------------------------------------------- Agence Bio
def producteurs_bio(journal):
    items, debut = [], 0
    while debut < 6000:
        d = json.loads(lire(API_BIO % debut).decode("utf-8"))
        lot = d.get("items") or []
        items += lot
        debut += 1000
        try:
            total = int(d.get("nbTotal") or 0)
        except (TypeError, ValueError):
            total = 0
        if len(lot) < 1000 or debut >= total:
            break
    lieux, ecartes = [], {"pas de vente aux particuliers": 0, "certification arrêtée": 0, "commerce ou artisan": 0,
                          "sans produit": 0, "sans position en Vendée": 0}
    for it in items:
        cats = " ".join((x or {}).get("nom", "") for x in it.get("categories") or [])
        vente = it.get("venteAnnuaire") or {}
        if "consommateur" not in norm(cats) or not vente.get("venteParticuliers"):
            ecartes["pas de vente aux particuliers"] += 1
            continue
        if not any(norm(c.get("etatCertification")).startswith("engag") for c in it.get("certificats") or []):
            ecartes["certification arrêtée"] += 1
            continue
        activites = [(x or {}).get("nom", "") for x in it.get("annuaireActivites") or []]
        agricole = [a for a in activites if not re.match(r"^(commerce|artisans|entreprise de transformation agro alimentaire (abattoir|boulang)|restaurat|transport|stockage|import|export)", norm(a))]
        prods = [(x or {}).get("nom", "") for x in it.get("productions") or []]
        if activites and not agricole:
            ecartes["commerce ou artisan"] += 1
            continue
        # les productions disent ce qui est vendu (prairies, céréales pour les bêtes : sans intérêt ici)
        prods_utiles = [p for p in prods if not re.search(r"prairie|jachere|gel |surfaces? non|parcours|fourrag|luzerne|trefle|culture inconnue|melange", norm(p))]
        fams = familles_texte(" ".join(agricole)) or familles_texte(" ".join(prods_utiles))
        if "Sel de mer" in prods:
            fams = [f for f in fams if f != "mer"] + ["sel"]
        if not fams:
            ecartes["sans produit"] += 1
            continue
        adrs = [a for a in it.get("adressesOperateurs") or [] if a.get("active", True) and a.get("lat") and str(a.get("codePostal", "")).startswith("85")]
        adrs.sort(key=lambda a: 0 if "Lieux d'activité" in (a.get("typeAdresseOperateurs") or []) else 1)
        pos = next(((a, (float(a["lat"]), float(a["long"]))) for a in adrs if coord({"la": a.get("lat"), "lo": a.get("long")}, "la", "lo")), None)
        if not pos:
            ecartes["sans position en Vendée"] += 1
            continue
        a, (la, lo) = pos
        nom = it.get("denominationcourante") or it.get("raisonSociale") or ""
        nom = re.sub(r"\s*\((EI|EIRL|EARL|GAEC|SCEA)\)\s*$", "", nom.strip(), flags=re.I)
        e = {"id": "ab:%s" % it.get("id"), "n": jolie(nom), "c": ranger(fams), "v": jolie(a.get("ville")), "a": jolie(a.get("lieu"))[:120],
             "la": round(la, 5), "lo": round(lo, 5), "bio": 1, "s": ["ab"], "_insee": str(a.get("codeCommune") or "")}
        t = tel(it.get("telephoneCommerciale") or it.get("telephone"))
        if t:
            e["tel"] = t
        webs = sorted([w for w in it.get("siteWebs") or [] if w.get("active", True) and w.get("url")],
                      key=lambda w: 0 if ((w.get("typeSiteWeb") or {}).get("nom") or "").startswith("Site") else 1)
        if webs and site(webs[0]["url"]):
            e["web"] = site(webs[0]["url"])
        lieux.append(e)
    journal("   Agence Bio : %d producteurs bio en vente directe sur %d fiches (écartés : %s)" % (
        len(lieux), len(items), ", ".join("%s %d" % kv for kv in ecartes.items())))
    return lieux


# --------------------------------------------------------------------------- OpenStreetMap
REQ_OSM = ('[out:json][timeout:120];area["ISO3166-2"="FR-85"]->.v;('
           'nwr(area.v)["shop"="farm"];'
           'nwr(area.v)["craft"~"^(beekeeper|winery|brewery|distillery|cider|oysters?|cheese|dairy|salt)$"];'
           'nwr(area.v)["shop"~"^(honey|wine|seafood)$"];'
           'nwr(area.v)["amenity"="vending_machine"]["vending"~"milk|egg|fruit|vegetable|potato|meat|cheese|honey"];'
           'nwr(area.v)["amenity"="marketplace"];'
           ');out center tags;')
PRODUCE_OSM = {"vegetables": "fl", "vegetable": "fl", "potatoes": "fl", "potato": "fl", "fruit": "fl", "fruits": "fl", "apples": "fl",
               "strawberries": "fl", "berries": "fl", "salad": "fl", "tomatoes": "fl", "meat": "viande", "beef": "viande",
               "pork": "viande", "veal": "viande", "lamb": "viande", "sausage": "viande", "poultry": "vo", "chicken": "vo",
               "duck": "vo", "eggs": "vo", "egg": "vo", "milk": "lait", "cheese": "lait", "dairy": "lait", "milk product": "lait",
               "yogurt": "lait", "butter": "lait", "honey": "miel", "wine": "vin", "beer": "biere", "cider": "cidre",
               "juice": "cidre", "apple_juice": "cidre", "oysters": "mer", "oyster": "mer", "mussels": "mer", "seafood": "mer",
               "fish": "mer", "salt": "sel", "bread": "pain", "flour": "epicerie", "cereals": "epicerie", "grain": "epicerie",
               "oil": "epicerie", "lentils": "epicerie", "spirulina": "epicerie", "flowers": "fleurs", "plants": "fleurs"}
CRAFT_OSM = {"beekeeper": "miel", "winery": "vin", "brewery": "biere", "distillery": "vin", "cider": "cidre", "oysters": "mer",
             "oyster": "mer", "cheese": "lait", "dairy": "lait", "salt": "sel"}


def commune_proche(communes, la, lo):
    best, dmin = None, 99
    for c in communes.values():
        d = distance_km((la, lo), (c["la"], c["lo"]))
        if d < dmin:
            best, dmin = c, d
    return best["nom"] if best and dmin < 12 else ""


def lire_osm(journal):
    """Serveur principal puis miroirs ; les serveurs Overpass sont souvent saturés le matin : un deuxième tour après une pause."""
    import time
    erreurs = []
    for tour in range(2):
        if tour:
            time.sleep(30)
        for url in OSM_API:
            try:
                els = json.loads(lire(url, urllib.parse.urlencode({"data": REQ_OSM}).encode(), essais=1, delai=130).decode("utf-8")).get("elements")
            except Exception as e:
                erreurs.append("%s : %s" % (urllib.parse.urlparse(url).netloc, e))
                continue
            if els:
                return els
            erreurs.append("%s : réponse vide" % urllib.parse.urlparse(url).netloc)
    raise RuntimeError(" ; ".join(erreurs[-3:]))


def producteurs_osm(els, communes, journal):
    lieux, marches = [], []
    for el in els:
        t = el.get("tags") or {}
        la, lo = el.get("lat") or (el.get("center") or {}).get("lat"), el.get("lon") or (el.get("center") or {}).get("lon")
        if not la or not lo:
            continue
        nom = t.get("name") or t.get("brand") or ""
        ville = t.get("addr:city") or commune_proche(communes, la, lo)
        oid = "osm:%s%s" % (el.get("type", "n")[:1], el.get("id"))
        if t.get("amenity") == "marketplace":
            h = horaires_osm(t.get("opening_hours"))
            if not h:
                continue
            marches.append({"id": oid, "n": nom if nom and norm(nom) != "marche" else ("Marché de " + ville if ville else "Marché"),
                            "v": ville, "la": round(la, 5), "lo": round(lo, 5), "h": h, "s": ["osm"]})
            continue
        texte = " ".join(t.get(k, "") for k in ("name", "description", "operator", "product", "produce", "website", "contact:website"))
        fams = [PRODUCE_OSM[p.strip().lower()] for k in ("produce", "product") for p in t.get(k, "").split(";") if p.strip().lower() in PRODUCE_OSM]
        if t.get("craft") in CRAFT_OSM:
            fams.append(CRAFT_OSM[t["craft"]])
        if t.get("shop") == "honey":
            fams.append("miel")
        distrib = t.get("amenity") == "vending_machine"
        if distrib:
            fams += [PRODUCE_OSM.get(v.strip().lower().rstrip("s"), PRODUCE_OSM.get(v.strip().lower(), "")) for v in t.get("vending", "").split(";")]
            fams = [f for f in fams if f]
        if t.get("shop") == "wine" and t.get("craft") != "winery" and not re.search(r"domaine|vignoble|vigneron|chateau|producteur|chai\b", norm(texte)):
            continue  # caviste : pas un producteur
        if t.get("shop") == "seafood" and "mer" not in fams and not re.search(r"huitr|ostrei|conchyl|cabane|claire|parc a|moule", norm(texte)):
            continue  # poissonnerie
        fams = fams or familles_texte(texte)
        if not fams and t.get("shop") != "farm":
            continue
        if not nom:
            if not distrib:
                continue
            nom = "Distributeur " + {"lait": "de lait", "vo": "d'œufs", "fl": "de fruits et légumes", "viande": "de viande", "miel": "de miel"}.get((fams or [""])[0], "de produits de la ferme")
        e = {"id": oid, "n": jolie(nom), "c": ranger(fams), "v": ville, "la": round(la, 5), "lo": round(lo, 5), "s": ["osm"]}
        adr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street") or t.get("addr:place")) if x)
        if adr:
            e["a"] = adr[:120]
        if distrib:
            e["dist"] = 1
        h = horaires_osm(t.get("opening_hours"))
        if h:
            e["h"] = h
        if t.get("organic") in ("only", "yes"):
            e["bio"] = 1
        p = tel(t.get("phone") or t.get("contact:phone"))
        if p:
            e["tel"] = p
        w = site(t.get("website") or t.get("contact:website"))
        if w:
            e["web"] = w
        lieux.append(e)
    journal("   OpenStreetMap : %d producteurs ou distributeurs, %d marchés avec leurs jours" % (len(lieux), len(marches)))
    return lieux, marches


# --------------------------------------------------------------------------- fusion des sources
def meme_lieu(a, b):
    d = distance_km((a["la"], a["lo"]), (b["la"], b["lo"]))
    if d > 0.6:
        return False
    if a.get("tel") and a.get("tel") == b.get("tel"):
        return True
    ma, mb = mots_nom(a["n"]), mots_nom(b["n"])
    if ma and mb and (len(ma & mb) / min(len(ma), len(mb)) >= 0.5):
        return True
    return d < 0.05 and bool(set(a.get("c", [])) & set(b.get("c", [])))


def fusionner(lieux):
    """Une même ferme peut venir de deux ou trois sources : on garde une seule fiche, la plus riche en tête
    (Vendée Expansion, puis OpenStreetMap, puis Agence Bio) et on complète avec les autres."""
    rang = {"vt": 0, "osm": 1, "ab": 2}
    lieux = sorted(lieux, key=lambda e: rang.get(e["s"][0], 3))
    gardes = []
    for e in lieux:
        double = next((g for g in gardes if meme_lieu(g, e)), None)
        if not double:
            gardes.append(e)
            continue
        double["c"] = ranger(double.get("c", []) + e.get("c", []))
        double["s"] = sorted(set(double["s"] + e["s"]), key=lambda s: rang.get(s, 3))
        for k in ("tel", "web", "a", "h", "bio"):
            if e.get(k) and not double.get(k):
                double[k] = e[k]
    return gardes


def fusionner_marches(vt, osm):
    """Les marchés de l'agenda ont les vraies dates ; ceux d'OpenStreetMap complètent les communes absentes de l'agenda."""
    hebdo = [m for m in vt if not m.get("noel")]
    out = list(vt)
    for m in osm:
        if any(distance_km((m["la"], m["lo"]), (x["la"], x["lo"])) < 1.2 for x in hebdo):
            continue
        out.append(m)
    return out


# --------------------------------------------------------------------------- mise à jour
def communes_vendee(journal):
    try:
        d = json.loads(lire(API_COMMUNES).decode("utf-8"))
        out = {}
        for c in d:
            xy = ((c.get("centre") or {}).get("coordinates") or [None, None])
            if c.get("code") and c.get("nom") and xy[0]:
                out[c["code"]] = {"nom": c["nom"], "la": xy[1], "lo": xy[0]}
        return out
    except Exception as e:
        journal("   Communes (geo.api.gouv.fr) injoignables : %s" % e)
        return {}


def a_refaire(ancien, aujourd):
    if not ancien or not ancien.get("maj"):
        return True
    try:
        derniere = date.fromisoformat(ancien["maj"])
    except ValueError:
        return True
    return (aujourd - derniere).days >= TOUS_LES


def mettre_a_jour(log=print, aujourd=None, forcer=False, essai=False):
    aujourd = aujourd or date.today()
    ancien = charger_json(FICHIER, {})
    if not forcer and not a_refaire(ancien, aujourd):
        return ancien
    log("Producteurs locaux et marchés (Vendée Expansion, Agence Bio, OpenStreetMap)…")
    communes = communes_vendee(log)
    vieux = {"vt": [], "ab": [], "osm": []}
    for e in ancien.get("lieux") or []:
        for s in e.get("s", []):
            if s in vieux:
                vieux[s].append(e)
    lieux, marches, etat = [], [], {}

    def garder(source, raison):
        log("   %s injoignable (%s) : fiches de la dernière fois gardées" % (source, raison))

    try:
        lieux += producteurs_vt(lire(FLUX_PRODUCTEURS, delai=120), communes, aujourd, log)
        etat["vt"] = aujourd.isoformat()
    except Exception as e:
        garder("Vendée Expansion (producteurs)", e)
        lieux += [x for x in vieux["vt"] if x["s"][0] == "vt"]
    try:
        marches += marches_vt(lire(FLUX_AGENDA, delai=120), communes, aujourd, log)
    except Exception as e:
        garder("Vendée Expansion (agenda)", e)
        marches += [m for m in ancien.get("marches") or [] if m["s"][0] == "vt"]
    try:
        bio = producteurs_bio(log)
        for e in bio:
            c = communes.get(e.pop("_insee", ""))
            if c:
                e["v"] = c["nom"]
        lieux += bio
        etat["ab"] = aujourd.isoformat()
    except Exception as e:
        garder("Agence Bio", e)
        lieux += [x for x in vieux["ab"] if x["s"][0] == "ab"]
    try:
        p_osm, m_osm = producteurs_osm(lire_osm(log), communes, log)
        lieux += p_osm
        etat["osm"] = aujourd.isoformat()
    except Exception as e:
        garder("OpenStreetMap", e)
        lieux += [x for x in vieux["osm"] if x["s"][0] == "osm"]
        m_osm = [m for m in ancien.get("marches") or [] if m["s"][0] == "osm"]
    for e in lieux:
        e.pop("_insee", None)
    avant = len(lieux)
    lieux = fusionner(lieux)
    marches = fusionner_marches(marches, m_osm)
    lieux.sort(key=lambda e: (e["v"], e["n"]))
    marches.sort(key=lambda m: (m.get("d") or [["9999"]])[0][0] + m["n"])
    if not lieux and not marches:
        log("   Aucune source n'a répondu : producteurs de la dernière fois gardés")
        return ancien
    res = {"maj": aujourd.isoformat(), "sources": {**(ancien.get("sources") or {}), **etat}, "lieux": lieux, "marches": marches}
    log("   %d producteurs (%d fiches avant de réunir les doublons), %d marchés" % (len(lieux), avant, len(marches)))
    ecrire_json(FICHIER, res)
    if essai:
        from collections import Counter
        print("Familles :", Counter(f for e in lieux for f in e["c"]).most_common())
        print("Sources :", Counter("+".join(e["s"]) for e in lieux).most_common())
        print("Avec horaires :", sum(1 for e in lieux if e.get("h")), "| tél :", sum(1 for e in lieux if e.get("tel")),
              "| site :", sum(1 for e in lieux if e.get("web")), "| bio :", sum(1 for e in lieux if e.get("bio")),
              "| sans famille :", sum(1 for e in lieux if not e["c"]))
        print("Taille :", os.path.getsize(FICHIER), "octets")
        for e in lieux[::max(1, len(lieux) // 25)]:
            print("  ", json.dumps(e, ensure_ascii=False)[:300])
        for m in marches[:60]:
            print("  M", json.dumps(m, ensure_ascii=False)[:260])
    return res


if __name__ == "__main__":
    mettre_a_jour(forcer="--forcer" in sys.argv or "--essai" in sys.argv, essai="--essai" in sys.argv)
