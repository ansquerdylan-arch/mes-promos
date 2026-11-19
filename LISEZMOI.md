# Mes promos

Promos et bons plans des supermarchés de toute la Vendée (Super U, Hyper U, U Express, E.Leclerc, Intermarché, Lidl, Carrefour…), avec des idées de plats, un agenda des opérations et une liste de courses.

- **La page** : `index.html` (servie par GitHub Pages), installable sur iPhone et Android.
- **Les promos** : mises à jour chaque matin par GitHub Actions (`.github/workflows/maj.yml`), qui lance `maj_promos.py`.
  - `promos.json` : magasins, horaires, catalogues en cours, offres nationales ; `offres/<catalogue>.json` : toutes les offres de chaque catalogue (l'appli ne charge que celles des magasins choisis).
  - Sources : les pages bonial.fr des enseignes (magasins, catalogues) puis la visionneuse publique de bonial, qui donne **toutes** les offres repérées dans chaque catalogue (prix, ancien prix, « le 2e à… », carte de fidélité, dates exactes, photo), plus les tableaux d'anti-crise.fr.
  - Opérations publiées en images (Jeudis Plus U…) : les visuels sont gardés et, sur GitHub, lus par Tesseract (jour exact, pourcentage, produits concernés) ; mémoire des lectures : `ocr.json`.
- **Fiche article** : toucher une promo ouvre sa fiche, avec trois liens : l'appli de l'enseigne (page App Store / Play Store, qui affiche « Ouvrir » si elle est installée ; le nom du produit est copié pour le coller dans sa recherche), la recherche du produit sur le site de l'enseigne, et la page du catalogue sur bonial.fr.
- **Rayons** : rangés par `rayon()` dans `maj_promos.py` (premier mot-clé du nom, rayon du magasin s'il est écrit, contrôles : vendu au litre = boisson ou soupe, dimensions = objet…).
- **Agenda / rappels** : `rappels.ics`, calendrier auquel le téléphone s'abonne.
- **Alertes même appli fermée** : l'appli enregistre les produits surveillés dans un gist public (`alertes-mes-promos.json`) ; chaque matin `alertes.py` cherche ces produits dans les promos, ajoute un rappel au calendrier et envoie une notification via l'appli ntfy si elle est activée (mémoire : `alertes_envoyees.json`).
- **Liste partagée et budget** : rangés dans un gist privé (`liste-mes-promos.json`), synchronisés en direct entre les téléphones invités.
- **Historique des prix** : `historique.json` (sert au badge « Plus bas prix vu » et à « Déjà vu à … »).
- **Forcer une mise à jour** : onglet *Actions* → *Mise à jour des promos* → *Run workflow* (ou le bouton MAJ dans l'appli).
- **Si un site change** : onglet *Actions* → *Diagnostic des sources* → coller une adresse → le détail de ce que le script y lit s'affiche (`diag.py`).
- **Changer de magasins ou de villes voisines** : `config.json`.
- **Plats** : `recettes.json` (54 recettes, chacune liée aux produits en promo).

Si un matin rien n'est trouvé, les promos précédentes encore valables sont gardées, et l'appli affiche un bandeau si les données ont plus de 36 h.
