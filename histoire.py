#!/usr/bin/env python3
"""Histoire des prix, pour « Remonter le temps » sur la fiche d'un article de Mogette.

Sources ouvertes de l'INSEE (service web SDMX gratuit) :
- indices des prix à la consommation, base 2025, France entière, ensemble des ménages : moyennes de chaque année
  depuis 1996 et dernier mois connu, pour chaque type de produit (nomenclature COICOP 2018) ;
- montant du SMIC horaire brut, chaque mois depuis 1996.
Relu une fois par semaine par la mise à jour du matin (les autres jours, rien n'est téléchargé).
Écrit histoire.json à côté des promos : pour chaque type de produit utile, son nom et ses indices, puis les règles
qui rangent un article dans un type d'après son nom ou son rayon.

Le prix d'une année = prix d'aujourd'hui × indice de l'année ÷ indice du dernier mois. C'est une estimation :
le vrai prix de cet article à l'époque a pu être différent (format, recette, magasin).

    python histoire.py            mise à jour si la dernière a plus de 6 jours
    python histoire.py --forcer   tout de suite
    python histoire.py --essai    tout de suite, avec les types de produits et l'essai sur les promos du jour
"""
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from maj_promos import DATA, charger_json, ecrire_json

FICHIER = os.path.join(DATA, "histoire.json")
SDMX = "https://bdm.insee.fr/series/sdmx"
UA = "Mogette/1.0 (appli de promos, github.com/ansquerdylan-arch/mes-promos)"
VERSION = 1         # format de histoire.json : un changement relit l'INSEE tout de suite
TOUS_LES = 6        # jours entre deux lectures
DEBUT = 1996        # les indices en base 2025 remontent à 1996
SMIC = "000822484"  # Montant du SMIC brut horaire, mensuel

# Types de produits (codes COICOP 2018 de l'INSEE). Le premier motif qui va avec le nom de l'article l'emporte.
# Les motifs portent sur le nom en minuscules, sans accents (comme normPy dans l'appli). Un code sans série à
# l'INSEE est remplacé par le type plus large qui le contient.
REGLES = []
# Rayon de Mogette -> type de produit, quand aucun motif ne va. None : pas d'estimation (l'électronique : l'INSEE
# compte les progrès techniques, le « même » téléviseur n'existait pas en 1996).
RAYONS = {}
# Repli pour les rayons inconnus
DEFAUT = "00"


