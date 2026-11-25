#!/usr/bin/env python3
"""Histoire des prix, pour « Remonter le temps » sur la fiche d'un article de Mogette.

Sources ouvertes de l'INSEE (service web SDMX gratuit) :
- indices des prix à la consommation, base 2025, France entière, ensemble des ménages : moyennes de chaque année
  depuis 1996 et dernier mois connu, pour chaque type de produit (nomenclature COICOP 2018) ;
- montant du SMIC horaire brut, chaque mois depuis 1996.
Relu une fois par semaine par la mise à jour du matin (les autres jours, rien n'est téléchargé).
Écrit histoire.json à côté des promos : pour chaque type de produit utile, son nom et ses indices, puis les règles
qui rangent un article dans un type d'après son nom ou son rayon.

Le prix d'une année = prix d'aujourd'hui × indice de l'année ÷ indice du dernier mois. C'est une estimation :
le vrai prix de cet article à l'époque a pu être différent (format, recette, magasin).

    python histoire.py            mise à jour si la dernière a plus de 6 jours
    python histoire.py --forcer   tout de suite
    python histoire.py --essai    tout de suite, avec les types de produits et l'essai sur les promos du jour
"""
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from maj_promos import DATA, charger_json, ecrire_json

FICHIER = os.path.join(DATA, "histoire.json")
SDMX = "https://bdm.insee.fr/series/sdmx"
UA = "Mogette/1.0 (appli de promos, github.com/ansquerdylan-arch/mes-promos)"
VERSION = 1         # format de histoire.json : un changement relit l'INSEE tout de suite
TOUS_LES = 6        # jours entre deux lectures
DEBUT = 1996        # les indices en base 2025 remontent à 1996
SMIC = "000822484"  # Montant du SMIC brut horaire, mensuel

