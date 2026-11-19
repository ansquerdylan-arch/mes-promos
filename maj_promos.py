# -*- coding: utf-8 -*-
"""
Mise à jour des promos — sans Claude, sans clé, sans compte.

  1. parcourt les pages bonial.fr des enseignes de Vendée (magasins, horaires, catalogues en cours) ;
  2. lit CHAQUE catalogue en entier dans la visionneuse publique de bonial (toutes les offres
     repérées page par page : titre, marque, prix, ancien prix, « le 2e à… », carte de fidélité,
     dates exactes) ;
  3. pour les opérations publiées en images (Jeudis Plus U, etc.), garde les images et, si le
     logiciel Tesseract est installé, lit le texte (34 % sur les chocolats de Noël, jour exact…) ;
  4. complète avec les tableaux d'anti-crise.fr.
Écrit promos.json, rappels.ics (calendrier) et historique.json (prix vus au fil des semaines).

Utilisation :
    python maj_promos.py            -> met à jour
    python maj_promos.py --debug    -> met à jour et garde les pages brutes dans debug/

Uniquement la bibliothèque standard de Python : rien à installer.
"""
import gzip
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

try:  # consoles Windows : éviter un plantage sur les caractères accentués
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ICI = os.path.dirname(os.path.abspath(__file__))
# Version PC : les données vont dans data/ ; version GitHub : à côté de la page.
DATA = os.path.join(ICI, "data") if os.path.isdir(os.path.join(ICI, "data")) else ICI
if os.environ.get("PROMOS_DATA"):  # essais : écrire ailleurs
    DATA = os.path.abspath(os.environ["PROMOS_DATA"])
