# -*- coding: utf-8 -*-
"""
Alertes de Mogette, lancées par GitHub Actions juste après la mise à jour des promos.

Pour chaque compte Mogette (Firebase), d'après ses réglages rangés dans comptes/<uid> :
  - ses produits surveillés qui passent en promo dans ses magasins ;
  - ses favoris dont la promo finit demain ou aujourd'hui ;
  - les opérations de ses magasins qui commencent aujourd'hui ou demain (s'il ne les a pas coupées) ;
envoyés par notification (Web Push) à chaque téléphone abonné (comptes/<uid>/appareils/*).
Chaque alerte ne part qu'une fois (mémoire dans alertes_envoyees.json).

Le script publie aussi les règles de la base (firestore.rules, quand elles changent) et crée une fois pour toutes les
clés d'envoi des notifications (config/push, fermé ; config/public, lisible par l'appli).
Il lui faut la clé de service Firebase, dans le secret GitHub FIREBASE_COMPTE. Sans elle, il ne fait rien.
Il ne fait jamais échouer la mise à jour : en cas de souci, il le dit et s'arrête.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

import maj_promos as m

ENVOYEES = os.path.join(m.DATA, "alertes_envoyees.json")
REGLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firestore.rules")
SITE = "https://ansquerdylan-arch.github.io/mes-promos/"  # adresse de contact des notifications (« sub » VAPID)
PORTEES = ["https://www.googleapis.com/auth/datastore", "https://www.googleapis.com/auth/firebase",
           "https://www.googleapis.com/auth/cloud-platform"]


class Firebase:
    """Firestore et règles de la base, avec la clé de service (droits d'administration : les règles ne s'appliquent pas)."""

    def __init__(self, info, jeton=None):
        self.projet = info["project_id"]
        self.info = info
        self.jeton = jeton or self._jeton()
        self.docs = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents" % self.projet

    def _jeton(self):
        from google.oauth2 import service_account
        import google.auth.transport.requests
        cred = service_account.Credentials.from_service_account_info(self.info, scopes=PORTEES)
        cred.refresh(google.auth.transport.requests.Request())
        return cred.token

    def appel(self, methode, url, corps=None):
        data = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(url, data=data, method=methode,
                                     headers={"Authorization": "Bearer " + self.jeton, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode("utf-8")
                return r.status, (json.loads(txt) if txt.strip() else {})
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(txt)
            except ValueError:
                return e.code, {"erreur": txt[:300]}

    def liste(self, collection):
        """Tous les documents d'une collection (par pages de 300)."""
        sortie, page = [], ""
        while True:
            st, j = self.appel("GET", "%s/%s?pageSize=300%s" % (self.docs, collection, "&pageToken=" + urllib.parse.quote(page) if page else ""))
            if st != 200:
                raise RuntimeError("lecture de %s : %s %s" % (collection, st, str(j)[:200]))
            sortie += j.get("documents") or []
            page = j.get("nextPageToken")
            if not page:
                return sortie

    def groupe(self, collection):
        """Tous les documents « collection », où qu'ils soient (ici : les appareils de tous les comptes)."""
        st, j = self.appel("POST", self.docs + ":runQuery",
                           {"structuredQuery": {"from": [{"collectionId": collection, "allDescendants": True}]}})
        if st != 200:
            raise RuntimeError("lecture des %s : %s %s" % (collection, st, str(j)[:200]))
        return [x["document"] for x in j if x.get("document")]

    def lire(self, chemin):
        st, j = self.appel("GET", "%s/%s" % (self.docs, chemin))
        return j if st == 200 else None

    def ecrire(self, chemin, champs, neuf=False):
        url = "%s/%s%s" % (self.docs, chemin, "?currentDocument.exists=false" if neuf else "")
        st, j = self.appel("PATCH", url, {"fields": {k: {"stringValue": v} for k, v in champs.items()}})
        if st != 200:
            raise RuntimeError("écriture de %s : %s %s" % (chemin, st, str(j)[:200]))

    def supprimer(self, nom_complet):
        self.appel("DELETE", "https://firestore.googleapis.com/v1/" + nom_complet)

    def publier_regles(self, log):
        """firestore.rules du dépôt -> règles de la base, seulement si elles ont changé."""
        try:
            regles = open(REGLES, encoding="utf-8").read()
        except OSError:
            return
        api = "https://firebaserules.googleapis.com/v1/projects/%s" % self.projet
        st, rel = self.appel("GET", api + "/releases/cloud.firestore")
        if st == 200 and rel.get("rulesetName"):
            st2, rs = self.appel("GET", "https://firebaserules.googleapis.com/v1/" + rel["rulesetName"])
            fichiers = ((rs.get("source") or {}).get("files") or []) if st2 == 200 else []
            if any(f.get("content") == regles for f in fichiers):
                log("Règles de la base : déjà à jour")
                return
        st3, neuf = self.appel("POST", api + "/rulesets", {"source": {"files": [{"name": "firestore.rules", "content": regles}]}})
        if st3 != 200:
            log("Règles de la base NON publiées (%s) : %s" % (st3, str(neuf)[:300]))
            return
        nom = "projects/%s/releases/cloud.firestore" % self.projet
        if st == 200:
            st4, r4 = self.appel("PATCH", api + "/releases/cloud.firestore", {"release": {"name": nom, "rulesetName": neuf["name"]}})
        else:
            st4, r4 = self.appel("POST", api + "/releases", {"name": nom, "rulesetName": neuf["name"]})
        log("Règles de la base publiées" if st4 == 200 else "Règles de la base NON publiées (%s) : %s" % (st4, str(r4)[:300]))


