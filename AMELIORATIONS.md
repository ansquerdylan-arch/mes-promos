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
- Fiche de l'article scanné (demandée par Dylan le 21/11) : produit d'Open Food Facts, promos du moment, promos passées
  (courbe + liste, via `codes.json` tenu par `mettre_codes()`), bouton « Alerte promo » (ajoute aux surveillés).
- Moments de Mogette (`feteDuJour()`) : bonnet en décembre, lunettes noires semaine du Black Friday, chapeau au Nouvel an et à
  l'anniversaire (réglage). Sans photo : mini-mogette + emoji du rayon.
- Widget Scriptable : `widget-mogette.js` ; Réglages > « Copier le script du widget » y met les magasins.

## Version finale, 21 novembre 2026 (fait)

- Carte des magasins pour les choisir (tuiles OpenStreetMap, regroupement, « Autour de moi »).
- Applis : dossier `app/` (Capacitor, coquille qui ouvre le site) + workflow `applis.yml` -> `Mogette.apk` et `Mogette.ipa`
  sur la page de téléchargement « applis ». iPhone : IPA non signée (Sideloadly + identifiant Apple, 7 jours), ou compte
  développeur Apple (99 €/an) pour TestFlight/App Store. Play Store : compte 25 $ + vraie clé de signature.

- Petite IA (demandée le 21/11) : saisons (Noël en avant jusqu'au 24/12), goûts appris sur le téléphone, rail « Pour toi »
  avec raisons, « Pas pour moi », demandes simples dans la recherche de l'accueil, « Ce que Mogette a appris » dans Réglages.

- Magasins Action (demandés le 21/11) : 10 pages de départ bonial (« Ville/Action/p-r1080 »), famille `action` dans
  `FAMILLES`, couleur, appli et site dans la page. 14 magasins en Vendée, catalogue de la semaine « La semaine d'Action »
  (environ 140 articles). Carte « Nouveau : Action » à l'accueil, une seule fois, qui propose le plus proche. Rayons :
  mots-clés et marques d'Action (FERM, Werckmann, Dickie Toys, Trolli…), de 47 articles dans « Autres » à 1.
  Photos (Dylan, 21/11 : « il a pas d'image ») : bonial les donne en `…/<id>/<nom>.jpeg` et la mise à jour ne gardait que
  `…/<id>/main.jpg`. Corrigé (`RE_PHOTO`, `photoDe()`), ce qui donne aussi leurs photos à Carrefour, Carrefour Market,
  Carrefour Proximité et aux catalogues Leclerc de bonial. Pas besoin du site d'Action pour les photos.
  Horaires : Bonial n'en donne aucun ; Action est un `variety_store` sur OpenStreetMap, ajouté à la requête Overpass,
  avec deux serveurs de secours. Le 21/11 les trois serveurs étaient saturés (502, 504) : la mise à jour du matin
  réessaie toute seule tant que le cache n'a pas été refait avec la nouvelle requête.

## 21 novembre, soirée (fait) : appli publique

- Plus rien de GitHub ni du propriétaire dans l'appli : section GitHub, jeton, sauvegarde et alertes par gist, lien
  d'invitation qui contenait le jeton, bouton MAJ, mention de Claude, tuto et script Scriptable (`widget-mogette.js`)
  retirés ; l'ancien jeton est effacé des téléphones à l'ouverture. Fichier .ipa plus proposé (installation par Safari).
- Comptes Google activés (projet Firebase `mogette-d4fa2`, vérifiés par `outils/verif_firebase.py`).
- Liste partagée par les comptes : `listes/<numéro>`, lien `#liste=<numéro>` sans secret, membres vérifiés par les règles.
- Notifications Mogette (Web Push) à la place de ntfy : `alertes.py` lit les comptes avec la clé de service, publie les
  règles, crée les clés d'envoi, envoie à chaque téléphone abonné.

## 21 novembre, fin d'après-midi (fait)

- Scan d'une boîte Lanvin pas vue en promo alors qu'elle l'était (« variétés au choix ») : la fiche du scan montre
  « Sûrement en promo » (même marque et même produit, `promosProbables()`), l'alerte surveille le nom de la promo.
- Recherche « chocolat » : familles reconnues à la marque (`familles_produit()`, champ `fam`) pour chocolat, bonbons,
  café, bière, soda, eau, lessive, biscuits, couches, yaourts, vin ; aussi pour les produits surveillés.
- Contrôle du matin (`controler()`, `controle.json`) : enseigne avec beaucoup moins de promos que d'habitude, catalogue
  commencé sans article. Le 21/11 : rien d'anormal ; le Super U d'Olonne a bien ses 6 catalogues (le 7e, « U traiteur »,
  dure 5 mois et n'a pas de promos : écarté exprès).
- Android : l'APK ouvrait la galerie au lieu de l'appareil photo (Android 11+ : déclaration `IMAGE_CAPTURE` manquante).
- Comptes perso Google (et Apple plus tard) : prêts dans l'appli, cachés tant que le projet Firebase n'existe pas.
  À faire par Dylan : voir « À faire du côté de Dylan ». Apple : compte développeur à 99 €/an.

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

1. Mettre la clé de service Firebase dans le secret GitHub `FIREBASE_COMPTE` (Repository secrets du dépôt mes-promos) :
   sans elle, pas de notifications, et les règles de la base (liste partagée) ne sont pas publiées.
2. Sur iPhone : ouvrir Mogette depuis l'icône de l'écran d'accueil, se connecter, Réglages > Activer les notifications.

## Plus tard

- Alerte de prix : « préviens-moi si la raclette passe sous 4 € » sur un produit surveillé.
- Ordre des rayons de son magasin dans le mode magasin.
- Mogette parle des surveillés dans la bulle de l'accueil (« Ta raclette est en promo chez Leclerc ! »).
- Les 3 magasins sans horaires, à la main si besoin.
- Comptes dans les applis Android/iPhone (Google refuse la connexion dans une vue web intégrée : module natif ou passage
  par le navigateur).
- Contrôle du matin envoyé en notification au propriétaire seulement (il faudrait marquer son compte).

## À surveiller

- Bonial ou E.Leclerc changent leur site : regarder le journal de la mise à jour sur GitHub.
- Open Food Facts limite les appels (429) : normal, ça reprend le lendemain.
- Horaires des Action : vérifier après le 22/11 que le journal dit plus que « 15 complétés sur 32 ».
- Anti-crise E.Leclerc : 0 produit au passage du matin le 20/11, 17 l'après-midi. À revoir seulement si c'est vide
  plusieurs jours de suite (en respectant robots.txt, sans contourner de protection).
- Taille du dépôt : environ 1 Mo d'historique par jour (30 Mo le 20/11/2026). À 500 Mo, ranger les données à part.
- Le lien d'invitation contient le jeton GitHub : ne le donner qu'à des proches.
