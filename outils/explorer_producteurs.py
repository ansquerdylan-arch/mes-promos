"""Exploration ponctuelle des sources ouvertes sur les producteurs de Vendée (lancée par diag.yml, brut=producteurs).
N'écrit rien : affiche seulement ce que chaque source contient."""
import collections
import json
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mogette/1.0 (appli de promos, github.com/ansquerdylan-arch/mes-promos)"}


def lire(url, data=None, limite=60_000_000):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.geturl(), r.headers.get("Content-Type", ""), r.read(limite)


def court(x, n=900):
    s = json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x
    return s[:n] + ("…" if len(s) > n else "")


def tourinsoft(nom, url):
    print("\n==================== %s" % nom)
    try:
        fin, typ, brut = lire(url)
    except Exception as e:
        print("ERREUR", e)
        return
    print("adresse finale :", fin)
    print("type :", typ, "| taille :", len(brut))
    txt = brut.decode("utf-8", "replace")
    print("début :", txt[:600].replace("\n", " "))
    try:
        d = json.loads(txt)
    except Exception:
        print("(pas du JSON)")
        return
    items = d.get("value") if isinstance(d, dict) else d
    if not isinstance(items, list):
        print("clés :", list(d)[:40] if isinstance(d, dict) else type(d))
        for k, v in (d.items() if isinstance(d, dict) else []):
            if isinstance(v, list):
                items = v
                print("liste trouvée sous", k)
                break
    if not isinstance(items, list):
        return
    print("éléments :", len(items))
    cles = collections.Counter(k for it in items for k in (it.keys() if isinstance(it, dict) else []))
    print("champs :", court(dict(cles.most_common(80)), 3000))
    for champ in ("ObjectTypeName", "Type", "TYPE", "type", "Bordereau", "BORDEREAU", "Categorie", "CATEGORIE", "TypeName"):
        if champ in cles:
            print("répartition", champ, ":", court(collections.Counter(str(it.get(champ)) for it in items).most_common(40), 2500))
    # éléments qui parlent de dégustation, producteurs, fermes, marchés
    mots = ("degust", "dégust", "produc", "ferme", "marché", "marche", "vigne", "cave", "huîtr", "huitr", "brass", "miel", "fromag")
    vus = 0
    for it in items:
        s = json.dumps(it, ensure_ascii=False).lower()
        if any(m in s for m in mots):
            vus += 1
            if vus <= 4:
                print("--- exemple", vus, ":", court(it, 2500))
    print("éléments qui parlent de producteurs/marchés :", vus)


def osm():
    print("\n==================== OpenStreetMap (Vendée)")
    q = ('[out:json][timeout:150];area["ISO3166-2"="FR-85"]->.v;('
         'nwr(area.v)["shop"="farm"];'
         'nwr(area.v)["amenity"="vending_machine"]["vending"~"milk|egg|food|fruit|vegetable|potato|meat|cheese|honey|farm|bread"];'
         'nwr(area.v)["craft"~"^(winery|brewery|distillery|beekeeper|cider|oyster|cheese|dairy|confectionery|salt)"];'
         'nwr(area.v)["shop"~"^(wine|seafood|cheese|butcher|greengrocer|honey|dairy)$"];'
         'nwr(area.v)["amenity"="marketplace"];'
         'nwr(area.v)["produce"];'
         'nwr(area.v)["landuse"="salt_pond"]["name"];'
         ');out center tags;')
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        try:
            _, _, brut = lire(url, urllib.parse.urlencode({"data": q}).encode())
            els = json.loads(brut.decode("utf-8")).get("elements") or []
            break
        except Exception as e:
            print("ERREUR", url, e)
            els = []
    print("éléments :", len(els))
    groupes = collections.defaultdict(list)
    for el in els:
        t = el.get("tags") or {}
        for k in ("shop", "craft", "amenity", "landuse"):
            if k in t:
                cle = "%s=%s" % (k, t[k])
                if k == "amenity" and t[k] == "vending_machine":
                    cle += " (%s)" % t.get("vending", "")
                groupes[cle].append(t)
                break
        else:
            groupes["produce seul"].append(t)
    for cle, l in sorted(groupes.items(), key=lambda x: -len(x[1])):
        avec = lambda k: sum(1 for t in l if t.get(k))
        print("%-45s %4d | nom %d, horaires %d, produce %d, site %d, tél %d" % (
            cle[:45], len(l), avec("name"), avec("opening_hours"), avec("produce"), avec("website") + avec("contact:website"),
            avec("phone") + avec("contact:phone")))
    for cle in ("shop=farm", "amenity=marketplace"):
        for t in groupes.get(cle, [])[:6]:
            print("  ex.", cle, ":", court(t, 500))
    print("  produce :", court(collections.Counter(p.strip() for l in groupes.values() for t in l for p in t.get("produce", "").split(";") if p.strip()).most_common(40), 1500))
    print("  vending :", court(collections.Counter(t.get("vending") for t in groupes.get("amenity=vending_machine (", []) or [t for l in groupes.values() for t in l if t.get("amenity") == "vending_machine"]).most_common(30), 1200))


def agence_bio():
    print("\n==================== Agence Bio (Vendée)")
    url = "https://opendata.agencebio.org/api/gouv/operateurs/?departements=85&nb=1000&debut=0"
    try:
        fin, typ, brut = lire(url)
    except Exception as e:
        print("ERREUR", e)
        return
    d = json.loads(brut.decode("utf-8"))
    print("clés :", list(d)[:20] if isinstance(d, dict) else type(d))
    items = d.get("items") if isinstance(d, dict) else d
    print("nbTotal :", d.get("nbTotal") if isinstance(d, dict) else "?", "| reçus :", len(items or []))
    if not items:
        return
    print("champs :", court(sorted(items[0].keys()), 1500))
    print("exemple :", court(items[0], 3000))
    for champ in ("categories", "activites", "productions"):
        c = collections.Counter()
        for it in items:
            for x in it.get(champ) or []:
                c[x.get("nom") if isinstance(x, dict) else str(x)] += 1
        print("répartition", champ, ":", court(c.most_common(40), 2500))
    vd = [it for it in items if any("direct" in json.dumps(x, ensure_ascii=False).lower() for x in (it.get("categories") or []))]
    print("vente directe :", len(vd))
    for it in vd[:3]:
        print("  ex. :", court(it, 2500))


if __name__ == "__main__":
    quoi = sys.argv[1:] or ["tourinsoft", "osm", "bio"]
    if "tourinsoft" in quoi:
        tourinsoft("Activités et visites (Vendée Expansion)", "https://www.data.gouv.fr/api/1/datasets/r/81fa2a94-d788-4a2f-85d0-800ba3fb5e96")
        tourinsoft("Agenda (Vendée Expansion)", "https://www.data.gouv.fr/api/1/datasets/r/5121010c-cdf4-40e9-8a49-64efd41f3fce")
    if "osm" in quoi:
        osm()
    if "bio" in quoi:
        agence_bio()