# Types de produits (codes COICOP 2018 de l'INSEE). Le premier motif qui va avec le nom de l'article l'emporte.
# Les motifs portent sur le nom en minuscules, sans accents (comme normPy dans l'appli). Un code sans série à
# l'INSEE est remplacé par le type plus large qui le contient.
# Un troisième élément limite la règle : « a » aux rayons alimentaires (et boissons), « n » aux autres rayons,
# ou une liste de rayons séparés par « | ». Le rayon « Autres » et un rayon inconnu passent partout.
# Code None : pas d'estimation (électronique, jeux vidéo, coffrets cadeaux : l'INSEE compte les progrès techniques,
# le « même » téléviseur n'existait pas en 1996).
REGLES = [
    # ========== d'abord les mots sans ambiguïté, quel que soit le rayon (les rayons de Mogette se trompent parfois)
    (r"shampo|gel douche|dentifrice|deodorant|anti ?transpirant|brosses? a dents?|bain de bouche|papier (toilette|hygienique)|serviettes? hygieniques|"
     r"protege ?slips?|pampers|huggies|mousse a raser|eau micellaire|demaquillant", "13120"),
    (r"lessiv|adoucissant|assouplissant|liquide vaisselle|(tablettes?|capsules?|pastilles?|gel|poudre) (pour )?lave ?(vaisselle|linge)|"
     r"nettoyant (wc|sol|vitres|multi|cuisine|salle de bain|menager)|\bjavel\b|deboucheur|detachant", "05611"),
    (r"lave ?glace|antigel|lave vitre auto|liquide de refroidissement|ninebot|segway|trottinette electrique", None),

    # ========== rayons non alimentaires
    (r"\bcroquettes|\bpatees?\b|litiere|friandises?|\b(chiens?|chats?|chatons?|chiots?|oiseaux|rongeurs?|lapins?|poissons?)\b|terrine|mousse|sachets?|bouchees|emince|boules? de graisse|graines|mangeoires?", "09322", "Animaux"),
    (r"whiskas|\bfelix\b|purina|pedigree|\bsheba\b|friskies|royal canin|gourmet (gold|perle|mon petit)|catisfactions|dreamies|perfect fit|"
     r"croquettes? (pour )?(petits? )?(chiens?|chats?|chatons?|chiots?)|patees? (pour )?(chiens?|chats?)|litiere|arbre a chat|griffoir|"
     r"(gamelle|panier|coussin|jouet|os a macher|laisse|harnais|niche) (pour )?(chiens?|chats?)|collier (anti|pour chien|pour chat)|pour (chiens?|chats?|chatons?|chiots?)\b", "09322"),
    (r"jeux? video|consoles?|playstation|\bps[45]\b|xbox|nintendo|\bswitch\b|jeu (ps[45]|switch|xbox|pc)|manettes?|steelbook|amiibo|carte (psn|xbox|nintendo)", None, "n"),
    (r"livres?\b|\bbd\b|bandes? dessinees?|mangas?|romans?|\btomes?\b|albums? (photo|souvenir|jeunesse|illustre)|dictionnaires?|atlas|guides? (de voyage|pratique)|"
     r"cahiers? d activites|livre (sonore|puzzle|anime)|encyclopedie|asterix", "09719", "n"),
    (r"jouets?|lego|duplo|playmobil|poupees?|poupons?|peluches?|doudous?|puzzles?|jeux? de societe|jeu (de|d) (construction|cartes|adresse|plateau|role|ambiance|strategie|memoire)|"
     r"jeux? educatifs?|voitures? (telecommandee|miniature|radiocommandee|de course|a pedales|electrique)|circuits?|dinettes?|barbie|hot wheels|"
     r"\bnerf\b|pate a modeler|play ?doh|loisirs creatifs|kits? creatifs?|draisiennes?|tricycles?|porteurs?|toboggans?|balancoires?|portique|cartes? (pokemon|a jouer|a collectionner)|"
     r"pokemon|meccano|vtech|fisher price|smoby|clementoni|ravensburger|hasbro|mattel|bandai|canal toys|lansay|spin master|gabby|paw patrol|pat patrouille|"
     r"monopoly|\buno\b|cluedo|scrabble|trivial|dobble|mille bornes|puissance 4|jenga|kapla|skyjo|deguisements?|baguette magique|pistolets? a eau|"
     r"maison de poupee|toupies?|slime|kinetic sand|bulles de savon|cerf volant|marionnettes?|quad electrique|moto (cross )?electrique|\bl o l\b|"
     r"tables? de jeux|jeux? \d+ en 1|radiocommande|telecommande|echecs|billard|baby ?foot|flechettes", "09212", "n"),
    (r"cahiers?|stylos?|crayons?|feutres?|classeurs?|trousses?(?! de toilette)|agendas?|calendriers?(?! de l avent)|papier (a dessin|imprimante|canson)|ramettes?|enveloppes?|post ?it|"
     r"surligneurs?|gommes?|\bregles?\b|compas|equerres?|protege ?cahiers?|pochettes?|ardoise|peinture (enfant|gouache|acrylique)|pinceaux?|gouache|aquarelle|"
     r"carnets?|bloc ?notes?|agrafeuses?|perforatrices?|\bbic\b|stabilo|set d art|chevalet|coloriages?", "09740", "n"),
    (r"platines?|tourne ?disques?", None, "n"),
    (r"\bdvd\b|blu ?ray|\bcds?\b|vinyles?", "09520", "n"),
    (r"guitares?|pianos?|ukulele|violon|batterie electronique|instruments? de musique", "09510", "n"),
    (r".", "09212", "Jouets & culture"),
    (r"coffrets? cadeaux?|wonderbox|smartbox|tick ?a ?box|bons? cadeau|cartes? cadeau|diner d exception|sejour|week ?end|escapade|nuit insolite", None, "n"),
    (r"plats? a (buche|tarte|four|gratin|cake|lasagne)|pelle a tarte|beurriers?|batterie de cuisson", "05403", "n"),
    (r"appareil a (raclette|fondue|crepes|gaufres|croque|hot dog|panini)|raclette|grill party|crepiere|gaufrier|fondue|cuiseur", "05321", "n"),
    (r"televiseurs?|television|\btv\b|smart ?tv|\boled\b|\bqled\b|\bqned\b|\bled \d|smartphones?|telephones?|iphone|galaxy|xiaomi|redmi|\boppo\b|\bhonor\b|pixel \d|tablettes?|"
     r"\bipad|ordinateurs?|pc portable|laptop|chromebook|macbook|ecrans? (pc|gamer|gaming|incurve|\d)|moniteurs?|casques?(?! (velo|ski|trottinette|de moto))|"
     r"ecouteurs?|airpods|enceintes?|barres? de son|home cinema|imprimantes?|cles? usb|disques? durs?|\bssd\b|cartes? (memoire|micro sd|sd)|appareils? photo|cameras?|"
     r"camescope|gopro|montres? connectees?|smartwatch|bracelets? connectes?|drones?|videoprojecteur|projecteur(?! led)|box (tv|internet)|chromecast|fire tv|routeurs?|"
     r"webcam|\bsouris\b(?! (d agneau|\d))|claviers?|chargeurs?|cables? (usb|hdmi|lightning)|batterie externe|powerbank|coques?\b|protections? d ecran|radio reveil|\bradio\b|"
     r"lecteur (dvd|blu ray|cd)|talkie|baby ?phone|ecoute bebe|liseuse|kindle|\bgps\b|dashcam|trottinette electrique|hoverboard", None, "n"),
    (r"(tablettes?|capsules?|pastilles?|gel|liquide|poudre|sel|dosettes?|doses?|pods?)( de lavage| regenerant)?( pour)? (lave ?vaisselle|lave ?linge|machine)|"
     r"lave ?vaisselle (tout en|all in|tablettes|capsules|gel|regular|classic)|vaisselle machine|liquide de rincage|anti ?calcaire|desinfectant|nettoyant(?! (vapeur|haute))|"
     r"degraissant|produit vaisselle|lingettes? (multi|menageres|nettoyantes|desinfectantes|sol|vitres|cuisine|salle de bain|meubles)|desodorisant|febreze|air wick|"
     r"parfum d interieur|bloc wc|gel wc|disc wc|fresh disc|canard wc|harpic|destop|\bajax\b|\bcif\b|mr propre|monsieur propre|st marc|saint marc|"
     r"vanish|calgon|soupline|lenor|\bmir\b|\bpaic\b|\bfinish\b|\bsun\b|vigor|insecticide|anti ?moustiques?|anti ?mites|piege a|\braid\b|baygon|plumeau|\bcire\b|"
     r"tampons? (gratte|a recurer|abrasif)|gratte ?eponge|detacheur|vinaigre menager|bicarbonate (menager|de soude)|savon noir|cristaux de soude", "05611", "n"),
    (r"rasoir electrique|tondeuse (barbe|cheveux|corps|nez)|epilateur|seche ?cheveux|lisseur|boucleur|multistyler|air ?wand|airwrap|brosse (a dents )?electrique|brosse soufflante|oral ?b (pro|io|vitality)", "13111", "n"),
    (r"eau de (toilette|parfum|cologne)|eau (thermale|florale)|lait (corporel|de toilette|hydratant|solaire|pour le corps|apres soleil)|"
     r"huile (de massage|seche|pour le corps|corporelle|solaire|capillaire|demaquillante)|cremes?\b|beurre (de karite|corporel)|baume|stick levres|levres|"
     r"apres ?shampo|douche|bain moussant|bombes? de bain|sels? de bain|savons?\b|fil dentaire|"
     r"cotons?\b|carres? coton|coton tiges?|disques? (a )?demaquiller|rasoirs?(?! anti)|lames de rasoir|gel a raser|apres rasage|"
     r"parfums?\b|maquillage|mascara|rouge a levres|vernis|fond de teint|serum|masques? (visage|capillaire|cheveux|tissu)|soins?\b|nail art|"
     r"coloration|color\b|laque|gel coiffant|cire coiffante|lingettes?|couches?\b|culottes? (d apprentissage|bebe|essentiel|pants)|lotus baby|"
     r"mouchoirs|tampons?\b|protections? (intimes|urinaires)|hygiene|incontinence|eryplast|dermophil|nivea|\bdove\b|garnier|l oreal|loreal|sanex|rexona|"
     r"\baxe\b|colgate|\bsignal\b|sensodyne|elmex|gillette|coffret (cosmetique|beaute|soin|parfum|inessance|baignoire|enfant|bain)|langes?|"
     r"calendrier de l avent (cosmetiques?|beaute)|cosmetiques?|vaseline", "13120", "n"),
    (r"aspirateurs?|\baspi\b|hoover|robot (aspirateur|laveur|nettoyeur)|nettoyeur (vapeur|de sols|multi)|laveur de sols|balai (vapeur|electrique|aspirateur)|shark|dyson|tineco", "05314", "n"),
    (r"lave ?linge|seche ?linge|lavante sechante", "05312", "n"),
    (r"cafetieres?|machines? (a cafe|a expresso|a espresso|expresso|espresso|a capsules?|a dosettes?|multi ?boissons|a the|a biere|a gazeifier|a soda)|multi ?boissons|expresso broyeur|"
     r"broyeur a cafe|bouilloires?|theieres? electrique|extracteurs? de jus|centrifugeuses?|presse agrumes|blender|blendeur|mixeurs?|soda ?stream|tireuse|"
     r"tassimo|nespresso|dolce gusto|senseo", "05322", "n"),
    (r"machine a (pain|pates|glaces|barbe)|yaourtiere|sorbetiere|robots? (patissiers?|cuiseurs?|multifonctions?|de cuisine|menagers?|culinaires?)|grille ?pains?|toasters?|"
     r"friteuses?|air ?fryers?|airfryer|cuiseurs?|batteurs?|fouets? electriques?|hachoirs?|moulinette|cookeo|thermomix|monsieur cuisine|companion|plancha|"
     r"barbecue electrique|grills?\b|multicuiseur|autocuiseur electrique|mijoteuse|cuit vapeur|four (a pizza|electrique|posable|mini)|mini four|balance (de )?cuisine|"
     r"croque ?monsieur|panini|\brobot\b|easy ?fry|actifry|glacons", "05321", "n"),
    (r"lave ?vaisselle|refrigerateurs?|frigo|congelateurs?|cave a vin|cuisinieres?|\bfours?\b(?! a (pain|pizza))|micro ?ondes?|plaques? (induction|de cuisson|vitroceramique)|"
     r"tables? (de cuisson|induction)|hottes?|piano de cuisson", "05311", "n"),
    (r"fers? a repasser|centrales? vapeur|defroisseurs?|machines? a coudre|pese ?personnes?|balances? (impedancemetre|connectee|salle de bain)|"
     r"humidificateurs?|purificateurs?|diffuseurs? (d huiles|ultrason)|anti ?bouloches|anti ?peluches", "05329", "n"),
    (r"radiateurs?|chauffages?|(coussin|couverture|sous couverture|plaid|bouillotte) chauffante?|convecteurs?|poeles? (a granules|a petrole|a bois|a pellets)|climatiseurs?|"
     r"climatisation|ventilateurs?|deshumidificateurs?|chauffe ?eau|seche serviettes|panneaux? rayonnants?|chauffe pieds", "05313", "n"),
    (r"serviettes? (de bain|de toilette|eponge|invite)|draps? de bain|peignoirs?|tapis de bain|gants? de toilette|nappes?|torchons?|sets? de table|"
     r"chemins? de table|linge de (table|toilette|maison)|essuie mains|serviettes? (\d|pointe|papier|de table)|\d+ serviettes", "05213", "n"),
    (r"essuie ?tout|sopalin|sacs? (poubelle|congelation|de congelation|cabas|a dechets|aspirateur)|eponges?|serpilleres?|lavettes?|chiffons?|gants? (de menage|menagers|vaisselle)|"
     r"allumettes|allume ?feu|briquets?|\bseaux?\b|balais?\b|pelle et balayette|pinces? a linge|etendoirs?|sechoirs? (a linge)?|panier a linge|"
     r"cintres?|rouleaux? (petit prix|essuie|tendance)|filtres? (a cafe|cafe|a eau)|granules de bois|buches? (de bois|compressees)|bois de chauffage|combustible|combuflam", "05619", "n"),
    (r"plantes? artificielles?|fleurs? artificielles?|orchidees? artificielles?|sapins? (artificiels?|spirale|lumineux|blanc|vert|floque|metal|bougie|led|en|anime)|"
     r"pere noel|boules?\b(?! de (petanque|graisse))|guirlandes?(?! lumineuses?)|cimier|creches?|santons?|couronnes?|suspensions?|sujets?|personnages?|automates?|lutins?|"
     r"village de noel|decorations?|\bdeco\b|decoratifs?|decoratives?|boites? cadeau|papier cadeau|sacs? cadeau|stickers?|crochets? deco|figurines? (de noel|lumineuses?)|"
     r"globes?|bonhommes? de neige|rennes?|cerfs? (lumineux|deco)|nappe rouleau|serviettes? (en papier|joyeux noel|de table)|tapis de neige|centre de table|\bvases?\b|animee?s?|villages?|manege|scenes?", "05114", "n"),
    (r"\bmoules?\b|planche a decouper|emportes? pieces?|poeles?\b|casseroles?|faitouts?|cocottes?|marmites?|sauteuses?|woks?|ustensiles?|spatules?|fouets?\b|louches?|"
     r"ecumoires?|passoires?|essoreuses?|\brapes?\b|eplucheurs?|mandolines?|presse ail|batterie de cuisine|autocuiseur|cuit oeufs|rouleau a patisserie|plaques? a patisserie|"
     r"poches? a douille|tupperware|boites? (de conservation|hermetiques?|a gateaux|a biscuits)|film alimentaire|papier (aluminium|cuisson|sulfurise)|tefal|mastrad|"
     r"le creuset|staub|pyrex|tablier|maniques?|gants? de cuisine|poses? plats?|dessous de plat|\bingenio\b", "05403", "n"),
    (r"couteaux?|couverts|fourchettes?|cuilleres?|menageres? (\d|de couverts)|ciseaux de cuisine|tire ?bouchons?|decapsuleur|aiguiseur|accessoires vin", "05402", "n"),
    (r"verres?\b|flutes?\b|assiettes?|\bbols?\b|mugs?|tasses?|vaisselle|carafes?|saladiers?|plats? (a four|de service|de presentation)|plateaux?|coupelles?|ramequins?|"
     r"theieres?|services? (de table|a the|a cafe|a raclette|a fondue)|pichets?|bocaux|bocal|boites? (repas|lunch|a gouter)|lunch ?box|gourdes?|thermos|bouteilles? isothermes?|"
     r"gobelets?|porcelaine|faience|ronds? de serviette", "05401", "n"),
    (r"chaussures?|baskets?|\bbottes?\b|bottines?|bottillons?|chaussons?|sandales?|\btongs?\b|escarpins?|mocassins?|sneakers?|pantoufles?|derbies|\bboots\b|ballerines?|"
     r"espadrilles?|\bcrocs\b|\bmules?\b|sabots?", "0321", "n"),
    (r"bagues?|colliers?|bracelets?|boucles? d oreilles|creoles?|pendentifs?|chaines? (en or|en argent|plaque)|bijoux?|\bmontres?\b|\bor (jaune|blanc|rose)\b|argent (rhodie|dore)|"
     r"diamants?|plaque or", "13211", "n"),
    (r"bonnets?|echarpes?|\bgants\b|moufles|casquettes?|ceintures?|cravates?|chapeaux?|\bbobs?\b|snoods?|tours? de cou|foulards?|bretelles|parapluies?|lunettes de soleil|cagoules?", "03132", "n"),
    (r"valises?|bagages?|sacs? (a dos|a main|de voyage|bandouliere|de sport|banane|isotherme)|cartables?|trousses? de toilette|portefeuilles?|porte ?monnaie|"
     r"poussettes?|sieges? auto|rehausseurs?|lits? parapluie|chaises? hautes?|transats? bebe|porte bebe|tetines?|biberons?|parc bebe|baignoire bebe|table a langer|"
     r"tapis d eveil|trotteur|sac a langer", "13291", "n"),
    (r"\bpulls?\b|t ?shirts?|tee ?shirts?|\btops?\b|chemises?|chemisiers?|blouses?|pantalons?|\bjeans?\b|joggings?|sweats?|hoodies?|vestes?|manteaux?|blousons?|"
     r"doudounes?|parkas?|impermeables?|robes?|jupes?|\bshorts?\b|bermudas?|leggings?|pyjamas?|nuisettes?|chaussettes?|socquettes|collants?|\bslips?\b|boxers?|"
     r"calecons?|culottes?|shortys?|strings?|soutiens? gorge|brassieres?|lingerie|maillots? (de bain|de corps)|debardeurs?|gilets?|cardigans?|polaires?|"
     r"\bbodys?\b|bodies|grenouilleres?|barboteuses?|combinaisons?|salopettes?|\bpolos?\b|sous ?vetements?|thermiques?|vetements?|ensembles?|snuggie", "0312", "n"),
    (r"rideaux?|voilages?|tissus? d ameublement|\bstores?\b|panneaux? japonais", "05211", "n"),
    (r"couettes?|oreillers?|traversins?|\bdraps?\b(?! de bain)|housses? de couette|parures? de lit|taies?|sur ?matelas|alese|plaids?|couvertures?|jetes? de (lit|canape)|edredon|linge de lit", "05212", "n"),
    (r"coussins?|housses? de coussin|housses? de canape", "05219", "n"),
    (r"\bmatelas\b(?! gonflable)|sommiers?|\blits?\b|tetes? de lit|canapes?|fauteuils?|chaises?|tabourets?|\btables?\b(?! de cuisson)|bureaux?|armoires?|commodes?|"
     r"etageres?|meubles?|bibliotheques?|buffets?|vaisseliers?|dressing|penderie|\bbancs?\b|\bpoufs?\b|chevets?|rangements?|caissons?|colonnes? (de salle de bain|de rangement)|"
     r"portants?|portes? manteaux|pateres?", "05111", "n"),
    (r"salons? de jardin|parasols?|transats?|bains? de soleil|tables? de jardin|chaises? de jardin|fauteuils? de jardin|hamacs?|balancelle|tonnelle|pergola|"
     r"barbecues?|braseros?|kamado|abris? de jardin|serres? de jardin|voile d ombrage", "05112", "n"),
    (r"lampes?(?! (frontale|torche|de poche))|lampadaires?|luminaires?|appliques?|plafonniers?|guirlandes? lumineuses?|veilleuses?|eclairage|bougies? led|projecteurs? led|panneau solaire", "05113", "n"),
    (r"plantes?\b|fleurs?\b|fleuries|bouquets?|\broses\b|rosiers?|orchidees?|poinsettias?|cyclamens?|bulbes?|\bplants?\b|arbustes?|arbres?(?! a chat)|bonsai|cactus|"
     r"succulentes?|chrysanthemes?|hortensias?|lavandes?|oliviers?|palmiers?|sapins?|nordmann|epicea|houx|\bgui\b|azalees?|bruyeres?|pensees?|primeveres?|jacinthes?|"
     r"amaryllis|compositions?|etoile de noel|spat?hiphyllum|ficus|monstera|pothos|sansevieria|calathea|anthurium|kalanchoe|plante verte|hellebores?|ellebores?|saintpaulia|violettes?", "09312", "n"),
    (r"tapis\b|miroirs?|cadres?|bougies?|photophores?|horloges?|pendules?|statuettes?|diffuseurs?|batons d encens|encens|sacs? a sapin|housse de sapin|"
     r"support pour sapin|pied de sapin|rubans?|paillettes|\bnoel\b|lumineux|lumineuse|\bleds?\b", "05114", "n"),
    (r"ballons?\b(?! de baudruche)|raquettes?|\bvelos?\b|trottinettes?|halteres?|kettlebell|tapis de (yoga|sport|course|gym)|velo d appartement|rameur|"
     r"elliptique|banc de musculation|reformer|pilates|corde a sauter|sacs? de frappe|gants de boxe|crampons|protege tibias|maillots? de foot|\bskis?\b|"
     r"luges?|snowboard|patins?|rollers?|skateboards?|casques? (velo|ski|trottinette)|masques? de ski|boules? de petanque|petanque|ping ?pong|badminton|tennis|fitness|"
     r"musculation|pompe a velo|antivol|domyos|kipsta|\bsport\b|running|randonnee|selle", "09221", "n"),
    (r"tentes?|sacs? de couchage|glacieres?|matelas gonflables?|rechauds?|camping|lampes? frontales?|jumelles|couteau suisse|"
     r"piscines?|\bspas?\b|jacuzzi|bouees?|jeux? de plage|pagaie|kayak|paddle|canne a peche|peche (a la ligne|en mer|au coup|sportive)|leurres?|moulinets?", "09222", "n"),
    (r"perceuses?|visseuses?|\bscies?\b|ponceuses?|tondeuses?|robots? tondeuses?|taille ?haies?|souffleurs?|"
     r"nettoyeurs? haute pression|karcher|tronconneuses?|meuleuses?|debroussailleuses?|coupe ?bordures?|broyeurs?|motobineuse|outils? multifonctions?|"
     r"perforateurs?|rabots?|defonceuses?|decapeurs?|pistolets? (a peinture|a colle)|compresseurs?|groupe electrogene|elagueuse|parkside|ryobi|einhell|makita|dewalt|"
     r"tournevis electrique|sans fil \d+ ?v|\d+ ?v\b", "05510", "n"),
    (r"tournevis|marteaux?|\bcles?\b (a|plates|allen|mixtes|dynamometrique|a molette)|\bpinces?\b|outils?|metres? ruban|niveaux? a bulle|escabeaux?|echelles?|"
     r"brouettes?|secateurs?|rateaux?|\bpelles?\b|beches?|binettes?|tuyaux? d arrosage|arrosoirs?|devidoir|cadenas|serrures?|visserie|chevilles?|clous|\bvis\b|"
     r"boites? a outils|caisses? a outils|chariots? a outils|servantes?|etablis?|serre joints?|cutters?|pistolets? d arrosage|lances? d arrosage|"
     r"gants? (de jardinage|de bricolage)|coffret (embouts|forets|douilles)|forets?|embouts?|clés mixtes|cles mixtes", "05521", "n"),
    (r"rallonges?|multiprises?|\bprises?\b|ampoules?|\bpiles?\b|alcalines?|\baaa?\b|\blr6\b|\blr03\b|lampes? (torches?|de poche)|ruban adhesif|\bscotch\b|colles?\b|crochets?|patafix|"
     r"\bcommand\b|detecteurs? (de fumee|de monoxyde)|minuterie|interrupteurs?|programmateur|cable electrique|velcro|joints?\b|mastic|silicone|enrouleurs?", "05522", "n"),
    (r"terreau|engrais|desherbants?|anti ?limaces|semences|graines?|gazon|paillage|ecorces|pots? (de fleurs|en terre|pour plantes)|"
     r"jardinieres?|bacs? a fleurs|substrat|tuteurs?|voile d hivernage|nichoirs?|mangeoires?|boules de graisse|recuperateur|reservoir d eau|composteur", "09311", "n"),

    # ========== boissons
    (r"sans alcool|\b0 0\b|champomy|virgin", "01290", "Boissons"),
    (r"whisk(e)?y|scotch|bourbon|rhums?\b|\bron\b|vodka|\bgin\b|pastis|ricard|pernod|anisette|anisee|spiritueuse|cognac|armagnac|calvados|liqueurs?|cointreau|get ?27|"
     r"baileys|martini|porto|muscat\b(?! sec)|tequila|mezcal|jagermeister|suze|picon|lillet|\bkir\b|creme de|eau de vie|spiritueux|amaretto|limoncello|grappa|"
     r"sambuca|chartreuse|grand marnier|malibu|planteur|punch|sangria|spritz|aperol|campari|vermouth|pineau|floc de gascogne|banyuls|maury|rivesaltes|"
     r"\d+ ans\b|single malt|blended|\bmalt\b|marc de|arranges?|anejo|bumbu|kraken|captain morgan|bacardi|havana|diplomatico|damoiseau|trois rivieres|"
     r"saint james|\bdillon\b|neisson|la mauny|don papa|zacapa|spiced|aperitif|apero|\bshots?\b|hydromel|absinthe|ouzo|raki|sake|soju", "02110", "Boissons|Autres"),
    (r"cidres?|poire (cidre|petillant)|pommeau|kerisac|loic raison|ecusson", "02122", "Boissons|Autres"),
    (r"\bbieres?\b|\blager\b|\bipa\b|\bblondes?\b|ambree|\bbrunes?\b|\btriple\b|tripel|kronenbourg|heineken|leffe|grimbergen|1664|desperados|affligem|pelforth|chouffe|"
     r"corona|carlsberg|tourtel|panache|karmeliet|chimay|duvel|delirium|goudale|\bch ti\b|fischer|pietra|meteor|brasserie|brassee|\bfuts?\b|"
     r"\bpils\b|stout|\bporter\b|weiss", "02130", "Boissons|Autres"),
    (r"\bvins?\b|vin (rouge|blanc|rose)|bordeaux|bourgogne|beaujolais|cotes? du rhone|cotes de provence|chablis|saint emilion|st emilion|medoc|\bgraves\b|"
     r"pomerol|margaux|pauillac|saint estephe|muscadet|sancerre|vouvray|chinon|bourgueil|anjou|saumur|fiefs vendeens|touraine|languedoc|corbieres|minervois|"
     r"cahors|madiran|gaillac|bergerac|pecharmant|monbazillac|sauternes|loupiac|buzet|jurancon|alsace|gewurztraminer|riesling|pinot|chardonnay|sauvignon|merlot|cabernet|syrah|grenache|malbec|"
     r"chateauneuf|gigondas|vacqueyras|crozes|saint joseph|cornas|cote rotie|hermitage|macon|pouilly|meursault|chassagne|puligny|nuits saint|"
     r"gevrey|morey|chambolle|vosne|aloxe|savigny|beaune|volnay|pommard|santenay|rully|mercurey|givry|montagny|fleurie|morgon|moulin a vent|brouilly|julienas|"
     r"chenas|chiroubles|saint amour|regnie|champagnes?|cremants?|prosecco|\bcava\b|mousseux|petillant|blanquette de limoux|clairette|lambrusco|rioja|chianti|tavel|lirac|bandol|"
     r"\baop\b|\baoc\b|\bigp\b|\bvdf\b|\ba o [pc]\b|\bi g p\b|chateau\b|domaine\b|cuvee|millesime|grand cru|premier cru|1er cru|cru bourgeois|vieilles vignes|vendanges|"
     r"coteaux|cotes de|bouteilles|les medailles|magnum|jeroboam|\brose\b|\brouge\b|blanc sec|moelleux|liquoreux|\bbrut\b", "02121", "Boissons|Autres"),
    (r"\bjus\b|nectars?|smoothies?|pur jus|tropicana|innocent\b|joker\b|pressade|capri ?sun|multifruits", "01210", "Boissons|Autres"),
    (r"\bcafes?\b|capsules?|dosettes?|nespresso|senseo|tassimo|dolce gusto|carte noire|lavazza|grand mere (cafe|moulu|grains|familial|l arome)|jacques vabre|"
     r"chicoree|ricore|moulu|en grains|soluble|nescafe|malongo|segafredo|\billy\b|starbucks|maxwell|expresso|espresso|arabica|robusta|cappuccino|\blatte\b", "01220", "Boissons|Épicerie sucrée|Épicerie salée|Autres"),
    (r"ice ?tea|\bthes? glaces?|fuze ?tea|lipton ice|boisson au the", "01260", "a"),
    (r"\bthes? (vert|noir|blanc|rouge|bio|earl|a la|aux?|menthe|parfume|en|de|darjeeling|ceylan|chai|oolong|matcha|jasmin)|\bthes\b|a base de the|sachets? de the|"
     r"\bthe$|^the\b(?! (legend|kraken|original|best|famous|walking|lord|witcher|last|lego|kooples))|infusions?|tisanes?|lipton|twinings|kusmi|\belephant\b|rooibos|verveine|"
     r"camomille|tilleul|matcha|palais des thes|damman|lov organic", "01230", "a"),
    (r"\beaux?\b|cristaline|evian|vittel|volvic|contrex|hepar|perrier(?! aromatise)|badoit|san pellegrino|salvetat|st yorre|saint yorre|vichy celestins|courmayeur|"
     r"thonon|abatilles|wattwiller|rozana|quezac|mont roucous|sant anna", "01250", "Boissons|Autres"),
    (r"\bsodas?\b|\bcoca\b|coca cola|\bcola\b|\bpepsi\b|\bfanta\b|\bsprite\b|orangina|schweppes|limonade|\boasis\b|7 ?up|seven up|red bull|monster|energisante|"
     r"\btonic\b|perrier aromatise|diabolo|ginger (ale|beer)|canada dry|lorina|breizh cola|tropico|dr pepper|gazeuses?|boissons? aux fruits|rafraichissante|pulco", "01260", "a"),
    (r"sirops?\b|grenadine|kombucha|cacaotee|boissons?\b", "01290", "Boissons|Autres"),

    # ========== alimentation : le cuisiné et le transformé d'abord, les produits de base ensuite
    (r"buchettes? de chevre|buches? de chevre", "01145", "a"),
    (r"marrons glaces", "01189", "a"),
    (r"buches? glacees?|buchettes? glacees?|vacherin glace|omelette norvegienne|nougat glace|dessert glace|bac glace|desserts? glaces|glacee? (vanille|chocolat)", "01186", "a"),
    (r"riz pour risotto|riz (arborio|carnaroli)", "01111", "a"),
    (r"plats? cuisines?|plats? prepares?|plats? complets|lasagnes?(?! (fraiches|feuilles))|hachis parmentier|parmentier|gratins?|paella|couscous (royal|poulet|merguez|garni)|"
     r"choucroute garnie|cassoulet|raviolis? (en conserve|au boeuf|bolognaise)|quiches?|pizzas?|\bpizz\b|tartes? (salees?|flambees?|aux legumes|au thon|aux poireaux)|"
     r"flammekueche|\bcroque\b|croque (monsieur|madame)|bouchees? a la reine|vol au vent|\bnems?\b|samoussas?|sushis?|makis?|salades? (composees?|repas|cesar|nicoise|de pates|de riz)|taboule|"
     r"sandwichs?|wraps?|burgers?|hot ?dogs?|soupes?(?! de poisson)|veloutes?(?! fruix)|gaspacho|nuggets|steak vegetal|falafels?|tofu|\brisottos?\b|tajine|\bchili\b|curry de|"
     r"cassolettes?|mini (bouchees|feuilletes|pizzas|quiches|burgers|cups)|aperitifs? (dinatoire|festif)|tapas|accras|blinis garnis|verrines?|"
     r"crepes? (fourrees|jambon|salees)|galettes? (jambon|complete|saucisse)|bagels?|kebab|fajitas|tacos|croissants? (jambon|au jambon)|friands?|"
     r"canapes?|plateau de \d+ (canapes|pieces)|mises? en bouche|timbales?|ecrase de|feuillete (de|aux|ris)|etoile coeur|air fryer|"
     r"sodebo|william saurin|garbit|zapetti|buitoni|daunat|escargots? (a la bourguignonne|de bourgogne)|bechamel|plats? bebe|rostis?|minut pocket", "01191", "a"),
    (r"lait (infantile|1er age|2e age|2eme age|3e age|de croissance|bebe)|petits? pots? (fruits|legumes|bebe)|bledina|bledilait|bledidej|guigoz|gallia|nidal|blediner|babybio|"
     r"gourdes? (bebe|fruits bebe|lactees)|\bpetits pots\b(?! de creme)|naturnes|des \d+ mois", "01192", "a"),
    (r"\bchips\b|pringles|\bcurly\b|soufflees?|pop ?corn", "01179", "a"),
    (r"pains? au chocolat|chocolatines?|croissants?|brioches?|viennoiseries?|\bpains?\b|baguettes?|baguettines?|biscottes?|cracottes?|krisprolls|tortillas?|"
     r"blinis|crepes?\b|gaufres?\b|galettes?|madeleines?|financiers?|\bcakes?\b|muffins?|cookies?|biscuits?|\bsables?\b|\bpalets?\b|"
     r"petits? beurres?|gateaux?|patisseries?|\btartes?\b|tartelettes?|eclairs?|\bchoux\b|chouquettes|macarons?|\bbuches?\b|buchettes?|beignets?|gourmelines|"
     r"savarins?|\bbabas?\b|kouign|far breton|meringues?|boudoirs?|gressins|crackers?|bretzels?|\btuc\b|feuilletes?|feuilletees?|pain d epices|"
     r"cannele|brownies?|fondants? au chocolat|moelleux|quatre quarts|marbre|\broules?\b|pates? (feuilletee|brisee|sablee|a pizza|a choux)|fonds? de tarte|"
     r"speculoos|gaufrettes?|\bpim s\b|\bprince\b|\bbn\b|oreo|petit ecolier|granola|barres? (de )?cereales|panettones?|pandoro|stollen|kouglof|bredele|"
     r"croutons?|fourres?\b|millefeuilles?|mille feuilles|paris brest|religieuses?|\bopera\b|fraisier|forets? noires?|tiramisu|profiteroles|kinder (cards|delice|pingui)|"
     r"napolitain|mikado|tresse|tressee|gache|teurgoule|crumble|kougelhopf|panetone|trompe l oeil|navettes?|couronnes? (de noel|des rois|au beurre)", "01113", "a"),
    (r"cremes? desserts?|creme brulee|cremes? (au chocolat|a la vanille|caramel)|danette|\bflans?\b|liegeois|mousses? (au chocolat|au citron|aux fruits|chocolat)|"
     r"riz au lait|semoule au lait|panna cotta|iles? flottantes?|petits? pots? de creme|boisson lactee|milk ?shake|lait (chocolate|aromatise|fraise)|"
     r"desserts? (lacte|vegetal|au soja|a l italienne|fruitiers)|la laitiere|mont blanc|\bviennois\b|coeurs? fondants?", "01147", "a"),
    (r"yaourts?|yogourts?|\byaos?\b|skyr|fromage blanc|petits? suisses?|faisselle|kefir|activia|danone|actimel|perle de lait|veloute fruix|yoplait|siggi|brasses?\b", "01146", "a"),
    (r"glaces?\b(?! (pilee|vitre|vitres|anti))|creme glacee|cremes glacees|sorbets?|\bcones?\b|magnum|esquimaux?|batonnets? glaces|carte d or|haagen|"
     r"ben (and )?jerry|kinder (bueno )?ice|frozen|pots? de glace|vacherin|igloo|le mystere", "01186", "a"),
    (r"chocolats?|chocolate|cacao|nutella|pates? a tartiner|kinder|ferrero|rocher|mon cheri|lindt|lindor|milka|cote d or|poulain|nestle dessert|"
     r"bounty|\bmars\b|snickers|twix|kit ?kat|\bm ?m ?s\b|smarties|\btruffes?\b(?! (noire|blanche|brumale))|pralines?|calendriers? de l avent|oeufs? de paques|"
     r"poudre chocolatee|nesquik|banania|ovomaltine|van houten|lanvin|crunch|\blion\b|toblerone|raffaello|after eight|chocolait|chocolatier|"
     r"mendiants?|orangettes|cemoi|revillon|jeff de bruges|leonidas|guylian|celebrations|\bmerci\b|ballotin|bueno|hanuta|maltesers|schokobons|moulages?", "01185", "a"),
    (r"bonbons?|confiseries?|caramels?|guimauves?|chamallows?|chewing ?gums?|reglisse|haribo|dragees?|nougats?|sucettes?|marshmallows?|calissons?|berlingots?|"
     r"pastilles|tagada|carambar|kremes|lutti|krema|ricola|mentos|tic tac|freedent|hollywood|airwaves|sucre d orge|papillotes|"
     r"fruits deguises|nougatine|decors? (de gateaux|sucres)|vermicelles (chocolat|multicolores)|tam tam|tubxl|acidules?|pates? de fruits|mochi|loukoums?", "01189", "a"),
    (r"confitures?|marmelades?|gelees? de|^miels?\b|\bmiels? (de|d|bio|toutes|acacia|liquide|cremeux|cremeuse|fleurs|lavande|chataignier|foret|tilleul|montagne|france|en pot)|"
     r"creme de marrons|st dalfour|lucien georgelin", "01183", "a"),
    (r"\bpates?\b|corbeille|assortiment|plateau|planche|tartinable", "01125", "Charcuterie"),
    (r"foie gras|pates? en croute|terrines?|rillettes?(?! de (thon|saumon|sardines?|maquereau|crabe))|"
     r"boudins?|andouilles?|andouillettes?|saucisses? de (strasbourg|morteau|montbeliard|francfort)|knacks?|cervelas|mousse (de canard|de foie)|galantine|quenelles?|"
     r"cordons? bleus?|panes? de (volaille|poulet)|grignottes|saucisses? (cocktail|aperitif)|mini saucisses|jambonneau|museau|tete de veau|"
     r"confits? de (canard|porc|oie|volaille|cuisses?|gesiers)|gesiers|"
     r"plats? de charcuterie|planches? (de charcuterie|apero|mixte)|plateaux? (de charcuterie|apero|raclette)|formule raclette|crepinettes?|pate (de campagne|grand mere|de foie|de lapin|de canard|de tete)", "01125", "a"),
    (r"jambons?|saucissons?|chorizo|lardons?|bacon|rosette|coppa|pancetta|bresaola|viande des grisons|serrano|prosciutto|speck|bayonne|magret seche|"
     r"poitrine (fumee|salee)|allumettes (fumees|nature)|salami|fuet|filet mignon seche|bouchons?|mortadelle|pastrami|baton de berger|herta|aoste|justin bridou|cochonou", "01123", "a"),
    (r"foies? (de veau|de volaille|de porc|de genisse)|\bfoie\b|rognons?|tripes|langues?\b|coeurs? de (boeuf|poulet|porc)|ris de veau|abats|\bgorge\b", "01124", "a"),
    (r"saumon fume|truite fumee|harengs?|anchois|haddock|morue|poisson fume|rollmops|oeufs de (lump|saumon|truite)|caviar", "01132", "a"),
    (r"surimi|rillettes? (de|du) (thon|saumon|sardines?|maquereau|crabe|poisson)|thon (en boite|au naturel|a l huile|entier)|\bsardines?|maquereaux?|"
     r"conserves? de poisson|soupe de poisson|tarama|poissons? panes?|batonnets?|brandade|terrine (de poisson|de saint)|miettes de|petit navire|saupiquet|connetable|"
     r"paupiettes? de (saumon|poisson)|coquilles? saint jacques (cuisinees|a la)|feuilletes? (de|aux) (saint|noix)|mini boites", "01133", "a"),
    (r"crevettes?|gambas|\bmoules?\b(?! (doux|demi|sel|sale|au sel))|huitres?|langoustines?|saint jacques|st jacques|crabes?|homards?|tourteaux?|araignee de mer|"
     r"langoustes?|calamars?|encornets?|seiches?|poulpes?|bulots|bigorneaux|palourdes|\bcoques\b|couteaux de mer|fruits de mer|plateau de fruits|ecrevisses|"
     r"escargots?(?! (chocolat|lanvin|praline))", "01134", "a"),
    (r"saumon|cabillaud|\bcolin|\blieu\b|merlu|merlan|\bsoles?\b|\bbar\b|dorade|daurade|truites?|\bthon\b|lotte|rouget|turbot|limande|julienne|"
     r"\bmaigre\b|eglefin|tilapia|pangasius|\bperche\b|sandre|poissons?|saint pierre", "01131", "a"),
    (r"\bboeuf|steaks?\b|steack|\bveau\b|\bporc\b|agneau|mouton|\bpoulets?\b|\bpoules?\b|chapons?|dindes?|dindonneau|canards?|canette|\boies?\b|pintades?|cailles?|"
     r"lapins?|\broti\b|\brotis\b|\bcotes?\b|cotelettes?|escalopes?|filet mignon|entrecotes?|bavettes?|faux filet|rumsteck|viande hachee|\bhaches?\b|vrac|"
     r"cuisses?|hauts de cuisse|pilons?|ailes?|aiguillettes?|blancs? de (poulet|dinde)|filets? de (poulet|dinde|canard)|saute de|blanquette|bourguignon|"
     r"pot au feu|osso bucco|jarret|epaule|gigot|magrets?|chipolatas?|saucisses?|merguez|brochettes?|tournedos|paupiettes?|\bcerf\b|chevreuil|sanglier|"
     r"gibier|biche|volailles?|viandes?|travers|echine|longe|grillades?|tomahawk|joue|bifteck|tende de tranche|charal|le gaulois|\bloue\b|maitre coq|souris d agneau", "01122", "a"),
    (r"fromages?|camembert|emmental|comte\b|\bbrie\b|roquefort|chevre|mozzarella|raclette|reblochon|coulommiers|mimolette|cantal|gruyere|"
     r"parmesan|parmigiano|grana padano|\bfeta\b|ricotta|mascarpone|saint (nectaire|marcellin|agur|moret|albray|felicien)|st (nectaire|marcellin|agur|moret|albray)|"
     r"tomme|\bbleu\b|fourme|morbier|munster|maroilles|beaufort|abondance|vacherin|carre frais|boursin|\bkiri\b|babybel|vache qui rit|"
     r"cancoillotte|fondue|tartiflette|caprice des dieux|chaource|pont l eveque|livarot|langres|epoisses|ossau|salers|burrata|halloumi|cheddar|gouda|\bedam\b|"
     r"leerdammer|chaumes|port salut|etorki|petit billy|soignon|\bpresident\b|entremont|riches monts|paysan breton|apericube|\brapes?\b|tartare (ail|aux)|ail et fines herbes|"
     r"lait (pasteurise|thermise|cru) de|au lait (cru|pasteurise|thermise)|gougeres?", "01145", "a"),
    (r"beurre de cacahuetes?|beurre d amandes?|pate d amandes?|puree d amandes", "01169", "a"),
    (r"\bbeurres?\b", "01152", "a"),
    (r"graisse de (canard|oie)|saindoux", "0115", "a"),
    (r"margarine|planta|st hubert|saint hubert|matiere grasse|tartine et cuisine|omega 3|epaisse (et|&) gourmande|onctuosite", "01153", "a"),
    (r"\bhuiles?\b|olive vierge|isio 4|lesieur|puget|spray de cuisson", "01151", "a"),
    (r"\briz\b(?! au lait)", "01111", "a"),
    (r"farine|semoule(?! au lait)|maizena|fecule|chapelure|polenta|quinoa|boulgour|ble (precuit|tendre)|ebly", "01112", "a"),
    (r"cereales|muesli|corn ?flakes|flocons (d avoine|bio)|porridge|chocapic|special k|\btresor\b|smacks|miel pops|coco pops|frosties|kellogg", "01114", "a"),
    (r"\bpates\b(?! (de fruits|a tartiner|d amande|feuilletee|brisee|sablee|a pizza|a choux|en croute))|spaghetti|tagliatelles?|penne|fusilli|coquillettes|macaronis?|nouilles|"
     r"vermicelles?|torsades|farfalle|linguine|gnocchis?|couscous|lasagnes? (fraiches|feuilles)|cappelletti|tortellinis?|raviolis?|ravioles|panzani|barilla|lustucru|\brana\b", "01115", "a"),
    (r"sauces? tomates?|pulpe de tomates?|coulis de tomates?|concentre de tomates?|puree de tomates?|ketchup", "01193", "a"),
    (r"conserves? de legumes|ratatouille|choucroute|cornichons|\bolives\b|capres|tomates? (pelees|concassees|sechees)|chair de tomates?|puree (en flocons|mousline|nature)|mousline|"
     r"legumes (cuisines|en conserve|le bio)|jardiniere|macedoine|piperade|caviar d aubergine|tapenade|antipasti|poivrons grilles|d aucy|bonduelle|cassegrain", "01179", "a"),
    (r"legumes? (surgeles|du soleil|au four)|poelees?|\bfrites\b|potatoes|pommes (noisettes|dauphines|duchesse|rissolees|sautees|wedges)|rissolee|"
     r"croustis|crispers|galettes de legumes|epinards (hach|en branches|feuilles)|mccain|mc cain|picard", "01178", "a"),
    (r"pommes? de terre|patates?\b|patate douce|grenaille|\brattes?\b", "01175", "a"),
    (r"lentilles|pois chiches|haricots (blancs|rouges|secs|tarbais|lingots|coco|a la tomate)|mogettes|flageolets|pois casses|feves seches|houmous|houmos|baked beans|legumineuses", "01176", "a"),
    (r"haricots? verts|haricots beurre|petits pois|pois gourmands|mange tout|\bfeves\b|edamame", "01173", "a"),
    (r"\bsalades?\b(?! de fruits)|laitues?|iceberg|batavia|\bmache\b|roquette|epinards|\bchoux?\b|chou fleur|brocolis?|poireaux?|sucrine|"
     r"endives?|\bceleri\b|fenouils?|asperges?|artichauts?|\bblettes|cresson|mesclun|herbes fraiches|crudettes", "01171", "a"),
    (r"\btomates?\b|courgettes?|aubergines?|poivrons?|concombres?|potirons?|courges?|citrouilles?|butternut|potimarron|"
     r"\bpiments?\b(?! d espelette)|mais doux|epis de mais", "01172", "a"),
    (r"carottes?|oignons?|echalotes?|\bail\b|\bradis\b|\bnavets?\b|betteraves?|champignons?|cepes|girolles|morilles|truffes? (noire|blanche|brumale)|panais|celeri rave|"
     r"topinambours?|rutabaga", "01174", "a"),
    (r"compotes?|puree de fruits|fruits au sirop|salade de fruits|fruits confits|pom potes|pompotes|andros|materne|preparations? de fruits|sans sucres? ajoutes?", "01169", "a"),
    (r"fruits secs|abricots secs|pruneaux?|raisins secs|dattes|figues sechees|cranberries|baies de goji|melange (etudiant|du randonneur)|mangue sechee|nuts", "01167", "a"),
    (r"\bnoix\b(?! de (coco|saint|st))|noisettes?|amandes?|pistaches?|cacahuetes?|cajou|pecan|macadamia|chataignes?|marrons?(?! glaces)|melange (aperitif|de noix)", "01168", "a"),
    (r"fruits? (rouges )?surgeles?|framboises surgelees|myrtilles surgelees", "01166", "a"),
    (r"\boranges?\b|clementines?|mandarines?|citrons?|pamplemousses?|pomelos?|agrumes|kumquats?|bergamote", "01162", "a"),
    (r"bananes?|ananas|mangues?|avocats?|papayes?|fruits? de la passion|litchis?|kiwis?|grenades?|figues?|noix de coco|exotiques?|kakis?|physalis", "01161", "a"),
    (r"fraises?(?! tagada)|framboises?|myrtilles?|\bmures?\b|cassis|groseilles?|\bbaies\b", "01164", "a"),
    (r"\bpommes?\b(?! de terre)|\bpoires?\b|\bpeches?\b|abricots?|cerises?|\bprunes?\b|nectarines?|brugnons?|mirabelles?|reines? claudes?|coings?", "01163", "a"),
    (r"raisins?|melons?|pasteques?|corbeilles? de fruits|\bfruits?\b|fruitee?s?", "01165", "a"),
    (r"\bsel\b|fleur de sel|poivres?\b|moutardes?|mayonnaise|vinaigres?|vinaigrettes?|\bsauces?\b|pesto|cubes? (bouillon|or)|bouillons?|harissa|tabasco|"
     r"coulis\b|fond (de veau|brun|blanc)|fumet|amora|maille|heinz|benedicta|bolognaise|carbonara|assaisonnement|"
     r"pistou|aioli|rouille|bearnaise|hollandaise|condiments?|chutney|wasabi|nuoc mam|balsamique", "01193", "a"),
    (r"epices?|herbes de provence|\bcurry\b|paprika|cannelle|muscade|cumin|curcuma|\bthym\b|laurier|basilic|origan|ciboulette|estragon|coriandre|gingembre (moulu|en poudre)|"
     r"vanille|gousses?|graines|levure|ducros|safran|piment d espelette|ras el hanout|quatre epices|bouquet garni", "01194", "a"),
    (r"preparations? (pour|patissiere)|aides? (a la )?patisserie|gelatine|\bagar\b|nappage|aromes?\b|colorant alimentaire|bicarbonate|fondant patissier|pate a sucre|"
     r"perles (de sucre|argentees)|kit (pour|a) (gateau|cookies|crepes|brioche)", "01199", "a"),
    (r"lait (demi ecreme|ecreme)|demi ecreme", "01142", "a"),
    (r"lait (de |d )(amande|soja|avoine|riz|coco|noisette)|boissons? (vegetales?|au soja|a l avoine|amande)|alpro|bjorg|brasse vegetal", "01144", "a"),
    (r"lait (concentre|en poudre|sucre)|creme (fraiche|liquide|epaisse|entiere|legere|uht|de cuisine|cuisine|laitiere|fluide)|chantilly|\bcremes?\b", "01143", "a"),
    (r"\blait\b|\blaits\b", "01185", "Épicerie sucrée"),
    (r"\blait\b|\blaits\b", "01141", "a"),
    (r"\boeufs?\b(?! (de paques|en chocolat|surprise|kinder))", "01148", "a"),
    (r"^sucres?\b|\bsucres? (en poudre|en morceaux|roux|blanc|de canne|glace|cristal|vanill|perle|gelifiant)|cassonade|vergeoise|daddy|beghin say", "01181", "a"),
    (r"edulcorant|stevia|canderel|sirop d agave|sirop d erable|xylitol", "01182", "a"),
]
ALIM = ["Poisson & mer", "Volaille", "Charcuterie", "Viande", "Fromage", "Crèmerie & œufs", "Fruits & légumes", "Traiteur", "Surgelés",
        "Boulangerie", "Épicerie sucrée", "Épicerie salée", "Boissons"]
