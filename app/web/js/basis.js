// Gedeelde hulpmiddelen: API, opmaak, datums, toasts, thema en prijsniveaus.

export const TZ = "Europe/Amsterdam";
export const $ = (sel, ouder = document) => ouder.querySelector(sel);
export const $$ = (sel, ouder = document) => [...ouder.querySelectorAll(sel)];

// ── API ───────────────────────────────────────────────────────────────────────

// pad → {tijd, belofte}: snel heen en weer tussen pagina's zonder nieuwe BigQuery-queries.
// De data verandert alleen per ronde van de verzamelaar; bij een nieuwe ronde gaat de cache leeg.
const cache = new Map();
const BEWAAR_MS = 5 * 60_000;
// De server bewaart antwoorden ook tot de volgende ronde. Na een wijziging of een nieuwe ronde vraagt
// de app een minuut lang om verse antwoorden (header x-thuis-vers), voor het geval een andere
// instantie van de server nog een ouder antwoord heeft.
const VERS_MS = 60_000;
let versTot = 0;

export class SessieVerlopen extends Error {}

export async function api(pad, { methode = "GET", body, vers = false } = {}) {
  if (methode === "GET" && !vers) {
    const c = cache.get(pad);
    if (c && Date.now() - c.tijd < BEWAAR_MS) return c.belofte;
  }
  const belofte = (async () => {
    let r;
    try {
      r = await fetch(`api/${pad}`, {
        method: methode,
        // Met deze header antwoordt IAP bij een verlopen sessie met 401 i.p.v. een redirect.
        headers: {
          "content-type": "application/json",
          "x-requested-with": "XMLHttpRequest",
          ...(methode === "GET" && (vers || Date.now() < versTot) ? { "x-thuis-vers": "1" } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new Error("Geen verbinding met de server");
    }
    if (r.status === 401) throw new SessieVerlopen("Je bent uitgelogd");
    if (!r.ok) {
      let detail = "";
      try { detail = (await r.json()).detail; } catch { /* geen JSON */ }
      throw new Error(typeof detail === "string" && detail ? detail : `Fout ${r.status} bij ${pad.split("?")[0]}`);
    }
    return r.json();
  })();
  if (methode === "GET") {
    cache.set(pad, { tijd: Date.now(), belofte });
    belofte.catch(() => cache.delete(pad));
  } else {
    legeCache();
  }
  return belofte;
}

export function legeCache() {
  cache.clear();
  versTot = Date.now() + VERS_MS;
}

// ── opmaak ────────────────────────────────────────────────────────────────────

const getalOpmaak = new Map();
export function getal(v, d = 1) {
  if (v == null || Number.isNaN(v)) return "–";
  if (!getalOpmaak.has(d)) {
    getalOpmaak.set(d, new Intl.NumberFormat("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d }));
  }
  return getalOpmaak.get(d).format(v);
}

/** kWh/m³ met een aantal decimalen dat bij de grootte past. */
export function hoeveelheid(v) {
  if (v == null) return "–";
  const a = Math.abs(v);
  return getal(v, a >= 100 ? 0 : a >= 10 ? 1 : 2);
}

const euroOpmaak = new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" });
export const euro = (v) => (v == null ? "–" : euroOpmaak.format(v));
export const prijs = (v) => (v == null ? "–" : `€ ${getal(v, 3)}`);
export const procent = (v) => (v == null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${getal(Math.abs(v) * 100, 0)}%`);

export const klok = (iso) =>
  new Date(iso).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

export function relatief(iso) {
  if (!iso) return "nooit";
  const t = new Date(iso);
  const min = Math.round((Date.now() - t) / 60000);
  if (min < 1) return "zojuist";
  if (min < 60) return `${min} min geleden`;
  if (min < 6 * 60) return `${Math.round(min / 60)} uur geleden`;
  const dag = isoDatum(t);
  if (dag === vandaag()) return `vandaag ${klok(iso)}`;
  if (dag === plusDagen(vandaag(), -1)) return `gisteren ${klok(iso)}`;
  return `${datumKort(dag)} ${klok(iso)}`;
}

/** Hoe vers de stand van de auto is. `bijgewerkt`: wanneer de auto zelf iets doorgaf; `tijd`: wanneer
 *  Thuis het opvroeg. Een geparkeerde auto meldt niets, dan lopen die twee ver uiteen en zeggen we dat. */
export function autoStand(auto) {
  if (!auto?.bijgewerkt) return "";
  const stil = auto.tijd && new Date(auto.tijd) - new Date(auto.bijgewerkt) > 30 * 60e3;
  return stil
    ? `stand van ${relatief(auto.bijgewerkt)}, opgehaald ${relatief(auto.tijd)}`
    : `bijgewerkt ${relatief(auto.bijgewerkt)}`;
}

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const icoon = (naam, klasse = "ic") => `<svg class="${klasse}" aria-hidden="true"><use href="#i-${naam}"/></svg>`;

// Foto's van auto's: vrijstaand (WebP met doorzichtige achtergrond) in img/auto/, gekozen op de naam die de auto doorgeeft.
// BMW CarData geeft "BMW <model>" (bijv. "BMW X3 30e xDrive"); Kia en Hyundai de naam uit hun app.
// Een auto zonder regel hier krijgt geen foto. Een nieuwe auto: foto in img/auto/ en een regel erbij.
const AUTOFOTO = [[/^BMW\b.*\bX3\b/i, "img/auto/bmw-x3.webp"]];
export const autoFoto = (naam) => AUTOFOTO.find(([patroon]) => patroon.test(naam || ""))?.[1] ?? null;

// ── datums (lokale kalenderdagen als "YYYY-MM-DD") ────────────────────────────

export const isoDatum = (d) => d.toLocaleDateString("sv-SE", { timeZone: TZ });
export const vandaag = () => isoDatum(new Date());

function alsUtc(iso) {
  const [j, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(j, m - 1, d));
}
const naarIso = (d) => d.toISOString().slice(0, 10);

export const plusDagen = (iso, n) => {
  const d = alsUtc(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return naarIso(d);
};
export const plusMaanden = (iso, n) => {
  const d = alsUtc(iso);
  return naarIso(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1)));
};
export const plusJaren = (iso, n) => `${Number(iso.slice(0, 4)) + n}-01-01`;
export const weekdag = (iso) => (alsUtc(iso).getUTCDay() + 6) % 7; // 0 = maandag

export function datumLang(iso) {
  const d = alsUtc(iso);
  const tekst = d.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  return iso.slice(0, 4) === vandaag().slice(0, 4) ? tekst : `${tekst} ${iso.slice(0, 4)}`;
}
export const datumKort = (iso) =>
  alsUtc(iso).toLocaleDateString("nl-NL", { day: "numeric", month: "short", timeZone: "UTC" });

/** "vandaag", "morgen", "gisteren" of een korte datum, voor een tijdstip. */
export function dagnaam(iso) {
  const dag = isoDatum(new Date(iso));
  const v = vandaag();
  if (dag === v) return "vandaag";
  if (dag === plusDagen(v, 1)) return "morgen";
  if (dag === plusDagen(v, -1)) return "gisteren";
  return datumKort(dag);
}

// ── toasts ────────────────────────────────────────────────────────────────────

export function toast(tekst, { soort = "info", actie } = {}) {
  const el = document.createElement("div");
  el.className = `toast ${soort}`;
  el.textContent = tekst;
  if (actie) {
    const knop = document.createElement("button");
    knop.type = "button";
    knop.textContent = actie.label;
    knop.addEventListener("click", actie.fn);
    el.append(knop);
  }
  $("#toasts").append(el);
  setTimeout(() => el.remove(), actie ? 10_000 : 4_000);
}

export function meldFout(err) {
  if (err instanceof SessieVerlopen) {
    toast("Je sessie is verlopen. Herlaad de pagina om opnieuw in te loggen.", {
      soort: "fout",
      actie: { label: "Herladen", fn: () => location.reload() },
    });
  } else {
    toast(err.message || String(err), { soort: "fout" });
  }
}

// ── thema ─────────────────────────────────────────────────────────────────────

export const thema = () => document.documentElement.dataset.theme || "systeem";

export function zetThema(t) {
  if (t === "licht" || t === "donker") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("thema", t); } catch { /* geen opslag beschikbaar */ }
  dispatchEvent(new Event("thema"));
}

export const css = (naam) => getComputedStyle(document.documentElement).getPropertyValue(naam).trim();

// ── prijsniveaus (t.o.v. het daggemiddelde, zoals Tibber) ──────────────────────

export const NIVEAUS = [
  { id: "negatief", naam: "Negatief", kleur: "--p-negatief" },
  { id: "zeer-goedkoop", naam: "Zeer goedkoop", kleur: "--p-zeer-goedkoop" },
  { id: "goedkoop", naam: "Goedkoop", kleur: "--p-goedkoop" },
  { id: "normaal", naam: "Normaal", kleur: "--p-normaal" },
  { id: "duur", naam: "Duur", kleur: "--p-duur" },
  { id: "zeer-duur", naam: "Zeer duur", kleur: "--p-zeer-duur" },
];

export function niveau(p, gemiddelde) {
  if (p < 0) return NIVEAUS[0];
  const r = p / Math.max(gemiddelde, 0.05);
  if (r <= 0.8) return NIVEAUS[1];
  if (r <= 0.93) return NIVEAUS[2];
  if (r < 1.07) return NIVEAUS[3];
  if (r < 1.2) return NIVEAUS[4];
  return NIVEAUS[5];
}

/** Tijdgewogen gemiddelde van prijsblokken {van, tot, prijs}. */
export function gemiddelde(blokken) {
  let som = 0, duur = 0;
  for (const b of blokken) {
    const d = new Date(b.tot) - new Date(b.van);
    som += b.prijs * d;
    duur += d;
  }
  return duur ? som / duur : null;
}

export const huidigBlok = (blokken, t = Date.now()) =>
  blokken.find((b) => new Date(b.van) <= t && t < new Date(b.tot)) || null;

/** Goedkoopste aaneengesloten venster van `uren` vanaf `vanaf`: {van, tot, prijs} of null. */
export function goedkoopsteVenster(blokken, uren, vanaf = Date.now()) {
  const lijst = blokken
    .map((b) => ({ van: +new Date(b.van), tot: +new Date(b.tot), prijs: b.prijs }))
    .filter((b) => b.tot > vanaf)
    .sort((a, b) => a.van - b.van);
  const duur = uren * 3600e3;
  let beste = null;
  for (let i = 0; i < lijst.length; i++) {
    const start = lijst[i].van; // het lopende blok telt mee vanaf zijn begin
    let t = start, som = 0, j = i;
    while (t < start + duur && j < lijst.length && lijst[j].van <= t) {
      const stuk = Math.min(lijst[j].tot, start + duur) - t;
      som += lijst[j].prijs * stuk;
      t += stuk;
      j++;
    }
    if (t < start + duur) continue; // gat in de prijzen of einde van de reeks
    const gem = som / duur;
    if (!beste || gem < beste.prijs - 1e-9) beste = { van: new Date(start).toISOString(), tot: new Date(start + duur).toISOString(), prijs: gem };
  }
  return beste;
}

export const LADER_STATUS = {
  laden: "Laadt",
  wacht_op_start: "Wacht op start",
  klaar_om_te_laden: "Klaar om te laden",
  niet_verbonden: "Geen auto",
  klaar: "Klaar",
  offline: "Offline",
  fout: "Fout",
  wacht_op_smart_start: "Wacht (smart charging)",
  wacht_op_schema: "Wacht op schema",
  wacht_op_autorisatie: "Wacht op autorisatie",
  wacht_op_loadbalancing: "Wacht op load balancing",
  gepauzeerd_equalizer: "Gepauzeerd (Equalizer)",
  auto_reageert_niet: "Auto reageert niet",
};

export const PLAN_REDEN = {
  gepland: "Laadt nu volgens plan",
  onder_drempel: "Laadt: prijs onder je drempel",
  wachten: "Wacht op goedkope uren",
  doel_bereikt: "Doel bereikt",
  geen_prijzen: "Nog geen prijzen",
  uitgeschakeld: "Uit",
  geen_behoefte: "Niets nodig",
};
