# Mes promos

Promos et bons plans des supermarchés autour d'Olonne-sur-Mer (Super U, E.Leclerc, Intermarché, Lidl, Carrefour Market), avec des idées de plats et une liste de courses.

- **La page** : `index.html` (servie par GitHub Pages).
- **Les promos** : `promos.json`, mis à jour chaque matin par GitHub Actions (`.github/workflows/maj.yml`), qui lance `maj_promos.py`.
- **Forcer une mise à jour** : onglet *Actions* → *Mise à jour des promos* → *Run workflow* (ou le bouton « Mettre à jour » dans l'appli).
- **Changer de magasins** : `config.json` (adresses bonial.fr de ta ville).
- **Plats** : `recettes.json`.

Si un matin rien n'est trouvé, les promos précédentes sont gardées. Le détail de chaque passage est dans *Actions*.
