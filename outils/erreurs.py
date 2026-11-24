"""Erreurs signalées par les téléphones et nombre de messages « Une idée, un problème ? » (lancé par diag.yml, brut=erreurs).
Les messages eux-mêmes ne s'affichent pas ici (le journal peut être public) : ils se lisent dans la console Firebase."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alertes  # noqa: E402

brut = os.environ.get("FIREBASE_COMPTE", "").strip()
if not brut:
    print("Pas de clé FIREBASE_COMPTE")
    sys.exit()
jours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
fb = alertes.Firebase(json.loads(brut))
alertes.resumer_retours(fb, print, jours=jours)
print("(fin du résumé sur %d jours)" % jours)
