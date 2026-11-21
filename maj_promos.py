# -*- coding: utf-8 -*-
"""
Mise à jour des promos — sans Claude, sans clé, sans compte.

  1. parcourt les pages bonial.fr des enseignes de Vendée (magasins, horaires, catalogues en cours) ;
  2. lit CHAQUE catalogue en entier dans la visionneuse publique de bonial (toutes les offres
     repérées page par page : titre, marque, prix, ancien prix, « le 2e à… », carte de fidélité,
     dates exactes) ;
  3. pour les opérations publiées en images (Jeudis Plus U, etc.), garde les images et, si le
     logiciel Tesseract est installé, lit le texte (34 % sur les chocolats de Noël, jour exact…) ;
  4. complète avec les tableaux d'anti-crise.fr ;
  5. E.Leclerc : bonial n'a pas les produits de ses catalogues, on les lit sur le catalogue en ligne
     officiel (nos-catalogues-promos-v2.e.leclerc), avec les « offres de la semaine » d'e.leclerc.
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
from datetime import date, datetime, timedelta, timezone
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


# nouveaux essais pour tout le passage : une panne générale ne doit pas allonger la mise à jour sans fin
RELANCES = {"reste": 40}


def telecharger(url, log, entetes=None, binaire=False):
    """Une erreur passagère (serveur 5xx, réseau coupé, délai dépassé) est retentée deux fois, après 3 puis 8 s.
    404 (enseigne absente de la ville) et 429 (trop de demandes) ne le sont pas."""
    h = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
    }
    h.update(entetes or {})
    for essai in range(3):
        DERNIER["code"] = None
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
            if not 500 <= e.code < 600 or essai == 2 or RELANCES["reste"] <= 0:
                if e.code != 404:  # 404 = l'enseigne n'existe pas dans cette ville, c'est normal
                    log("   ! %s -> erreur HTTP %s" % (url, e.code))
                return None
            raison = "erreur HTTP %s" % e.code
        except Exception as e:  # réseau coupé, délai dépassé…
            if essai == 2 or RELANCES["reste"] <= 0:
                log("   ! %s -> %s" % (url, e))
                return None
            raison = str(e)[:80]
        RELANCES["reste"] -= 1
        attente = (3, 8)[essai]
        log("   … %s -> %s, nouvel essai dans %d s" % (url, raison, attente))
        time.sleep(attente)
    return None


# --------------------------------------------------------------------------- rayons
RAYONS = {
    "High-tech & électroménager": "smartphone, tablette tactile, galaxy tab, ipad, telephone, telephone portable, aspirateur, balai aspirateur, lave linge, seche linge, lave vaisselle, refrigerateur, congelateur, airfryer, friteuse, expresso, cafetiere, senseo, machine a cafe, imprimante, casque, ecouteurs, enceinte, television, tv, console, jeu video, electromenager, multimedia, ordinateur, pc portable, souris, clavier, disque dur, cle usb, robot, blender, mixeur, bouilloire, grille pain, micro ondes, four multifonction, mini four, plancha, radiateur, chauffage, seche cheveux, lisseur, boucleur, montre connectee, trottinette electrique, smartwatch, barre de son, appareil a raclette, appareil raclette, gaufrier, crepiere, fondue electrique, air fryer, appareil a raclette, raclette electrique, nettoyeur vapeur, aspirateur laveur, jeu video, jeux video, pour ps5, pour ps4, nintendo switch, switch 2, xbox, nintendo, sony, philips, krups, moulinex, calor, seb, rowenta, braun, babyliss, remington, dyson, bosch, siemens, samsung, hisense, tcl, xiaomi, jbl, ninja, tristar, livoo, silvercrest, medion, konix, delonghi, magimix, kenwood, machine a biere, machine a granite, machine multi boissons, machine a boissons, distributeur de boissons, machine a dosettes, machine a capsules, machine a pain, machine a pates, machine a soda, centrale vapeur, cookeo, iphone, macbook, imac, airpods, apple watch, piles, micro sd, carte sd, carte memoire, chargeur, cable, cable usb, batterie externe, siege gaming, chaise gaming, fauteuil gaming, manette, ecran pc, moniteur, ssd, webcam, croque gaufre, teppanyaki, grill teppanyaki, machine a coudre, camera, microphone, micro sans fil, televiseur, televiseurs, appareil photo, appareil photo instantane",
    "Jouets & culture": "jouet, jouets, lego, playmobil, peluche, poupee, puzzle, jeu de societe, jeu de cartes, livre, livres, manga, bd, tome, roman, coloriage, feutres, stylos, cartable, nerf, beyblade, figurine, voiture radiocommandee, circuit, pokemon, pokedex, autocollants, papeterie, peluches, poupees, jeu de construction, roman policier, thriller, vtech, hasbro, hasbro gaming, mattel, ravensburger, goliath, fisher price, smoby, trotteur, baby foot, babyfoot, play doh, nathan, harpercollins, bibliotheque, pat patrouille, jeux de societe, jeu d adresse, jeu educatif, jeux educatifs, poupon, poupons, majorette, kpop demon hunters, polly pocket, rainbow high, sylvanian, mallette d artiste, pate a modeler, slime, jeu d echecs, semainier, agenda, agendas, balle magique, super balle, radiocommande, radiocommandee, monster truck, marqueurs, sachets postaux, enveloppes, balle volante",
    "Mode & sport": "t shirt, tee shirt, pull, chaussures, baskets, chaussettes, pyjama, veste, pantalon, jean, sweat, collant, collants, slip, slips, boxer, boxers, soutien gorge, legging, bonnet, gants, echarpe, manteau, doudoune, sac a main, sac a dos, bague, collier, bracelet, pendentif, boucles d oreilles, montre, lingerie, chemise, robe, jupe, peignoir, chaussons, brassiere, vetement, ski, debardeur, valise, bagagerie, combinaison, body, grenouillere, creoles, boucles d oreilles, chaine, bottines, mules, sandales, escarpins, ballerines, mocassins, pantoufles, charentaises, boots, argent rhodie, oxyde de zirconium, oxydes de zirconium, marcassite, perles de culture, plaque or, argent 925, trottinette, trottinettes, panier de basket",
    "Maison & déco": "couette, oreiller, drap, housse de couette, plaid, sapin, guirlande, decoration, boule, suspension, bougie, bouquet, tulipes, fleurs, vaisselle, poele, casserole, sauteuse, faitout, torchons, torchon, lampe, coussin, rideau, tapis, cadre, vase, creche, papier cadeau, sac cadeau, nappe, serviettes, verres, assiettes, couverts, boite de rangement, lanterne, scene de noel, figurine de noel, calendrier de l avent decoratif, cheminee, photophore, bougies, allumettes, cuiseur, cuiseur camembert, cuiseur a camembert, moules a gateau, moule a gateau, moules a muffins, moule a muffins, moules en silicone, sacs cadeaux, sac cadeaux, pot ceramique, pot en ceramique, ceramique, corbeille a linge, laguiole, couteaux, couteau, fourchettes, cuilleres, menagere, filtres, filtre a cafe, filtres a cafe, snuggie, sechoir, sechoirs, etendoir, etendoirs, couverture, couvertures, parure de lit, parures de lit, miroir, gnome, gnomes, boite a bijoux, plateau en marbre, plateau de service, bouillotte, chemin de table, set de table, sets de table, batonnets parfumes, pouf, pouf de rangement, led, eclairage, figurines de noel, accessoires textiles, petit train de noel",
    "Jardin & bricolage": "perceuse, visseuse, outil, outils, combustible, petrole, granules, granule bois, bois de chauffage, taille haies, tondeuse, plante, plantes, poinsettia en pot, cactus, orchidee, terreau, bouteille de gaz, batterie, ampoule, ampoules, rallonge, multiprise, prises, bloc prises, pneu, essuie glace, lave glace, antigel, nettoyeur haute pression, buches de bois, bois densifie, buches, poinsettia, poinsettias, huile moteur, huiles moteur, huile auto, huiles auto, liquide de refroidissement, chrysantheme, chrysanthemes, film isolant, bande d etancheite, joint brosse, metre ruban, pistolet a colle, souffleur, carreaux adhesifs, etoile de noel en pot",
    "Hygiène & beauté": "shampoing, gel douche, deodorant, dentifrice, brosse a dents, rasoir, maquillage, creme visage, creme mains, lingettes, demaquillant, savon, parfum, couches, culottes, protege slip, serviettes hygieniques, coton, vernis, apres shampoing, soin, mouchoirs, coloration, visage, eau de toilette, eau de parfum, eau micellaire, gel lavant, preservatifs, durex, manix, brossettes, oral b, colgate, elmex, sensodyne, gillette, nivea, garnier, l oreal, loreal, mixa, cadum, le petit marseillais, sanex, rexona, narta, schwarzkopf, elseve, ushuaia, always, tampax, pampers, huggies, john frieda, carrefour soft, fructis, dove, blanchiment dentaire, kit de blanchiment, bandes de blanchiment, hydropulseur, faux cils, gloss, gloss a levres",
    "Entretien": "lessive, adoucissant, liquide vaisselle, pastilles lave, eponge, nettoyant, javel, essuie tout, papier toilette, sacs poubelle, desodorisant, capsules de lessive, vinaigre d alcool, papier hygienique, lessive pods, capsules de lessive, lessive liquide, pods, plumeau, swiffer, eau de javel, capsules lave vaisselle, capsules blanchissantes, mr propre, finish, omo, ariel, skip, persil, le chat, fairy, genie, sun, cif, ajax, harpic, canard wc, saint marc, vanish, soupline, lenor, mir",
    "Animaux": "chat, chien, croquettes, patee, litiere, sheba, felix, whiskas, pedigree, friskies, ultima, a macher, batonnets a macher, patee, patee pour chat, patee pour chien, pour chat, pour chien, pour chats, pour chiens, croquettes, boules de graisse, oiseaux, litiere, companino, purina, perfect fit, royal canin, frolic, sanicat, dreamies",
    "Boissons": "biere, vin, rose, champagne, cremant, whisky, rhum, vodka, gin, jus, soda, coca, pepsi, eau minerale, eau gazeuse, sirop, ice tea, cafe, cafe grains, capsules cafe, dosettes, infusion, beaujolais, mousseux, martini, porto, ron, rhum arrange, arranges, liqueur, cognac, armagnac, calvados, pastis, ricard, cidre, nescafe, ricore, chicoree, bieres, jus d orange, pur jus, jus de pomme, jus de raisin, sirop, teisseire, oasis, ice tea, jus de fruits, capri sun, whiskey, electrolytes, bordeaux, bourgogne, brouilly, chablis, medoc, cotes du rhone, cotes de provence, saint emilion, muscadet, sancerre, chinon, saumur, cuvee, chateau, domaine, vin rouge, vin blanc, vin rose, aop rouge, aop blanc, aop rose, igp rouge, igp blanc, igp rose, pays d oc, vacqueyras, gigondas, cahors, madiran, bergerac, pomerol, margaux, pauillac, riesling, gewurztraminer, prosecco, cava, lambrusco, energy drink, red bull, punch, planteur, arrange, arranges, smoothie, smoothies, nectar, nectars, limonade, fanta, orangina, schweppes, sprite, seven up, perrier, evian, vittel, badoit, volvic, cristaline, san pellegrino, eau aromatisee, eaux aromatisees, pulp, lipton, the noir, the vert, tisane, tisanes, cocktail, cocktails, spritz, sangria, kir, liqueur, creme de cassis, pineau, muscat, cidre, bieres, biere blonde, tropicana, innocent, pur jus, jus de, punch, planteur, the noir, the vert, the rouge, the glace, the menthe, the a la menthe, the earl grey, the english breakfast, sachets de the, twinings, tetley, kusmi, elephant, monster energy, canettes, canette, capsules cafe, capsules espresso, capsules compatibles, thes, infusions, sirops, fuzetea, corona, goudale, heineken, leffe, kronenbourg, grimbergen, affligem, desperados, pelforth, chouffe, karmeliet, carlsberg, hoegaarden, paulaner, chimay, duvel, jenlain, tourtel, jurancon, vouvray, gaillac, minervois, corbieres, fitou, sauternes, monbazillac, crozes hermitage, chateauneuf du pape, tavel, bandol, pouilly fume, fiefs vendeens, haut medoc, entre deux mers, cotes de gascogne, fronsac, buzet, rasteau, cairanne, fleurie, morgon, julienas, moulin a vent, gros plant, bourgueil, menetou salon, picpoul de pinet, costieres de nimes",
    "Poisson & mer": "saumon, cabillaud, crevette, crevettes, thon, sardine, maquereau, moules, huitres, coquilles saint jacques, coquilles, colin, merlu, bar, dorade, poisson, surimi, crabe, langoustine, truite, rillettes de thon, calamar, seiche, delpierre, petit navire, poissons, limande, sole, lieu noir, filet de lieu, dos de lieu, merlan, eglefin, fletan, blinis, saint jacques, noix de saint jacques, brandade, huitre, lotte, anchois, bulots, homard, homards, langouste, langoustes, tourteau, tourteaux, palourdes, rouget, rougets, turbot, aile de raie, ailes de raie, encornets, poulpe, tarama, oeufs de lump, blini",
    "Volaille": "poulet, dinde, pintade, canard, magret, caille, chapon, volaille, cordon bleu, cordons bleus, nuggets, aiguillettes, maitre coq, loue, tenders, nuggets, cordon bleu, aiguillettes, grignottes, pilon, pilons, cuisse de canard, cuisses de canard, confit de canard, magret",
    "Charcuterie": "jambon, saucisson, tripes, lardons, rillettes, pate, terrine, chorizo, bacon, knacki, saucisse de strasbourg, foie gras, foie de canard, foies de canard, mousse de foie, andouille, andouillette, boudin, fleury michon, fuet, rosette, charcuterie, mortadelle, boudins, boudin noir, boudin blanc, boudins blancs, terrine de campagne, saucissons, jambons, chiffonnade, coppa, pancetta, bresaola, viande des grisons, rillons, rillauds, grattons, salami, pastrami",
    "Viande": "boeuf, veau, porc, agneau, lapin, steak, steaks haches, hache, entrecote, cote, roti, filet mignon, echine, saucisse, saucisses, merguez, chipolatas, paupiette, paupiettes, rognons, foie de boeuf, langue, osso bucco, bavette, charal, viande, boulettes, bavettes, entrecotes",
    "Fromage": "fromage, camembert, emmental, comte, brie, raclette, mozzarella, cheddar, chevre, cabecou, crottin, roquefort, bleu d auvergne, reblochon, coulommiers, mimolette, parmesan, feta, tomme, madame loik, saint nectaire, tartiflette, buche aux laits, parmigiano, reggiano, tartiflette, rondele, tartare ail et fines herbes, boursin, fromages, beaufort, babybel, mini babybel, vache qui rit, fondue savoyarde, saint albray, kiri, apericube, cantal, munster, morbier, gouda, edam, maroilles, pont l eveque, livarot, epoisses, mont d or, saint moret, st moret, carre frais, chavroux, caprice des dieux, burrata, ricotta, gorgonzola, fourme d ambert, rocamadour, sainte maure, leerdammer, saint agur, port salut",
    "Crèmerie & œufs": "yaourt, yaourts, creme fraiche, creme liquide, beurre, beurrier, oeufs, oeuf, margarine, skyr, fromage blanc, dessert lacte, petits suisses, liegeois, danette, bridelice, desserts, creme legere, creme fouettee, petit pot de creme, lait, lait demi ecreme, lait entier, lait ecreme, activia, danone, yaourt brasse, yaourts brasses, riz au lait, creme dessert, cremes desserts, creme brulee, cremes brulees, flan nappe, flans nappes, ile flottante, iles flottantes, mousse au chocolat, mousses au chocolat, panna cotta, cheesecake, cheesecakes",
    "Fruits & légumes": "pomme, pommes, poire, banane, orange, clementine, mandarine, kiwi, avocat, raisin, fraise, citron, ananas, mangue, tomate, tomates, carotte, carottes, courgette, poireau, oignon, echalote, ail, salade, concombre, poivron, champignon, champignons, chou, brocoli, epinards, haricots verts, patate douce, pomme de terre, pommes de terre, potiron, courge, navet, radis, endive, pak choi, betterave, mache, fruits, legumes, potimarron, marrons, chataignes, noix, morilles, cepes, girolles, corbeille de fruits secs, poireaux, oignons, echalotes, courgettes, concombres, poivrons, brocolis, navets, endives, betteraves, asperges, asperge, clementines, mandarines, oranges, citrons, poires, bananes, kiwis, avocats, fraises, framboises, myrtilles, mangues",
    "Surgelés": "pommes de terre surgelees, legumes surgeles, poisson pane, poissons panes, frites surgelees, surgele, surgeles, surgelee, surgelees, glace, glaces, cone, cones, mccain, frites, pizza surgelee, poelee, pommes noisettes, picard, airfryer frite, frites surgelees, surgelee, surgelees, pommes duchesse, legumes bruts",
    "Boulangerie": "pain, baguette, brioche, viennoiserie, croissant, pain de mie, pains a burger, pain a burger, wraps, tortilla, harrys, jacquet, pains au chocolat, boules mais, flan, tarte, tartelettes, galette des rois, bande feuilletee, tarte fine, tarte aux pommes, chausson aux pommes, chaussons, millefeuille, millefeuilles, mille feuille, mille feuilles, eclair, eclairs, macarons, paris brest, religieuses, chouquettes",
    "Épicerie sucrée": "beurre de cacahuete, beurre de cacahuetes, beurre de cacahouete, beurre de cacahouetes, peanut butter, chocolat, chocolats, biscuit, biscuits, gateau, gateaux, bonbon, bonbons, confiserie, gouter, gouters, fourre, confiture, pate a tartiner, nutella, cereales, granola, cacao, sucre, miel, compote, calendrier de l avent, ferrero, kinder, madeleine, panettone, milka, lindor, flocons d avoine, buche, canderel, delacre, deli choc, galettes, orangettes, barre, barres, barre tendre, pain d epices, marrons glaces, truffes, pralines, pandoro, papillotes, nesquik, poudre chocolatee, chocolatee, chocolatees, tablette de chocolat, tablettes de chocolat, chocolat lait, chocolat noir, chocolat au lait, chocolat blanc, noisettes grillees, sucres, decors sucres, pates de fruits, escargots praline, fourres, mini fourres, biscuits fourres, calissons, nougat, nougats, beignet, beignets, tiramisu, praline, boules praline, kit kat, compotes, gourde, gourdes, pom potes, cool fruits, petits pots, bledina, specialite de fruits, preparation de fruits, creme de marrons, cake, cakes, crumble, trompe l oeil, popcorn, pop corn, choco, daco bello, trompe loeil, palmiers, palmier, confitures, gourdes lactees, muesli, mueslis, biscottes, biscotte, cracottes, pain grille, speculoos, gaufres, financiers, sucette, sucettes, figurines de noel en chocolat, figurines en chocolat, figurine en chocolat",
    "Traiteur": "quiche, quiches, coeur de quiche, pizza, pizzas, lasagnes, lasagne, gratin, gratins, gratin dauphinois, hachis parmentier, parmentier, plat cuisine, plats cuisines, salade composee, salade de pates, taboule, paella, choucroute, choucroute garnie, croque monsieur, feuillete, feuilletes, friand, friands, bouchees a la reine, nems, samoussa, samoussas, sushi, sushis, sandwich, sandwichs, prefou, risotto, blanquette, bourguignon, tajine, couscous royal, pommes paillasson, tarte salee, tourte, wrap garni, farci, farcis, farcie, farcies, plat prepare, plats prepares, gnocchi a poeler, cordon bleu traiteur, burger, burgers, galette de ble noir, galettes de ble noir, crepe garnie, crepes garnies, tofu, plat vegetal, plats vegetaux, gougeres, pomme de terre farcie, pommes de terre farcies, tomate farcie, tomates farcies, rosti, rostis, rosti farci, salades preparees, salade preparee, houmous, guacamole, tzatziki",
    "Épicerie salée": "pates, pates fraiches, pennette, spaghetti, riz, lentilles, semoule, couscous, quinoa, gnocchi, gnocchis, conserve, sauce, huile, vinaigre, moutarde, mayonnaise, ketchup, epices, sel, poivre, soupe, chips, chipster, aperitif, biscuits aperitifs, cacahuetes, olives, bouillon, farine, lustucru, panzani, barilla, rana, tuc, ravioli, raviolis, legumineuses, escargots, aligot, truffade, burgers aperitifs, pois chiches, escargots de bourgogne, soupes, soupe, tagliatelles, pates aux oeufs, pates, coquillettes, veloute, veloutes, mouline, potage, gazpacho, bouillon, croutons, chair de tomates, pulpe de tomates, puree de tomates, coulis de tomates, sauces, sauce tomate, lait de coco, bouquet garni, baked beans, puree, purees, mix bretzel, bretzels, haricots a la tomate, legumes cuisines, conserve de legumes, quinotto, tyrrells, pringles, lay s, vico, bret s, belin, curly, monster munch, crackers, tortellini, tortelloni, ravioles, nouilles, antipasti, graines de tournesol",
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
           "pizza", "burger", "donut", "glace", "sucre", "bonbon", "bonbons", "frites", "avocat", "ananas", "banane", "cookie",
           "oranges", "citrons", "fraises", "framboises", "myrtilles", "avocats", "bananes", "fromages"}


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
                         "dujardin", "asmodee", "gigamic", "janod", "djeco", "monster high", "dickie toys", "van bleiswijck", "gear2play",
                         "office essentials"],
    "High-tech & électroménager": ["nintendo", "sony", "philips", "krups", "moulinex", "calor", "seb", "rowenta", "braun", "babyliss",
                                   "remington", "dyson", "bosch", "siemens", "samsung", "hisense", "tcl", "xiaomi", "jbl", "ninja",
                                   "tristar", "livoo", "silvercrest", "medion", "konix", "delonghi", "magimix", "kenwood",
                                   "russell hobbs", "domo", "essentielb", "proline", "qilive", "tomado", "fresh n rebel"],
    "Jardin & bricolage": ["ferm", "werckmann"],
    "Hygiène & beauté": ["max more"],
    "Entretien": ["finish", "omo", "ariel", "skip", "persil", "le chat", "fairy", "genie", "sun", "cif", "ajax", "harpic", "canard wc",
                  "saint marc", "vanish", "soupline", "lenor", "mir", "mr propre", "sanytol", "destop", "air wick", "febreze", "spontex"],
}
# chocolatiers, confiseurs et biscuitiers : la marque suffit (« Assortiment lait & noir » Lanvin, « Mini roc » Côte d'Or)
MARQUES_SUCREES = ["lindt", "lindor", "lanvin", "cote d or", "milka", "ferrero", "kinder", "raffaello", "mon cheri", "suchard", "cemoi",
                   "revillon", "toblerone", "after eight", "guylian", "leonidas", "jeff de bruges", "neuhaus", "godiva", "galler",
                   "valrhona", "poulain", "menier", "celebrations", "quality street", "maltesers", "kit kat", "galak", "daim",
                   "haribo", "trolli", "carambar", "lutti", "la mere de famille", "michel et augustin", "st michel", "saint michel", "lu"]
RE_FRAIS_GLACE = re.compile(r"\b(glace|glaces|creme glacee|cremes glacees|cone|cones|batonnet|batonnets|yaourt|yaourts|mousse|mousses|liegeois|dessert lacte|desserts lactes)\b")
BOISSONS_SECHES = {"cafe", "cafe grains", "capsules cafe", "capsules espresso", "capsules compatibles", "dosettes", "infusion",
                   "tisane", "tisanes", "the noir", "the vert", "the rouge", "the menthe", "the a la menthe", "the earl grey",
                   "the english breakfast", "sachets de the", "twinings", "tetley", "kusmi", "elephant", "lipton", "the glace", "thes", "infusions"}
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
    if not strict and any(" " + x + " " in nm for x in MARQUES_SUCREES) and not RE_FRAIS_GLACE.search(nn) \
            and not _liquide(nom, texte, unite):
        return "Épicerie sucrée"  # chocolats, bonbons, biscuits de marque (pas leurs glaces ni leurs desserts frais)
    r, mot = _choix(nn)
    if r in ("Maison & déco", "Jouets & culture") and re.search(r"\ben chocolat\b", nn):
        r, mot = "Épicerie sucrée", "chocolat"  # « Sapin en chocolat », « Figurines de Noël en chocolat »
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


RE_PAGE_IMG = re.compile(r"content-media\.bonial\.biz/([0-9a-f-]{36})/")


def catalogue_complet(cid, typ, pos, log, pause=0.6):
    """-> (offres, images de bannières, pages) ou None si la visionneuse n'a pas répondu.
    pages : identifiant de l'image de chaque page (pour feuilleter le catalogue dans l'appli)."""
    offres, images, pages = [], [], []
    if typ != "DYNAMIC":
        d = visionneuse("/brochures/%s/pages" % cid, pos, log)
        time.sleep(pause)
        if d is None:
            return None
        for pg in d.get("contents") or []:
            m = next((RE_PAGE_IMG.search(im.get("url") or "") for im in pg.get("images") or [] if RE_PAGE_IMG.search(im.get("url") or "")), None)
            pages.append(m.group(1) if m else "")
            for o in pg.get("offers") or []:
                it = offre_visionneuse(o.get("content") or {})
                if it:
                    offres.append(it)
        if d.get("contents") or typ == "BROCHURE":
            return offres, images, pages
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
    return offres, images, pages


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


# --------------------------------------------------------------------------- E.Leclerc : site officiel
# Bonial montre les pages des catalogues Leclerc mais pas leurs produits. Le catalogue en ligne d'E.Leclerc
# (nos-catalogues-promos-v2.e.leclerc, celui des liens « Nos catalogues » de chaque magasin) les donne tous,
# magasin par magasin : prix, mécanique de la promo, photo et code-barres. Les offres de quelques jours
# (« -30 % sur les raclettes Entremont les 19 et 20 novembre ») sont sur la page « Les offres de la semaine »
# d'e.leclerc, celles que les magasins reprennent sur leurs réseaux. On lit les deux comme le navigateur
# le fait sur ces sites, une fois par jour.
LEC_SITE = "https://nos-catalogues-promos-v2.e.leclerc"
LEC_API = "https://nos-catalogues-promos-v2-api.e.leclerc"
LEC_ENTETES = {"Accept": "application/json, text/plain, */*", "Origin": LEC_SITE, "Referer": LEC_SITE + "/"}
LEC_SEMAINE = "https://www.e.leclerc/api/rest/live-api/category-details-by-code/EDITO_offres-de-la-semaine"
LEC_SEMAINE_PAGE = "https://www.e.leclerc/e/offres-de-la-semaine"
LEC_SEMAINE_ENTETES = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.e.leclerc",
                       "Referer": LEC_SEMAINE_PAGE}
LEC_ETAT = os.path.join(DATA, "leclerc.json")
LEC_GRAINES = ["26G095G"]  # un catalogue connu, pour demander la liste de ceux d'un magasin
# pas des promos : guides, cartes traiteur (menus à commander), voyages, bijoux à l'année
LEC_IGNORES = re.compile(r"^(guide|carte traiteur|voyages?|mariage|enfants|alliances)\b")
# rayon du magasin (catégorie Leclerc) quand il ne laisse pas de doute : rayon() le lit comme « au rayon … »
LEC_RAYON_MAGASIN = {"1001": "boulangerie", "1004": "surgele", "1005": "fruits et legumes", "1006": "boisson",
                     "1008": "hygiene", "1009": "droguerie", "1022": "boisson", "1023": "cave"}
# sinon son premier niveau, comme les catégories bonial (une peluche « ananas » n'est pas un fruit)
LEC_HAUT = {"1010": "multimedia", "1011": "bebe et enfant", "1012": "mode", "1013": "maison et meubles",
            "1014": "bricolage et jardin", "1015": "animaux", "1024": "sport et loisirs", "1025": "jeux et jouets",
            "1026": "bricolage et jardin", "1028": "papeterie et articles de bureau", "1091": "multimedia"}
for _c in range(1047, 1058):
    LEC_HAUT[str(_c)] = "article culturel"
for _c in range(1058, 1066):
    LEC_HAUT[str(_c)] = "animaux"
for _c in list(range(1066, 1073)) + list(range(1084, 1091)) + [1092, 1093]:
    LEC_HAUT[str(_c)] = "bricolage et jardin"
for _c in range(1073, 1084):
    LEC_HAUT[str(_c)] = "cosmetiques"
for _c in list(range(1029, 1047)) + list(range(1094, 1099)):
    LEC_RAYON_MAGASIN[str(_c)] = "cave"
# rayons possibles dans une catégorie Leclerc : si le nom mène ailleurs (« nouilles saveur poulet » en épicerie,
# « bûche de chèvre » en crèmerie), on reste dans la catégorie ; le premier rayon sert si le nom ne dit rien
LEC_RAYONS_OK = {"1002": ["Viande", "Volaille", "Poisson & mer", "Charcuterie"],
                 "1007": ["Épicerie salée", "Épicerie sucrée", "Boissons"],
                 "1016": ["Traiteur", "Charcuterie"],
                 "1017": ["Fromage", "Crèmerie & œufs"],
                 "1021": ["Hygiène & beauté", "Épicerie sucrée", "Épicerie salée", "Crèmerie & œufs", "Boissons"]}
# catégories alimentaires (tout le catalogue compte) ; ailleurs (jouets, livres, mode…) seulement les vraies promos
LEC_ALIM = {str(c) for c in list(range(1001, 1008)) + [1016, 1017, 1021, 1022, 1023] + list(range(1029, 1047)) + list(range(1094, 1099))}
LEC_NOMS_CAT = {"1001": "pain viennoiserie patisserie", "1002": "viandes et poissons", "1004": "surgeles",
                "1005": "fruits et legumes", "1007": "epicerie", "1008": "hygiene et beaute", "1009": "entretien",
                "1016": "charcuterie traiteur", "1017": "cremerie fromagerie", "1022": "boissons", "1023": "boissons"}
LEC_MOTS_VIDES = set("rue route avenue av boulevard bd bp place zone za zac zi d de du des la le les l et rond point "
                     "cedex centre commercial parc espace activite activites sur sous en aux st ste".split())
RE_LEC_GAMME = re.compile(r"(?i)^\s*sur\s+(?:les|tous les|toute la|la)\s+(?:produits|gamme)\b")
RE_LEC_UNITE = re.compile(r"(?i)\ble\s+(kg|l|litre)\s*:\s*\d+(?:[.,]\d{1,2})?\s*€")
RE_LEC_LOT = re.compile(r"(?i)\bpar\s+(\d+)\s*(?:\([^)]*\))?\s*:\s*(\d+(?:[.,]\d{1,2})?)\s*€")
RE_LEC_BLABLA = re.compile(r"(?i)non cumulable|offre d.avantage|prix conseill|voir d[ée]tails|dans la limite|^par\s+\d+\s*\(")
RE_LEC_JOURS = re.compile(r"\bles\s+(\d{1,2})(?:er)?\s+et\s+(\d{1,2})(?:er)?\s+(%s)\b" % "|".join(MOIS))
RE_LEC_JOUR = re.compile(r"\b(\d{1,2})(?:er)?\s+(%s)\b" % "|".join(MOIS))


def lec_json(url, log, entetes=None):
    txt = telecharger(url, log, entetes or LEC_ENTETES)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def _lec_date(v):
    """« 2026-11-28T23:59:59Z » -> « 2026-11-28 » (le jour du catalogue)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v or ""))
    return m.group(1) if m else ""


