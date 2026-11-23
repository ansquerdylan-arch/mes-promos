"""Vérifie la mise en route des comptes de Mogette (Firebase), sans se connecter à aucun compte.
Usage : python outils/verif_firebase.py CLE_API PROJET [ADRESSE_DE_RETOUR]

1. Firebase Authentication : connexion Google activée, identifiant client OAuth web (lu dans l'adresse que
   Firebase prépare pour Google), domaine du site accepté.
2. Google : l'adresse de retour de Mogette est bien enregistrée dans le client OAuth (sinon « redirect_uri_mismatch »).
3. Firestore : la base existe et refuse la lecture sans connexion (les règles de firestore.rules sont en place).
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

cle, projet = sys.argv[1], sys.argv[2]
retour = sys.argv[3] if len(sys.argv) > 3 else "https://ansquerdylan-arch.github.io/mes-promos/"
NAV = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"


class SansSuivre(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def appel(url, corps=None, methode=None, suivre=True, entetes=None):
    data = json.dumps(corps).encode() if corps is not None else None
    h = {"User-Agent": NAV, "Accept-Language": "fr-FR,fr;q=0.9"}
    if data:
        h["Content-Type"] = "application/json"
    h.update(entetes or {})
    req = urllib.request.Request(url, data=data, method=methode or ("POST" if data else "GET"), headers=h)
    ouvreur = urllib.request.build_opener() if suivre else urllib.request.build_opener(SansSuivre)
    try:
        with ouvreur.open(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)
    except Exception as e:
        return -1, repr(e), {}


bilan = []
# 1. Firebase Authentication + Google
code, txt, _ = appel("https://identitytoolkit.googleapis.com/v1/accounts:createAuthUri?key=" + cle,
                     {"providerId": "google.com", "continueUri": retour})
client = None
try:
    j = json.loads(txt)
except ValueError:
    j = {}
m = re.search(r"[?&]client_id=([^&]+)", j.get("authUri", ""))
if m:
    client = urllib.parse.unquote(m.group(1))
    bilan.append("OK   connexion Google activée, ID client : " + client)
else:
    err = (j.get("error") or {}).get("message", txt[:200])
    bilan.append("NON  connexion Google : " + err + {"CONFIGURATION_NOT_FOUND": " (Authentication pas encore commencé)",
                                                     "OPERATION_NOT_ALLOWED": " (Google pas activé)"}.get(err.split(" ")[0], ""))
print("createAuthUri :", code, txt[:300].replace("\n", " "))

# 2. adresse de retour enregistrée chez Google
if client:
    url = ("https://accounts.google.com/o/oauth2/v2/auth?client_id=" + urllib.parse.quote(client) + "&redirect_uri=" +
           urllib.parse.quote(retour, safe="") + "&response_type=id_token&scope=openid%20email%20profile&nonce=verif&state=verif")
    code, txt, h = appel(url, suivre=False)
    loc = h.get("Location") or h.get("location") or ""
    # la page d'erreur de Google porte le motif en base64 dans authError (« redirect_uri_mismatch »…)
    m2 = re.search(r"authError=([A-Za-z0-9_-]+)", loc)
    if m2:
        try:
            import base64
            brut = m2.group(1)
            loc += " " + base64.urlsafe_b64decode(brut + "=" * (-len(brut) % 4)).decode("utf-8", "replace")
        except Exception:
            pass
    if "redirect_uri_mismatch" in txt or "redirect_uri_mismatch" in loc:
        bilan.append("NON  adresse de retour pas enregistrée dans le client OAuth : " + retour)
    elif code in (301, 302, 303) and "/error" not in loc and "authError" not in loc:
        bilan.append("OK   Google accepte l'adresse de retour " + retour)
    elif code == 200 and "error" not in txt[:3000].lower():
        bilan.append("OK   Google accepte l'adresse de retour " + retour)
    else:
        erreur = re.search(r"(invalid_client|invalid_request|unauthorized_client|access_denied|disallowed_useragent|[a-z_]+_mismatch)", txt + loc)
        bilan.append("?    réponse de Google %s %s" % (code, erreur.group(1) if erreur else loc[:160]))
    print("authorize :", code, loc[:200])

# 3. Firestore : la base existe et refuse la lecture sans connexion
# sans clé d'API (comme l'appli, qui passe son jeton de connexion) : seules les règles de la base répondent
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/comptes/verification" % projet)
print("Firestore :", code, txt[:300].replace("\n", " "))
if code == 403 and "insufficient permissions" in txt.lower():
    bilan.append("OK   base Firestore créée, lecture refusée sans connexion (règles en place)")
elif code == 404 and "does not exist" in txt.lower():
    bilan.append("NON  base Firestore pas encore créée")
elif code == 403 and ("has not been used" in txt or "disabled" in txt):
    bilan.append("NON  base Firestore pas encore créée (API Firestore pas activée)")
elif code in (200, 404):
    bilan.append("NON  la base se lit sans connexion : les règles de firestore.rules ne sont pas publiées")
else:
    bilan.append("?    Firestore %s" % code)

# 4. clé publique des notifications lisible par tous ; listes partagées fermées sans connexion
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/config/public" % projet)
bilan.append("OK   clé publique des notifications lisible" if code == 200 and '"vapid"' in txt else "NON  clé publique des notifications : %s" % code)
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/listes/verification" % projet)
bilan.append("OK   listes partagées fermées sans connexion" if code == 403 else "NON  listes partagées : réponse %s sans connexion" % code)
# 5. connexion dans l'appli : un numéro inconnu se lit (absent, 404) mais la liste des jetons est fermée
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/liaisons/%s" % (projet, "0" * 40))
bilan.append("OK   connexion de l'appli prête (règle liaisons publiée)" if code == 404 else "NON  connexion de l'appli : réponse %s (règles pas encore publiées ?)" % code)
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/liaisons" % projet)
bilan.append("OK   jetons de connexion impossibles à lister" if code == 403 else "NON  jetons de connexion : liste en réponse %s" % code)
code, txt, _ = appel("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/config/push" % projet)
bilan.append("OK   clé privée des notifications fermée" if code == 403 else "NON  clé privée des notifications : réponse %s" % code)

print("\n=== BILAN ===")
for b in bilan:
    print(b)
