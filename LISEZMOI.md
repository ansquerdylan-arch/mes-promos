# Mes promos

Promos et bons plans des supermarchés autour d'Olonne-sur-Mer (Super U, E.Leclerc, Intermarché, Lidl, Carrefour Market), avec des idées de plats, un agenda des opérations et une liste de courses.

- **La page** : `index.html` (servie par GitHub Pages), installable sur iPhone et Android.
- **Les promos** : `promos.json`, mis à jour chaque matin par GitHub Actions (`.github/workflows/maj.yml`), qui lance `maj_promos.py`.
  - Source principale : les pages bonial.fr de chaque enseigne à Olonne (dates exactes, offres « le 2e à… »), complétées par les mêmes pages dans quelques villes voisines (seulement les catalogues valables à Olonne) et par les tableaux d'anti-crise.fr.
- **Agenda / rappels** : `rappels.ics`, calendrier auquel le téléphone s'abonne.
- **Alertes même appli fermée** : l'appli enregistre les produits surveillés dans un gist public (`alertes-mes-promos.json`) ; chaque matin `alertes.py` cherche ces produits dans les promos, ajoute un rappel au calendrier et envoie une notification via l'appli ntfy si elle est activée (mémoire : `alertes_envoyees.json`).
- **Liste partagée et budget** : rangés dans un gist privé (`liste-mes-promos.json`), synchronisés en direct entre les téléphones invités.
- **Historique des prix** : `historique.json` (sert au badge « Plus bas prix vu » et à « Déjà vu à … »).
- **Forcer une mise à jour** : onglet *Actions* → *Mise à jour des promos* → *Run workflow* (ou le bouton MAJ dans l'appli).
- **Si un site change** : onglet *Actions* → *Diagnostic des sources* → coller une adresse → le détail de ce que le script y lit s'affiche (`diag.py`).
- **Changer de magasins ou de villes voisines** : `config.json`.
- **Plats** : `recettes.json` (54 recettes, chacune liée aux produits en promo).

Si un matin rien n'est trouvé, les promos précédentes encore valables sont gardées, et l'appli affiche un bandeau si les données ont plus de 36 h.