def _lec_nombre(v):
    try:
        f = float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return round(f, 2) if f > 0 else None


def _lec_nb(x):
    return ("%d" % x) if float(x).is_integer() else ("%.2f" % x).rstrip("0").replace(".", ",")


def _lec_mots(t):
    return {w for w in norm(t).split() if len(w) > 1 and w not in LEC_MOTS_VIDES and not w.isdigit()}


def lec_magasins(dept, etat, log, aujourd):
    """Magasins E.Leclerc du département sur le catalogue en ligne (code, adresse, page). Liste gardée une semaine."""
    deja = etat.get("magasins") or []
    try:
        age = (aujourd - date.fromisoformat(etat.get("magasins_maj") or "2000-01-01")).days
    except ValueError:
        age = 999
    if deja and age < 7:
        return deja
    lst = lec_json(LEC_API + "/shops", log)
    if not isinstance(lst, list):
        return deja
    sortie = []
    for x in lst:
        ci = (x or {}).get("contact_info") or {}
        cp = str(ci.get("location_code") or "")
        if not x.get("code") or not cp.startswith(dept):
            continue
        ds = {e.get("name"): e.get("value") for e in x.get("dataset") or [] if isinstance(e, dict)}
        sortie.append({"code": str(x["code"]), "nom": x.get("name") or "", "adresse": ci.get("address") or "", "cp": cp,
                       "ville": re.sub(r"(?i)\s+cedex\b.*$", "", ci.get("city") or ""), "url": ds.get("sue_url") or ""})
    if sortie:
        etat["magasins"], etat["magasins_maj"] = sortie, aujourd.isoformat()
    return sortie or deja


