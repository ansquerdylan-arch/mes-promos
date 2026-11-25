"""Exploration des séries de l'INSEE pour « Remonter le temps » (lancé par diag.yml, brut=histoire).

Écrit ce qu'il trouve dans le dossier explo/ (poussé dans la branche diag-brut) et un résumé dans le journal.
Usage : python outils/explorer_histoire.py [flux] [series idbank...] [donnees FLUX CLE]
"""
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BASES = ["https://bdm.insee.fr/series/sdmx", "https://api.insee.fr/series/BDM"]
SORTIE = "explo"
os.makedirs(SORTIE, exist_ok=True)


def lire(url, nom=None, limite=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mogette (appli de promos, Vendee)", "Accept": "application/xml"})
    corps = None
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                corps = r.read()
                print("  %s -> %s (%d octets)" % (url, r.status, len(corps)))
            break
        except urllib.error.HTTPError as e:
            print("  %s -> HTTP %s : %s" % (url, e.code, e.read()[:300].decode("utf-8", "replace").replace("\n", " ")))
            if e.code < 500:
                return None
        except Exception as e:  # noqa: BLE001
            print("  %s -> échec (essai %d) : %s" % (url, essai + 1, e))
        time.sleep(5 * (essai + 1))
    if corps is None:
        return None
    if nom:
        open(os.path.join(SORTIE, nom), "wb").write(corps if limite is None else corps[:limite])
    return corps


def local(tag):
    return tag.rsplit("}", 1)[-1]


def noms(el):
    """Libellés fr d'un élément SDMX."""
    for n in el:
        if local(n.tag) == "Name" and n.get("{http://www.w3.org/XML/1998/namespace}lang") == "fr":
            return (n.text or "").strip()
    for n in el:
        if local(n.tag) == "Name":
            return (n.text or "").strip()
    return ""


def flux():
    for base in BASES:
        print("Liste des regroupements sur", base)
        corps = lire(base + "/dataflow", "dataflows_%s.xml" % base.split("//")[1].split("/")[0])
        if not corps:
            continue
        racine = ET.fromstring(corps)
        trouves = []
        for el in racine.iter():
            if local(el.tag) == "Dataflow":
                ident, nom = el.get("id"), noms(el)
                if re.search(r"IPC|PRIX|SMIC|SALAIRE|MONNAIE|POUVOIR", (ident or "") + " " + nom, re.I):
                    trouves.append((ident, nom))
        for ident, nom in sorted(trouves):
            print("   %-28s %s" % (ident, nom))
        return base
    return None


def structure(base, ident):
    print("Structure de", ident)
    corps = lire(base + "/datastructure/FR1/" + ident + "?references=children", "structure_%s.xml" % ident)
    if not corps:
        return
    racine = ET.fromstring(corps)
    listes = {}
    for cl in racine.iter():
        if local(cl.tag) == "Codelist":
            codes = [(c.get("id"), noms(c)) for c in cl if local(c.tag) == "Code"]
            listes[cl.get("id")] = codes
    for el in racine.iter():
        if local(el.tag) in ("Dimension", "TimeDimension"):
            ref = None
            for r in el.iter():
                if local(r.tag) == "Ref" and r.get("class") == "Codelist":
                    ref = r.get("id")
            codes = listes.get(ref, [])
            apercu = ", ".join("%s=%s" % c for c in codes[:12])
            print("   dim %s (position %s) liste %s : %d codes : %s" % (el.get("id"), el.get("position"), ref, len(codes), apercu[:600]))


def series(base, idbanks):
    print("Séries", idbanks)
    corps = lire(base + "/data/SERIES_BDM/" + "+".join(idbanks) + "?startPeriod=1990", "series_%s.xml" % "_".join(idbanks)[:60])
    if not corps:
        return
    racine = ET.fromstring(corps)
    for s in racine.iter():
        if local(s.tag) == "Series":
            obs = [(o.get("TIME_PERIOD"), o.get("OBS_VALUE")) for o in s if local(o.tag) == "Obs"]
            obs.sort()
            print("   %s | %s | %s | %d valeurs : %s … %s" % (s.get("IDBANK"), s.get("TITLE_FR", "")[:120], s.get("FREQ"), len(obs), obs[:2], obs[-2:]))


def donnees(base, ident, cle, nom):
    print("Données", ident, cle)
    corps = lire(base + "/data/%s/%s?detail=full" % (ident, cle), nom)
    if not corps:
        return
    racine = ET.fromstring(corps)
    n = 0
    for s in racine.iter():
        if local(s.tag) == "Series":
            n += 1
            if n <= 40:
                obs = [(o.get("TIME_PERIOD"), o.get("OBS_VALUE")) for o in s if local(o.tag) == "Obs"]
                obs.sort()
                print("   %s | %s | %d valeurs %s … %s" % (s.get("IDBANK"), s.get("TITLE_FR", "")[:110], len(obs), obs[:1], obs[-1:]))
    print("   %d séries en tout" % n)


args = sys.argv[1:] or ["flux"]
base = BASES[0]
i = 0
while i < len(args):
    a = args[i]
    if a == "flux":
        base = flux() or base
    elif a == "structure":
        structure(base, args[i + 1]); i += 1
    elif a == "series":
        ids = []
        while i + 1 < len(args) and re.fullmatch(r"\d{9}", args[i + 1]):
            ids.append(args[i + 1]); i += 1
        series(base, ids)
    elif a == "donnees":
        donnees(base, args[i + 1], args[i + 2], "donnees_%s.xml" % args[i + 1]); i += 2
    elif a.startswith("base="):
        base = a[5:]
    i += 1