def b64url(octets):
    return base64.urlsafe_b64encode(octets).decode().rstrip("=")


def champ(doc, nom):
    v = ((doc or {}).get("fields") or {}).get(nom) or {}
    return v.get("stringValue", v.get("integerValue"))


def cles_envoi(fb, log):
    """Clés VAPID des notifications : créées la première fois, la privée dans config/push (aucune règle ne l'ouvre),
    la publique aussi dans config/public, que l'appli lit pour abonner un téléphone."""
    d = fb.lire("config/push")
    if d and champ(d, "prive") and champ(d, "public"):
        prive, public = champ(d, "prive"), champ(d, "public")
    else:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        k = ec.generate_private_key(ec.SECP256R1())
        prive = b64url(k.private_numbers().private_value.to_bytes(32, "big"))
        public = b64url(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        fb.ecrire("config/push", {"prive": prive, "public": public}, neuf=True)
        log("Clés d'envoi des notifications créées")
    if champ(fb.lire("config/public"), "vapid") != public:
        fb.ecrire("config/public", {"vapid": public})
    return prive, public


def correspond(p, mot):
    # « fam » : famille reconnue à la marque (« chocolat » pour un « Assortiment » Lanvin, « bière » pour Leffe)
    return (" " + m.norm(mot)) in (" " + m.norm((p.get("nom") or "") + " " + (p.get("marque") or "") + " " + (p.get("fam") or "")) + " ")


def prix_txt(p):
    if p.get("prix") is not None:
        return m.euro(p["prix"]) + ((" au lieu de " + m.euro(p["avant"])) if p.get("avant") else "")
    if p.get("remise"):
        return "-%d %%" % p["remise"]
    return p.get("bon_plan") or "en promo"


def alertes_du_compte(uid, reglages, donnees, aujourd, deja):
    """-> liste de notifications { titre, texte, tag } à envoyer à ce compte (et les retient dans deja)."""
    jour = aujourd.isoformat()
    demain = (aujourd + timedelta(days=1)).isoformat()
    ids = [i for i in (reglages.get("magasins") or []) if i] or donnees.get("defaut", [])
    ens, promos, evts = m.vue_magasins(donnees, ids)
    masques = set(reglages.get("hiddenStores") or [])
    noms = {k: v.get("nom", k) for k, v in (ens or {}).items()}
    sortie = []

    trouvees = []
    for mot in reglages.get("watch") or []:
        for p in promos:
            if p.get("enseigne") in masques or not correspond(p, mot) or (p.get("fin") and p["fin"] < jour):
                continue
            cle = "%s|p|%s|%s" % (uid, p["id"], p.get("fin", ""))
            if cle in deja:
                continue
            quand = (" (le %s seulement)" % m.jj_mm(p["debut"])) if p.get("debut") and p.get("debut") == p.get("fin") else \
                ((" jusqu'au %s" % m.jj_mm(p["fin"])) if p.get("fin") else "")
            deja[cle] = {"date": jour}
            trouvees.append("%s, %s : %s%s" % (p["nom"], noms.get(p["enseigne"], p["enseigne"]), prix_txt(p), quand))
    if trouvees:
        n = len(trouvees)
        sortie.append({"titre": "%d produit%s surveillé%s en promo" % (n, "s" if n > 1 else "", "s" if n > 1 else ""),
                       "texte": "\n".join(trouvees[:6]) + ("\n…" if n > 6 else ""), "tag": "surveilles", "url": "./#promos"})

    par_id = {p["id"]: p for p in promos}
    rappels = []
    for fid in reglages.get("fav") or []:
        p = par_id.get(fid)
        if not p or p.get("fin") not in (jour, demain):
            continue
        quand = "Dernier jour aujourd'hui" if p["fin"] == jour else "Dernier jour demain"
        cle = "%s|f|%s|%s|%s" % (uid, fid, p["fin"], quand)
        if cle in deja:
            continue
        deja[cle] = {"date": jour}
        rappels.append("%s : %s, %s" % (quand, p["nom"], noms.get(p["enseigne"], p["enseigne"])))
    if rappels:
        sortie.append({"titre": "Tes favoris finissent", "texte": "\n".join(rappels[:6]), "tag": "favoris", "url": "./"})

    if reglages.get("alertesOps", True) is not False:
        ops = []
        for e in evts or []:
            if not e.get("operation") or e.get("enseigne") in masques or e.get("debut") not in (jour, demain):
                continue
            quand = "Aujourd'hui" if e["debut"] == jour else "Demain"
            cle = "%s|o|%s|%s|%s|%s" % (uid, e["enseigne"], m.norm(e["titre"]), e["debut"], quand)
            if cle in deja:
                continue
            deja[cle] = {"date": jour}
            titre = e["titre"].title() if e["titre"].isupper() else e["titre"]
            ops.append("%s, %s : %s%s" % (quand, e["nom"], titre, (" (" + e["resume"] + ")") if e.get("resume") else ""))
        if ops:
            sortie.append({"titre": "Opérations dans tes magasins", "texte": "\n".join(ops[:6]), "tag": "operations", "url": "./"})
    return sortie


def envoyer_push(abonnement, message, prive):
    """-> True envoyé, False téléphone désabonné (à oublier) ; lève une exception sinon."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=abonnement, data=json.dumps(message, ensure_ascii=False), vapid_private_key=prive,
                vapid_claims={"sub": SITE}, ttl=86400)
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):
            return False
        raise


def principal(log=print, aujourd=None, fb=None, envoyer=envoyer_push):
    aujourd = aujourd or date.today()
    if fb is None:
        brut = os.environ.get("FIREBASE_COMPTE", "").strip()
        if not brut:
            log("Alertes : pas de clé FIREBASE_COMPTE, rien n'est envoyé.")
            return {}
        try:
            fb = Firebase(json.loads(brut))
        except Exception as e:
            log("Alertes : clé FIREBASE_COMPTE illisible (%s)" % e)
            return {}
    try:
        fb.publier_regles(log)
    except Exception as e:
        log("Règles de la base non publiées : %s" % e)
    prive, _ = cles_envoi(fb, log)

    donnees = m.charger_donnees(m.FICHIER) or {}
    if donnees.get("v") != 2:
        log("Alertes : promos illisibles")
        return {}
    comptes = {}
    for d in fb.liste("comptes"):
        uid = d["name"].rsplit("/", 1)[1]
        try:
            comptes[uid] = json.loads(champ(d, "donnees") or "{}") or {}
        except ValueError:
            comptes[uid] = {}
    appareils = {}
    for d in fb.groupe("appareils"):
        morceaux = d["name"].split("/")
        uid = morceaux[morceaux.index("comptes") + 1] if "comptes" in morceaux else None
        try:
            abonnement = json.loads(champ(d, "push") or "{}")
        except ValueError:
            abonnement = {}
        if uid not in comptes or not abonnement.get("endpoint"):
            fb.supprimer(d["name"])  # appareil d'un compte supprimé, ou abonnement illisible
            continue
        appareils.setdefault(uid, []).append((d["name"], abonnement))

    deja = m.charger_json(ENVOYEES, {})
    envois, comptes_prevenus, oublies, erreurs, partis = 0, 0, 0, 0, set()
    for uid, liste in appareils.items():
        messages = alertes_du_compte(uid, comptes[uid], donnees, aujourd, deja)
        if messages:
            comptes_prevenus += 1
        for msg in messages:
            for nom, abonnement in liste:
                if nom in partis:
                    continue
                try:
                    if envoyer(abonnement, msg, prive):
                        envois += 1
                    else:
                        fb.supprimer(nom)  # téléphone désabonné : on l'oublie
                        partis.add(nom)
                        oublies += 1
                except Exception as e:
                    erreurs += 1
                    log("   notification non envoyée : %s" % str(e)[:160])

    limite = (aujourd - timedelta(days=60)).isoformat()
    deja = {k: v for k, v in deja.items() if v.get("date", "") >= limite}
    m.ecrire_json(ENVOYEES, deja, indent=1)
    log("Alertes : %d compte(s), %d téléphone(s) abonné(s), %d notification(s) envoyée(s) à %d compte(s)%s%s." % (
        len(comptes), sum(len(v) for v in appareils.values()), envois, comptes_prevenus,
        (", %d téléphone(s) désabonné(s) oublié(s)" % oublies) if oublies else "", (", %d erreur(s)" % erreurs) if erreurs else ""))
    return {"comptes": len(comptes), "envois": envois}


if __name__ == "__main__":
    try:
        principal()
    except Exception as e:
        print("Alertes ignorées : %s" % e)
    sys.exit(0)