def lec_associer(magasins, officiels):
    """Magasin Leclerc de bonial -> le même magasin sur le catalogue en ligne (même ville, même adresse)."""
    res = {}
    for m in magasins.values():
        if m.get("chaine") != "leclerc":
            continue
        adr, ville = _lec_mots(m.get("adresse")), _lec_mots(m.get("ville"))
        best, score = None, 0
        for o in officiels:
            s = 2 * len(adr & _lec_mots(o["adresse"])) + (2 if ville & _lec_mots(o["ville"]) else 0) \
                + (1 if str(o["cp"])[:4] == str(m.get("cp") or "")[:4] else 0)
            if s > score:
                best, score = o, s
        if best and score >= 3:
            res[m["id"]] = best
    return res


def lec_catalogues(mag, graines, log):
    """Catalogues d'un magasin : la liste « autres catalogues » vue depuis un catalogue connu (une graine), plus la
    graine si le magasin l'a. Si aucune graine ne répond (nouvelle année…) : les liens de sa page sur e.leclerc."""
    code = mag["code"]
    essais = list(dict.fromkeys(list(graines) + LEC_GRAINES))[:6]
    for tour in range(2):
        for g in essais:
            lst = lec_json("%s/%s/%s/other_catalogs" % (LEC_API, g, code), log)
            time.sleep(0.3)
            if not isinstance(lst, list) or not lst:
                continue
            ops = {}
            for x in lst:
                if isinstance(x, dict) and x.get("operationCode") and x.get("uid"):
                    ops[x["operationCode"]] = {"op": x["operationCode"], "nom": x.get("name") or "", "doc": x["uid"],
                                               "debut": _lec_date(x.get("startDate")), "fin": _lec_date(x.get("endDate"))}
            if g not in ops:
                info = lec_json("%s/%s/%s" % (LEC_API, g, code), log)
                if isinstance(info, dict) and info.get("documentUid"):
                    ops[g] = {"op": g, "nom": info.get("name") or "", "doc": info["documentUid"],
                              "debut": _lec_date(info.get("start_date")), "fin": _lec_date(info.get("end_date"))}
            return list(ops.values())
        if tour or not mag.get("url"):
            break
        url = urllib.parse.quote(mag["url"].replace("https://e.leclerc/", "https://www.e.leclerc/"), safe=":/")
        page = telecharger(url, log) or ""
        essais = list(dict.fromkeys(re.findall(r"nos-catalogues-promos-v2\.e\.leclerc/catalog/([A-Za-z0-9]+)/", page)))[:6]
        if not essais:
            break
    return None


