// Mogette : widget d'écran d'accueil pour l'appli gratuite Scriptable (iPhone).
// Dans Mogette : Réglages > Widget > « Copier le script du widget » remplit les deux lignes ci-dessous avec tes magasins.
// Dans Scriptable : touche +, colle le script, appelle-le « Mogette ». Puis ajoute un widget Scriptable sur l'écran d'accueil.
const MAGASINS = [];
const PRENOM = "";
const ADRESSE = "https://ansquerdylan-arch.github.io/mes-promos/";

const CIEL = new Color("#cfeaf7"), ENCRE = new Color("#000000"), ROUGE = new Color("#b3261e"), GRIS = new Color("#34495a");

function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
function joli(t) { t = String(t || "").trim(); return t === t.toUpperCase() ? t.toLowerCase().replace(/(^|[\s'’-])\S/g, (x) => x.toUpperCase()) : t; }

async function donnees() {
  const fm = FileManager.local(), cache = fm.joinPath(fm.cacheDirectory(), "mogette-promos.json");
  try {
    const r = new Request(ADRESSE + "promos.json");
    r.timeoutInterval = 20;
    const d = await r.loadJSON();
    fm.writeString(cache, JSON.stringify(d));
    return d;
  } catch (e) {
    return fm.fileExists(cache) ? JSON.parse(fm.readString(cache)) : null;
  }
}

// catalogues en cours dans tes magasins, ce qui finit, ce qui commence, les opérations du jour
function resume(d) {
  const auj = iso(new Date()), dem = iso(new Date(Date.now() + 86400000));
  const ids = MAGASINS.length ? MAGASINS : (d.defaut || []);
  const mags = (d.magasins || []).filter((m) => ids.includes(m.id));
  const vus = {}, lignes = [];
  let promos = 0, catalogues = 0;
  for (const m of mags) {
    const z = (d.zones || {})[m.zone] || {};
    for (const id of z.catalogues || []) {
      const c = (d.catalogues || {})[id];
      if (!c || vus[id] || c.fin < auj) continue;
      vus[id] = true;
      const ou = joli(c.titre).toLowerCase().includes(String(m.nom || "").split(" ")[0].toLowerCase()) ? (m.ville || "") : (m.nom || "") + " " + (m.ville || "");
      if (c.debut <= auj) { catalogues++; promos += c.n || 0; }
      if (c.operation && (c.debut === auj || c.debut === dem)) lignes.push({ rang: 0, txt: "⚡ " + (c.debut === auj ? "Aujourd'hui" : "Demain") + " : " + joli(c.titre) + " · " + m.nom });
      else if (c.fin === auj) lignes.push({ rang: 1, txt: "Finit ce soir : " + joli(c.titre) + " · " + ou });
      else if (c.fin === dem) lignes.push({ rang: 2, txt: "Finit demain : " + joli(c.titre) + " · " + ou });
      else if (c.debut === auj) lignes.push({ rang: 3, txt: "Nouveau : " + joli(c.titre) + " · " + ou });
    }
  }
  lignes.sort((a, b) => a.rang - b.rang);
  return { promos, catalogues, lignes: [...new Set(lignes.map((l) => l.txt))] };
}

async function creer() {
  const w = new ListWidget(), taille = config.widgetFamily || "medium";
  w.backgroundColor = CIEL;
  w.url = ADRESSE;
  w.setPadding(14, 14, 12, 14);
  w.refreshAfterDate = new Date(Date.now() + 3 * 3600 * 1000);
  const titre = w.addText("🫘 Mogette" + (PRENOM && taille !== "small" ? " · salut " + PRENOM : ""));
  titre.font = Font.heavySystemFont(15);
  titre.textColor = ENCRE;
  titre.lineLimit = 1;
  w.addSpacer(6);
  const d = await donnees();
  if (!d) {
    const t = w.addText("Pas de réseau : je réessaie plus tard.");
    t.font = Font.mediumSystemFont(13);
    t.textColor = GRIS;
    return w;
  }
  const r = resume(d);
  const n = w.addText(r.promos.toLocaleString("fr-FR") + " promos");
  n.font = Font.heavySystemFont(taille === "small" ? 24 : 28);
  n.textColor = ENCRE;
  n.minimumScaleFactor = 0.6;
  n.lineLimit = 1;
  const sous = w.addText("en cours dans " + r.catalogues + " catalogue" + (r.catalogues > 1 ? "s" : ""));
  sous.font = Font.mediumSystemFont(12);
  sous.textColor = GRIS;
  sous.lineLimit = 1;
  w.addSpacer(6);
  const max = taille === "small" ? 2 : taille === "large" ? 9 : 3;
  for (const l of r.lignes.slice(0, max)) {
    const t = w.addText(l);
    t.font = Font.semiboldSystemFont(12);
    t.textColor = l.startsWith("⚡") || l.startsWith("Finit ce soir") ? ROUGE : ENCRE;
    t.lineLimit = 1;
    t.minimumScaleFactor = 0.75;
  }
  if (!r.lignes.length) {
    const t = w.addText("Rien qui finit ou commence aujourd'hui.");
    t.font = Font.mediumSystemFont(12);
    t.textColor = GRIS;
  }
  w.addSpacer();
  return w;
}

const widget = await creer();
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentMedium();
Script.complete();