NONALIM = ["Hygiène & beauté", "Entretien", "Animaux", "Maison & déco", "High-tech & électroménager", "Jouets & culture", "Mode & sport",
           "Jardin & bricolage", "Maison & loisirs"]
# Rayon de Mogette -> type de produit, quand aucun motif ne va
RAYONS = {
    "Poisson & mer": "0113", "Volaille": "01122", "Charcuterie": "01125", "Viande": "01122", "Fromage": "01145",
    "Crèmerie & œufs": "0114", "Fruits & légumes": "011", "Traiteur": "01191", "Surgelés": "011", "Boulangerie": "01113",
    "Épicerie sucrée": "0118", "Épicerie salée": "0119", "Boissons": "021", "Hygiène & beauté": "13120", "Entretien": "0561",
    "Animaux": "09322", "Maison & déco": "05", "High-tech & électroménager": None, "Jouets & culture": "09212",
    "Mode & sport": "03", "Jardin & bricolage": "055", "Maison & loisirs": "05", "Autres": "00",
}
# Repli pour les rayons inconnus
DEFAUT = "00"


def lire(url, essais=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml"})
    for n in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or n == essais - 1:
                raise
        except Exception:  # noqa: BLE001  (l'INSEE coupe parfois la connexion)
            if n == essais - 1:
                raise
        time.sleep(8 * (n + 1))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def series(xml):
    """Séries d'une réponse SDMX : [(attributs, {période: valeur})]."""
    res = []
    for s in ET.fromstring(xml).iter():
        if local(s.tag) != "Series":
            continue
        obs = {}
        for o in s:
            if local(o.tag) == "Obs" and o.get("OBS_VALUE") not in (None, "", "NaN"):
                try:
                    obs[o.get("TIME_PERIOD")] = float(o.get("OBS_VALUE"))
                except ValueError:
                    pass
        res.append((dict(s.attrib), obs))
    return res


def libelles():
    """Codes COICOP 2018 -> nom, d'après la structure du regroupement IPC-2025."""
    xml = lire(SDMX + "/datastructure/FR1/IPC-2025?references=children")
    noms = {}
    for cl in ET.fromstring(xml).iter():
        if local(cl.tag) == "Codelist" and cl.get("id") == "CL_COICOP2018":
            for c in cl:
                if local(c.tag) != "Code":
                    continue
                nom = ""
                for n in c:
                    if local(n.tag) == "Name" and n.get("{http://www.w3.org/XML/1998/namespace}lang") == "fr":
                        nom = (n.text or "").strip()
                noms[c.get("id")] = re.sub(r"\s*\((ND|SD|D|S)\)$", "", re.sub(r"^[\d.]+\s*-\s*", "", nom))
    return noms


def indices(freq, depuis):
    """{code COICOP: {période: indice}} pour la France entière, ensemble des ménages, base 2025."""
    xml = lire(SDMX + "/data/IPC-2025/%s.....INDICE.ENSEMBLE.FE..BRUT..?startPeriod=%s" % (freq, depuis))
    res = {}
    for a, obs in series(xml):
        if a.get("PRIX_CONSO", "SO") != "SO" or a.get("COICOP2018", "SO") == "SO" or not obs:
            continue
        res[a["COICOP2018"]] = obs
    return res


def smic(aujourd):
    """SMIC horaire brut : moyenne de chaque année, et le dernier mois connu."""
    (a, obs), = series(lire(SDMX + "/data/SERIES_BDM/%s?startPeriod=%d-01" % (SMIC, DEBUT)))
    par_an = {}
    for p, v in obs.items():
        par_an.setdefault(int(p[:4]), []).append(v)
    dernier = max(obs)
    return {str(y): round(sum(l) / len(l), 3) for y, l in par_an.items() if y < aujourd.year}, round(obs[dernier], 3), dernier


def code_dispo(code, dispo):
    """Le code, ou le type plus large qui a des séries (011821 -> 01182 -> 0118 …)."""
    while code and code not in dispo:
        code = code[:-1] if len(code) > 2 else ("00" if code != "00" else "")
    return code or None


def a_refaire(ancien, aujourd):
    try:
        age = (aujourd - date.fromisoformat(ancien.get("maj"))).days
    except (TypeError, ValueError):
        age = 999
    return age >= TOUS_LES or ancien.get("v") != VERSION


def regle_va(r, rayon):
    """La règle vaut-elle pour ce rayon ? (« a » : alimentaire, « n » : le reste, sinon une liste de rayons)"""
    if len(r) < 3:
        return True
    if r[2] == "a":
        return rayon not in NONALIM
    if r[2] == "n":
        return rayon not in ALIM
    return rayon in r[2].split("|")


def ranger(nom, marque, rayon, regles, rayons, defaut=DEFAUT):
    """Comme typeHisto() dans l'appli : le code du type de produit d'un article, ou None (pas d'estimation).
    Le nom d'abord, puis la marque (sans la règle « tout le rayon »), puis le rayon."""
    for texte, tout in ((nom, True), (marque, False)):
        if not texte:
            continue
        for r in regles:
            if (tout or r[0].pattern != ".") and regle_va(r, rayon) and r[0].search(texte):
                return r[1]
    return rayons.get(rayon, defaut)


def norm_py(t):
    import unicodedata
    t = str(t or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae").replace("Æ", "ae")
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def mettre_a_jour(log=print, aujourd=None, forcer=False, essai=False):
    aujourd = aujourd or date.today()
    ancien = charger_json(FICHIER, {})
    if not forcer and not a_refaire(ancien, aujourd):
        return ancien
    log("Histoire des prix (INSEE : indices des prix par type de produit, SMIC)…")
    try:
        noms = libelles()
        annuels = indices("A", DEBUT)
        mensuels = indices("M", "%d-01" % (aujourd.year - 1))
        smic_ans, smic_now, smic_mois = smic(aujourd)
    except Exception as e:  # noqa: BLE001
        log("   INSEE injoignable (%s) : histoire de la dernière fois gardée" % e)
        return ancien
    dispo = {c for c in annuels if c in mensuels}
    # dernier mois publié (le même pour tous les types)
    mois = max(max(m) for m in mensuels.values())
    regles, rayons, utiles = [], {}, set()
    for r in REGLES:
        motif, code = r[0], r[1]
        c = code_dispo(code, dispo) if code else None
        if code and not c:
            log("   type %s sans série : règle « %s » ignorée" % (code, motif[:60]))
            continue
        regles.append([motif, c] + list(r[2:]))
        if c:
            utiles.add(c)
    for r, code in RAYONS.items():
        c = code_dispo(code, dispo) if code else None
        rayons[r] = c
        if c:
            utiles.add(c)
    utiles.add(code_dispo(DEFAUT, dispo))
    cat = {}
    for c in sorted(x for x in utiles if x):
        an = annuels[c]
        ans = [an.get(str(y)) for y in range(DEBUT, aujourd.year)]
        m = mensuels[c]
        cat[c] = {"n": noms.get(c, c), "i": [round(v, 2) if v is not None else None for v in ans], "m": round(m[max(m)], 2)}
    res = {"v": VERSION, "maj": aujourd.isoformat(), "debut": DEBUT, "fin": aujourd.year, "mois": mois,
           "smic": {"ans": [smic_ans.get(str(y)) for y in range(DEBUT, aujourd.year)], "m": smic_now, "mois": smic_mois},
           "cat": cat, "regles": regles, "rayons": rayons, "defaut": code_dispo(DEFAUT, dispo), "alim": ALIM, "nonalim": NONALIM}
    log("   %d types de produits, indices jusqu'à %s, SMIC %s € brut de l'heure (%s)" % (len(cat), mois, str(smic_now).replace(".", ","), smic_mois))
    ecrire_json(FICHIER, res)
    if essai:
        essai_detail(res, noms, annuels, mensuels, dispo)
    return res


def essai_detail(res, noms, annuels, mensuels, dispo):
    print("Types de produits avec séries (code | nom | 1re année | indice %d | dernier mois) :" % DEBUT)
    for c in sorted(dispo, key=lambda x: (x[:2], x)):
        if c[:2] in ("01", "02", "03", "05", "08", "09", "13", "00"):
            an = annuels[c]
            prem = min(an)
            print("   %-7s %-70s %s %7s %7s" % (c, noms.get(c, "?")[:70], prem, an.get(str(DEBUT), "-"), mensuels[c][max(mensuels[c])]))
    # essai sur les promos du jour
    regles = [[re.compile(r[0])] + r[1:] for r in res["regles"]]
    from collections import Counter
    vus, exemples = Counter(), {}
    ici = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(os.path.join(DATA, "offres", "*.json")) or glob.glob(os.path.join(ici, "offres", "*.json")):
        for p in charger_json(f, []):
            if not isinstance(p, dict) or p.get("prix") is None:
                continue
            c = ranger(norm_py(p.get("nom")), norm_py(p.get("marque")), p.get("rayon"), regles, res["rayons"], res["defaut"])
            vus[c] += 1
            exemples.setdefault(c, []).append(p.get("nom"))
    print("Promos du jour par type :")
    for c, n in vus.most_common():
        print("   %5d %-8s %-45s ex. %s" % (n, c, (res["cat"].get(c) or {}).get("n", "(pas d'estimation)")[:45], " | ".join(exemples[c][:4])[:160]))
    print("Taille :", os.path.getsize(FICHIER), "octets")


if __name__ == "__main__":
    mettre_a_jour(forcer="--forcer" in sys.argv or "--essai" in sys.argv, essai="--essai" in sys.argv)