def _lec_sans_marque(nom, marque):
    """« FRITES POULET 800G MAITRE COQ » (marque Maître Coq) -> « FRITES POULET 800G »."""
    nm = norm(marque).split()
    mots = nom.split()
    if nm and len(mots) > len(nm) and [norm(w) for w in mots[-len(nm):]] == nm:
        return " ".join(mots[:-len(nm)])
    return nom


def offre_leclerc(p, op, est_alim):
    """Un produit du catalogue en ligne Leclerc -> une offre (même forme que celles de bonial). None : à ignorer."""
    nom = re.sub(r"\s+", " ", str(p.get("name") or "").replace("\n", " ")).strip(" *·-")
    marque = re.sub(r"\s+", " ", str(p.get("brand") or "").replace("\n", " ")).strip(" *·-")
    lab = str(p.get("discountLabel") or "").strip()
    cats = [str(c) for c in p.get("categoriesParentUid") or []]
    alim = (cats[0] in LEC_ALIM) if cats else est_alim  # la catégorie du produit fait foi (« is_food » vaut pour tout le catalogue)
    if len(nom) < 2 or (not alim and lab in ("", "Prix simple")):
        return None  # hors alimentaire : seulement les vraies promos (pas le prix d'un livre ou d'un jouet)
    prix, avant = _lec_nombre(p.get("price")), _lec_nombre(p.get("priceWithoutDiscount"))
    if prix and avant and avant <= prix + 0.005:
        avant = None
    x = _lec_nombre(p.get("discountAmount"))
    en_euros = str(p.get("discountUnit") or "").upper() == "EURO"
    qte = int(_lec_nombre(p.get("discountPriceQty")) or 2)
    desc = [l.strip() for l in str(p.get("description") or "").replace("\r", "").split("\n") if l.strip()]
    gamme = bool(RE_LEC_GAMME.match(nom))
    if gamme:
        # « SUR LES PRODUITS PRÉSENTS EN MAGASIN DE LA GAMME SOUPES DÉSHYDRATÉES "KNORR" » -> « Gamme soupes
        # déshydratées » (Knorr) ; le prix et le poids sont ceux d'un produit parmi d'autres : on ne les garde pas
        reste = re.sub(r"(?i)^\s*sur\s+(?:les|tous les|toute la|la)\s+produits?\s+(?:pr[ée]sents?\s+)?(?:en\s+magasin\s+)?"
                       r"(?:de\s+)?(?:la\s+|l['’]\s*)?", "", nom)
        hors = ""
        m = re.search(r"(?i)[\s.*(]*\bhors\b.*$", reste)
        if m:
            hors, reste = reste[m.start():].strip(" .*()"), reste[:m.start()]
        cite = re.findall(r'["“”«»]\s*([^"“”«»]+?)\s*["“”«»]', reste)
        famille = re.sub(r'["“”«»][^"“”«»]*["“”«»]', " ", reste)
        mot = "Sélection" if re.match(r"(?i)\s*s[ée]lection\b", famille) else "Gamme"
        famille = re.sub(r"(?i)^\s*(gamme|s[ée]lection)\b", "", famille).strip(" .:-")
        famille = re.sub(r"(?i)\s+(de|des|du|d['’])$", "", famille).strip(" .:-")
        if not marque and cite:
            marque = cite[0].title() if cite[0].isupper() else cite[0]
        nom = mot + " " + (adoucir(famille, False) if famille else (marque.title() if marque.isupper() else marque))
        prix = avant = None
        desc = [adoucir(hors)] if hors else []
    else:
        nom = _lec_sans_marque(nom, marque)
    plan, cond, r2, reff, carte = "", None, None, None, False
    if lab in ("BRII %", "BRII EURO"):  # remise immédiate
        if x and not (prix and avant):
            plan = ("-%s immédiatement" % euro(x)) if en_euros else ("-%s %% immédiatement" % _lec_nb(x))
            if not en_euros:
                reff = int(round(x))
    elif lab.startswith("-X%"):  # -X % sur le 2e (ou le 3e…)
        if x and not en_euros:
            if qte == 2 and prix:
                p2 = _lec_nombre(p.get("discountedPriceSecondProduct"))
                if not p2 or p2 >= prix:
                    p2 = round(prix * (1 - x / 100), 2)
                cond, r2 = "le 2e", int(round((1 - p2 / prix) * 100))
                reff = int(round((1 - (prix + p2) / (2 * prix)) * 100))
                avant, prix = prix, p2
            else:
                plan, reff = "-%s %% sur le %de" % (_lec_nb(x), qte), int(round(x / qte))
    elif lab == "X+Y OFFERTS":
        a, b = int(_lec_nombre(p.get("offertX")) or 2), int(_lec_nombre(p.get("offertY")) or 1)
        plan = "%d acheté%s + %d offert%s" % (a, "s" if a > 1 else "", b, "s" if b > 1 else "")
        lot = _lec_nombre(p.get("discountedPriceLot"))
        if not lot:
            m = RE_LEC_LOT.search(" ".join(desc))
            lot = prix_float(m.group(2)) if m and int(m.group(1)) == a + b else None
        if lot and prix:
            plan += ", les %d : %s" % (a + b, euro(lot))
        reff = int(round(b * 100 / (a + b)))
    elif lab.upper().startswith("TEL") or "TICKET" in lab.upper():  # cagnotté en Ticket E.Leclerc (avec la carte)
        carte = True
        if x:
            sur = (" sur le %de" % qte) if "XEME" in norm(lab).upper().replace(" ", "") else ""
            plan = "%s en Ticket E.Leclerc%s" % (euro(x) if en_euros else ("%s %%" % _lec_nb(x)), sur)
            if en_euros:
                reff = int(round(x * 100 / prix)) if prix else None
            else:
                reff = int(round(x / (qte if sur else 1)))
    mm = p.get("mechanicMentions") or {}
    if isinstance(mm, dict) and mm.get("reservedForCardholders"):
        carte = True
    if isinstance(mm, dict) and mm.get("cheapestProduct") and plan:
        plan += " (sur le moins cher)"
    if prix is None and not plan:
        return None
    jointe = " ".join(desc)
    mu = RE_LEC_UNITE.search(jointe)
    unite = unite_et_poids(mu.group(0))[0] if mu else ""
    if not unite and prix and norm(p.get("conditioning")) == "le kg":
        unite = "%s le kg" % euro(avant if cond else prix)
    lignes = []
    for l in desc:
        for y in re.split(r"(?<=\.)\s*(?=[A-ZÀ-ÖØ-Ý])", l):
            y = y.strip()
            if y and not RE_LEC_BLABLA.search(y) and not RE_LEC_UNITE.search(y):
                lignes.append(y)
    drapeaux = set()
    nom_p = propre_nom(nom)
    detail = propre_detail(lignes, nom_p, unite, drapeaux)
    c0 = cats[0] if cats else ""
    force = LEC_RAYON_MAGASIN.get(c0)
    texte = ("au rayon %s" % force) if force else jointe[:200]
    haut = LEC_HAUT.get(c0, "alimentation et boisson" if alim and c0 != "1021" else "")
    r = rayon(nom_p, marque, "", haut, texte, unite)
    permis = LEC_RAYONS_OK.get(c0)
    if permis and r not in permis:
        if c0 == "1016" and r == "Viande":
            r = "Charcuterie"  # saucisses fumées, saucisson
        elif c0 == "1007" and r == "Boulangerie":
            r = "Épicerie sucrée"  # brioche, tartelettes en sachet
        elif c0 == "1007" and r == "Fruits & légumes":
            r = "Épicerie sucrée" if re.search(r"(?i)fraise|pomme|poire|abricot|cerise|framboise|p[eê]che|fruit|myrtille|figue|datte|pruneau",
                                              nom_p) else "Épicerie salée"
        elif c0 == "1017":
            r = "Fromage" if re.search(r"(?i)mat\.?\s*gr|\d\s*%\s*m\.?\s*g\b|fromage|ch[eè]vre|brebis", nom_p + " " + jointe) \
                else "Crèmerie & œufs"
        else:
            tr = [t for t in _mots_cles(norm(nom_p)) if t[2] in permis]
            r = min(tr)[2] if tr else permis[0]
    d1 = _lec_date(p.get("mandatStartDate")) or op["debut"]
    d2 = _lec_date(p.get("mandatEndDate")) or op["fin"]
    if d1 < op["debut"] or d1 > op["fin"]:
        d1 = op["debut"]
    if d2 > op["fin"] or d2 < d1:
        d2 = op["fin"]
    it = {"nom": nom_p, "marque": marque if len(marque) > 1 else "", "prix": prix, "avant": avant, "unite": unite,
          "detail": detail, "debut": d1, "fin": d2, "bon_plan": plan, "rayon": r, "remise_effective": reff}
    if cond:
        it["condition"], it["remise_affichee"] = cond, r2
    if carte:
        it["carte"] = True
    for dr in drapeaux:
        it[dr] = True
    imgs = [i for i in p.get("images") or [] if isinstance(i, dict) and i.get("url")]
    img = next((i["url"] for i in imgs if i.get("type") == "packshot"), None) or (imgs[0]["url"] if imgs else None)
    if img:
        it["ph"] = img  # photo officielle (l'appli demande la taille voulue : ?g=300x300)
    if re.fullmatch(r"\d{8,14}", str(p.get("ean") or "")):
        it["ean"] = str(p["ean"])
    return it