def lire(url, essais=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml"})
    for n in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or n == essais - 1:
                raise
        except Exception:  # noqa: BLE001  (l'INSEE coupe parfois la connexion)
            if n == essais - 1:
                raise
        time.sleep(8 * (n + 1))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def series(xml):
    """Séries d'une réponse SDMX : [(attributs, {période: valeur})]."""
    res = []
    for s in ET.fromstring(xml).iter():
        if local(s.tag) != "Series":
            continue
        obs = {}
        for o in s:
            if local(o.tag) == "Obs" and o.get("OBS_VALUE") not in (None, "", "NaN"):
                try:
                    obs[o.get("TIME_PERIOD")] = float(o.get("OBS_VALUE"))
                except ValueError:
                    pass
        res.append((dict(s.attrib), obs))
    return res


def libelles():
    """Codes COICOP 2018 -> nom, d'après la structure du regroupement IPC-2025."""
    xml = lire(SDMX + "/datastructure/FR1/IPC-2025?references=children")
    noms = {}
    for cl in ET.fromstring(xml).iter():
        if local(cl.tag) == "Codelist" and cl.get("id") == "CL_COICOP2018":
            for c in cl:
                if local(c.tag) != "Code":
                    continue
                nom = ""
                for n in c:
                    if local(n.tag) == "Name" and n.get("{http://www.w3.org/XML/1998/namespace}lang") == "fr":
                        nom = (n.text or "").strip()
                noms[c.get("id")] = re.sub(r"\s*\(ND\)$", "", re.sub(r"^[\d.]+\s*-\s*", "", nom))
    return noms


def indices(freq, depuis):
    """{code COICOP: {période: indice}} pour la France entière, ensemble des ménages, base 2025."""
    xml = lire(SDMX + "/data/IPC-2025/%s.....INDICE.ENSEMBLE.FE..BRUT..?startPeriod=%s" % (freq, depuis))
    res = {}
    for a, obs in series(xml):
        if a.get("PRIX_CONSO", "SO") != "SO" or a.get("COICOP2018", "SO") == "SO" or not obs:
            continue
        res[a["COICOP2018"]] = obs
    return res


def smic(aujourd):
    """SMIC horaire brut : moyenne de chaque année, et le dernier mois connu."""
    (a, obs), = series(lire(SDMX + "/data/SERIES_BDM/%s?startPeriod=%d-01" % (SMIC, DEBUT)))
    par_an = {}
    for p, v in obs.items():
        par_an.setdefault(int(p[:4]), []).append(v)
    dernier = max(obs)
    return {str(y): round(sum(l) / len(l), 3) for y, l in par_an.items() if y < aujourd.year}, round(obs[dernier], 3), dernier


def code_dispo(code, dispo):
    """Le code, ou le type plus large qui a des séries (011821 -> 01182 -> 0118 …)."""
    while code and code not in dispo:
        code = code[:-1] if len(code) > 2 else ("00" if code != "00" else "")
    return code or None


def a_refaire(ancien, aujourd):
    try:
        age = (aujourd - date.fromisoformat(ancien.get("maj"))).days
    except (TypeError, ValueError):
        age = 999
    return age >= TOUS_LES or ancien.get("v") != VERSION


def ranger(nom, rayon, regles, rayons):
    """Comme typeHisto() dans l'appli : le code du type de produit d'un article, ou None."""
    for motif, code in regles:
        if motif.search(nom):
            return code
    if rayon in rayons:
        return rayons[rayon]
    return DEFAUT


def norm_py(t):
    import unicodedata
    t = str(t or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def mettre_a_jour(log=print, aujourd=None, forcer=False, essai=False):
    aujourd = aujourd or date.today()
    ancien = charger_json(FICHIER, {})
    if not forcer and not a_refaire(ancien, aujourd):
        return ancien
    log("Histoire des prix (INSEE : indices des prix par type de produit, SMIC)…")
    try:
        noms = libelles()
        annuels = indices("A", DEBUT)
        mensuels = indices("M", "%d-01" % (aujourd.year - 1))
        smic_ans, smic_now, smic_mois = smic(aujourd)
    except Exception as e:  # noqa: BLE001
        log("   INSEE injoignable (%s) : histoire de la dernière fois gardée" % e)
        return ancien
    dispo = {c for c in annuels if c in mensuels}
    # dernier mois publié (le même pour tous les types)
    mois = max(max(m) for m in mensuels.values())
    regles, rayons, utiles = [], {}, set()
    for motif, code in REGLES:
        c = code_dispo(code, dispo)
        if c:
            regles.append([motif, c])
            utiles.add(c)
        else:
            log("   type %s sans série : règle « %s » ignorée" % (code, motif))
    for r, code in RAYONS.items():
        c = code_dispo(code, dispo) if code else None
        rayons[r] = c
        if c:
            utiles.add(c)
    utiles.add(code_dispo(DEFAUT, dispo))
    cat = {}
    for c in sorted(x for x in utiles if x):
        an = annuels[c]
        ans = [an.get(str(y)) for y in range(DEBUT, aujourd.year)]
        m = mensuels[c]
        cat[c] = {"n": noms.get(c, c), "i": [round(v, 2) if v is not None else None for v in ans], "m": round(m[max(m)], 2)}
    res = {"v": VERSION, "maj": aujourd.isoformat(), "debut": DEBUT, "fin": aujourd.year, "mois": mois,
           "smic": {"ans": [smic_ans.get(str(y)) for y in range(DEBUT, aujourd.year)], "m": smic_now, "mois": smic_mois},
           "cat": cat, "regles": regles, "rayons": rayons, "defaut": code_dispo(DEFAUT, dispo)}
    log("   %d types de produits, indices jusqu'à %s, SMIC %s € brut de l'heure (%s)" % (len(cat), mois, str(smic_now).replace(".", ","), smic_mois))
    ecrire_json(FICHIER, res)
    if essai:
        essai_detail(res, noms, annuels, mensuels, dispo)
    return res


def essai_detail(res, noms, annuels, mensuels, dispo):
    print("Types de produits avec séries (code | nom | 1re année | indice %d | dernier mois) :" % DEBUT)
    for c in sorted(dispo, key=lambda x: (x[:2], x)):
        if c[:2] in ("01", "02", "03", "05", "08", "09", "13", "00"):
            an = annuels[c]
            prem = min(an)
            print("   %-7s %-70s %s %7s %7s" % (c, noms.get(c, "?")[:70], prem, an.get(str(DEBUT), "-"), mensuels[c][max(mensuels[c])]))
    # essai sur les promos du jour
    regles = [(re.compile(m), c) for m, c in res["regles"]]
    from collections import Counter
    vus, exemples = Counter(), {}
    ici = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(os.path.join(DATA, "offres", "*.json")) or glob.glob(os.path.join(ici, "offres", "*.json")):
        for p in charger_json(f, []):
            if not isinstance(p, dict) or p.get("prix") is None:
                continue
            c = ranger(norm_py(p.get("nom")), p.get("rayon"), regles, res["rayons"])
            vus[c] += 1
            exemples.setdefault(c, []).append(p.get("nom"))
    print("Promos du jour par type :")
    for c, n in vus.most_common():
        print("   %5d %-8s %-45s ex. %s" % (n, c, (res["cat"].get(c) or {}).get("n", "(pas d'estimation)")[:45], " | ".join(exemples[c][:4])[:160]))
    print("Taille :", os.path.getsize(FICHIER), "octets")


if __name__ == "__main__":
    mettre_a_jour(forcer="--forcer" in sys.argv or "--essai" in sys.argv, essai="--essai" in sys.argv)
