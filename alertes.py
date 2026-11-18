# -*- coding: utf-8 -*-
"""
Alertes « même appli fermée », lancées par GitHub Actions juste après la mise à jour des promos.

L'appli enregistre tes produits surveillés dans un petit fichier GitHub (un gist public nommé
alertes-mes-promos.json). Chaque matin, ce script :
  - cherche ces produits dans les nouvelles promos ;
  - ajoute un rappel dans le calendrier des promos (rappels.ics) ;
  - envoie une notification sur ton téléphone via l'appli gratuite ntfy, si tu l'as activée ;
  - prévient aussi des opérations qui commencent aujourd'hui (Jeudis Plus U…), si tu l'as demandé.
Chaque alerte n'est envoyée qu'une fois (mémoire dans alertes_envoyees.json).
Le script ne fait jamais échouer la mise à jour : en cas de souci, il le dit et s'arrête.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

import maj_promos as m

FICHIER_ALERTES = "alertes-mes-promos.json"
ENVOYEES = os.path.join(m.DATA, "alertes_envoyees.json")
DEPOT = os.environ.get("GITHUB_REPOSITORY", "")              # ex. ansquerdylan-arch/mes-promos
PROPRIO = os.environ.get("GITHUB_REPOSITORY_OWNER") or DEPOT.split("/")[0]
JETON = os.environ.get("GITHUB_TOKEN", "")
ADRESSE_APPLI = ("https://%s.github.io/%s/" % (PROPRIO, DEPOT.split("/")[1])) if "/" in DEPOT else ""


def api(chemin, avec_jeton=True):
    """Lecture de l'API GitHub. Le jeton d'Actions n'a pas accès aux gists : on réessaie sans."""
    entetes = {"Accept": "application/vnd.github+json", "User-Agent": "mes-promos"}
    if avec_jeton and JETON:
        entetes["Authorization"] = "Bearer " + JETON
    req = urllib.request.Request("https://api.github.com" + chemin, headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if avec_jeton and JETON and e.code in (401, 403):
            return api(chemin, avec_jeton=False)
        raise


def lire_reglages():
    """Trouve le gist d'alertes parmi les gists publics du propriétaire du dépôt."""
    if not PROPRIO:
        return None
    for g in api("/users/%s/gists?per_page=100" % PROPRIO):
        if FICHIER_ALERTES in (g.get("files") or {}):
            detail = api("/gists/%s" % g["id"])
            contenu = ((detail.get("files") or {}).get(FICHIER_ALERTES) or {}).get("content") or "{}"
            return json.loads(contenu)
    return None


def correspond(p, mot):
    return (" " + m.norm(mot)) in (" " + m.norm((p.get("nom") or "") + " " + (p.get("marque") or "")) + " ")


def ntfy(sujet, titre, message, tags=None):
    corps = {"topic": sujet, "title": titre, "message": message, "tags": tags or ["shopping_cart"], "priority": 3}
    if ADRESSE_APPLI:
        corps["click"] = ADRESSE_APPLI
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def prix_txt(p):
    if p.get("prix") is None:
        return p.get("bon_plan") or "bon plan"
    if p.get("condition") == "le 2e":
        return "le 2e à %s (les 2 : %s)" % (m.euro(p["prix"]), m.euro(p["prix"] + (p.get("avant") or 0)))
    return m.euro(p["prix"]) + (" au lieu de %s" % m.euro(p["avant"]) if p.get("avant") else "")


def principal(log=print, aujourd=None, reglages=None, envoyer=ntfy):
    aujourd = aujourd or date.today()
    if reglages is None:
        reglages = lire_reglages()
    if not reglages:
        log("Pas de produits surveillés enregistrés (l'appli n'est pas encore connectée à GitHub).")
        return {}
    donnees = m.charger_json(m.FICHIER, {"promos": [], "evenements": [], "enseignes": {}})
    masques = set(reglages.get("magasins_masques") or [])
    noms = {k: v.get("nom", k) for k, v in (donnees.get("enseignes") or {}).items()}
    deja = m.charger_json(ENVOYEES, {})
    jour = aujourd.isoformat()

    trouvees = []
    for mot in reglages.get("produits") or []:
        for p in donnees.get("promos", []):
            if p.get("enseigne") in masques or not correspond(p, mot):
                continue
            if p.get("fin") and p["fin"] < jour:
                continue
            cle = "p|%s|%s" % (p["id"], p.get("fin", ""))
            if cle in deja:
                continue
            texte = "%s — %s : %s%s" % (p["nom"], noms.get(p["enseigne"], p["enseigne"]), prix_txt(p),
                                       (" (jusqu'au %s)" % m.jj_mm(p["fin"])) if p.get("fin") else "")
            deja[cle] = {"date": jour, "texte": texte, "mot": mot}
            trouvees.append(texte)

    operations = []
    if reglages.get("operations"):
        for e in donnees.get("evenements", []):
            if e.get("operation") and e.get("debut") == jour and e.get("enseigne") not in masques:
                cle = "o|%s|%s|%s" % (e["enseigne"], m.norm(e["titre"]), e["debut"])
                if cle not in deja:
                    texte = "%s : %s (jusqu'au %s)" % (e["nom"], e["titre"].title() if e["titre"].isupper() else e["titre"], m.jj_mm(e["fin"]))
                    deja[cle] = {"date": jour, "texte": texte}
                    operations.append(texte)

    sujet = (reglages.get("ntfy") or "").strip()
    if sujet and trouvees:
        try:
            titre = "%d produit%s surveillé%s en promo" % (len(trouvees), "s" if len(trouvees) > 1 else "", "s" if len(trouvees) > 1 else "")
            envoyer(sujet, titre, "\n".join(trouvees[:12]) + ("\n…" if len(trouvees) > 12 else ""), ["shopping_cart"])
            log("Notification envoyée : %s" % titre)
        except Exception as e:
            log("Notification non envoyée : %s" % e)
    if sujet and operations:
        try:
            envoyer(sujet, "Aujourd'hui dans tes magasins", "\n".join("⚡ " + o for o in operations), ["zap"])
            log("Notification opérations envoyée (%d)" % len(operations))
        except Exception as e:
            log("Notification opérations non envoyée : %s" % e)

    # mémoire des 60 derniers jours + rappels calendrier des 14 derniers jours
    limite = (aujourd - timedelta(days=60)).isoformat()
    deja = {k: v for k, v in deja.items() if v.get("date", "") >= limite}
    m.ecrire_json(ENVOYEES, deja, indent=1)
    extras = []
    for k, v in sorted(deja.items(), key=lambda kv: kv[1]["date"]):
        if k.startswith("p|") and v["date"] >= (aujourd - timedelta(days=14)).isoformat():
            extras.append({"uid": "alerte-" + m.slug(k)[:80] + "@mes-promos", "jour": date.fromisoformat(v["date"]),
                           "resume": "🛒 " + v["texte"], "desc": "Produit surveillé : " + v.get("mot", "")})
    try:
        m.ecrire_ics(donnees.get("evenements", []), os.path.join(m.DATA, "rappels.ics"), extras=extras)
    except Exception as e:
        log("Calendrier non mis à jour : %s" % e)
    log("Alertes : %d produit(s) trouvé(s), %d opération(s) du jour." % (len(trouvees), len(operations)))
    return {"produits": trouvees, "operations": operations}


if __name__ == "__main__":
    try:
        principal()
    except urllib.error.HTTPError as e:
        print("Alertes ignorées : GitHub a répondu %s" % e.code)
    except Exception as e:
        print("Alertes ignorées : %s" % e)
    sys.exit(0)