def _lec_jours(a, b):
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def _lec_titre(info, nom):
    t = (info.get("catch_phrase") or "").strip()
    if not t:
        t = re.sub(r"(?i)\s*(-\s*mixte|gsa)\s*$", "", nom or "").strip()
        t = adoucir(t.title() if t.isupper() else t)
    return t[:1].upper() + t[1:] if t else "Catalogue"


def _lec_dates_texte(t, ref):
    """« Les 19 et 20 novembre », « Du 1er au 30 novembre », « Le 21 novembre » -> (début, fin)."""
    n = norm(t)
    m = RE_DU_AU.search(n)
    if m:
        d2 = _date_fr(m.group(3), m.group(4), ref)
        d1 = _date_fr(m.group(1), m.group(2) or m.group(4), ref)
        if d1 and d2 and d1 <= d2:
            return d1, d2
    m = RE_LEC_JOURS.search(n)
    if m:
        d1, d2 = _date_fr(m.group(1), m.group(3), ref), _date_fr(m.group(2), m.group(3), ref)
        if d1 and d2 and d1 <= d2:
            return d1, d2
    m = RE_LEC_JOUR.search(n)
    if m:
        d = _date_fr(m.group(1), m.group(2), ref)
        if d:
            return d, d
    return None, None


def lec_semaine(log, aujourd):
    """« Les offres de la semaine » d'e.leclerc (nationales, magasins participants) -> {id catalogue: (catalogue, offres)} :
    une seule entrée d'agenda, chaque offre avec ses jours (les 19 et 20 novembre, le 21 novembre, tout le mois…)."""
    d = lec_json(LEC_SEMAINE, log, LEC_SEMAINE_ENTETES)
    page = (d or {}).get("page") or {}
    jour, horizon = aujourd.isoformat(), (aujourd + timedelta(days=10)).isoformat()
    par_periode = {}
    for z in ((page.get("template") or {}).get("zones") or []):
        for c in z.get("components") or []:
            if not isinstance(c, dict) or c.get("type") != "IMAGE":
                continue
            if re.match(r"(header|teasing|renvoi)\b", norm(c.get("name"))):
                continue  # titres de rubriques, annonces, liens
            titre = re.sub(r"\s+", " ", c.get("seoTitle") or "").strip()
            txt = re.sub(r"\s+", " ", c.get("description") or c.get("seoAlt") or titre).strip()
            if not re.search(r"(?i)\d\s*%|\d\s*€|ticket|offert", txt):
                continue
            d1, d2 = _lec_dates_texte(txt, aujourd)
            a1, a2 = _lec_date(c.get("startDate")), _lec_date(c.get("endDate"))
            if not d1:
                if not a2:
                    continue  # avantage permanent (« chaque semaine… ») : pas une promo datée
                d1, d2 = date.fromisoformat(a1 or jour), date.fromisoformat(a2)
            if d2.isoformat() < jour or d1.isoformat() > horizon:
                continue
            nom = re.sub(r"(?i)^(les immanquables e\.?\s?leclerc\s+vu [àa] la t[ée]l[ée]|"
                         r"offre(\s+rayon)?(\s+frais traditionnel)?(\s+immanquable)?(\s+e\.?\s?leclerc)?|"
                         r"mardis? b[ée]b[ée] sur la marque)\s*:?\s*", "", titre).strip()
            nom = re.sub(r"(?i)\s+[àa]\s+\d+(?:[.,]\d+)?\s*€.*$", "", nom).strip(" :")
            if not nom or re.search(r"(?i)\b(du|le|les)\s+\d|%|ticket", nom) or re.match(r"(?i)mardis? b[ée]b[ée]", titre):
                m = re.search(r"(?i)\bsur\s+(?:une\s+s[ée]lection\s+de\s+|la\s+marque\s+|la\s+gamme\s+|le\s+rayon\s+|des\s+)?"
                              r"(.+?)(?:\s+de\s+marque\b.*|\s+(?:de la marque|des marques)\b.*|\s+[àa]\s+activer\b.*|[.,]|$)", txt)
                if m:
                    nom = ("Bébé : " if re.match(r"(?i)mardis? b[ée]b[ée]", titre) else "") + m.group(1).strip()
            if not nom:
                continue
            nom = nom[:1].upper() + nom[1:]
            mq = re.search(r"(?i)\b(?:de la marque|des marques)\s+(.+?)(?:\.|$)", txt)
            marque = mq.group(1).strip() if mq else ""
            carte = bool(re.search(r"(?i)porteurs?\s+de\s+la\s+carte|ticket|avec la carte|application mon e\.?\s?leclerc", txt))
            plan, rem = "", None
            m = re.search(r"(?i)(\d+(?:[.,]\d+)?)\s*%\s*en\s+tickets?", txt)
            if m:
                rem = int(float(m.group(1).replace(",", ".")))
                plan = "%d %% en Ticket E.Leclerc" % rem
            else:
                m = re.search(r"-\s*(\d+(?:[.,]\d+)?)\s*%", txt) or re.search(r"(?i)moins\s+(\d+)\s*pour\s*cent", txt)
                if m:
                    rem = int(float(m.group(1).replace(",", ".")))
                    plan = "-%d %%%s" % (rem, " avec la carte" if carte else "")
            prix = avant = None
            m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*€", txt)
            if m and not plan:  # « 13,50€ la bourriche », « à 75€ au lieu de 99€ »
                prix = prix_float(m.group(1))
                m2 = re.search(r"(?i)au lieu de\s*(\d+(?:[.,]\d{1,2})?)\s*€", txt)
                avant = prix_float(m2.group(1)) if m2 else None
            if prix is None and not plan:
                continue
            m = re.search(r"(?i)(\d+(?:[.,]\d{1,2})?)\s*€\s*(?:le|la)\s*(kg|litre)\b", txt)
            unite = ("%s € le %s" % (m.group(1).replace(".", ","), m.group(2).lower())) if m else ""
            img = ((c.get("mobilePicture") or {}).get("url") or (c.get("desktopPicture") or {}).get("url") or "")
            it = {"nom": couper(nom, 70), "marque": couper(marque, 40), "prix": prix, "avant": avant if avant and prix and avant > prix else None,
                  "unite": unite, "detail": couper(txt + " Offre nationale E.Leclerc, dans les magasins participants.", 260),
                  "debut": d1.isoformat(), "fin": d2.isoformat(), "bon_plan": plan, "remise_effective": rem if not prix else None,
                  "op": True, "rayon": rayon(nom, marque, "", "", txt, unite)}
            if img:
                it["image"] = img
            if carte:
                it["carte"] = True
            par_periode.setdefault("tout", []).append(it)
    items = sorted(par_periode.get("tout", []), key=lambda i: (i["debut"], i["fin"]))
    if not items:
        return {}
    # une seule entrée « Offres de la semaine » (pas une par période : elles se répétaient dans l'agenda),
    # chaque offre garde ses jours ; le résumé commence par celles d'aujourd'hui
    a, b = min(i["debut"] for i in items), max(i["fin"] for i in items)
    def quand(i):
        if i["debut"] <= jour:
            return "jusqu'au %s" % date.fromisoformat(i["fin"]).strftime("%d/%m")
        return "dès le %s" % date.fromisoformat(i["debut"]).strftime("%d/%m")
    ordre = sorted(items, key=lambda i: (i["debut"] > jour, _lec_jours(i["fin"], i["debut"]) > 10, i["fin"], i["debut"]))
    resume = " · ".join(dict.fromkeys("%s %s (%s)" % (i["nom"], i["bon_plan"] or euro(i["prix"]), quand(i)) for i in ordre))
    cid = "lecsem-%s-%s" % (a.replace("-", ""), b.replace("-", "")[4:])
    sortie = {cid: ({"chaine": "leclerc", "titre": "Offres de la semaine E.Leclerc", "debut": a, "fin": b, "pages": None,
                     "operation": True, "type": "LECLERC", "src": "lec", "lien": LEC_SEMAINE_PAGE, "resume": couper(resume, 220),
                     "images": [i["image"] for i in ordre if i.get("image")][:6]}, items)}
    return sortie