FICHIER = os.path.join(DATA, "promos.json")
HISTORIQUE = os.path.join(DATA, "historique.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


# --------------------------------------------------------------------------- outils
def norm(t):
    t = str(t or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def slug(t):
    return norm(t).replace(" ", "-")


def prix_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    if isinstance(v, dict):
        for k in ("amount", "value", "price", "valeur"):
            if k in v:
                return prix_float(v[k])
        return None
    m = re.search(r"(\d{1,4})(?:[.,](\d{1,2}))?", str(v).replace(" ", "").replace(" ", ""))
    if not m:
        return None
    return float(m.group(1) + "." + (m.group(2) or "0"))


def euro(x):
    return ("%.2f €" % x).replace(".", ",") if x is not None else ""


DERNIER = {"code": None}


def telecharger(url, log, entetes=None, binaire=False):
    DERNIER["code"] = None
    h = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
    }
    h.update(entetes or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            brut = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                brut = gzip.decompress(brut)
            if binaire:
                return brut
            return brut.decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        DERNIER["code"] = e.code
        if e.code != 404:  # 404 = l'enseigne n'existe pas dans cette ville, c'est normal
            log("   ! %s -> erreur HTTP %s" % (url, e.code))
    except Exception as e:  # réseau coupé, délai dépassé…
        log("   ! %s -> %s" % (url, e))
    return None


# --------------------------------------------------------------------------- rayons
RAYONS = {
    "High-tech & électroménager": "smartphone, tablette tactile, galaxy tab, ipad, telephone, telephone portable, aspirateur, balai aspirateur, lave linge, seche linge, lave vaisselle, refrigerateur, congelateur, airfryer, friteuse, expresso, cafetiere, senseo, machine a cafe, imprimante, casque, ecouteurs, enceinte, television, tv, console, jeu video, electromenager, multimedia, ordinateur, pc portable, souris, clavier, disque dur, cle usb, robot, blender, mixeur, bouilloire, grille pain, micro ondes, four multifonction, mini four, plancha, radiateur, chauffage, seche cheveux, lisseur, boucleur, montre connectee, trottinette electrique, smartwatch, barre de son, appareil a raclette, appareil raclette, gaufrier, crepiere, fondue electrique, air fryer, appareil a raclette, raclette electrique, nettoyeur vapeur, aspirateur laveur, jeu video, jeux video, pour ps5, pour ps4, nintendo switch, switch 2, xbox, nintendo, sony, philips, krups, moulinex, calor, seb, rowenta, braun, babyliss, remington, dyson, bosch, siemens, samsung, hisense, tcl, xiaomi, jbl, ninja, tristar, livoo, silvercrest, medion, konix, delonghi, magimix, kenwood, machine a biere, machine a granite, machine multi boissons, machine a boissons, distributeur de boissons, machine a dosettes, machine a capsules, machine a pain, machine a pates, machine a soda, centrale vapeur, cookeo",
    "Jouets & culture": "jouet, jouets, lego, playmobil, peluche, poupee, puzzle, jeu de societe, jeu de cartes, livre, livres, manga, bd, tome, roman, coloriage, feutres, stylos, cartable, nerf, beyblade, figurine, voiture radiocommandee, circuit, pokemon, pokedex, autocollants, papeterie, peluches, poupees, jeu de construction, roman policier, thriller, vtech, hasbro, hasbro gaming, mattel, ravensburger, goliath, fisher price, smoby, trotteur, baby foot, babyfoot, play doh, nathan, harpercollins, bibliotheque, pat patrouille, jeux de societe, jeu d adresse, jeu educatif, jeux educatifs",
    "Mode & sport": "t shirt, tee shirt, pull, chaussures, baskets, chaussettes, pyjama, veste, pantalon, jean, sweat, collant, collants, slip, slips, boxer, boxers, soutien gorge, legging, bonnet, gants, echarpe, manteau, doudoune, sac a main, sac a dos, bague, collier, bracelet, pendentif, boucles d oreilles, montre, lingerie, chemise, robe, jupe, peignoir, chaussons, brassiere, vetement, ski, debardeur, valise, bagagerie, combinaison, body, grenouillere, creoles, boucles d oreilles, chaine, bottines, mules, sandales, escarpins, ballerines, mocassins, pantoufles, charentaises",
    "Maison & déco": "couette, oreiller, drap, housse de couette, plaid, sapin, guirlande, decoration, boule, suspension, bougie, bouquet, tulipes, fleurs, vaisselle, poele, casserole, sauteuse, faitout, torchons, torchon, lampe, coussin, rideau, tapis, cadre, vase, creche, papier cadeau, sac cadeau, nappe, serviettes, verres, assiettes, couverts, boite de rangement, lanterne, scene de noel, figurine de noel, calendrier de l avent decoratif, cheminee, photophore, bougies, allumettes, cuiseur, cuiseur camembert, cuiseur a camembert, moules a gateau, moule a gateau, moules a muffins, moule a muffins, moules en silicone, sacs cadeaux, sac cadeaux, pot ceramique, pot en ceramique, ceramique, corbeille a linge, laguiole, couteaux, couteau, fourchettes, cuilleres, menagere, filtres, filtre a cafe, filtres a cafe",
    "Jardin & bricolage": "perceuse, visseuse, outil, outils, combustible, petrole, granules, granule bois, bois de chauffage, taille haies, tondeuse, plante, plantes, poinsettia en pot, cactus, orchidee, terreau, bouteille de gaz, batterie, ampoule, ampoules, rallonge, multiprise, prises, bloc prises, pneu, essuie glace, lave glace, antigel, nettoyeur haute pression, buches de bois, bois densifie, buches",
    "Hygiène & beauté": "shampoing, gel douche, deodorant, dentifrice, brosse a dents, rasoir, maquillage, creme visage, creme mains, lingettes, demaquillant, savon, parfum, couches, culottes, protege slip, serviettes hygieniques, coton, vernis, apres shampoing, soin, mouchoirs, coloration, visage, eau de toilette, eau de parfum, eau micellaire, gel lavant",
    "Entretien": "lessive, adoucissant, liquide vaisselle, pastilles lave, eponge, nettoyant, javel, essuie tout, papier toilette, sacs poubelle, desodorisant, capsules de lessive, vinaigre d alcool, papier hygienique, lessive pods, capsules de lessive, lessive liquide, pods, plumeau, swiffer, eau de javel, capsules lave vaisselle, capsules blanchissantes, mr propre, finish, omo, ariel, skip, persil, le chat, fairy, genie, sun, cif, ajax, harpic, canard wc, saint marc, vanish, soupline, lenor, mir",
    "Animaux": "chat, chien, croquettes, patee, litiere, sheba, felix, whiskas, pedigree, friskies, ultima, a macher, batonnets a macher, patee, patee pour chat, patee pour chien, pour chat, pour chien, pour chats, pour chiens, croquettes, boules de graisse, oiseaux, litiere",
    "Boissons": "biere, vin, rose, champagne, cremant, whisky, rhum, vodka, gin, jus, soda, coca, pepsi, eau minerale, eau gazeuse, sirop, ice tea, cafe, cafe grains, capsules cafe, dosettes, infusion, beaujolais, mousseux, martini, porto, ron, rhum arrange, arranges, liqueur, cognac, armagnac, calvados, pastis, ricard, cidre, nescafe, ricore, chicoree, bieres, jus d orange, pur jus, jus de pomme, jus de raisin, sirop, teisseire, oasis, ice tea, jus de fruits, capri sun, whiskey, electrolytes, bordeaux, bourgogne, brouilly, chablis, medoc, cotes du rhone, cotes de provence, saint emilion, muscadet, sancerre, chinon, saumur, cuvee, chateau, domaine, vin rouge, vin blanc, vin rose, aop rouge, aop blanc, aop rose, igp rouge, igp blanc, igp rose, pays d oc, vacqueyras, gigondas, cahors, madiran, bergerac, pomerol, margaux, pauillac, riesling, gewurztraminer, prosecco, cava, lambrusco, energy drink, red bull, punch, planteur, arrange, arranges, smoothie, smoothies, nectar, nectars, limonade, fanta, orangina, schweppes, sprite, seven up, perrier, evian, vittel, badoit, volvic, cristaline, san pellegrino, eau aromatisee, eaux aromatisees, pulp, lipton, the noir, the vert, tisane, tisanes, cocktail, cocktails, spritz, sangria, kir, liqueur, creme de cassis, pineau, muscat, cidre, bieres, biere blonde, tropicana, innocent, pur jus, jus de, punch, planteur, the noir, the vert, the rouge, the glace, the menthe, the a la menthe, the earl grey, the english breakfast, sachets de the, twinings, tetley, kusmi, elephant, monster energy, canettes, canette, capsules cafe, capsules espresso, capsules compatibles",
    "Poisson & mer": "saumon, cabillaud, crevette, crevettes, thon, sardine, maquereau, moules, huitres, coquilles saint jacques, coquilles, colin, merlu, bar, dorade, poisson, surimi, crabe, langoustine, truite, rillettes de thon, calamar, seiche, delpierre, petit navire, poissons, limande, sole, lieu noir, filet de lieu, dos de lieu, merlan, eglefin, fletan, blinis, saint jacques, noix de saint jacques, brandade",
    "Volaille": "poulet, dinde, pintade, canard, magret, caille, chapon, volaille, cordon bleu, cordons bleus, nuggets, aiguillettes, maitre coq, loue, tenders, nuggets, cordon bleu, aiguillettes, grignottes, pilon, pilons, cuisse de canard, cuisses de canard, confit de canard, magret",
    "Charcuterie": "jambon, saucisson, lardons, rillettes, pate, terrine, chorizo, bacon, knacki, saucisse de strasbourg, foie gras, andouille, andouillette, boudin, fleury michon, fuet, rosette, charcuterie, mortadelle, boudins, boudin noir, boudin blanc, boudins blancs, terrine de campagne",
    "Viande": "boeuf, veau, porc, agneau, steak, steaks haches, hache, entrecote, cote, roti, filet mignon, echine, saucisse, saucisses, merguez, chipolatas, paupiette, paupiettes, rognons, foie de boeuf, langue, osso bucco, bavette, charal, viande, boulettes",
    "Fromage": "fromage, camembert, emmental, comte, brie, raclette, mozzarella, cheddar, chevre, cabecou, crottin, roquefort, bleu d auvergne, reblochon, coulommiers, mimolette, parmesan, feta, tomme, madame loik, saint nectaire, tartiflette, buche aux laits, parmigiano, reggiano, tartiflette, rondele, tartare ail et fines herbes, boursin",
    "Crèmerie & œufs": "yaourt, yaourts, creme fraiche, creme liquide, beurre, oeufs, oeuf, margarine, skyr, fromage blanc, dessert lacte, petits suisses, liegeois, danette, bridelice, desserts, creme legere, creme fouettee, petit pot de creme, lait, lait demi ecreme, lait entier, lait ecreme, activia, danone, yaourt brasse, yaourts brasses, riz au lait, creme dessert, cremes desserts, creme brulee, cremes brulees, flan nappe, flans nappes, ile flottante, iles flottantes, mousse au chocolat, mousses au chocolat, panna cotta",
    "Fruits & légumes": "pomme, pommes, poire, banane, orange, clementine, mandarine, kiwi, avocat, raisin, fraise, citron, ananas, mangue, tomate, tomates, carotte, carottes, courgette, poireau, oignon, echalote, ail, salade, concombre, poivron, champignon, champignons, chou, brocoli, epinards, haricots verts, patate douce, pomme de terre, pommes de terre, potiron, courge, navet, radis, endive, pak choi, betterave, mache, fruits, legumes, potimarron, marrons, chataignes, noix, morilles, cepes, girolles, corbeille de fruits secs",
    "Surgelés": "pommes de terre surgelees, legumes surgeles, poisson pane, poissons panes, frites surgelees, surgele, surgeles, surgelee, surgelees, glace, glaces, cone, cones, mccain, frites, pizza surgelee, poelee, pommes noisettes, picard, airfryer frite, frites surgelees, surgelee, surgelees, pommes duchesse, legumes bruts",
    "Boulangerie": "pain, baguette, brioche, viennoiserie, croissant, pain de mie, pains a burger, pain a burger, wraps, tortilla, harrys, jacquet, pains au chocolat, boules mais, flan, tarte, tartelettes, galette des rois, bande feuilletee, tarte fine, tarte aux pommes, chausson aux pommes, chaussons",
    "Épicerie sucrée": "chocolat, chocolats, biscuit, biscuits, gateau, gateaux, bonbon, bonbons, confiture, pate a tartiner, nutella, cereales, granola, cacao, sucre, miel, compote, calendrier de l avent, ferrero, kinder, madeleine, panettone, milka, lindor, flocons d avoine, buche, canderel, delacre, deli choc, galettes, orangettes, barre, barres, barre tendre, pain d epices, marrons glaces, truffes, pralines, pandoro, papillotes, nesquik, poudre chocolatee, chocolatee, chocolatees, tablette de chocolat, tablettes de chocolat, chocolat lait, chocolat noir, chocolat au lait, chocolat blanc, noisettes grillees, sucres, decors sucres, pates de fruits, escargots praline, fourres, mini fourres, biscuits fourres, calissons, nougat, nougats, beignet, beignets, tiramisu, praline, boules praline, kit kat, compotes, gourde, gourdes, pom potes, cool fruits, petits pots, bledina, specialite de fruits, preparation de fruits, creme de marrons, cake, cakes, crumble, trompe l oeil, popcorn, pop corn, choco, daco bello, trompe loeil, palmiers, palmier, confitures, gourdes lactees",
    "Traiteur": "quiche, quiches, coeur de quiche, pizza, pizzas, lasagnes, lasagne, gratin, gratins, gratin dauphinois, hachis parmentier, parmentier, plat cuisine, plats cuisines, salade composee, salade de pates, taboule, paella, choucroute, choucroute garnie, croque monsieur, feuillete, feuilletes, friand, friands, bouchees a la reine, nems, samoussa, samoussas, sushi, sushis, sandwich, sandwichs, prefou, risotto, blanquette, bourguignon, tajine, couscous royal, pommes paillasson, tarte salee, tourte, wrap garni, farci, farcis, farcie, farcies, plat prepare, plats prepares, gnocchi a poeler, cordon bleu traiteur, burger, burgers, galette de ble noir, galettes de ble noir, crepe garnie, crepes garnies, tofu, plat vegetal, plats vegetaux, gougeres, pomme de terre farcie, pommes de terre farcies, tomate farcie, tomates farcies, rosti, rostis, rosti farci",
    "Épicerie salée": "pates, pates fraiches, pennette, spaghetti, riz, lentilles, semoule, couscous, quinoa, gnocchi, gnocchis, conserve, sauce, huile, vinaigre, moutarde, mayonnaise, ketchup, epices, sel, poivre, soupe, chips, chipster, aperitif, biscuits aperitifs, cacahuetes, olives, bouillon, farine, lustucru, panzani, barilla, rana, tuc, ravioli, raviolis, legumineuses, escargots, aligot, truffade, burgers aperitifs, pois chiches, escargots de bourgogne, soupes, soupe, tagliatelles, pates aux oeufs, pates, coquillettes, veloute, veloutes, mouline, potage, gazpacho, bouillon, croutons, chair de tomates, pulpe de tomates, puree de tomates, coulis de tomates, sauces, sauce tomate, lait de coco, bouquet garni, baked beans, puree, purees, mix bretzel, bretzels, haricots a la tomate, legumes cuisines, conserve de legumes, quinotto",
}
RAYONS_ALIMENTAIRES = {"Poisson & mer", "Volaille", "Charcuterie", "Viande", "Fromage", "Crèmerie & œufs",
                       "Fruits & légumes", "Surgelés", "Boulangerie", "Traiteur", "Épicerie sucrée", "Épicerie salée"}
_RAYONS = [(r, [k.strip() for k in mots.split(",") if k.strip()]) for r, mots in RAYONS.items()]
# catégories bonial -> rayon, quand les mots-clés ne suffisent pas
_CATS = [("electromenager", "High-tech & électroménager"), ("multimedia", "High-tech & électroménager"),
         ("informatique", "High-tech & électroménager"), ("telephon", "High-tech & électroménager"),
         ("bijou", "Mode & sport"), ("jouet", "Jouets & culture"), ("vetement", "Mode & sport"), ("mode", "Mode & sport"),
         ("decoration", "Maison & déco"), ("maison", "Maison & déco"), ("jardin", "Jardin & bricolage"),
         ("bricolage", "Jardin & bricolage"), ("animal", "Animaux"),
         ("hygiene", "Hygiène & beauté"), ("beaute", "Hygiène & beauté"), ("cosmetique", "Hygiène & beauté"),
         ("entretien", "Entretien"), ("menage", "Entretien"), ("boisson", "Boissons"), ("alcool", "Boissons"), ("vin", "Boissons"),
         ("surgele", "Surgelés"), ("fromage", "Fromage"), ("viande", "Viande"), ("volaille", "Volaille"),
         ("poisson", "Poisson & mer"), ("fruit", "Fruits & légumes"), ("legume", "Fruits & légumes"),
         ("charcuterie", "Charcuterie"), ("produits laitiers", "Crèmerie & œufs"), ("sucre", "Épicerie sucrée"),
         ("chocolat", "Épicerie sucrée"), ("alimentation", "Épicerie salée")]
# premier niveau des catégories bonial -> rayon (quand le nom du produit ne suffit pas)
_HAUT = {"article culturel": "Jouets & culture", "jeux et jouets": "Jouets & culture", "papeterie et articles de bureau": "Jouets & culture",
         "multimedia": "High-tech & électroménager", "informatique": "High-tech & électroménager", "electromenager": "High-tech & électroménager",
         "telephonie": "High-tech & électroménager", "maison et meubles": "Maison & déco", "saisons et evenements": "Maison & déco",
         "cadeau et produit derive": "Maison & déco", "mode": "Mode & sport", "sport et loisirs": "Mode & sport",
         "bricolage et jardin": "Jardin & bricolage", "auto et moto": "Jardin & bricolage", "cosmetiques": "Hygiène & beauté",
         "sante": "Hygiène & beauté", "animaux": "Animaux", "droguerie": "Entretien", "bebe et enfant": "Jouets & culture",
         "alimentation et boisson": "Épicerie salée"}


RAYONS_MANGER = {"Fruits & légumes", "Viande", "Volaille", "Poisson & mer", "Charcuterie", "Fromage", "Crèmerie & œufs",
                 "Boulangerie", "Traiteur", "Épicerie salée", "Épicerie sucrée", "Surgelés", "Boissons"}


# mots qui sont aussi des couleurs, parfums ou motifs (« mules rose », « bougie vanille »)
AMBIGUS = {"rose", "raclette", "orange", "citron", "vanille", "cerise", "fraise", "framboise", "chocolat", "caramel", "miel",
           "pomme", "olive", "cafe", "the", "menthe", "coco", "noix de coco", "peche", "lavande", "cannelle", "prune", "abricot",
           "cassis", "myrtille", "pistache", "praline", "creme", "lait", "beurre", "vin", "champagne", "biere", "sapin", "fromage",
           "pizza", "burger", "donut", "glace", "sucre", "bonbon", "bonbons", "frites", "avocat", "ananas", "banane", "cookie"}


def _mots_cles(t):
    """Tous les mots-clés trouvés : (position, -longueur, rayon, mot)."""
    t = " " + t + " "
    trouves = []
    for r, cles in _RAYONS:
        for k in cles:
            i = t.find(" " + k + " ")
            if i >= 0:
                trouves.append((i, -len(k), r, k))
    return trouves


def _mot_cle(texte):
    """Mot-clé le plus long (ancien calcul, gardé pour les catégories)."""
    tr = _mots_cles(norm(texte))
    if not tr:
        return "Autres", ""
    _, l, r, k = min(tr, key=lambda x: (x[1], x[0]))
    return r, k


# « Yaourt brassé SUR crème de marrons », « Cake AU citron » : ce qui suit est un parfum, pas le produit
RE_PARFUM = re.compile(r"\s(?:au|aux|a la|a l|sur|saveur|saveurs|gout|parfum|parfums|arome|aromes|facon|avec)\s")
# où le magasin range le produit (« au rayon surgelés », « au rayon traiteur libre-service »…)
RAYON_MAGASIN = [("fruits et legumes", "Fruits & légumes"), ("fruits legumes", "Fruits & légumes"), ("traiteur", "Traiteur"),
                 ("surgele", "Surgelés"), ("boucherie", "Viande"), ("volaille", "Volaille"), ("charcuterie", "Charcuterie"),
                 ("fromage", "Fromage"), ("cremerie", "Crèmerie & œufs"), ("produits laitiers", "Crèmerie & œufs"),
                 ("poissonnerie", "Poisson & mer"), ("maree", "Poisson & mer"), ("boulangerie", "Boulangerie"),
                 ("patisserie", "Boulangerie"), ("liquide", "Boissons"), ("boisson", "Boissons"), ("cave", "Boissons"),
                 ("parfumerie", "Hygiène & beauté"), ("hygiene", "Hygiène & beauté"), ("droguerie", "Entretien")]
MARQUES_OBJETS = {
    "Jouets & culture": ["vtech", "lego", "playmobil", "hasbro", "mattel", "goliath", "ravensburger", "play doh", "zuru", "clementoni",
                         "ecoiffier", "smoby", "fisher price", "nathan", "harpercollins", "hot wheels", "hotwheels", "barbie", "silverlit",
                         "dujardin", "asmodee", "gigamic", "janod", "djeco", "monster high"],
    "High-tech & électroménager": ["nintendo", "sony", "philips", "krups", "moulinex", "calor", "seb", "rowenta", "braun", "babyliss",
                                   "remington", "dyson", "bosch", "siemens", "samsung", "hisense", "tcl", "xiaomi", "jbl", "ninja",
                                   "tristar", "livoo", "silvercrest", "medion", "konix", "delonghi", "magimix", "kenwood",
                                   "russell hobbs", "domo", "essentielb", "proline", "qilive"],
    "Entretien": ["finish", "omo", "ariel", "skip", "persil", "le chat", "fairy", "genie", "sun", "cif", "ajax", "harpic", "canard wc",
                  "saint marc", "vanish", "soupline", "lenor", "mir", "mr propre", "sanytol", "destop", "air wick", "febreze", "spontex"],
}
BOISSONS_SECHES = {"cafe", "cafe grains", "capsules cafe", "capsules espresso", "capsules compatibles", "dosettes", "infusion",
                   "tisane", "tisanes", "the noir", "the vert", "the rouge", "the menthe", "the a la menthe", "the earl grey",
                   "the english breakfast", "sachets de the", "twinings", "tetley", "kusmi", "elephant", "lipton", "the glace"}
MARQUES_CONSERVE = {"d aucy", "daucy", "bonduelle", "cassegrain", "saint eloi", "geant vert", "heinz", "cirio", "mutti", "william saurin"}
RE_NON_ALIMENT = re.compile(r"(?i)\bd[eè]s\s+\d+\s*(ans|mois)\b|\bhauteur\b|\bø|\b\d+\s*(cm|mm)\b|\b\d+\s*w\b|\d+\s*%\s*(coton|polyester|viscose|laine|acrylique)")
RE_POIDS = re.compile(r"(?i)\b\d+(?:[.,]\d+)?\s*(g|kg|cl|ml|l|litres?)\b")


def rayon(nom, marque="", categories="", haut="", texte="", unite=""):
    """Rayon le plus probable.
    1. alcool (« 40° », « % vol ») ; 2. le rayon du magasin s'il est écrit (« au rayon surgelés ») ;
    3. le PREMIER mot-clé du nom (« Thé noir fruits rouges » = thé, « Yaourt aux marrons » = yaourt),
       les parfums après « au / aux / sur / saveur… » ne comptent qu'en dernier ;
    4. contrôles : objet (dimensions, âge, tissu), liquide vendu au litre, fromage (« % mat. gr. »)…
    haut : premier niveau de catégorie bonial (« Mode », « Électroménager »…)."""
    h = norm(haut)
    r_haut = _HAUT.get(h)
    non_alim = bool(r_haut) and h != "alimentation et boisson"
    strict = non_alim and h not in ("saisons et evenements", "cadeau et produit derive", "bebe et enfant")
    nom, texte, marque = (nom or "").replace("’", "'"), (texte or "").replace("’", "'"), (marque or "").replace("’", "'")
    nn, nt = norm(nom + " " + marque), norm(texte)
    if re.search(r"\b\d{1,2}(?:[.,]\d)?\s*°(?!\s*c)", nom) or re.search(r"\d+(?:[.,]\d+)?\s*%\s*vol\b", (nom + " " + texte).lower()):
        return "Boissons"
    m = re.search(r"\bau rayon ([a-z ]+)", nt)
    if m:
        for mot, r in RAYON_MAGASIN:
            if mot in m.group(1):
                if r == "Viande":  # boucherie-volaille : le nom tranche
                    r2, _ = _choix(nn)
                    return r2 if r2 in ("Viande", "Volaille") else r
                if r == "Fruits & légumes":
                    # le rayon fruits et légumes du magasin a aussi des jus frais, des soupes, du pop-corn, des bretzels…
                    if _liquide(nom, texte, unite):
                        return "Épicerie salée" if re.search(r"soupe|veloute|mouline|potage|gazpacho|sauce|huile|vinaigre|coulis", nn + " " + nt) else "Boissons"
                    r2, _ = _choix(nn)
                    return r2 if r2 not in ("Autres", "Fruits & légumes") else r
                return r
    nm = " " + norm(marque) + " "
    for rb, liste in MARQUES_OBJETS.items():  # marque d'objets (Vtech, Moulinex, Finish…) : elle suffit
        if any(" " + x + " " in nm for x in liste):
            return rb
    if re.search(r"\bsurgel", nn):
        return "Surgelés"  # « Pommes rissolées surgelées », « Lasagnes surgelées »
    if re.search(r"\beditions?\s+[A-Z]", texte):
        return "Jouets & culture"  # un livre
    if re.search(r"\bpour (chat|chats|chaton|chatons|chien|chiens|chiot|chiots|oiseaux|rongeurs|lapin)\b", nn):
        return "Animaux"
    r, mot = _choix(nn)
    if r == "Boissons" and mot not in BOISSONS_SECHES and re.search(r"(?i)\b\d+(?:[.,]\d+)?\s*(g|kg)\b", nom + " " + texte) \
            and not re.search(r"(?i)\b\d+(?:[.,]\d+)?\s*(cl|ml|l|litres?)\b", nom + " " + texte):
        autres = [x for x in _mots_cles(nn) if x[2] != "Boissons"]  # « Cocktail apéritif 120 g » : pas une boisson
        if autres:
            _, _, r, mot = min(autres)
    if r == "Autres":
        for source in (nt, norm(categories)):
            if source.strip():
                r, mot = _choix(source)
                if r != "Autres":
                    break
    if r == "Autres":
        tr = _mots_cles(nn)  # en dernier : les parfums
        if tr:
            _, _, r, mot = min(tr)
    if r != "Autres" and non_alim and r in RAYONS_MANGER and (strict or mot in AMBIGUS):
        return r_haut  # râpe à légumes électrique, mules rose, pâtée pour chat au thon…
    if r in RAYONS_MANGER and RE_NON_ALIMENT.search(nom + " " + texte) and not RE_POIDS.search(nom + " " + texte) \
            and not re.search(r"calibre|categorie|variete", nt):  # « calibre 28/40 mm » : un légume
        # un objet : ananas en céramique, jeu « Croque carotte »…
        if r_haut and non_alim:
            return r_haut
        t = (nom + " " + texte).lower()
        if re.search(r"d[eè]s\s+\d+\s*(ans|mois)", t):
            return "Jouets & culture"
        if re.search(r"coton|polyester|viscose|laine|acrylique", t):
            return "Mode & sport"
        if re.search(r"\b\d+\s*w\b", t):
            return "High-tech & électroménager"
        return "Maison & déco"
    if r == "Fruits & légumes":
        if _liquide(nom, texte, unite):
            return "Épicerie salée" if re.search(r"soupe|veloute|mouline|potage|gazpacho|sauce|huile|vinaigre|coulis", nn + " " + nt) else "Boissons"
        if (norm(marque) in MARQUES_CONSERVE and "sachet" not in nt) or re.search(r"\bconserves?\b|\bbocal\b|\bboites? de conserve", nt):
            return "Épicerie salée"  # légumes en conserve
    if r in ("Fruits & légumes", "Épicerie salée", "Épicerie sucrée", "Autres") and re.search(r"\bmat\s*gr\b|\b\d+\s*%\s*m\s*g\b", nt):
        return "Crèmerie & œufs" if re.search(r"yaourt|skyr|fromage blanc|dessert|creme", nn) else "Fromage"
    if r != "Autres":
        return r
    if r_haut:
        return r_haut
    c = " " + norm(categories) + " "
    for mot, r in _CATS:
        if mot in c:
            return r
    return "Autres"


def _liquide(nom, texte, unite):
    """Vendu au litre ou en cl / ml / l : une boisson ou une soupe, pas un fruit."""
    return bool(re.search(r"€\s*le\s*litre|€\s*/\s*l\b", (unite or "").lower())
                or re.search(r"\b\d+(?:[.,]\d+)?\s*(cl|ml)\b|\b\d+(?:[.,]\d+)?\s*l\b|\bbouteille\b|\bbrique\b", ((nom or "") + " " + (texte or "")).lower()))


def _choix(t):
    """Premier mot-clé du texte avant un éventuel parfum (« au / aux / sur / saveur… »).
    Les noms composés qui chevauchent la coupure comptent (« riz au lait », « pains au chocolat »)."""
    t = t.strip()
    coupe = RE_PARFUM.search(" " + t + " ")
    limite = coupe.start() if coupe else len(t) + 1
    tr = [x for x in _mots_cles(t) if x[0] <= limite]
    if not tr:
        return "Autres", ""
    _, _, r, k = min(tr)  # le plus à gauche, puis le plus long
    return r, k


# --------------------------------------------------------------------------- bonial : données structurées
def donnees_next(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _date_locale(iso, fin=False):
    """bonial donne des heures UTC (23:00 la veille / 22:55 le dernier jour) : on revient au jour français."""
    try:
        d = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None
    return (d + timedelta(hours=1 if fin else 2)).date()


RE_2E = re.compile(r"\b(2\s*(e|eme|ème|nd)|deuxi[eè]me|second)\b", re.I)
RE_UTILE = re.compile(r"%|offert|gratuit|remise|carte|achat|achete|2\s*(e|eme|nd)|3\s*(e|eme)|deuxieme|troisieme|\+|€|euro")


def condition_banale(c):
    """« Le sachet de 500 g », « LE PRODUIT », « L’unité » : description du produit, pas une condition."""
    n = norm(c.replace("’", "'"))
    return bool(re.match(r"(le|la|les|l)\s", n + " ")) and not RE_UTILE.search(n) and "€" not in c


# --------------------------------------------------------------------------- textes propres
SIGLES = {"aop", "aoc", "igp", "uht", "led", "ssd", "tv", "usb", "hd", "4k", "xs", "xl", "xxl", "xxxl", "bio", "pc", "ps4",
          "ps5", "nfc", "dvd", "asc", "msc", "gps", "hdmi", "rgb", "mg", "vtt", "u", "lcd", "oled", "qled", "dab", "wifi",
          "jbl", "lg", "hp", "abs", "vsop", "xo", "ipa", "ddp", "bbq", "diy", "sav", "cb", "nba", "nfl", "ufc", "dc", "u.h.t",
          "a.o.p", "i.g.p", "a.o.c"}
NOMS_PROPRES = {"france": "France", "noel": "Noël", "norvege": "Norvège", "espagne": "Espagne", "italie": "Italie",
                "ecosse": "Écosse", "irlande": "Irlande", "bretagne": "Bretagne", "vendee": "Vendée", "europe": "Europe",
                "belgique": "Belgique", "allemagne": "Allemagne", "chili": "Chili", "perou": "Pérou", "maroc": "Maroc",
                "egypte": "Égypte", "bordeaux": "Bordeaux", "bourgogne": "Bourgogne", "alsace": "Alsace", "savoie": "Savoie",
                "lidl": "Lidl", "carrefour": "Carrefour", "intermarche": "Intermarché", "leclerc": "Leclerc", "paques": "Pâques"}
RE_MOT_MAJ = re.compile(r"^[^a-zà-ÿ]*[A-ZÀ-ÖØ-Ý][^a-zà-ÿ]*$")


def _est_maj(mot):
    return sum(ch.isalpha() for ch in mot) >= 2 and bool(RE_MOT_MAJ.match(mot))


def adoucir(t, phrase=True):
    """Les passages en MAJUSCULES (2 mots et plus, ou tout le texte) passent en minuscules, sauf les sigles."""
    if not t:
        return t
    mots = t.split(" ")
    tout_maj = sum(_est_maj(m) for m in mots if m) >= max(1, len([m for m in mots if sum(ch.isalpha() for ch in m) >= 2]))
    sortie = []
    for i, m in enumerate(mots):
        voisin = (i > 0 and _est_maj(mots[i - 1])) or (i + 1 < len(mots) and _est_maj(mots[i + 1]))
        if _est_maj(m) and (tout_maj or voisin or len(m) >= 7):
            n = norm(m)
            if n in SIGLES or n.replace(" ", ".") in SIGLES:
                sortie.append(m)
            elif n in NOMS_PROPRES:
                sortie.append(NOMS_PROPRES[n] + m[len(m.rstrip(".,;:!?)»\"")):] if m[-1:] in ".,;:!?)»\"" else NOMS_PROPRES[n])
            else:
                sortie.append(m.lower())
        else:
            sortie.append(m)
    t = " ".join(sortie)
    t = re.sub(r"\bcarte u\b", "Carte U", t, flags=re.I)
    t = re.sub(r"\blidl plus\b", "Lidl Plus", t, flags=re.I)
    t = re.sub(r"(\d)\s*(?:ème|eme|EME|ÈME)\b", r"\1e", t)
    if phrase and t:
        t = t[0].upper() + t[1:]
    return t


def couper(t, n):
    t = t.strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(" ,;·:-") + "…"


RE_DEAL = re.compile(r"[-+]?\s?\d+(?:[.,]\d+)?\s*(?:%|€)|\b\d\s*\+\s*\d\b|\ble\s+\d\s*(?:e|eme|ème|nd)\b|\boffert|\bgratuit|\bremise|\bpromo", re.I)
RE_LABEL_PRIX = re.compile(r"deduit|^soit\b|^(le|la|les|l)\s.*\b(avec|sur)\s+(ma|la|votre)\s+carte\b|^(le|la|les|l)\s+\d+\s+produits?\s*$|^prix\s+(carte|avec)")
RE_PORTEURS = re.compile(r"offre reservee aux (porteurs|clients|titulaires)|avec (ma|la|votre) carte|carte (u|fidelite|carrefour|intermarche|leclerc|e leclerc)|lidl plus|cagnott")


def propre_plan(plan, nom, drapeaux):
    """Bon plan lisible : sans étiquettes de prix, sans le nom du produit répété, en minuscules."""
    morceaux = []
    for x in re.split(r"\s+·\s+", plan or ""):
        x = re.sub(r"^[\s·*–]+|[\s·*–-]+$", "", x)
        x = re.sub(r"^-\s+(?!\d)", "", x)
        n = norm(x.replace("’", "'"))
        if not n or n == norm(nom):
            continue
        if re.match(r"(a partir de|des)\b", n):
            drapeaux.add("des")
            x = re.sub(r"^\s*(à|a)\s+partir\s+de\s*,?\s*(le produit|la piece|l'unite)?\s*|^\s*dès\s*", "", x, flags=re.I).strip()
            if not x or condition_banale(x):
                continue
            n = norm(x)
        if RE_PORTEURS.search(n):
            drapeaux.add("carte")
        if RE_LABEL_PRIX.search(n) or condition_banale(x) or re.fullmatch(r"\d+([.,]\d+)?\s*(kg|g|l|cl|ml)", n):
            continue
        if re.search(r"\b(a|de|du|des|pour|sur|le|la|les)$", n) and len(n) < 25:
            continue  # « Le 2e à » sans le prix
        if " " not in n and not re.search(r"\d", n) and n not in ("offert", "gratuit", "promo"):
            continue  # « Gourde », « Bouteille »
        x = re.sub(r"(?i),?\s*(le|la|les)\s+(produit|pi[eè]ce|unit[ée]|lot)s?(\s+au\s+choix)?\s*$", "", x).strip()
        n = norm(x)
        if not n:
            continue
        if not RE_DEAL.search(x) and not RE_PORTEURS.search(n) and set(n.split()) & set(norm(nom).split()):
            continue  # une variante du produit, pas une promo
        x = re.sub(r"\bma\s+€\s+carte\b", "ma carte", x, flags=re.I)
        m = RE_DEAL.search(x)
        if m and m.start() > 0:
            avant = norm(x[:m.start()])
            mots_nom = set(norm(nom).split())
            if avant and len(set(avant.split()) & mots_nom) >= max(1, len(avant.split()) // 2):
                x = x[m.start():].strip()  # « Bloc 6 prises -50 % sur le 2e » -> « -50 % sur le 2e »
        x = adoucir(x)
        if norm(x) not in [norm(y) for y in morceaux]:
            morceaux.append(x)
    return couper(" · ".join(morceaux), 120)


RE_BLABLA = re.compile(r"^(voir prix|produits? dangereux|respectez les precautions|photo non contractuelle|visuel non contractuel|"
                       r"offre reservee aux (porteurs|clients|titulaires)|dans la limite des stocks|existe aussi en|selon arrivage|"
                       r"offre valable sur d ?autres|du \d{1,2}(er)? (au|jusqu) |a paraitre|repondant a des caracteristiques|distinctifs de qualite)|deduit")
# phrases à retirer où qu'elles soient
RE_PHRASES = re.compile(r"(?i)\**\s*(l.abus d.alcool est dangereux pour la sant[ée]\.?|[àa] consommer avec mod[ée]ration\.?|"
                        r"voir prix et caract[ée]ristiques[^.]*\.?|en cas de[^.]*rupture[^.]*\.?|"
                        r"pour votre sant[ée][^.]*\.?|www\.mangerbouger\.fr\.?)")
RE_DATES = re.compile(r"\s*\b(du|le)\s+(?:(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?\d{1,2}(?:er)?\s*(?:au|jusqu.au)\s+(?:(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\b", re.I)


def propre_detail(lignes, nom, unite, drapeaux):
    """Détail du produit : lignes utiles recollées, sans références, mentions légales ni MAJUSCULES."""
    sortie = []
    saute = False  # suite d'une mention légale coupée sur plusieurs lignes
    for l in lignes:
        l = l.replace("•", " · ").replace(" ", " ")
        for x in re.split(r"\s+·\s+", l):
            if saute:
                saute = not x.rstrip().endswith(".")
                continue
            x = re.sub(r"\[[A-Z]\]\s*", "", x)
            x = re.sub(r"\b(?:r[ée]f(?:[ée]rence)?\.?\s*:?\s*[A-Za-z0-9][A-Za-z0-9/._\-]{3,})\.?", "", x, flags=re.I)
            x = re.sub(r"\b(?:n[o°º])\s?\d{4,}\b|(?:^|\s)/\d{5,}\b", "", x, flags=re.I)
            x = re.sub(r"(?i)\b(mod[eè]le|code|ean|article)\s*:\s*[A-Za-z0-9/._-]*\d[A-Za-z0-9/._-]*", "", x)
            x = re.sub(r"^\s*:\s*[A-Za-z0-9/._-]*\d[A-Za-z0-9/._-]*\s*", "", x)
            x = RE_DATES.sub("", x)
            x = RE_PHRASES.sub("", x)
            x = re.sub(r"(?i)panachage possible\.?\s*la remise s.applique sur (le produit |les produits )?le moins cher( des produits)?\.?", "Panachage possible.", x)
            x = re.sub(r"\s+", " ", x).strip()
            x = re.sub(r"\s+", " ", x).strip(" *·-–;")
            n = norm(x.replace("’", "'"))
            if not n or "€" in x or x == unite:
                continue
            if re.match(r"(?i)^(le|la|les)?\s*[,.]\d", x) or not re.sub(r"\b(le|la|les|l|de|du)\b|[^a-z]", "", n):
                continue  # « Le ,99 » : morceau de prix
            if RE_PORTEURS.search(n) and len(n) < 70:
                drapeaux.add("carte")
                continue
            if "uniquement en ligne" in n or "disponible uniquement sur" in n:
                drapeaux.add("en_ligne")
                continue
            if RE_BLABLA.search(n):
                saute = not x.rstrip().endswith(".") and not n.startswith("deduit")
                continue
            if n in ("les 2 produits", "le produit", "les 3 produits", "au choix") or (condition_banale(x) and not re.search(r"\d", x)):
                continue
            if n == norm(nom):
                continue
            if sortie and re.search(r"(\b(de|du|des|d|à|a|en|et|ou|pour|avec|sans|au|aux|par)|[:,(/-])$", sortie[-1].strip(), re.I):
                sortie[-1] = sortie[-1].rstrip() + " " + x
            else:
                sortie.append(x)
    sortie = [re.sub(r"\s*:\s*$", "", adoucir(x)) for x in sortie]
    sortie = [x for x in sortie if x and norm(x) not in ("le produit de", "les 2 produits")]
    return couper(" · ".join(dict.fromkeys(sortie)), 150)


def propre_nom(nom):
    nom = re.sub(r"\s+", " ", (nom or "").replace(" ", " ")).strip(" *·-")
    if norm(nom) in ("sur tout", "sur toute la gamme", "sur tous les produits", "sur la gamme", "toute la gamme"):
        return "Toute la gamme"
    m = re.match(r"(?i)^sur\s+(tous les|toutes les|tout le|toute la|les|la gamme|le rayon|l'ensemble des)\s+(.+)$", nom)
    if m:
        quoi = m.group(1).lower()
        quoi = {"les": "tous les", "la gamme": "toute la gamme", "le rayon": "tout le rayon", "l'ensemble des": "tous les"}.get(quoi, quoi)
        nom = quoi + " " + m.group(2)
    return adoucir(nom)


RE_PRIX_UNITE = [
    re.compile(r"(?i)\b(kg|l|litre)\s*(?:des 2|au lot)?\s*[:=]\s*(\d+(?:[.,]\d{1,2})?)\s*€"),
    re.compile(r"(?i)(\d+(?:[.,]\d{1,2})?)\s*€\s*(?:/|le|la|par)\s*(kg|l|litre)\b"),
    re.compile(r"(?i)(\d+)\s*€\s*,\s*(\d{2})\s*(?:/|le|la|par)\s*(kg|l|litre)\b"),
]


def unite_et_poids(u):
    """« 3 x 100g - soit 300 g - 7,23 € le kg » -> (« 7,23 € le kg », « 3 x 100g - soit 300 g »)."""
    u = (u or "").strip()
    if not u:
        return "", ""
    for i, rx in enumerate(RE_PRIX_UNITE):
        m = rx.search(u)
        if not m:
            continue
        if i == 0:
            qte, val = m.group(1), m.group(2)
        elif i == 1:
            val, qte = m.group(1), m.group(2)
        else:
            val, qte = m.group(1) + "," + m.group(2), m.group(3)
        val = val.replace(".", ",")
        if "," in val and len(val.split(",")[1]) == 1:
            val += "0"
        qte = {"l": "litre"}.get(qte.lower(), qte.lower())
        reste = (u[:m.start()] + " " + u[m.end():]).strip(" -–·,;()")
        reste = re.sub(r"(?i)\(?\s*1\s*$", "", reste).strip(" -–·,;(")
        if reste and (not re.search(r"\d", reste) or "€" in reste or len(reste) > 40):
            reste = ""
        return "%s € le %s" % (val, qte), reste
    return (u if len(u) <= 30 and re.search(r"(?i)\b(kg|litre|l|pi[eè]ce)\b", u) and "€" in u else ""), ""


def unite_propre(u):
    u = (u or "").strip().rstrip(".; ")
    if u.startswith("(") and u.endswith(")"):
        u = u[1:-1]
    elif u.startswith("(") and ")" not in u:
        u = u[1:]
    elif u.endswith(")") and "(" not in u:
        u = u[:-1]
    u = re.sub(r"(?i)^soit\s+", "", u)
    u = re.sub(r"/\s*KG\b", "/ kg", u)
    u = re.sub(r"(\d+)\.(\d{1,2})\s*€", lambda m: "%s,%s €" % (m.group(1), m.group(2).ljust(2, "0")), u)
    u = re.sub(r"(?i)^\(?\s*1\s*kg\s*=\s*([\d.,]+\s*€)\s*\)?$", r"Le kg : \1", u)
    u = re.sub(r"(?i)^(le|la)\s+l\s*:", "Le litre :", u)
    u = re.sub(r"(?i)^le\s+kg\s*:", "Le kg :", u)
    return u


def offre_bonial(o):
    """Une offre bonial -> notre format. None si inutilisable."""
    titre = (o.get("title") or "").strip()
    if not titre:
        return None
    pr = o.get("prices") or {}
    p1 = prix_float(pr.get("mainPrice")) or None
    p2 = prix_float(pr.get("secondaryPrice")) or None
    conds = []
    for c in pr.get("conditions") or []:
        if isinstance(c, dict):
            conds += [str(v) for v in c.values() if isinstance(v, (str, int, float)) and str(v).strip()]
        elif isinstance(c, str):
            conds.append(c)
    drapeaux = set()
    conds = [c for c in conds if not condition_banale(c)]
    texte_prix = (pr.get("description") or "").strip()
    desc = [l.strip() for l in (o.get("description") or "").splitlines() if l.strip()]
    brute = (pr.get("unitPrice") or "").strip() or next((l for l in desc if re.search(r"\b(kg|litre|le l|la piece)\b", norm(l)) and "€" in l), "")
    unite, poids = unite_et_poids(brute)
    detail = propre_detail(([poids] if poids else []) + [l for l in desc[:4] if l != brute], titre, brute, drapeaux)
    d1, d2 = _date_locale(o.get("validFrom")), _date_locale(o.get("validUntil"), fin=True)
    chemins = [p for p in (o.get("categoryPaths") or []) if p and isinstance(p[0], dict)]
    haut = (chemins[0][0].get("name") or "") if chemins else ""
    utiles = []
    for path in chemins:
        if len(path) > 1 and norm(path[1].get("name")) == "marque":
            continue  # Alimentation et boisson > Marque > Père Dodu : rien sur le produit
        utiles += [n.get("name", "") for n in path[1:] if norm(n.get("name")) not in ("produits", "produit")][-3:]
    cats = " ".join(utiles) + " " + " ".join(o.get("categories") or [])
    if p1 and p2 and p2 > 5 * p1:  # erreur de saisie dans le catalogue (10,30 € écrit 1030)
        p2 = p2 / 100 if p1 < p2 / 100 < 3 * p1 else None
    it = {
        "nom": titre, "marque": (o.get("brand") or "").strip() if len((o.get("brand") or "").strip()) > 1 else "", "prix": p1,
        "avant": p2 if (p1 and p2 and p2 > p1) else None, "unite": unite, "detail": detail,
        "debut": d1.isoformat() if d1 else "", "fin": d2.isoformat() if d2 else "",
        "categories": cats, "haut": haut, "texte": " ".join(desc[:2])[:200],
        "catalogue": str((o.get("parentContent") or {}).get("legacyId") or ""),
        "page": ((o.get("parentContent") or {}).get("page") or {}).get("number"),
    }
    tout_cond = " ".join(conds + [texte_prix])
    if p1 and it["avant"] and RE_2E.search(tout_cond):
        # « -60 % sur le 2e » : le prix affiché est celui du 2e produit, pas de chaque produit
        it["condition"] = "le 2e"
        it["remise_affichee"] = round((1 - p1 / it["avant"]) * 100)
        it["remise_effective"] = round((1 - (it["avant"] + p1) / (2 * it["avant"])) * 100)
    if not p1:
        # offre sans prix (« -50 % sur le 2e », « 34 % sur la carte U ») : le titre EST le bon plan
        it["prix"] = None
        it["bon_plan"] = texte_prix if texte_prix and norm(texte_prix) != norm(titre) else titre
        if it["marque"] and len(titre) > 30:
            it["nom"] = it["marque"].title() if it["marque"].isupper() else it["marque"]
    elif texte_prix and not it.get("condition") and len(texte_prix) < 120:
        it["bon_plan"] = texte_prix
    if conds and not it.get("condition"):
        c = " · ".join(dict.fromkeys(conds))
        if len(c) < 120 and norm(c) not in norm(it.get("bon_plan", "")):
            it["bon_plan"] = (it.get("bon_plan", "") + " · " + c).strip(" ·")
    elif conds:
        propre_plan(" · ".join(conds), titre, drapeaux)  # seulement pour repérer « avec la carte »
    it["bon_plan"] = propre_plan(it.get("bon_plan", ""), it["nom"], drapeaux)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*€\s*de remise", it["bon_plan"])
    if m and it["prix"] and it["avant"]:
        rem = float(m.group(1).replace(",", "."))
        for f in (10, 100):
            if rem and abs((it["avant"] - it["prix"]) - rem * f) < 0.02 * f:
                it["prix"], it["avant"] = round(it["prix"] / f, 2), round(it["avant"] / f, 2)
                break
    if it["prix"] and it["avant"] and it["bon_plan"]:
        # « -58 % » ou « -40 € » répètent ce que l'étiquette de prix montre déjà
        rem, ecart = round((1 - it["prix"] / it["avant"]) * 100), it["avant"] - it["prix"]
        garde = []
        for x in it["bon_plan"].split(" · "):
            m1 = re.fullmatch(r"(?i)(?:promo\s*:\s*)?-?\s*(\d+)\s*%", x.strip())
            m2 = re.fullmatch(r"-?\s*(\d+(?:[.,]\d+)?)\s*€", x.strip())
            if (m1 and abs(int(m1.group(1)) - rem) <= 1) or (m2 and abs(float(m2.group(1).replace(",", ".")) - ecart) < 0.02):
                continue
            garde.append(x)
        it["bon_plan"] = " · ".join(garde)
    it["nom"] = propre_nom(it["nom"])
    if it["prix"] is None and not it["bon_plan"]:
        it["bon_plan"] = "Promo"
    for d in drapeaux:
        it[d] = True
    return it


def brochures_bonial(pi):
    sortie = []
    br = pi.get("brochures") or {}
    for cle in ("viewer", "publisher"):
        for b in br.get(cle) or []:
            if not isinstance(b, dict) or not b.get("id"):
                continue
            pages = None
            for pg in b.get("pages") or []:
                alt = ((pg or {}).get("metaData") or {}).get("imageAlt") or ""
                m = re.search(r"(\d+)\s+pages?", alt)
                if m:
                    pages = int(m.group(1))
                    break
            sortie.append({"id": str(b.get("id")), "titre": (b.get("title") or "").strip(), "type": b.get("type") or "",
                           "debut": _date_locale(b.get("validFrom")), "fin": _date_locale(b.get("validUntil"), fin=True),
                           "pages": pages or len(b.get("pages") or []) or 1})
    return sortie


def infos_page(page):
    d = donnees_next(page)
    return (((d or {}).get("props") or {}).get("pageProps") or {}).get("pageInformation") or {}


def page_bonial(page, pi=None):
    """-> (offres, catalogues, liens magasins) depuis une page bonial « enseigne dans une ville »."""
    if pi is None:
        d = donnees_next(page)
        if not d:
            return [], [], []
        pi = ((d.get("props") or {}).get("pageProps") or {}).get("pageInformation") or {}
    offres = []
    for cle, bloc in (pi.get("offers") or {}).items():
        for o in (bloc or {}).get("items") or []:
            it = offre_bonial(o)
            if it:
                offres.append(it)
    return offres, brochures_bonial(pi), re.findall(r'href="(https://www\.bonial\.fr/Magasins/[^"]+/v-f\d+)"', page)


# --------------------------------------------------------------------------- bonial : catalogues complets
# La page d'une enseigne ne montre que 16 offres. La visionneuse publique de bonial (celle qui
# s'ouvre quand on clique sur un catalogue) donne toutes les offres repérées, page par page.
VISIONNEUSE = "https://content-viewer-be.bonial.fr/v1"
ENTETES_VISIONNEUSE = {"Bonial-Api-Consumer": "web-content-viewer-fe", "Accept": "application/json",
                       "Origin": "https://www.bonial.fr", "Referer": "https://www.bonial.fr/"}


def visionneuse(chemin, pos, log):
    url = "%s%s?partner=bonial_web&lat=%s&lng=%s" % (VISIONNEUSE, chemin, round(pos[0], 4), round(pos[1], 4))
    txt = telecharger(url, log, ENTETES_VISIONNEUSE)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def _prix_deal(d):
    if not d:
        return None
    v = d.get("min") or d.get("max")
    return prix_float(v) or None


def offre_visionneuse(c):
    """Offre de la visionneuse -> même forme que les offres des pages, puis offre_bonial()."""
    prods = c.get("products") or []
    if not prods or not (prods[0].get("name") or "").strip():
        return None
    p = prods[0]
    deals = c.get("deals") or []
    vente = next((d for d in deals if d.get("type") == "SALES_PRICE"), None)
    normal = next((d for d in deals if d.get("type") == "REGULAR_PRICE"), None)
    autre = next((d for d in deals if d.get("type") not in ("SALES_PRICE", "REGULAR_PRICE")), None)
    princ = vente or normal or autre or {}
    second = normal if vente else None
    carte = any(isinstance(x, dict) and x.get("loyaltyProgram") for d in deals for x in (d.get("conditions") or []))
    conds = [x for x in (princ.get("conditions") or []) if not (isinstance(x, dict) and x.get("loyaltyProgram"))]
    desc = "\n".join((x.get("paragraph") or "") for x in (p.get("description") or []) if isinstance(x, dict))
    pc = c.get("parentContent") or {}
    val = ((c.get("publicationProfiles") or [{}])[0] or {}).get("validity") or {}
    cats = p.get("categoryPaths") or []
    if cats and isinstance(cats[0], dict):
        cats = [cats]
    o = {"title": p.get("name"), "brand": p.get("brandName") or "", "description": desc, "categoryPaths": cats,
         "categories": [], "validFrom": val.get("startDate"), "validUntil": val.get("endDate"),
         "prices": {"mainPrice": _prix_deal(princ), "secondaryPrice": _prix_deal(second), "conditions": conds,
                    "description": princ.get("description") or "", "unitPrice": princ.get("priceByBaseUnit") or ""},
         "parentContent": {"legacyId": pc.get("legacyId"), "page": {"number": (pc.get("page") or {}).get("number")}}}
    it = offre_bonial(o)
    if not it:
        return None
    if (c.get("image") or "").endswith("/main.jpg") and c.get("id"):
        it["img"] = c["id"]  # photo : https://content-media.bonial.biz/<id>/main.jpg
    if carte:
        it["carte"] = True
    if princ.get("min") and princ.get("max") and princ["max"] > princ["min"]:
        it["des"] = True  # « dès 2,99 € » : plusieurs produits à des prix différents
    lab = c.get("discountLabel") or {}
    if lab.get("type") == "DISCOUNT_PERCENTAGE" and str(lab.get("value") or "").isdigit() and it.get("prix") is None:
        it["remise_label"] = int(lab["value"])
    return it


def catalogue_complet(cid, typ, pos, log, pause=0.6):
    """-> (offres, images de bannières) ou None si la visionneuse n'a pas répondu."""
    offres, images = [], []
    if typ != "DYNAMIC":
        d = visionneuse("/brochures/%s/pages" % cid, pos, log)
        time.sleep(pause)
        if d is None:
            return None
        for pg in d.get("contents") or []:
            for o in pg.get("offers") or []:
                it = offre_visionneuse(o.get("content") or {})
                if it:
                    offres.append(it)
        if d.get("contents") or typ == "BROCHURE":
            return offres, images
    # catalogue « dynamique » : des sections avec des offres et/ou des images
    meta = visionneuse("/brochures/%s" % cid, pos, log)
    time.sleep(pause)
    if meta is None:
        return None
    for sec in ((meta.get("content") or {}).get("sections") or [])[:6]:
        d = visionneuse("/brochures/%s/section/%s" % (cid, sec.get("number", 0)), pos, log)
        time.sleep(pause)
        for b in ((d or {}).get("content") or {}).get("blocks") or []:
            for x in b.get("contents") or []:
                cc = x.get("content") or {}
                if cc.get("products") and cc.get("deals") is not None:
                    it = offre_visionneuse(cc)
                    if it:
                        offres.append(it)
                elif cc.get("type") == "image_banner" and cc.get("image"):
                    images.append(cc["image"])
    return offres, images


# --------------------------------------------------------------------------- opérations en images (OCR)
JOURS_SEM = "lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"
RE_JOUR = re.compile(r"\b(?:%s)\s+(\d{1,2})(?:er)?\s+(%s)\b" % (JOURS_SEM, "|".join(MOIS)))
RE_DU_AU = re.compile(r"\bdu\s+(\d{1,2})(?:er)?\s+(?:(%s)\s+)?au\s+(\d{1,2})(?:er)?\s+(%s)\b" % ("|".join(MOIS), "|".join(MOIS)))
RE_SUR = re.compile(r"^SUR\s+(?:LES|LA|LE|L'|L’|TOUS LES|TOUTES LES|TOUT LE|TOUTE LA|TOUT|TOUTE|VOS|NOS)\s+([A-ZÀ-ÖØ-Ý' ’-]{3,60}?)[\s.,;:!]*$")
MAJ_MOTS = {"noel": "Noël", "paques": "Pâques", "u": "U", "carte": "carte"}


def ocr_dispo():
    import shutil
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("tesseract"))


def ocr_image(donnees):
    """Texte d'une bannière (plusieurs passes : petits textes, gros titres) + le plus gros nombre (34 %…)."""
    import io
    import subprocess
    import tempfile
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(donnees)).convert("RGB")
    if im.width > 1600:
        im = im.resize((1600, int(im.height * 1600 / im.width)))
    vert = im.split()[1]  # le jaune et le blanc ressortent dans le vert, pas le rouge ni le magenta
    gris = ImageOps.grayscale(im)
    textes = [(gris, "3"), (gris, "11"), (ImageOps.invert(vert.point(lambda v: 255 if v > 170 else 0)), "11"),
              (ImageOps.invert(gris.point(lambda v: 255 if v > 200 else 0)), "11")]
    lignes, nombres = [], []

    def tess(img, psm, tsv=False):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "i.png")
            img.save(f)
            cmd = ["tesseract", f, "-", "-l", "fra", "--psm", psm] + (["tsv"] if tsv else [])
            return subprocess.run(cmd, capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    for img, psm in textes:
        try:
            for l in tess(img, psm).splitlines():
                l = l.strip()
                if len(l) >= 3 and sum(ch.isalpha() for ch in l) >= 3 and l not in lignes:
                    lignes.append(l)
        except Exception:
            continue
    # les très gros chiffres ne se lisent qu'en réduisant beaucoup l'image
    for k in (2, 4, 8, 12, 16):
        petite = vert.resize((max(1, im.width // k), max(1, im.height // k)), Image.LANCZOS)
        petite = ImageOps.expand(petite.point(lambda v: 0 if v > 170 else 255), border=16, fill=255)
        try:
            out = tess(petite, "11", tsv=True)
        except Exception:
            continue
        for row in out.splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 12:
                continue
            for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", c[11]):
                try:
                    nombres.append((int(c[9]) * k, int(x)))
                except ValueError:
                    pass
    grands = [x for x in nombres if x[0] >= 0.12 * im.height]
    return {"t": "\n".join(lignes)[:2000], "n": max(grands)[1] if grands else None}


def _date_fr(jour, mois, ref):
    try:
        y = ref.year + (1 if MOIS[mois] < ref.month - 6 else 0)
        return date(y, MOIS[mois], int(jour))
    except (KeyError, ValueError):
        return None


def operation_depuis_texte(lu, cat, url, famille):
    """Texte d'une bannière -> une offre « opération » (ex. 34 % reversés sur la Carte U sur les chocolats de Noël)."""
    texte = lu.get("t") or ""
    n = norm(texte)
    if not texte or "ne ratez pas" in n:
        return None
    sujet = None
    for l in texte.splitlines():
        m = RE_SUR.match(l.strip().replace("’", "'"))
        if m and not re.match(r"\d", m.group(1)) and "PRODUIT" not in m.group(1):
            sujet = m.group(1).strip(" -'")
            break
    if not sujet:
        return None  # bannière produit (déjà dans le catalogue) ou simple visuel
    mots = [MAJ_MOTS.get(norm(w), w.lower()) for w in sujet.split()]
    nom = " ".join(mots)
    nom = nom[:1].upper() + nom[1:]
    pct = re.search(r"(\d{1,2})\s*%", texte)
    pct = int(pct.group(1)) if pct else lu.get("n")
    dates = [d for d in (_date_fr(a, b, cat["debut"]) for a, b in RE_JOUR.findall(n)) if d]
    for a, m1, b, m2 in RE_DU_AU.findall(n):
        d1, d2 = _date_fr(a, m1 or m2, cat["debut"]), _date_fr(b, m2, cat["debut"])
        if d1 and d2:
            dates += [d1, d2]
    dates = [d for d in dates if cat["debut"] - timedelta(days=1) <= d <= cat["fin"]]
    if "revers" in n:
        meca = "reversés en € sur la Carte U" if famille == "u" else "reversés sur la carte de fidélité"
    elif "remise immediate" in n:
        meca = "de remise immédiate"
    elif "offert" in n:
        meca = "offert"
    elif "carte" in n:
        meca = "avec la carte"
    else:
        meca = "de réduction"
    plan = ("%d %% %s" % (pct, meca)) if pct and 3 <= pct <= 90 else meca[:1].upper() + meca[1:]
    lignes = texte.splitlines()
    cond = " ".join(x.strip() for x in lignes if re.search(r"limit|une seule fois|maximum|par foyer|par compte", norm(x)) and len(x) > 30)[:200]
    hors = next((x.strip() for x in lignes if norm(x).startswith("hors ") and len(x) > 20), "")
    if hors and hors not in cond:
        cond = (cond + " " + hors).strip()
    it = {"nom": nom, "marque": "", "prix": None, "bon_plan": plan, "detail": "",
          "debut": min(dates).isoformat() if dates else cat["debut"].isoformat(),
          "fin": max(dates).isoformat() if dates else cat["fin"].isoformat(),
          "categories": nom, "catalogue": str(cat["id"]), "image": url, "op": True}
    it["detail"] = cond[:300]
    if "carte" in n:
        it["carte"] = True
    if pct and 3 <= pct <= 90:
        it["remise_label"] = pct
    return it


# --------------------------------------------------------------------------- bonial : texte (secours)
RE_PRIX_LIGNE = re.compile(r"^(?:Dès\s*:?\s*)?(\d{1,4}[.,]\d{2})\s*€$", re.I)
RE_ALT = re.compile(r"Promo\s+(.{2,160}?)\s+à\s+(\d{1,4}(?:[.,]\d{1,2})?)?\s*€?\s*dans le catalogue\s+", re.I)


class Texte(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lignes, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.ignore += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.ignore:
            self.ignore -= 1

    def handle_data(self, d):
        if not self.ignore:
            d = re.sub(r"\s+", " ", d).strip()
            if d:
                self.lignes.append(d)


def lignes_texte(page):
    p = Texte()
    try:
        p.feed(page)
    except Exception:
        pass
    return p.lignes


def extraire_bonial_texte(page, nom_enseigne):
    items = []
    for m in RE_ALT.finditer(html.unescape(page)):
        nom = m.group(1).strip().strip('"')
        p = prix_float(m.group(2)) if m.group(2) else None
        items.append({"nom": nom, "marque": "", "prix": p, "avant": None, "bon_plan": "" if p else nom})
    return items


# extraction JSON générique (utilisée par diag.py)
CLES_NOM = ("name", "title", "productName", "product_name", "label", "nom", "offerTitle")
CLES_PRIX = ("price", "priceValue", "salePrice", "currentPrice", "prix", "finalPrice", "promoPrice",
             "offerPrice", "lowPrice", "dealPrice", "mainPrice")


def extraire_json(page):
    trouves = []

    def marche(o, prof=0):
        if prof > 40:
            return
        if isinstance(o, dict):
            nom = next((o[k] for k in CLES_NOM if isinstance(o.get(k), str)), None)
            prix = next((o[k] for k in CLES_PRIX if o.get(k) not in (None, "", 0)), None)
            if prix is None and isinstance(o.get("prices"), dict):
                prix = o["prices"].get("mainPrice")
            if nom and prix is not None and prix_float(prix):
                trouves.append({"nom": nom, "prix": prix_float(prix)})
            for v in o.values():
                marche(v, prof + 1)
        elif isinstance(o, list):
            for v in o:
                marche(v, prof + 1)
    for mm in re.finditer(r"<script([^>]*)>(.*?)</script>", page, re.S | re.I):
        corps = mm.group(2).strip()
        if corps[:1] in "{[":
            try:
                marche(json.loads(corps))
            except ValueError:
                pass
    return trouves


# --------------------------------------------------------------------------- catalogues & calendrier
MOTS_OPE = ("jeudi", "vendredi", "samedi", "week", "carte", "flash", "inratable", "prix bas", "black", "foire",
            "anniversaire", "jours", "%")


def est_operation(titre, debut, fin):
    t = norm(titre)
    duree = (fin - debut).days + 1 if debut and fin else 99
    return duree <= 5 or "%" in titre or any(norm(k) in t for k in MOTS_OPE if k != "%")


def ecrire_ics(evenements, chemin, nom_cal="Mes promos", extras=()):
    """Calendrier à s'abonner sur le téléphone : un événement par catalogue / opération, avec alerte à 9 h.
    extras : événements en plus (alertes produits surveillés) : dicts uid, jour (date), resume, desc."""
    def e(t):
        return str(t).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mes promos//FR", "CALSCALE:GREGORIAN",
              "X-WR-CALNAME:" + nom_cal, "X-WR-TIMEZONE:Europe/Paris", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
              "X-PUBLISHED-TTL:PT12H"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def evt(uid, jour, resume, desc=""):
        lignes.extend(["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + stamp,
                       "DTSTART;VALUE=DATE:" + jour.strftime("%Y%m%d"),
                       "DTEND;VALUE=DATE:" + (jour + timedelta(days=1)).strftime("%Y%m%d"),
                       "SUMMARY:" + e(resume)] + (["DESCRIPTION:" + e(desc)] if desc else []) +
                      ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + e(resume),
                       "TRIGGER;RELATED=START:PT9H", "END:VALARM", "END:VEVENT"])
    for x in evenements:
        d1, d2 = date.fromisoformat(x["debut"]), date.fromisoformat(x["fin"])
        uid = slug(x["enseigne"] + " " + x["titre"] + " " + x["debut"]) + "@mes-promos"
        titre = x["titre"].title() if x["titre"].isupper() else x["titre"]
        resume = ("⚡ " if x.get("operation") else "") + "%s : %s" % (x["nom"], titre)
        if x.get("resume"):
            resume += " (" + x["resume"] + ")"
        quand = ("Le %s." % d1.strftime("%d/%m")) if d1 == d2 else ("Du %s au %s." % (d1.strftime("%d/%m"), d2.strftime("%d/%m")))
        evt(uid, d1, resume, quand + " Ouvre l'appli Mes promos pour le détail.")
        if x.get("operation") and (d2 - d1).days >= 1:
            evt("fin-" + uid, d2, "Dernier jour : " + resume)
    for x in extras:
        evt(x["uid"], x["jour"], x["resume"], x.get("desc", ""))
    lignes.append("END:VCALENDAR")
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lignes) + "\r\n")


# --------------------------------------------------------------------------- anti-crise
class Tableaux(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._t, self._r, self._c = [], None, None, None

    def handle_starttag(self, tag, a):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._r = []
        elif tag in ("td", "th") and self._r is not None:
            self._c = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._c is not None and self._r is not None:
            self._r.append(re.sub(r"\s+", " ", "".join(self._c)).strip())
            self._c = None
        elif tag == "tr" and self._r is not None and self._t is not None:
            self._t.append(self._r)
            self._r = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, d):
        if self._c is not None:
            self._c.append(d)


def dates_slug(s):
    s = norm(s.replace("-", " "))
    m = re.search(r"du (\d{1,2})(?: (\w+))? au (\d{1,2}) (\w+) (\d{4})", s)
    if not m:
        return None
    j1, m1, j2, m2, an = m.groups()
    try:
        mo2 = MOIS[m2]
        mo1 = MOIS.get(m1, mo2) if m1 else mo2
        d1 = date(int(an) - (1 if mo1 > mo2 else 0), mo1, int(j1))
        return d1, date(int(an), mo2, int(j2))
    except (KeyError, ValueError):
        return None


def trouver_anticrise(motif, secours, log, cache):
    if "pages" not in cache:
        cache["pages"] = []
        p = telecharger("https://anti-crise.fr/", log)
        if p:
            cache["pages"].append(p)
    liens = set()
    for p in cache["pages"]:
        for m in re.finditer(r"https://anti-crise\.fr/catalogue/[^\"'#?\s<>]+", p):
            liens.add(m.group(0).rstrip("/") + "/")
    aujourd = date.today()
    for mot in (motif, secours):
        if not mot:
            continue
        bons = []
        for l in liens:
            if re.search(mot, l):
                d = dates_slug(l.rsplit("/", 2)[-2])
                if d:
                    bons.append((d, l))
        en_cours = [b for b in bons if b[0][0] <= aujourd <= b[0][1]]
        if en_cours:
            b = sorted(en_cours, key=lambda b: b[0][0])[-1]
            return b[1], b[0]
        futurs = sorted([b for b in bons if b[0][1] >= aujourd], key=lambda b: b[0][0])
        if futurs:
            return futurs[0][1], futurs[0][0]
    return None, None


def extraire_anticrise(page):
    t = Tableaux()
    try:
        t.feed(page)
    except Exception:
        pass
    items = []
    for tab in t.tables:
        if not tab:
            continue
        ent = [norm(c) for c in tab[0]]
        if "produit" not in ent or "prix" not in ent:
            continue
        ix = {k: ent.index(k) for k in ("marque", "produit", "q", "prix", "promo", "prix final") if k in ent}
        for r in tab[1:]:
            try:
                produit = r[ix["produit"]]
                total = prix_float(r[ix["prix"]])
            except (IndexError, KeyError):
                continue
            if not produit or total is None:
                continue
            q = int(prix_float(r[ix["q"]]) or 1) if "q" in ix and ix["q"] < len(r) else 1
            promo = prix_float(r[ix["promo"]]) or 0.0 if "promo" in ix and ix["promo"] < len(r) else 0.0
            final = prix_float(r[ix["prix final"]]) if "prix final" in ix and ix["prix final"] < len(r) else None
            marque = r[ix["marque"]] if "marque" in ix and ix["marque"] < len(r) else ""
            prix = round(total - abs(promo), 2)
            it = {"nom": produit + (" (lot de %d)" % q if q > 1 else ""), "marque": marque, "prix": prix,
                  "avant": total if promo else None}
            if final is not None and final < prix - 0.01:
                it["bon_plan"] = "%s avec bons / remboursement" % euro(final)
            items.append(it)
    return items


# --------------------------------------------------------------------------- configuration
def charger_config():
    with open(os.path.join(ICI, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    # compatibilité avec l'ancien format ("sources": [...])
    for e in cfg.get("enseignes", []):
        for s in e.pop("sources", []) or []:
            if s.get("type") == "bonial" and "bonial" not in e:
                m = re.match(r"https://www\.bonial\.fr/([^/]+)/(.+)$", s.get("url", ""))
                if m:
                    e["bonial"] = {"ville": m.group(1), "page": m.group(2)}
            if s.get("type") == "anticrise" and "anticrise" not in e:
                e["anticrise"] = {"motif": s.get("motif"), "secours": s.get("secours")}
    return cfg


def charger_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defaut


def ecrire_json(chemin, obj, indent=None):
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=(",", ":") if indent is None else None)
    os.replace(tmp, chemin)


# --------------------------------------------------------------------------- nettoyage
def jj_mm(iso):
    return iso[8:10] + "/" + iso[5:7] if iso else ""


def nettoyer(items, ens, validite_defaut, aujourd):
    vus, sortie = {}, []
    for it in items:
        nom = re.sub(r"\s+", " ", (it.get("nom") or "")).strip(" –:")
        if len(nom) < 2:
            continue
        if it.get("fin") and it["fin"] < aujourd.isoformat():
            continue  # offre terminée
        marque = (it.get("marque") or "").strip()
        if marque.isupper() and len(marque) > 3:
            marque = marque.title()
        cle = norm(nom) + "|" + norm(marque)
        if cle in vus:  # garder la version la plus complète
            a = vus[cle]
            for k in ("avant", "prix", "unite", "detail", "debut", "fin"):
                if not a.get(k) and it.get(k):
                    a[k] = it[k]
            continue
        p, av = it.get("prix"), it.get("avant")
        rem = it.get("remise_effective")
        if rem is None and p and av and av > p:
            rem = round((1 - p / av) * 100)
        validite = ("du %s au %s" % (jj_mm(it["debut"]), jj_mm(it["fin"]))) if it.get("debut") and it.get("fin") else validite_defaut
        e = {
            "id": "%s-%s%s" % (ens["id"], slug(nom)[:55], ("-" + slug(marque)[:18]) if marque else ""),
            "enseigne": ens["id"], "nom": nom, "marque": marque, "prix": p, "avant": av, "remise": rem,
            "unite": it.get("unite") or "", "detail": it.get("detail") or "", "bon_plan": it.get("bon_plan") or "",
            "rayon": rayon(nom, marque, it.get("categories", "")), "validite": validite,
            "debut": it.get("debut") or "", "fin": it.get("fin") or "",
        }
        if it.get("condition"):
            e["condition"] = it["condition"]
            e["remise_2e"] = it.get("remise_affichee")
        vus[cle] = e
        sortie.append(e)
    return sortie


# --------------------------------------------------------------------------- enseignes suivies
# nom de page bonial -> (id, nom affiché, famille)
FAMILLES = [
    (r"Super-U", "superu", "Super U", "u"),
    (r"Hyper-U", "hyperu", "Hyper U", "u"),
    (r"U-Express", "uexpress", "U Express", "u"),
    (r"Marche-U", "marcheu", "Marché U", "u"),
    (r"E-Leclerc", "leclerc", "E.Leclerc", "leclerc"),
    (r"Intermarche(-(?:Super|Hyper|Contact|Express))?", "intermarche", "Intermarché", "intermarche"),
    (r"Lidl", "lidl", "Lidl", "lidl"),
    (r"Carrefour(-(?:Market|City|Contact|Express|Proximite))?", "carrefour", "Carrefour", "carrefour"),
]


def chaine_de(nom_page):
    for motif, ident, nom, fam in FAMILLES:
        m = re.fullmatch(motif, nom_page or "")
        if m:
            suffixe = (m.group(1) or "").strip("-") if m.groups() else ""
            if suffixe:
                jolis = {"Proximite": "Proximité"}
                return {"id": ident + suffixe.lower(), "nom": nom + " " + jolis.get(suffixe, suffixe), "famille": fam}
            return {"id": ident, "nom": nom, "famille": fam}
    return None


def distance_km(a, b):
    try:
        from math import radians, sin, cos, asin, sqrt
        la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
        h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
        return 6371 * 2 * asin(sqrt(h))
    except Exception:
        return 9999


# --------------------------------------------------------------------------- exploration de la Vendée
def explorer(cfg, log, debug=False):
    """Parcourt les pages bonial « enseigne dans une ville » de proche en proche :
    chaque page donne ses promos, ses catalogues, les magasins de l'enseigne aux alentours
    (adresse, code postal, horaires) et les autres enseignes de la ville."""
    from collections import deque
    dept = str(cfg.get("departement", "85"))
    maxi = int(cfg.get("max_pages", 400))
    pause = float(cfg.get("pause", 0.7))
    file = deque(cfg.get("graines", []))
    vus, zones, magasins, catalogues, offres = set(), {}, {}, {}, []
    n, arret = 0, False
    while file and n < maxi:
        chemin = file.popleft()
        if chemin in vus:
            continue
        vus.add(chemin)
        try:
            ville, nom_page, pid = chemin.split("/")
        except ValueError:
            continue
        ch = chaine_de(nom_page)
        if not ch:
            continue
        page = telecharger("https://www.bonial.fr/" + chemin, log)
        n += 1
        time.sleep(pause)
        if not page:
            if DERNIER["code"] in (403, 429):
                log("   ! le site freine (%s) : arrêt de l'exploration, les données manquantes seront reprises de la veille" % DERNIER["code"])
                arret = True
                break
            continue
        pi = infos_page(page)
        cite = pi.get("city") or {}
        cp = str(cite.get("primaryZipCode") or "")
        if not cp.startswith(dept):
            continue  # hors Vendée
        if debug:
            with open(os.path.join(DATA, "debug", chemin.replace("/", "_") + ".html"), "w", encoding="utf-8") as f:
                f.write(page)
        its, brochures, _ = page_bonial(page, pi)
        cle = ville + "|" + ch["id"]
        zones[cle] = {"ville": cite.get("displayName") or cite.get("name") or ville, "slug": ville, "chaine": ch["id"],
                      "page": chemin, "cp": cp, "lat": cite.get("lat"), "lng": cite.get("lng"),
                      "catalogues": sorted({b["id"] for b in brochures})}
        for b in brochures:
            catalogues[b["id"]] = dict(b, chaine=ch["id"])
        for it in its:
            it["chaine"] = ch["id"]
            offres.append(it)
        cont = (pi.get("template") or {}).get("content") or {}
        # magasins de l'enseigne aux alentours
        for l in ((cont.get("StoreLogoLinkbox") or {}).get("links") or []):
            m = re.match(r"https://www\.bonial\.fr/Magasins/([^/]+)/[^/]+/v-f(\d+)", l.get("link_href") or "")
            lt = l.get("link_text") or {}
            mc = re.match(r"(\d{5})\s+(.+)", (lt.get("city") or "").strip())
            if not m or not mc or not mc.group(1).startswith(dept):
                continue
            chm = chaine_de(l.get("publisherUrl") or nom_page)
            if not chm or chm["id"] != ch["id"]:
                continue
            sid = ch["id"] + "-" + m.group(2)
            horaires = [[h.get("dayOfWeek"), h.get("minutesFrom"), h.get("minutesTo")]
                        for h in ((l.get("openingHours") or {}).get("regularOpeningHours") or []) if h.get("dayOfWeek")]
            magasins[sid] = {"id": sid, "chaine": ch["id"], "nom": ch["nom"], "adresse": (lt.get("address") or "").strip(),
                             "cp": mc.group(1), "ville": mc.group(2).strip(), "slug_ville": m.group(1),
                             "horaires": horaires, "zone_ref": cle, "fiche": l.get("link_href")}
            file.append("%s/%s/%s" % (m.group(1), nom_page, pid))
        # autres enseignes de la même ville
        for l in ((cont.get("PublisherLogoLinkbox") or {}).get("links") or []):
            m = re.match(r"https://www\.bonial\.fr/([^/]+)/([^/]+)/(p-r\d+)$", l.get("link_href") or "")
            if m and chaine_de(m.group(2)):
                file.append("%s/%s/%s" % m.groups())
    log("Exploration : %d pages lues, %d villes/enseignes, %d magasins, %d catalogues" % (n, len(zones), len(magasins), len(catalogues)))
    return zones, magasins, catalogues, offres, arret


def construire_offres(brutes, aujourd):
    """Offres dédoublonnées par enseigne + catalogue."""
    vus, sortie = {}, []
    for it in brutes:
        nom = re.sub(r"\s+", " ", (it.get("nom") or "")).strip(" –:")
        if len(nom) < 2 or (it.get("fin") and it["fin"] < aujourd.isoformat()):
            continue
        marque = (it.get("marque") or "").strip()
        if marque.isupper() and len(marque) > 3:
            marque = marque.title()
        cat = it.get("catalogue") or "*"
        cle = "%s|%s|%s|%s" % (it["chaine"], cat, norm(nom), norm(marque))
        if cle in vus:
            a = vus[cle]
            for k in ("avant", "prix", "unite", "detail", "debut", "fin"):
                if not a.get(k) and it.get(k):
                    a[k] = it[k]
            continue
        p, av = it.get("prix"), it.get("avant")
        rem = it.get("remise_effective")
        if rem is None and p and av and av > p:
            rem = round((1 - p / av) * 100)
        if rem is None and p is None and it.get("remise_label"):
            rem = it["remise_label"]
        e = {"k": "%s-%s%s" % (it["chaine"], slug(nom)[:55], ("-" + slug(marque)[:18]) if marque else ""),
             "chaine": it["chaine"], "cat": cat, "nom": nom, "marque": marque, "prix": p, "avant": av, "remise": rem,
             "unite": it.get("unite") or "", "detail": it.get("detail") or "", "bon_plan": it.get("bon_plan") or "",
             "rayon": it.get("rayon") or rayon(nom, marque, it.get("categories", ""), it.get("haut", ""), it.get("texte", ""), it.get("unite", "")),
             "debut": it.get("debut") or "", "fin": it.get("fin") or ""}
        if it.get("condition"):
            e["condition"], e["remise_2e"] = it["condition"], it.get("remise_affichee")
        for x in ("carte", "des", "image", "op", "img", "en_ligne"):
            if it.get(x):
                e[x] = it[x]
        if isinstance(it.get("page"), int) and cat != "*":
            e["pg"] = it["page"]  # page du catalogue (0 = couverture) : lien « voir dans le catalogue »
        vus[cle] = e
        sortie.append(e)
    return sortie


def lire_catalogues(cats, zones, ancien, brutes, cfg, log):
    """Chaque catalogue en entier (visionneuse bonial) ; si elle ne répond pas, les offres complètes de la veille."""
    dom = cfg.get("domicile") or {}
    pause = float(cfg.get("pause", 0.6))
    anciens = (ancien.get("catalogues") or {}) if ancien.get("v") == 2 else {}
    vieilles = etendre(ancien.get("offres") or [], anciens) if ancien.get("v") == 2 else []
    ocr = ocr_dispo()
    cache = charger_json(os.path.join(DATA, "ocr.json"), {}) if ocr else {}
    if not ocr:
        log("   (lecture des images d'opérations : Tesseract absent, les images sont gardées sans texte)")
    par_cat = {}
    for b in brutes:
        par_cat.setdefault(b.get("catalogue") or "*", []).append(b)
    vus_images = {}
    n_ok, n_total = 0, 0
    for cid, c in sorted(cats.items()):
        z = next((z for z in zones.values() if cid in z.get("catalogues", [])), {})
        pos = (z.get("lat") or dom.get("lat") or 46.67, z.get("lng") or dom.get("lng") or -1.43)
        res = catalogue_complet(cid, c.get("type", ""), pos, log, pause)
        if res is None:
            if (anciens.get(cid) or {}).get("complet"):
                par_cat[cid] = [dict(o, catalogue=cid, remise_effective=o.get("remise") if o.get("condition") else None,
                                     remise_affichee=o.get("remise_2e")) for o in vieilles if o["cat"] == cid]
                for k in ("complet", "images", "resume"):
                    if anciens[cid].get(k):
                        c[k] = anciens[cid][k]
                if anciens[cid].get("op_debut"):
                    c["debut"], c["fin"] = anciens[cid]["op_debut"], anciens[cid]["op_fin"]
            continue
        offres, images = res
        for it in offres:
            it["chaine"], it["catalogue"] = c["chaine"], cid
        if offres:
            par_cat[cid] = offres
        c["complet"] = True
        n_ok += 1
        n_total += len(offres)
        if images:
            c["images"] = images
            for u in images:
                vus_images.setdefault(u.rsplit("/", 1)[-1], set()).add(norm(c["titre"]))
    log("Catalogues lus en entier : %d/%d (%d offres)" % (n_ok, len(cats), n_total))

    # images : on retire les visuels communs à plusieurs catalogues (logos, « ne ratez pas… »)
    garde = {}
    for cid, c in cats.items():
        imgs = [u for u in c.get("images", []) if len(vus_images.get(u.rsplit("/", 1)[-1], ())) < 2]
        ops = []
        for u in imgs:
            if not ocr:
                garde.setdefault(cid, []).append(u)
                continue
            if u not in cache:
                data = telecharger(u, log, binaire=True)
                try:
                    cache[u] = dict(ocr_image(data), vu=date.today().isoformat()) if data else {"t": "", "n": None}
                except Exception as e:
                    log("   ! lecture d'image impossible : %s" % e)
                    cache[u] = {"t": "", "n": None}
            lu = cache[u]
            lu["vu"] = date.today().isoformat()
            t = lu.get("t", "")
            lettres = sum(ch.isalpha() for ch in t)
            if lettres < 25 or "ne ratez pas" in norm(t) or (lettres < 120 and not re.search(r"\d", t)):
                continue  # logo, visuel décoratif
            garde.setdefault(cid, []).append(u)
            info = {"id": cid, "debut": date.fromisoformat(c["debut"]), "fin": date.fromisoformat(c["fin"])}
            op = operation_depuis_texte(lu, info, u, chaine_de_id(c["chaine"]))
            if op:
                op["chaine"] = c["chaine"]
                ops.append(op)
        if ops:
            par_cat[cid] = [o for o in par_cat.get(cid, []) if not o.get("op")] + ops
            # le vrai jour de l'opération (ex. le jeudi seulement) pour l'agenda et les rappels
            d1, d2 = min(o["debut"] for o in ops), max(o["fin"] for o in ops)
            if c.get("type") == "DYNAMIC" and (d1, d2) != (c["debut"], c["fin"]):
                c["debut"], c["fin"], c["op_debut"], c["op_fin"] = d1, d2, d1, d2
            c["resume"] = " · ".join(dict.fromkeys("%s — %s" % (o["nom"], o["bon_plan"]) for o in ops))[:200]
            c["operation"] = True
    for cid, c in cats.items():
        if garde.get(cid):
            c["images"] = garde[cid][:6]
        else:
            c.pop("images", None)
    if ocr:
        limite = (date.today() - timedelta(days=60)).isoformat()
        ecrire_json(os.path.join(DATA, "ocr.json"), {u: v for u, v in cache.items() if v.get("vu", "9") >= limite})
    return [o for l in par_cat.values() for o in l]


def charger_donnees(chemin=None):
    """promos.json avec toutes ses offres (y compris celles rangées par catalogue dans offres/)."""
    chemin = chemin or FICHIER
    d = charger_json(chemin, {})
    if d.get("fichiers"):
        dossier = os.path.join(os.path.dirname(chemin), d["fichiers"])
        offres = list(d.get("offres") or [])
        for cid, c in (d.get("catalogues") or {}).items():
            if c.get("n"):
                offres += charger_json(os.path.join(dossier, cid + ".json"), [])
        d["offres"] = offres
    return d


CHAMPS_VIDES = {"marque": "", "prix": None, "avant": None, "remise": None, "unite": "", "detail": "", "bon_plan": ""}


def compacter(offres, cats):
    """Allège promos.json : pas de champs vides, ni des dates/enseigne quand ce sont celles du catalogue."""
    sortie = []
    for o in offres:
        c = cats.get(o["cat"]) or {}
        e = {}
        for k, v in o.items():
            if k == "histo" or (k in CHAMPS_VIDES and v == CHAMPS_VIDES[k]):
                continue
            if k == "chaine" and c.get("chaine") == v:
                continue
            if k in ("debut", "fin") and (c.get("op_" + k) or c.get(k)) == v:
                continue
            e[k] = v
        if o.get("histo"):
            h = o["histo"]
            e["h"] = [h["min"], h["min_date"], h["fois"]]
        sortie.append(e)
    return sortie


def etendre(offres, cats):
    """Inverse de compacter() (accepte aussi l'ancien format)."""
    sortie = []
    for o in offres:
        c = cats.get(o.get("cat")) or {}
        e = dict(CHAMPS_VIDES)
        e.update(o)
        e.setdefault("chaine", c.get("chaine", ""))
        e.setdefault("debut", c.get("debut", ""))
        e.setdefault("fin", c.get("fin", ""))
        if "h" in e:
            h = e.pop("h")
            e["histo"] = {"min": h[0], "min_date": h[1], "fois": h[2]}
        sortie.append(e)
    return sortie


def vue_magasins(donnees, ids):
    """Ce que voit l'appli pour une sélection de magasins : promos, enseignes, agenda.
    (même logique que dans la page, utilisée ici pour le calendrier et les alertes)"""
    mags = {m["id"]: m for m in donnees.get("magasins", [])}
    zones, cats = donnees.get("zones", {}), donnees.get("catalogues", {})
    toutes = etendre(donnees.get("offres", []), cats)
    aujourd = date.today().isoformat()
    enseignes, promos, evts = {}, [], []
    for sid in ids:
        m = mags.get(sid)
        if not m:
            continue
        z = zones.get(m.get("zone") or "", {})
        ok = set(z.get("catalogues", []))
        nom = "%s %s" % (m["nom"], m["ville"])
        mes, vus = [], {}
        for o in toutes:
            if o["chaine"] != m["chaine"] or not (o["cat"] == "*" or o["cat"] in ok):
                continue
            if o["k"] in vus:  # même produit dans deux catalogues : on garde le meilleur prix
                a = vus[o["k"]]
                if (o.get("prix") or 9e9) < (a.get("prix") or 9e9):
                    a.update(o)
                continue
            vus[o["k"]] = dict(o)
            mes.append(vus[o["k"]])
        for o in mes:
            q = dict(o, id=sid + "|" + o["k"], enseigne=sid,
                     validite=("du %s au %s" % (jj_mm(o["debut"]), jj_mm(o["fin"]))) if o.get("debut") and o.get("fin") else "")
            promos.append(q)
        enseignes[sid] = {"nom": nom, "chaine": m["chaine"], "nb": len(mes)}
        for c in ok:
            x = cats.get(c)
            if x and x.get("fin", "") >= aujourd:
                evts.append({"enseigne": sid, "nom": nom, "titre": x["titre"], "pages": x.get("pages"),
                             "debut": x["debut"], "fin": x["fin"], "operation": x.get("operation"),
                             "resume": x.get("resume", ""), "images": x.get("images", [])})
    evts.sort(key=lambda e: (e["debut"], e["nom"]))
    return enseignes, promos, evts


# --------------------------------------------------------------------------- notes produits (Open Food Facts)
# Nutri-Score, groupe NOVA et Green-Score des produits alimentaires de marque, d'après Open Food Facts, la base
# libre dont se sert Yuka pour l'alimentaire. Les offres n'ont pas de code-barres : on cherche « nom » chez la
# marque et on ne garde le produit trouvé que si son nom colle (au moins 60 % des mots). Mémoire : notes.json.
NOTES = os.path.join(DATA, "notes.json")
OFF_URL = "https://search.openfoodfacts.org/search"
OFF_UA = "MesPromos/1.0 (https://github.com/ansquerdylan-arch/mes-promos)"
RAYONS_NOTES = {"Poisson & mer", "Volaille", "Charcuterie", "Viande", "Fromage", "Crèmerie & œufs", "Fruits & légumes",
                "Traiteur", "Surgelés", "Boulangerie", "Épicerie sucrée", "Épicerie salée", "Boissons"}
RE_ALCOOL = re.compile(r"\b(vins?|champagnes?|cremant|whiske?y|rhums?|vodka|gin|bieres?|cidres?|liqueurs?|porto|cognac|armagnac|"
                       r"pastis|calvados|aoc|aop|igp|cuvee|chateau|domaine|beaujolais|bordeaux|bourgogne|muscadet|sauvignon|"
                       r"chardonnay|merlot|pinot|cabernet|riesling|malbec|syrah|grenache|prosecco|cava|spritz|tequila|sake|"
                       r"brut|aperitif|mousseux|sangria|punch|planteur|arrange|kir|pineau|muscat|ricard|martini|vermouth|baileys|"
                       r"suze|picon|lillet|jagermeister|malibu|amaretto|limoncello|ouzo|absinthe|get 27|bianco|rosso|"
                       r"hydromel|poire williams|eau de vie|marc|grappa|sake|soju|hard seltzer)\b|\d\s*°|\d\s*% ?vol")
# mots qui changent la nature d'un produit : « oignon » n'est pas « oignons au vinaigre », ni un poulet cru un poulet rôti
TRANSFO = set("vinaigre sauce soupe veloute puree compote jus chips sirop confiture pickles roti rotie roties rotis "
              "poele poelee frit frite frites pane panee panes "
              "beignet beignets biscuit biscuits gateau gateaux tarte pizza glace glacee rape rapee rapees".split())
MOTS_VIDES = set("les des aux avec sans pour une par sur dans format familial maxi offre speciale lot pack edition "
                 "gamme toute tous toutes nouveau nouvelle recette".split())
# aliments « clés » : si le produit trouvé en a un que le nôtre n'a pas (homard / foie gras, poulet / jambon), ce n'est pas le même
CLES = set("poulet dinde canard porc boeuf veau agneau lapin jambon saucisse saucisson lardon chorizo foie saumon thon cabillaud "
           "colin lieu truite homard crevette moule hareng sardine maquereau surimi chevre brebis vache emmental comte "
           "camembert roquefort raclette mozzarella fraise framboise orange citron pomme poire peche abricot cerise banane "
           "mangue ananas coco noisette amande pistache cacahuete mais tomate oignon carotte champignon olive "
           "chocolat vanille caramel miel menthe cassis".split())
# noms trop vagues (« Soda », « Café moulu ») : il faut alors que la marque figure dans le nom du produit trouvé
VAGUES = set("soda sodas jus sirop cafe moulu grain grains capsule capsules dosette dosettes the infusion eau eaux minerale "
             "naturelle gazeuse petillante source boisson energisante fromage fromages chocolat chocolats biscuit biscuits "
             "gateau gateaux bonbon bonbons confiserie yaourt yaourts dessert desserts glace glaces pate pates riz huile "
             "sauce soupe nectar smoothie mini original classique regular nature assortiment coffret cola limonade "
             "multifruits fruit fruits pur bio standard maxi giga special".split())
NOTES_LIMITE = 900  # recherches au plus par mise à jour (les autres attendent le lendemain)


def _off_mots(nom, marque):
    t = re.sub(r"\([^)]*\)|[«»\"“”]", " ", nom or "")
    t = re.sub(r"(?i)\b\d+(?:[.,]\d+)?\s*(?:g|kg|cl|ml|l|x|cm|mm|%)\b|\bx\s*\d+\b|\b\d+\s*x\b|\blot de \d+\b", " ", t)
    m = set(norm(marque).split())
    vus, mots = set(), []
    for w in norm(t).split():
        if len(w) > 2 and w not in MOTS_VIDES and w not in m and not w.isdigit() and w not in vus:
            vus.add(w)
            mots.append(w)
    return mots


def _racine(w):
    return w[:-1] if len(w) > 3 and w[-1] in "sx" else w


def _note_valeur(v, permis):
    v = str(v or "").lower()
    return v if v in permis else None


def _off_chercher(mots, nom, marque, log):
    gardes = []
    for w in re.split(r"[^\w]+", (nom or "").lower()):
        if w and norm(w) in mots and w not in gardes:
            gardes.append(w)
    q = " ".join(gardes[:8]) or " ".join(mots[:8])
    q += ' brands:"%s"' % marque.replace('"', " ").strip()
    url = OFF_URL + "?" + urllib.parse.urlencode({
        "q": q, "langs": "fr", "page_size": 8,
        "fields": "code,product_name,product_name_fr,generic_name_fr,brands,nutriscore_grade,nova_group,ecoscore_grade,unique_scans_n,quantity"})
    req = urllib.request.Request(url, headers={"User-Agent": OFF_UA, "Accept": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        brut = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            brut = gzip.decompress(brut)
    return json.loads(brut.decode("utf-8")).get("hits") or []


def _off_compatible(nos, nom_h, nm, b0=None):
    """Le produit trouvé est-il bien le nôtre ? Pas transformé autrement (oignon / oignons au vinaigre), pas un autre
    aliment (homard / foie gras), au moins un mot du nom en commun, et pour un nom vague (« Nectar multifruits »)
    la même marque principale. Un nom d'un seul mot vague (« Soda », « Jus ») désigne toute une gamme : pas de note."""
    eux = {_racine(w) for w in norm(nom_h).split()}
    if (TRANSFO & eux) - nos - {_racine(w) for w in TRANSFO if w in nos}:
        return False
    if not nos & eux:
        return False
    cles = {_racine(w) for w in CLES}
    if (eux & cles) - nos and nos & cles:
        return False
    if nos <= {_racine(w) for w in VAGUES}:
        if len(nos) == 1:
            return False
        if b0 is not None and nm and b0 != nm:
            return False
    return True


def _off_meilleur(hits, mots, marque):
    nm = norm(marque)
    nos = {_racine(w) for w in mots}
    best, cle_best = None, None
    for h in hits:
        b = h.get("brands") or []
        b = norm(" ".join(b) if isinstance(b, list) else b)
        if nm and nm not in b and not all(w in b.split() for w in nm.split()):
            continue
        nom_h = h.get("product_name_fr") or h.get("product_name") or ""
        leurs = {_racine(w) for w in norm(nom_h + " " + (h.get("generic_name_fr") or "")).split()}
        commun = len(nos & leurs) / max(1, len(nos))
        premiere = h.get("brands") or []
        premiere = norm(premiere[0] if isinstance(premiere, list) and premiere else str(premiere).split(",")[0])
        if commun < 0.6 or not _off_compatible(nos, nom_h, nm, premiere):
            continue
        ns = _note_valeur(h.get("nutriscore_grade"), ("a", "b", "c", "d", "e"))
        nv = h.get("nova_group") if h.get("nova_group") in (1, 2, 3, 4) else None
        if not ns and not nv:
            continue
        cle = (round(commun, 2), 1 if ns else 0, h.get("unique_scans_n") or 0)
        if cle_best is None or cle > cle_best:
            best, cle_best = h, cle
    if not best:
        return None
    gs = str(best.get("ecoscore_grade") or "").lower()
    gs = "A+" if gs == "a-plus" else (gs.upper() if gs in ("a", "b", "c", "d", "e", "f") else None)
    e = {"c": str(best.get("code") or ""), "n": (best.get("product_name_fr") or best.get("product_name") or "").strip()[:70]}
    ns = _note_valeur(best.get("nutriscore_grade"), ("a", "b", "c", "d", "e"))
    if ns:
        e["ns"] = ns.upper()
    if best.get("nova_group") in (1, 2, 3, 4):
        e["nv"] = best["nova_group"]
    if gs:
        e["gs"] = gs
    return e


def noter_offres(offres, log, aujourd=None):
    """Ajoute aux offres alimentaires de marque : ns (Nutri-Score), nv (NOVA), gs (Green-Score), off (code), offn (produit)."""
    jour = (aujourd or date.today()).isoformat()
    cache = charger_json(NOTES, {})
    a_faire, par_cle = {}, {}
    for o in offres:
        if o.get("rayon") not in RAYONS_NOTES:
            continue
        marque, nom = (o.get("marque") or "").strip(), (o.get("nom") or "").strip()
        if not marque or not nom or norm(nom) == norm(marque):
            continue
        if re.match(r"(?i)\s*(sur\s+)?(toute la gamme|toutes? les|tous les|tout le|toute la)\b", nom):
            continue
        if o.get("rayon") == "Boissons" and RE_ALCOOL.search(norm(nom + " " + (o.get("detail") or "")) + " " + nom):
            continue  # pas de Nutri-Score pour l'alcool
        mots = _off_mots(nom, marque)
        if not mots:
            continue
        cle = norm(marque) + "|" + " ".join(mots)
        par_cle.setdefault(cle, []).append(o)
        e = cache.get(cle)
        age = (date.fromisoformat(jour) - date.fromisoformat(e["t"])).days if e and e.get("t") else 999
        if (not e or age > (45 if e.get("ns") or e.get("nv") else 14)) and cle not in a_faire:
            a_faire[cle] = (mots, nom, marque)
    faits, trouves, erreurs = 0, 0, 0
    for cle, (mots, nom, marque) in a_faire.items():
        if faits >= NOTES_LIMITE or erreurs >= 6:
            break
        try:
            r = _off_meilleur(_off_chercher(mots, nom, marque, log), mots, marque)
            erreurs = 0
        except Exception as ex:
            erreurs += 1
            if erreurs == 1:
                log("   ! Open Food Facts : %s" % ex)
            time.sleep(2)
            continue
        faits += 1
        cache[cle] = dict(r or {}, t=jour)
        trouves += 1 if r else 0
        time.sleep(0.3)
    notes = 0
    for cle, lst in par_cle.items():
        e = cache.get(cle) or {}
        if not (e.get("ns") or e.get("nv")):
            continue
        for o in lst:
            for k_src, k_dst in (("ns", "ns"), ("nv", "nv"), ("gs", "gs"), ("c", "off"), ("n", "offn")):
                if e.get(k_src):
                    o[k_dst] = e[k_src]
            notes += 1
    limite = (date.fromisoformat(jour) - timedelta(days=120)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("t", "") >= limite}
    ecrire_json(NOTES, cache)
    log("Notes produits : %d offres notées (%d recherches Open Food Facts aujourd'hui, %d trouvées, %d en attente)" % (
        notes, faits, trouves, max(0, len(a_faire) - faits)))


# --------------------------------------------------------------------------- historique des prix
# --------------------------------------------------------------------------- historique des prix
def mettre_historique(promos, aujourd):
    h = charger_json(HISTORIQUE, {})
    jour = aujourd.isoformat()
    limite = (aujourd - timedelta(days=400)).isoformat()
    for p in promos:
        if p.get("prix") is None:
            continue
        cle = p.get("chaine", p.get("enseigne")) + "|" + norm(p["nom"]) + "|" + norm(p.get("marque"))
        lst = [x for x in h.get(cle, []) if x[0] >= limite]
        # infos pour l'appli : prix vus avant cette semaine
        avant = [x for x in lst if x[0] < (aujourd - timedelta(days=6)).isoformat()]
        if avant:
            mini = min(avant, key=lambda x: x[1])
            p["histo"] = {"min": mini[1], "min_date": mini[0], "fois": len({x[0][:7] for x in avant}) + 1}
        if not lst or lst[-1][1] != p["prix"] or lst[-1][0] < (aujourd - timedelta(days=6)).isoformat():
            if not (lst and lst[-1][0] == jour):
                lst.append([jour, p["prix"]])
        h[cle] = lst[-40:]
    h = {k: v for k, v in h.items() if v and v[-1][0] >= limite}
    ecrire_json(HISTORIQUE, h)


# --------------------------------------------------------------------------- mise à jour
def mettre_a_jour(debug=False, log=print, essai=False):
    os.makedirs(DATA, exist_ok=True)
    if debug:
        os.makedirs(os.path.join(DATA, "debug"), exist_ok=True)
    cfg = charger_config()
    ancien = charger_donnees(FICHIER)
    aujourd = date.today()
    jour = aujourd.isoformat()

    zones, magasins, catalogues, brutes, arret = explorer(cfg, log, debug)

    # promos nationales d'anti-crise : valables dans tous les magasins de l'enseigne
    cache = {}
    for ident, a in (cfg.get("anticrise") or {}).items():
        url, dates = trouver_anticrise(a.get("motif"), a.get("secours"), log, cache)
        if not url:
            continue
        page = telecharger(url, log)
        its = extraire_anticrise(page) if page else []
        for it in its:
            it["chaine"] = ident
            it["catalogue"] = "*"
            if dates:
                it["debut"], it["fin"] = dates[0].isoformat(), dates[1].isoformat()
        brutes += its
        log("   anti-crise %s : %d produits" % (ident, len(its)))
        time.sleep(0.7)

    # si l'exploration a été coupée : on garde ce qu'on avait la veille pour les villes non relues
    if ancien.get("v") == 2:
        for k, z in (ancien.get("zones") or {}).items():
            if k not in zones:
                zones[k] = z
        for k, mg in {m["id"]: m for m in ancien.get("magasins", [])}.items():
            magasins.setdefault(k, mg)
        for k, c in (ancien.get("catalogues") or {}).items():
            if c.get("fin", "") >= jour:
                catalogues.setdefault(k, c)
        lus = {(o["chaine"], o.get("catalogue")) for o in brutes}
        for o in etendre(ancien.get("offres", []), ancien.get("catalogues") or {}):
            if (o["chaine"], o["cat"]) not in lus and o["cat"] in catalogues and (not o.get("fin") or o["fin"] >= jour):
                brutes.append(dict(o, catalogue=o["cat"]))

    # magasins -> zone (page de leur ville, sinon celle où on les a trouvés), position
    for m in magasins.values():
        z = m["slug_ville"] + "|" + m["chaine"]
        m["zone"] = z if z in zones else m.get("zone_ref")
        zz = zones.get(m["zone"]) or {}
        zv = next((x for k, x in zones.items() if k.startswith(m["slug_ville"] + "|")), None) or zz
        m["lat"], m["lng"] = zv.get("lat"), zv.get("lng")
    magasins = {k: m for k, m in magasins.items() if m.get("zone") in zones}

    # catalogues : dates françaises, opérations courtes repérées
    cats = {}
    for k, c in catalogues.items():
        d1, d2 = c.get("debut"), c.get("fin")
        if isinstance(d1, date):
            d1, d2 = d1.isoformat(), d2.isoformat()
        if not d1 or not d2 or d2 < jour:
            continue
        if (date.fromisoformat(d2) - date.fromisoformat(d1)).days > 120:
            continue
        cats[k] = {"chaine": c["chaine"], "titre": c["titre"], "debut": d1, "fin": d2, "pages": c.get("pages"),
                   "operation": est_operation(c["titre"], date.fromisoformat(d1), date.fromisoformat(d2)),
                   "type": c.get("type") or ""}
    for z in zones.values():
        z["catalogues"] = [c for c in z["catalogues"] if c in cats]

    brutes = lire_catalogues(cats, zones, ancien, brutes, cfg, log)

    offres = construire_offres(brutes, aujourd)
    offres = [o for o in offres if o["cat"] == "*" or o["cat"] in cats]
    try:
        noter_offres(offres, log, aujourd)
    except Exception as e:
        log("Notes produits non mises à jour : %s" % e)

    # magasins proposés par défaut : le plus proche de chez toi pour chaque enseigne de config
    dom = cfg.get("domicile") or {}
    pos = (dom.get("lat"), dom.get("lng"))
    defaut = []
    for ident in cfg.get("enseignes_defaut", []):
        cand = [m for m in magasins.values() if m["chaine"] == ident or (ident.endswith("*") and m["chaine"].startswith(ident[:-1]))]
        cand = [m for m in cand if m.get("lat")]
        if cand and pos[0]:
            defaut.append(min(cand, key=lambda m: distance_km(pos, (m["lat"], m["lng"])))["id"])

    chaines = {}
    for m in magasins.values():
        ch = chaine_de_id(m["chaine"])
        chaines[m["chaine"]] = {"nom": m["nom"], "famille": ch}
    resultat = {"v": 2, "maj": datetime.now().isoformat(timespec="seconds"), "ville": dom.get("ville", ""),
                "departement": str(cfg.get("departement", "85")), "domicile": dom, "chaines": chaines,
                "zones": zones, "magasins": sorted(magasins.values(), key=lambda m: (m["ville"], m["nom"])),
                "catalogues": cats, "offres": offres, "defaut": defaut}

    if not offres:
        log("Aucune promo trouvée (connexion internet ? site changé ?). Les promos actuelles sont gardées.")
        return ancien
    try:
        mettre_historique(offres, aujourd)
    except Exception as e:
        log("Historique non mis à jour : %s" % e)
    # vue « magasins par défaut » (calendrier de base)
    ens, promos, evts = vue_magasins(resultat, defaut)
    resultat["enseignes"], resultat["evenements"] = ens, evts
    if essai:
        log("ESSAI : rien n'est enregistré.")
        return resultat
    try:
        ecrire_ics(evts, os.path.join(DATA, "rappels.ics"))
    except Exception as e:
        log("Calendrier non écrit : %s" % e)
    # les offres vont dans un fichier par catalogue (offres/<id>.json) : l'appli ne charge que
    # ceux des magasins choisis ; promos.json garde les magasins, catalogues et offres nationales
    par = {}
    for o in compacter(offres, cats):
        par.setdefault(o["cat"], []).append(o)
    resultat["offres"] = par.pop("*", [])
    resultat["fichiers"] = "offres"
    dossier = os.path.join(DATA, "offres")
    os.makedirs(dossier, exist_ok=True)
    total = 0
    for cid, c in cats.items():
        c["n"] = len(par.get(cid, []))
        if c["n"]:
            ecrire_json(os.path.join(dossier, cid + ".json"), par[cid])
            total += os.path.getsize(os.path.join(dossier, cid + ".json"))
    for f in os.listdir(dossier):  # catalogues terminés
        if f.endswith(".json") and not cats.get(f[:-5], {}).get("n"):
            os.remove(os.path.join(dossier, f))
    ecrire_json(FICHIER, resultat)
    log("Terminé : %d magasins, %d catalogues, %d offres (promos.json %d Ko + offres %d Ko)" % (
        len(magasins), len(cats), len(offres), os.path.getsize(FICHIER) // 1024, total // 1024))
    return resultat


def chaine_de_id(ident):
    for motif, i, nom, fam in FAMILLES:
        if ident.startswith(i):
            return fam
    return ident


if __name__ == "__main__":
    r = mettre_a_jour(debug="--debug" in sys.argv, essai="--essai" in sys.argv)
    if "--essai" in sys.argv and r:
        from collections import Counter
        print("Magasins par enseigne :", dict(Counter(m["chaine"] for m in r.get("magasins", []))))
        print("Offres par enseigne :", dict(Counter(o["chaine"] for o in r.get("offres", []))))
        print("Villes :", sorted({m["ville"] for m in r.get("magasins", [])}))
        print("Par défaut :", [(m["nom"], m["ville"]) for m in r.get("magasins", []) if m["id"] in r.get("defaut", [])])
        print("Exemple magasin :", json.dumps(r.get("magasins", [{}])[0], ensure_ascii=False)[:400])
        print("Slugs de villes :", sorted({z["slug"] for z in r.get("zones", {}).values()}))
        print("Catalogues par zone (moyenne) :", round(sum(len(z["catalogues"]) for z in r.get("zones", {}).values()) / max(1, len(r.get("zones", {}))), 1))
