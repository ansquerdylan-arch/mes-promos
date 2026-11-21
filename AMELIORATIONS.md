# Mogette : idées d'améliorations

Liste tenue à jour avec Claude, pour reprendre le fil d'une conversation à l'autre.
Version à lire sur le téléphone : le doc « Mogette : idées d'améliorations »
(https://claude.ai/artifact/BE13MizFVK85Lfxk3hrMzK).

## Ajouts du 21 novembre 2026 (fait)

- Promos « toute la gamme » : `gamme()` ; étiquette de la marque à la place de la photo, badge « Toute la gamme ».
- Horaires manquants : 15 sur 18 complétés par `completer_horaires()` (même magasin listé sous un autre nom chez Bonial,
  même adresse ; sinon OpenStreetMap, même enseigne à 250 m, ou 1 km si aucun autre magasin de l'enseigne n'est plus près ;
  pas de devinette quand plusieurs magasins sont placés au même point). Restent : Chavagnes-en-Paillers,
  La Chaize-le-Vicomte, La Roche-sur-Yon rue Serpentine.
- Courbe des prix sur la fiche (`montrerCourbe()`, historique.json chargé à la demande). `mettre_historique()` garde le
  prix le plus bas du jour par clé « chaîne|nom|marque », arrondi au centime ; historique remis à un point par produit
  le 21/11 (les 4 premiers jours mélangeaient des produits de même nom).
- Favoris qui finissent : carte à l'accueil ; `favoris` dans le gist d'alertes, `alertes.py` prévient la veille et le jour même.
  État des alertes visible dans Réglages (bouton « Envoyer » si besoin), envoi automatique à l'ouverture.
- Sauvegarde des réglages : gist privé `reglages-mes-promos.json` ; à la connexion GitHub, un téléphone neuf reprend tout,
  un téléphone déjà rempli demande (« Remettre la sauvegarde » / « Garder ce téléphone ») avant d'écraser.
- Panier comparé (`moinsCherAilleurs()`) : code-barres de l'enseigne (`ean`, pas `off` qui est deviné par le nom) ou même
  nom + même marque, pas de lot contre un produit seul, prix au kilo/litre vérifié.
- Code-barres : photo, BarcodeDetector si présent, sinon décodeur maison EAN-13/EAN-8/UPC-A ; sinon nom via Open Food Facts.
- Moments de Mogette (`feteDuJour()`) : bonnet en décembre, lunettes noires semaine du Black Friday, chapeau au Nouvel an et à
  l'anniversaire (réglage). Sans photo : mini-mogette + emoji du rayon.
- Widget Scriptable : `widget-mogette.js` ; Réglages > « Copier le script du widget » y met les magasins.

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

## À faire du côté de Dylan

1. Connecter GitHub dans Mogette (Réglages > Liste partagée et alertes) : active alertes appli fermée, rappels de favoris,
   sauvegarde. Question posée en commentaire du doc le 20/11, pas encore de réponse.
2. Installer ntfy pour les notifications.
3. Le widget, s'il le veut (Scriptable).

## Plus tard

- Alerte de prix : « préviens-moi si la raclette passe sous 4 € » sur un produit surveillé.
- Ordre des rayons de son magasin dans le mode magasin.
- Mogette parle des surveillés dans la bulle de l'accueil (« Ta raclette est en promo chez Leclerc ! »).
- Les 3 magasins sans horaires, à la main si besoin.

## À surveiller

- Bonial ou E.Leclerc changent leur site : regarder le journal de la mise à jour sur GitHub.
- Open Food Facts limite les appels (429) : normal, ça reprend le lendemain.
- Anti-crise E.Leclerc : 0 produit au passage du matin le 20/11, 17 l'après-midi. À revoir seulement si c'est vide
  plusieurs jours de suite (en respectant robots.txt, sans contourner de protection).
- Taille du dépôt : environ 1 Mo d'historique par jour (30 Mo le 20/11/2026). À 500 Mo, ranger les données à part.
- Le lien d'invitation contient le jeton GitHub : ne le donner qu'à des proches.