def _lec_veille(ancien, cid, jour):
    """Offres d'un catalogue Leclerc officiel d'hier (site injoignable aujourd'hui)."""
    anc_cats = ancien.get("catalogues") or {}
    if "_offres" not in ancien:
        ancien["_offres"] = etendre(ancien.get("offres") or [], anc_cats)
    return [dict(o, catalogue=cid, remise_effective=o.get("remise") if o.get("condition") or o.get("op") else None,
                 remise_affichee=o.get("remise_2e")) for o in ancien["_offres"] if o["cat"] == cid and (o.get("fin") or "9") >= jour]


def leclerc_officiel(magasins, zones, cats, brutes, cfg, log, aujourd, ancien=None):
    """Ajoute les produits des catalogues Leclerc (site officiel) et les offres de la semaine.
    Un catalogue que bonial a déjà (mêmes dates, même nombre de pages) garde son identifiant et ses pages,
    et prend les produits officiels à la place des siens ; les autres deviennent des catalogues du magasin."""
    jour, dans7 = aujourd.isoformat(), (aujourd + timedelta(days=7)).isoformat()
    etat = charger_json(LEC_ETAT, {})
    officiels = lec_magasins(str(cfg.get("departement", "85")), etat, log, aujourd)
    lien = lec_associer(magasins, officiels)
    graines = list(etat.get("graines") or [])
    infos, produits, pages_doc, vus, remplaces, nouveaux = {}, {}, {}, [], set(), {}
    ancien = ancien or {}
    anc_cats = ancien.get("catalogues") or {}
    anc_mags = {x["id"]: x for x in ancien.get("magasins") or []}
    n_mag = 0
    for sid, mo in sorted(lien.items()):
        m = magasins[sid]
        lst = lec_catalogues(mo, graines, log)
        if lst is None:  # site injoignable : les catalogues de la veille pour ce magasin
            m["catalogues"] = [c for c in (anc_mags.get(sid) or {}).get("catalogues") or []
                               if (anc_cats.get(c) or {}).get("fin", "") >= jour]
            for cid in m["catalogues"]:
                if cid not in cats:
                    cats[cid] = {k: v for k, v in anc_cats[cid].items() if k != "n"}
                    nouveaux[cid] = _lec_veille(ancien, cid, jour)
            continue
        n_mag += 1
        z = zones.get(m.get("zone")) or {}
        m["catalogues"] = []
        for x in sorted(lst, key=lambda y: y["op"]):
            vus.append((x["fin"] or "", x["op"]))
            if not x["debut"] or not x["fin"] or x["fin"] < jour or x["debut"] > dans7:
                continue
            if _lec_jours(x["fin"], x["debut"]) > 120 or LEC_IGNORES.search(norm(x["nom"])):
                continue
            cle = x["op"] + "|" + x["doc"]
            if cle not in infos:
                infos[cle] = lec_json("%s/%s/%s" % (LEC_API, x["op"], mo["code"]), log) or {}
                time.sleep(0.3)
            info = infos[cle]
            pages = int(_lec_nombre(info.get("pageCount")) or 0)
            titre = _lec_titre(info, x["nom"])
            jumeau = None
            for cid in z.get("catalogues", []):
                c = cats.get(cid) or {}
                if c.get("chaine") != "leclerc" or c.get("src") == "lec" or not c.get("debut"):
                    continue
                if abs(_lec_jours(c["debut"], x["debut"])) <= 1 and abs(_lec_jours(c["fin"], x["fin"])) <= 1 and \
                        (not pages or not c.get("pages") or c.get("type") == "DYNAMIC" or abs(c["pages"] - pages) <= max(4, pages // 5)):
                    jumeau = cid
                    break
            doc = x["doc"]
            if doc not in produits:
                pr = lec_json("%s/document/%s/products" % (LEC_API, doc), log)
                produits[doc] = pr if isinstance(pr, list) else []
                time.sleep(0.3)
            est_alim = bool(info.get("is_food"))
            items = [it for it in (offre_leclerc(p, x, est_alim) for p in produits[doc] if isinstance(p, dict)) if it]
            lien_cat = "%s/catalog/%s/%s" % (LEC_SITE, x["op"], mo["code"])
            if jumeau:
                cats[jumeau].setdefault("lien", lien_cat)
                if items and jumeau not in remplaces:
                    remplaces.add(jumeau)
                    nouveaux[jumeau] = items
                continue
            cid = "lec-%s-%s" % (x["op"].lower(), doc[:8])
            if cid not in cats:
                d1, d2 = date.fromisoformat(x["debut"]), date.fromisoformat(x["fin"])
                cats[cid] = {"chaine": "leclerc", "titre": titre, "debut": x["debut"], "fin": x["fin"], "pages": pages or None,
                             "operation": est_operation(titre, d1, d2), "type": "LECLERC", "src": "lec", "lien": lien_cat,
                             "complet": True}
                if doc not in pages_doc:
                    pl = lec_json("%s/document/%s/pages" % (LEC_API, doc), log)
                    pl = [y for y in pl if isinstance(y, dict) and y.get("source")] if isinstance(pl, list) else []
                    pages_doc[doc] = [y["source"] for y in sorted(pl, key=lambda y: _lec_nombre(y.get("index")) or 0)]
                    time.sleep(0.3)
                if pages_doc[doc]:
                    cats[cid]["_pages"] = pages_doc[doc]
                nouveaux[cid] = items
            if cid not in m["catalogues"]:
                m["catalogues"].append(cid)
    if remplaces:
        brutes = [b for b in brutes if b.get("catalogue") not in remplaces]
    total = 0
    for cid, items in nouveaux.items():
        for it in items:
            it["chaine"], it["catalogue"] = "leclerc", cid
        brutes += items
        total += len(items)
    # offres de la semaine : nationales, pour tous les magasins Leclerc
    try:
        sem = lec_semaine(log, aujourd)
    except Exception as e:
        log("   ! offres de la semaine E.Leclerc : %s" % e)
        sem = {}
    if not sem:  # page injoignable : celles de la veille encore valables
        sem = {cid: ({k: v for k, v in c.items() if k != "n"}, _lec_veille(ancien, cid, jour))
               for cid, c in anc_cats.items() if cid.startswith("lecsem-") and c.get("fin", "") >= jour}
    for cid, (c, items) in sem.items():
        cats[cid] = c
        for it in items:
            it["chaine"], it["catalogue"] = "leclerc", cid
        brutes += items
        for z in zones.values():
            if z.get("chaine") == "leclerc" and cid not in z["catalogues"]:
                z["catalogues"].append(cid)
    if vus:  # graines pour demain : les catalogues qui durent le plus longtemps
        etat["graines"] = [op for _, op in sorted(set(vus), reverse=True)][:6]
    etat["maj"] = jour
    ecrire_json(LEC_ETAT, etat)
    log("E.Leclerc (site officiel) : %d/%d magasins, %d produits de catalogue (%d catalogues complétés, %d ajoutés), "
        "%d offres de la semaine" % (n_mag, len(lien), total, len(remplaces), len(nouveaux) - len(remplaces),
                                     sum(len(v[1]) for v in sem.values())))
    return brutes


# --------------------------------------------------------------------------- catalogues & calendrier
MOTS_OPE = ("jeudi", "vendredi", "samedi", "week", "carte", "flash", "inratable", "prix bas", "black", "foire",
            "anniversaire", "jours", "%")


def est_operation(titre, debut, fin):
    t = norm(titre)
    duree = (fin - debut).days + 1 if debut and fin else 99
    return duree <= 5 or "%" in titre or any(norm(k) in t for k in MOTS_OPE if k != "%")


def ecrire_ics(evenements, chemin, nom_cal="Mogette", extras=()):
    """Calendrier à s'abonner sur le téléphone : un événement par catalogue / opération, avec alerte à 9 h.
    extras : événements en plus (alertes produits surveillés) : dicts uid, jour (date), resume, desc."""
    def e(t):
        return str(t).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mogette//FR", "CALSCALE:GREGORIAN",
              "X-WR-CALNAME:" + nom_cal, "X-WR-TIMEZONE:Europe/Paris", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
              "X-PUBLISHED-TTL:PT12H"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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
        evt(uid, d1, resume, quand + " Ouvre l'appli Mogette pour le détail.")
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
    (r"Action", "action", "Action", "action"),
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
        for x in ("carte", "des", "image", "op", "img", "en_ligne", "ph", "ean"):
            if it.get(x):
                e[x] = it[x]
        if isinstance(it.get("page"), int) and cat != "*":
            e["pg"] = it["page"]  # page du catalogue (0 = couverture) : lien « voir dans le catalogue »
        vus[cle] = e
        sortie.append(e)
    # un produit que les mots-clés ne classent pas prend le rayon de son catalogue quand celui-ci est presque
    # entièrement dans un même rayon non alimentaire (catalogue jouets : « Skyjo », « Hitster », « Peekimo »…)
    compte = {}
    for e in sortie:
        if e["cat"] != "*" and e["rayon"] != "Autres":
            c = compte.setdefault(e["cat"], {})
            c[e["rayon"]] = c.get(e["rayon"], 0) + 1
    for e in sortie:
        c = compte.get(e["cat"])
        if e["rayon"] != "Autres" or not c or e.get("op") or norm(e["nom"]) == norm(e["marque"]):
            continue
        r = max(c, key=c.get)
        if r not in RAYONS_ALIMENTAIRES and r != "Boissons" and c[r] >= 20 and c[r] >= 0.6 * sum(c.values()):
            e["rayon"] = r
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
                for k in ("complet", "images", "resume", "vp"):
                    if anciens[cid].get(k):
                        c[k] = anciens[cid][k]
                if anciens[cid].get("op_debut"):
                    c["debut"], c["fin"] = anciens[cid]["op_debut"], anciens[cid]["op_fin"]
            continue
        offres, images, pages = res
        if any(pages):
            c["_pages"] = pages
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


VIDES_SIG = set("de du des la le les l d au aux a et en avec pour x".split())


def _signature(o):
    mots = sorted(set(w for w in norm(re.sub(r"(?i)\(?\s*\"?\s*lot\s+de\s+\d+\s*\"?\s*\)?", " ", o.get("nom") or "")).split()
                      if w not in VIDES_SIG))
    return " ".join(mots)


def _marques_compatibles(a, b):
    x = [w for w in norm(a.get("marque")).split() if not w.isdigit() and w != "et"]
    y = [w for w in norm(b.get("marque")).split() if not w.isdigit() and w != "et"]
    jx, jy = "".join(x), "".join(y)  # « Silvercrest » / « Silver Crest »
    return not x or not y or set(x) <= set(y) or set(y) <= set(x) or jx in jy or jy in jx  # absente d'un côté, « Clément 40 »


def _lot(o):
    m = re.search(r"(?i)lot\s+de\s+(\d+)", o.get("nom") or "")
    return max(1, int(m.group(1))) if m else 1


def sans_doublons(liste, jour=None):
    """Une même offre une seule fois par magasin (même logique que l'appli) : même produit (mots du nom), marque
    identique ou absente d'un côté, jours communs, même prix à l'unité ; une ligne d'anti-crise (« lot de 2 »)
    commencée à quelques jours près cède la place au catalogue."""
    jour = jour or date.today().isoformat()
    note = lambda p: (8 if (p.get("debut") or "") <= jour else 0) + (4 if p.get("cat") != "*" else 0) + \
        (2 if p.get("img") or p.get("ph") else 0) + (1 if p.get("pg") is not None else 0) + (1 if _lot(p) == 1 else 0) + \
        (1 if p.get("marque") else 0)
    par, garde = {}, []
    for o in liste:
        if o.get("op"):
            garde.append(o)
            continue
        l = par.setdefault(_signature(o), [])
        trouve = None
        for i, x in enumerate(l):
            if (x.get("fin") and o.get("debut") and o["debut"] > x["fin"]) or (o.get("fin") and x.get("debut") and x["debut"] > o["fin"]):
                continue
            if not _marques_compatibles(x, o):
                continue
            if x.get("cat") == "*" or o.get("cat") == "*":
                if not x.get("debut") or not o.get("debut") or abs(_lec_jours(x["debut"], o["debut"])) <= 3:
                    trouve = i
                    break
                continue
            p1 = x["prix"] / _lot(x) if x.get("prix") is not None else None
            p2 = o["prix"] / _lot(o) if o.get("prix") is not None else None
            if (p2 is None and norm(x.get("bon_plan")) == norm(o.get("bon_plan"))) if p1 is None else \
                    (p2 is not None and abs(p1 - p2) <= 0.02 * max(p1, p2) + 0.01):
                trouve = i
                break
        if trouve is None:
            l.append(o)
            garde.append(o)
            continue
        a = l[trouve]
        if note(o) > note(a):
            l[trouve] = o
            garde[garde.index(a)] = o
    return garde


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
        ok = set(z.get("catalogues", [])) | set(m.get("catalogues") or [])  # + catalogues propres au magasin
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
        mes = sans_doublons(mes, aujourd)
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
    return _off_notes(best) if best else None


def _off_notes(best):
    """Fiche Open Food Facts -> {c, n, ns, nv, gs} (None sans Nutri-Score ni NOVA)."""
    if not _note_valeur(best.get("nutriscore_grade"), ("a", "b", "c", "d", "e")) and best.get("nova_group") not in (1, 2, 3, 4):
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


OFF_PRODUIT = ("https://world.openfoodfacts.org/api/v2/product/%s"
               "?fields=code,product_name,product_name_fr,brands,nutriscore_grade,nova_group,ecoscore_grade")


def _off_produit(ean):
    """Produit Open Food Facts par son code-barres (offres Leclerc) : pas de doute sur le produit."""
    req = urllib.request.Request(OFF_PRODUIT % ean, headers={"User-Agent": OFF_UA, "Accept": "application/json",
                                                             "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            brut = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                brut = gzip.decompress(brut)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # pas dans la base
            return None
        raise
    h = json.loads(brut.decode("utf-8")).get("product") or {}
    return _off_notes(h) if h else None


def noter_offres(offres, log, aujourd=None):
    """Ajoute aux offres alimentaires de marque : ns (Nutri-Score), nv (NOVA), gs (Green-Score), off (code), offn (produit)."""
    jour = (aujourd or date.today()).isoformat()
    cache = charger_json(NOTES, {})
    a_faire, par_cle = {}, {}
    for o in offres:
        if o.get("rayon") not in RAYONS_NOTES:
            continue
        marque, nom = (o.get("marque") or "").strip(), (o.get("nom") or "").strip()
        if not nom or re.match(r"(?i)\s*(sur\s+)?(toute la gamme|toutes? les|tous les|tout le|toute la|gamme)\b", nom) or o.get("op"):
            continue
        if o.get("rayon") == "Boissons" and RE_ALCOOL.search(norm(nom + " " + (o.get("detail") or "")) + " " + nom):
            continue  # pas de Nutri-Score pour l'alcool
        if o.get("ean"):  # code-barres connu (catalogue Leclerc) : recherche directe
            cle = "ean:" + o["ean"]
            par_cle.setdefault(cle, []).append(o)
            e = cache.get(cle)
            age = (date.fromisoformat(jour) - date.fromisoformat(e["t"])).days if e and e.get("t") else 999
            if (not e or age > (45 if e.get("ns") or e.get("nv") else 14)) and cle not in a_faire:
                a_faire[cle] = ("ean", o["ean"])
            continue
        if not marque or norm(nom) == norm(marque):
            continue
        mots = _off_mots(nom, marque)
        if not mots:
            continue
        cle = norm(marque) + "|" + " ".join(mots)
        par_cle.setdefault(cle, []).append(o)
        e = cache.get(cle)
        age = (date.fromisoformat(jour) - date.fromisoformat(e["t"])).days if e and e.get("t") else 999
        if (not e or age > (45 if e.get("ns") or e.get("nv") else 14)) and cle not in a_faire:
            a_faire[cle] = ("txt", mots, nom, marque)
    faits, trouves, erreurs, n_ean, stop_ean = 0, 0, 0, 0, False
    for cle, tache in a_faire.items():
        if faits >= NOTES_LIMITE or erreurs >= 6:
            break
        if tache[0] == "ean" and (stop_ean or n_ean >= 300):
            continue  # fiches par code-barres : 300 par jour au plus, la suite le lendemain
        try:
            if tache[0] == "ean":
                n_ean += 1
                r = _off_produit(tache[1])
                time.sleep(0.75)  # fiche produit : 100 demandes par minute au plus chez Open Food Facts
            else:
                r = _off_meilleur(_off_chercher(tache[1], tache[2], tache[3], log), tache[1], tache[3])
            erreurs = 0
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and tache[0] == "ean":
                stop_ean = True  # trop de demandes : les codes-barres restants attendent demain
                log("   ! Open Food Facts : trop de demandes, les fiches par code-barres restantes attendent demain")
                continue
            erreurs += 1
            if erreurs == 1:
                log("   ! Open Food Facts : %s" % ex)
            time.sleep(2)
            continue
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


# --------------------------------------------------------------------------- horaires manquants (OpenStreetMap)
# Bonial n'a pas les horaires de certains magasins (Carrefour Proximité…). OpenStreetMap les a souvent :
# une seule demande par semaine à l'API Overpass (données © contributeurs OpenStreetMap, licence ODbL).
OSM_CACHE = os.path.join(DATA, "horaires_osm.json")
OSM_API = "https://overpass-api.de/api/interpreter"
JOURS_OSM = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
NUM_BONIAL = {"Mo": 2, "Tu": 3, "We": 4, "Th": 5, "Fr": 6, "Sa": 7, "Su": 1}  # bonial : 1 = dimanche … 7 = samedi


def horaires_osm(txt):
    """Comprend les formes courantes d'opening_hours (« Mo-Sa 08:30-19:30; Su 09:00-12:30 », « 24/7 »…).
    Rend [[jour bonial, minute début, minute fin], …], ou None pour une forme inconnue (saisons, exceptions) :
    mieux vaut pas d'horaires que des horaires faux."""
    t = (txt or "").strip()
    if t == "24/7":
        return [[NUM_BONIAL[j], 0, 1440] for j in JOURS_OSM]
    res = {}
    for regle in [r.strip() for r in t.split(";") if r.strip()]:
        if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|easter|SH)\b", regle) and regle.endswith(("off", "closed")):
            continue  # fermetures exceptionnelles (« Dec 25 off ») : sans effet sur la semaine type
        m = re.match(r"^((?:Mo|Tu|We|Th|Fr|Sa|Su|PH)(?:\s*[-,]\s*(?:Mo|Tu|We|Th|Fr|Sa|Su|PH))*)\s+(.+)$", regle)
        if not m:
            return None
        jours = []
        for morceau in m.group(1).split(","):
            morceau = morceau.strip()
            if morceau == "PH":  # jours fériés : ignorés
                continue
            if "-" in morceau:
                a, b = [x.strip() for x in morceau.split("-")]
                if a not in JOURS_OSM or b not in JOURS_OSM:
                    return None
                i, k = JOURS_OSM.index(a), JOURS_OSM.index(b)
                jours += JOURS_OSM[i:k + 1] if i <= k else JOURS_OSM[i:] + JOURS_OSM[:k + 1]
            else:
                jours.append(morceau)
        if not jours:
            continue
        plages = m.group(2).strip()
        if plages in ("off", "closed"):
            for j in jours:
                res[j] = []
            continue
        tranches = []
        for pl in plages.split(","):
            mm = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", pl.strip())
            if not mm:
                return None
            d, f = int(mm.group(1)) * 60 + int(mm.group(2)), int(mm.group(3)) * 60 + int(mm.group(4))
            if f <= d:
                f = 1440  # ferme après minuit
            tranches.append([d, min(f, 1440)])
        for j in jours:
            res[j] = tranches  # une règle plus loin remplace la précédente, comme dans OpenStreetMap
    out = [[NUM_BONIAL[j], d, f] for j in JOURS_OSM for d, f in res.get(j, [])]
    return out or None


def lire_osm(log, aujourd):
    cache = charger_json(OSM_CACHE, {})
    # Action est rangé dans les « variety_store » (bazars) sur la carte, pas dans les supermarchés
    requete = ('[out:json][timeout:90];area["ISO3166-2"="FR-85"]->.v;'
               'nwr(area.v)["shop"~"^(supermarket|convenience|variety_store)$"]["opening_hours"];out center tags;')
    if cache.get("date", "") >= (aujourd - timedelta(days=7)).isoformat() and cache.get("lieux") and cache.get("q") == requete:
        return cache["lieux"]
    req = urllib.request.Request(OSM_API, data=urllib.parse.urlencode({"data": requete}).encode(),
                                 headers={"User-Agent": "Mogette/1.0 (appli de promos, github.com/ansquerdylan-arch/mes-promos)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            elements = json.loads(r.read().decode("utf-8")).get("elements") or []
    except Exception as e:
        log("   OpenStreetMap injoignable (%s) : horaires de la semaine dernière gardés" % e)
        return cache.get("lieux") or []
    lieux = []
    for el in elements:
        tags = el.get("tags") or {}
        lat, lng = el.get("lat") or (el.get("center") or {}).get("lat"), el.get("lon") or (el.get("center") or {}).get("lon")
        if lat and lng and tags.get("opening_hours"):
            lieux.append({"lat": lat, "lng": lng, "nom": norm(" ".join(tags.get(k, "") for k in ("brand", "name"))), "oh": tags["opening_hours"]})
    ecrire_json(OSM_CACHE, {"date": aujourd.isoformat(), "q": requete, "lieux": lieux})
    return lieux


# enseignes de proximité d'un même groupe : un « Carrefour Proximité » s'appelle souvent « Carrefour Contact » ou « 8 à Huit » sur la carte
FAMILLES_OSM = {"carrefour": ["carrefour", "8 a huit", "proxi"]}


def mots_famille(nom):
    n = norm(nom)
    for cle, mots in FAMILLES_OSM.items():
        if cle in n.split():
            return mots
    return [w for w in n.split() if len(w) > 2 and w not in ("express", "city", "contact", "proximite", "market")][:1] or n.split()[:1]


def meme_adresse(a, b):
    """« 7 Quai de Franqueville » et « 7 quai de Franqueville » : même numéro et au moins un mot de rue en commun."""
    na, nb = norm(a), norm(b)
    num = lambda t: (re.findall(r"\b\d+\b", t) or [""])[0]
    mots = lambda t: {w for w in t.split() if len(w) > 3 and not w.isdigit()}
    return num(na) == num(nb) and bool(mots(na) & mots(nb))


def completer_horaires(magasins, log, aujourd=None):
    """Horaires OpenStreetMap pour les magasins que Bonial donne sans horaires : même enseigne à moins de 250 m,
    ou jusqu'à 1 km si aucun autre magasin de l'enseigne n'est plus près (les positions Bonial sont parfois approximatives)."""
    manquent = [m for m in magasins.values() if not m.get("horaires") and m.get("lat") and m.get("lng")]
    if not manquent:
        return
    lieux = lire_osm(log, aujourd or date.today())
    trouves = 0
    for m in manquent:
        mots = mots_famille(m.get("nom"))
        meme = [x for x in magasins.values() if x.get("lat") and x.get("lng") and mots_famille(x.get("nom")) == mots]
        voisins = [x for x in meme if x is not m and distance_km((m["lat"], m["lng"]), (x["lat"], x["lng"])) < 0.03]
        # même magasin listé sous deux noms (« Carrefour Contact » et « Carrefour Proximité », même adresse) : ses horaires Bonial
        jumeau = [x for x in voisins if x.get("horaires") and not x.get("horaires_src") and meme_adresse(m.get("adresse"), x.get("adresse"))]
        if jumeau:
            m["horaires"] = jumeau[0]["horaires"]
            trouves += 1
            continue
        if any(not meme_adresse(m.get("adresse"), x.get("adresse")) for x in voisins):
            continue  # plusieurs magasins placés au même point (centre-ville) : position pas fiable, on ne devine pas
        cands = []
        for l in lieux:
            if any((" %s " % w) in (" %s " % l["nom"]) for w in mots):
                d = distance_km((m["lat"], m["lng"]), (l["lat"], l["lng"]))
                if d <= 1.0:
                    cands.append((d, l))
        choix = None
        for d, l in sorted(cands, key=lambda x: x[0]):
            if d <= 0.25 or min(distance_km((x["lat"], x["lng"]), (l["lat"], l["lng"])) for x in meme) >= d - 0.03:
                choix = l
                break
        h = horaires_osm(choix["oh"]) if choix else None
        if h:
            m["horaires"] = h
            m["horaires_src"] = "osm"
            trouves += 1
    log("Horaires manquants : %d magasin(s) complété(s) sur %d (même adresse chez Bonial ou OpenStreetMap)" % (trouves, len(manquent)))


# --------------------------------------------------------------------------- historique des prix
CODES = os.path.join(DATA, "codes.json")


def mettre_codes(promos):
    """Code-barres -> produits vus en promo (clés de l'historique) : la fiche d'un article scanné retrouve ses promos passées.
    « ean » vient de l'enseigne (sûr, noté « s »), « off » du produit Open Food Facts trouvé par son nom (probable)."""
    h = charger_json(HISTORIQUE, {})
    c = charger_json(CODES, {})
    for p in promos:
        if p.get("prix") is None:
            continue
        cle = p.get("chaine", p.get("enseigne")) + "|" + norm(p["nom"]) + "|" + norm(p.get("marque"))
        for champ in ("ean", "off"):
            code = str(p.get(champ) or "").lstrip("0")
            if len(code) < 7 or not code.isdigit():
                continue
            e = c.setdefault(code, {"n": p["nom"], "m": p.get("marque") or "", "k": []})
            if cle not in e["k"]:
                e["k"] = (e["k"] + [cle])[-8:]
            if champ == "ean":
                e["s"] = 1
    for code in list(c):  # ce que l'historique a oublié, on l'oublie aussi
        c[code]["k"] = [k for k in c[code]["k"] if k in h]
        if not c[code]["k"]:
            del c[code]
    ecrire_json(CODES, c)


def mettre_historique(promos, aujourd):
    h = charger_json(HISTORIQUE, {})
    jour = aujourd.isoformat()
    limite = (aujourd - timedelta(days=400)).isoformat()
    semaine = (aujourd - timedelta(days=6)).isoformat()
    # un même produit peut avoir deux prix le même jour (deux magasins de l'enseigne, deux formats au même nom) :
    # on garde le plus bas du jour, sinon la courbe ferait des allers-retours d'un jour à l'autre
    du_jour, cles = {}, []
    for p in promos:
        if p.get("prix") is None:
            continue
        cle = p.get("chaine", p.get("enseigne")) + "|" + norm(p["nom"]) + "|" + norm(p.get("marque"))
        cles.append((p, cle))
        prix = round(float(p["prix"]), 2)  # certains sites donnent 1111.4000244 pour 1111,40 €
        if cle not in du_jour or prix < du_jour[cle]:
            du_jour[cle] = prix
    for p, cle in cles:
        # infos pour l'appli : prix vus avant cette semaine
        avant = [x for x in h.get(cle, []) if limite <= x[0] < semaine]
        if avant:
            mini = min(avant, key=lambda x: x[1])
            p["histo"] = {"min": mini[1], "min_date": mini[0], "fois": len({x[0][:7] for x in avant}) + 1}
    for cle, prix in du_jour.items():
        lst = [x for x in h.get(cle, []) if x[0] >= limite]
        if lst and lst[-1][0] == jour:
            lst[-1][1] = min(lst[-1][1], prix)  # deuxième passage le même jour
        elif not lst or lst[-1][1] != prix or lst[-1][0] < semaine:
            lst.append([jour, prix])
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
            if c.get("fin", "") >= jour and c.get("src") != "lec":  # Leclerc officiel : relu plus bas
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
    try:  # E.Leclerc : produits des catalogues et offres de la semaine, sur le site officiel
        brutes = leclerc_officiel(magasins, zones, cats, brutes, cfg, log, aujourd, ancien)
    except Exception as e:
        log("E.Leclerc (site officiel) non lu : %s" % e)

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
    try:
        completer_horaires(magasins, log, aujourd)
    except Exception as e:
        log("Horaires OpenStreetMap ignorés : %s" % e)
    resultat = {"v": 2, "maj": datetime.now().isoformat(timespec="seconds"), "ville": dom.get("ville", ""),
                "departement": str(cfg.get("departement", "85")), "domicile": dom, "chaines": chaines,
                "zones": zones, "magasins": sorted(magasins.values(), key=lambda m: (m["ville"], m["nom"])),
                "catalogues": cats, "offres": offres, "defaut": defaut}

    if not offres:
        log("Aucune promo trouvée (connexion internet ? site changé ?). Les promos actuelles sont gardées.")
        return ancien
    try:
        mettre_historique(offres, aujourd)
        mettre_codes(offres)
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
    # pages de chaque catalogue (images) : l'appli les feuillette, même quand bonial n'en donne pas les produits
    dpages = os.path.join(DATA, "pages")
    os.makedirs(dpages, exist_ok=True)
    for cid, c in cats.items():
        pg = c.pop("_pages", None)
        if pg:
            ecrire_json(os.path.join(dpages, cid + ".json"), pg)
            c["vp"] = len(pg)
        elif c.get("vp") and not os.path.exists(os.path.join(dpages, cid + ".json")):
            c.pop("vp", None)
    for f in os.listdir(dpages):
        if f.endswith(".json") and not cats.get(f[:-5], {}).get("vp"):
            os.remove(os.path.join(dpages, f))
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
