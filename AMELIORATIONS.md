# Mogette : idées d'améliorations

Liste tenue à jour avec Claude, pour reprendre le fil d'une conversation à l'autre.
Version à lire sur le téléphone : le doc « Mogette : idées d'améliorations »
(https://claude.ai/artifact/BE13MizFVK85Lfxk3hrMzK).

## Check-up du 20 novembre 2026 (fait)

Vérifié : 4 tailles d'écran (iPhone SE à Pro Max), clair et sombre, hors connexion, tous les parcours
(recherche, fiche, catalogue, plats, liste), le journal des mises à jour du matin et les 9 787 promos du jour.
Aucune erreur, aucun débordement, ouverture en moins d'une demi-seconde.

Corrigé :
- Croix dans les trois champs de recherche (accueil, Promos, choix des magasins).
- Rayon « Autres » : d'environ 155 produits à une trentaine (piles, fromages AOP, vins, bières, hygiène,
  jouets). Un produit inconnu d'un catalogue presque entièrement « jouets » ou « mode » prend ce rayon.
- Page de catalogue qui ne charge pas : « Page pas disponible pour l'instant ». Visuel cassé de l'agenda : retiré.
- Cibles tactiles agrandies : « + prix » dans la liste, liens « Tout voir ».
- Mise à jour : 2 nouveaux essais (après 3 puis 8 s) sur erreur serveur 5xx ou coupure réseau, 40 au plus par passage.
  Pas de nouvel essai sur 404 ni 429.
- Plus de demande `/api/etat` sur GitHub Pages (404 à chaque ouverture) ; la version PC la garde.
- GitHub Actions : `actions/checkout@v5` et `actions/setup-python@v6` (Node 24) ; `datetime.utcnow()` remplacé.

## Priorités

1. **Alertes appli fermée** : `alertes.py` écrit « Pas de produits surveillés enregistrés ». Vérifier sur l'iPhone
   le jeton GitHub dans les réglages de Mogette et qu'au moins un produit est surveillé.
2. **Leclerc anti-crise à 0 produit** dans le journal du matin : la page a dû changer. À revoir en respectant
   robots.txt et sans contourner de protection.
3. **Horaires** : 18 Carrefour Proximité sans horaires.
4. **Promos sur une marque entière** (« Toute la gamme Blini », « Carrefour Bio ») : les montrer comme une
   étiquette de marque plutôt qu'une fiche produit vide.

## Plus tard

- Courbe de prix sur la fiche : `historique.json` note le prix de chaque produit chaque jour depuis le 18/11/2026.
- Rappel la veille de la fin d'une promo mise en favori.
- Panier comparé : total de la liste par enseigne pour les produits en promo à plusieurs endroits.
- Plus de moments mascotte (Noël, Black Friday, anniversaire de Dylan).
- Sans photo : une petite Mogette par rayon au lieu de l'emoji.
- Réglages (magasins, prénom) sauvegardés avec la liste partagée, pour tout retrouver si l'icône est supprimée.
- Scanner un code-barres en magasin (champ `ean` déjà présent pour une partie des promos ; il faudra une
  bibliothèque de lecture, Safari ne le fait pas seul).
- Widget d'écran d'accueil via l'appli Scriptable, qui lirait `promos.json`.

## À surveiller

- Bonial ou E.Leclerc changent leur site : regarder le journal de la mise à jour sur GitHub.
- Open Food Facts limite les appels (429) : normal, ça reprend le lendemain.
- Taille du dépôt : environ 1 Mo d'historique par jour (30 Mo le 20/11/2026). À 500 Mo, ranger les données à part.
- Le lien d'invitation contient le jeton GitHub : ne le donner qu'à des proches.
