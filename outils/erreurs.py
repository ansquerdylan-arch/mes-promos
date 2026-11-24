"""Erreurs signalées par les téléphones et nombre de messages « Une idée, un problème ? » (lancé par diag.yml, brut=erreurs).
Les messages eux-mêmes ne s'affichent pas ici (le journal peut être public) : ils se lisent dans la console Firebase.

Usage : python outils/erreurs.py [JOURS]   résumé des JOURS derniers jours (7 par défaut)
        python outils/erreurs.py test      vérifie en vrai qu'un téléphone peut déposer un rapport et un message
                                           (sans compte, comme l'appli), que les dépôts mal formés et la lecture sont
                                           refusés, puis efface les documents d'essai.
"""
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ICI)
import alertes  # noqa: E402


def depot_public(cle, projet, collection, champs, ident):
    """Comme deposer() dans index.html : sans connexion, heure posée par le serveur, document neuf."""
    nom = "projects/%s/databases/(default)/documents/%s/%s" % (projet, collection, ident)
    f = {k: ({"integerValue": str(v)} if isinstance(v, int) else {"stringValue": v}) for k, v in champs.items()}
    corps = {"writes": [{"update": {"name": nom, "fields": f},
                         "updateTransforms": [{"fieldPath": "t", "setToServerValue": "REQUEST_TIME"}],
                         "currentDocument": {"exists": False}}]}
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents:commit?key=%s" % (projet, cle)
    req = urllib.request.Request(url, data=json.dumps(corps).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, nom
    except urllib.error.HTTPError as e:
        return e.code, nom


def lecture_publique(cle, projet, collection, ident):
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/%s/%s?key=%s" % (projet, collection, ident, cle)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def tester(fb):
    page = open(os.path.join(ICI, "index.html"), encoding="utf-8").read()
    cle = re.search(r'COMPTE_CFG = \{ apiKey: "([^"]+)"', page).group(1)
    projet = fb.projet
    ua = "Mozilla/5.0 (essai automatique)"
    a_effacer, ok = [], True
    cas = [
        ("rapport d'erreur valable", "erreurs", {"m": "Essai automatique (à ignorer)", "s": "/mes-promos/", "l": 1, "p": "",
                                                 "v": "accueil", "ver": "essai", "ua": ua, "app": "site"}, 200),
        ("message valable", "retours", {"msg": "Essai automatique (à ignorer)", "v": "accueil", "ver": "essai", "ua": ua, "app": "site"}, 200),
        ("rapport avec un champ en trop", "erreurs", {"m": "x", "nom": "Dupont"}, 403),
        ("rapport avec une ligne en texte", "erreurs", {"m": "x", "l": "beaucoup"}, 403),
        ("message vide", "retours", {"msg": "", "v": "accueil"}, 403),
        ("message trop long", "retours", {"msg": "x" * 2001}, 403),
    ]
    for titre, collection, champs, attendu in cas:
        ident = "essai-" + secrets.token_hex(8)
        st, nom = depot_public(cle, projet, collection, champs, ident)
        if st == 200:
            a_effacer.append(nom)
        bon = st == attendu
        ok &= bon
        print("%s %s : %s (attendu %s)" % ("OK " if bon else "NON", titre, st, attendu))
        if collection == "erreurs" and st == 200:
            lu = lecture_publique(cle, projet, collection, ident)
            ok &= lu == 403
            print("%s lecture d'un rapport sans être propriétaire : %s (attendu 403)" % ("OK " if lu == 403 else "NON", lu))
    for nom in a_effacer:
        fb.supprimer(nom)
    restants = [n for n in a_effacer if fb.lire(n.split("/documents/", 1)[1])]
    print("documents d'essai effacés : %d sur %d" % (len(a_effacer) - len(restants), len(a_effacer)))
    print("TOUT EST BON" if ok and not restants else "À REVOIR")


brut = os.environ.get("FIREBASE_COMPTE", "").strip()
if not brut:
    print("Pas de clé FIREBASE_COMPTE")
    sys.exit()
fb = alertes.Firebase(json.loads(brut))
if len(sys.argv) > 1 and sys.argv[1] == "test":
    tester(fb)
else:
    jours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    alertes.resumer_retours(fb, print, jours=jours)
    print("(fin du résumé sur %d jours)" % jours)
