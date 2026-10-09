// Apparaten: je slimme stekkers, lampen, thermostaten, rolluiken en sensoren uit Smart Life of Tuya Smart.
// De stand komt live uit de cloud van Tuya (hooguit 15 seconden oud); de historie en het geschatte
// verbruik uit wat de verzamelaar elk kwartier bewaart. Bedienen gaat meteen naar Tuya: de app toont
// direct wat je vroeg en kijkt een paar seconden later of het apparaat het ook meldt.

import {
  $, $$, api, css, dagnaam, esc, euro, gemiddelde, getal, hoeveelheid, huidigBlok, icoon, klok, meldFout, niveau, prijs,
  relatief, vandaag,
} from "../basis.js";
import { basis, doorzichtig, grafiek, lijn, regel, ruimOp } from "../grafiek.js";
import { kaart, leeg, melding, pijl, skeletKaart } from "../onderdelen.js";

// ── woorden voor de codes van Tuya ────────────────────────────────────────────

export const SOORTEN = {
  stekker: { naam: "Stekkers", icoon: "stekker" },
  schakelaar: { naam: "Schakelaars", icoon: "schakelaar" },
  lamp: { naam: "Lampen", icoon: "lamp" },
  klimaat: { naam: "Klimaat", icoon: "thermometer" },
  gordijn: { naam: "Rolluiken", icoon: "gordijn" },
  sensor: { naam: "Sensoren", icoon: "sensor" },
  overig: { naam: "Overig", icoon: "apparaten" },
};
const TOESTAND = { open: "Open", dicht: "Dicht", beweging: "Beweging", rust: "Geen beweging", alarm: "Alarm", normaal: "In orde" };
const TOESTAND_SOORT = { open: "let_op", alarm: "fout", beweging: "accent" };

// Wat je kunt bedienen: label, uitleg en woorden voor de keuzes.
const BEDIENING = {
  switch: { label: "Aan of uit" },
  switch_led: { label: "Licht" },
  switch_usb1: { label: "USB" },
  switch_usb2: { label: "USB 2" },
  child_lock: { label: "Kinderslot", uitleg: "Knop op het apparaat zelf werkt niet" },
  relay_status: {
    label: "Na een stroomstoring",
    keuzes: { power_off: "Uit", power_on: "Aan", last: "Zoals het was", off: "Uit", on: "Aan", memory: "Zoals het was", 0: "Uit", 1: "Aan", 2: "Zoals het was" },
  },
  light_mode: { label: "Lampje op de stekker", keuzes: { relay: "Als aan", pos: "Als uit", none: "Uit", off: "Uit", on: "Aan" } },
  work_mode: { label: "Lichtsoort", keuzes: { white: "Wit", colour: "Kleur", scene: "Scène", music: "Muziek" } },
  bright_value: { label: "Helderheid", procent: true },
  bright_value_v2: { label: "Helderheid", procent: true },
  temp_value: { label: "Kleur van het wit", procent: true, uitleg: "Van warm naar koel" },
  temp_value_v2: { label: "Kleur van het wit", procent: true, uitleg: "Van warm naar koel" },
  temp_set: { label: "Gewenste temperatuur" },
  mode: {
    label: "Stand",
    keuzes: { auto: "Automatisch", manual: "Handmatig", eco: "Eco", comfort: "Comfort", holiday: "Vakantie", off: "Uit", cold: "Koelen", hot: "Verwarmen", wet: "Drogen", wind: "Ventileren", smart: "Slim", sleep: "Slapen" },
  },
  window_check: { label: "Raamdetectie", uitleg: "Stopt met verwarmen als het raam open staat" },
  eco: { label: "Eco" },
  control: { label: "Rolluik", keuzes: { open: "Open", stop: "Stop", close: "Dicht" } },
  percent_control: { label: "Hoe ver open", procent: true },
  fan_speed_percent: { label: "Snelheid" },
  fan_speed: { label: "Snelheid", keuzes: { low: "Laag", middle: "Midden", high: "Hoog", auto: "Automatisch" } },
  temp_unit_convert: { label: "Eenheid", keuzes: { c: "°C", f: "°F" } },
};
// Wat een apparaat verder meldt (kaart Gegevens).
const STATUS = {
  battery_state: { label: "Batterij", keuzes: { low: "Bijna leeg", middle: "Half vol", high: "Vol" } },
  doorcontact_state: { label: "Deur of raam", keuzes: { true: "Open", false: "Dicht" } },
  pir: { label: "Beweging", keuzes: { pir: "Ja", none: "Nee" } },
  percent_state: { label: "Open", eenheid: "%" },
  work_state: { label: "Beweegt", keuzes: { opening: "Gaat open", closing: "Gaat dicht" } },
  smoke_sensor_status: { label: "Rook", keuzes: { alarm: "Alarm", normal: "Niets" } },
  watersensor_state: { label: "Water", keuzes: { alarm: "Lek", normal: "Droog" } },
  valve_state: { label: "Klep", keuzes: { open: "Open", close: "Dicht" } },
};
// Al getoond via `metingen`: niet nog eens in de lijst.
const GEMETEN = new Set(["cur_power", "cur_voltage", "cur_current", "add_ele", "forward_energy_total", "va_temperature", "temp_current",
  "va_humidity", "humidity_value", "battery_percentage", "va_battery"]);
const TIMER = [[0, "Geen"], [900, "15 min"], [1800, "30 min"], [3600, "1 uur"], [7200, "2 uur"]];

/** "BRAKE_FLUID" of "temp_indoor" → "Temp indoor": leesbaar als we de code (nog) niet kennen. */
const mens = (w) => {
  const s = String(w).replace(/[_-]+/g, " ").toLowerCase().trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const kanaalNaam = (code, a) => {
  if (BEDIENING[code]) return BEDIENING[code].label;
  const n = code.match(/^switch_(\d)$/)?.[1];
  if (!n) return mens(code);
  return a.soort === "stekker" && a.schakelaars.filter((c) => /^switch_\d$/.test(c)).length > 1 ? `Stopcontact ${n}` : `Kanaal ${n}`;
};
const keuzeNaam = (code, k) => BEDIENING[code]?.keuzes?.[k] ?? mens(k);
const bed = (a, code) => a.bediening.find((b) => b.code === code) || null;
const bedienbaar = (a, code) => a.online && Boolean(bed(a, code));
const wattTekst = (w) => `${getal(w, Math.abs(w) < 10 ? 1 : 0)} W`;
const graden = (t) => `${getal(t, 1)} °C`;

/** Hoofdschakelaar(s): bij een stekkerdoos alle stopcontacten tegelijk. */
export const hoofd = (a) => a.schakelaars.filter((c) => bed(a, c));

const pct = (b) => (b?.waarde == null ? null : Math.max(0, Math.min(100, Math.round(((b.waarde - Math.min(b.min, 0)) / (b.max - Math.min(b.min, 0))) * 100))));
const vanPct = (b, p) => Math.max(b.min, Math.min(b.max, Math.round((p / 100) * b.max)));
const helderheid = (a) => pct(bed(a, "bright_value_v2") || bed(a, "bright_value"));
function positie(a) {
  const s = a.status.find((x) => x.code === "percent_state");
  return s?.waarde ?? bed(a, "percent_control")?.waarde ?? null;
}

export function icoonVan(a) {
  if (a.soort === "sensor") {
    if (a.toestand === "open" || a.toestand === "dicht") return "deur";
    if (a.metingen.temperatuur != null) return "thermometer";
    if (a.status.some((s) => s.code === "watersensor_state")) return "druppel";
  }
  return SOORTEN[a.soort]?.icoon || "apparaten";
}

/** Korte stand onder de naam: "Aan · 486 W", "16,8 °C · 61%", "Open". */
export function stand(a) {
  if (!a.online) return "Offline";
  const m = a.metingen;
  const delen = [];
  if (a.toestand) delen.push(TOESTAND[a.toestand] || mens(a.toestand));
  else if (a.soort === "gordijn") {
    const p = positie(a);
    // Na Open of Dicht beweegt het rolluik nog even: zolang het er niet is, zeggen we dat.
    const doel = { open: 100, close: 0 }[bed(a, "control")?.waarde];
    if (p != null && doel != null && Math.abs(p - doel) > 1) delen.push(doel ? "Gaat open" : "Gaat dicht");
    else if (p != null) delen.push(p >= 99 ? "Open" : p <= 1 ? "Dicht" : `${getal(p, 0)}% open`);
  } else if (a.aan != null) delen.push(a.aan ? "Aan" : "Uit");
  if (m.vermogen_w >= 0.05 && a.aan !== false) delen.push(wattTekst(m.vermogen_w)); // net aangezet: nog 0 W
  if (a.soort === "lamp" && a.aan && helderheid(a) != null) delen.push(`${helderheid(a)}%`);
  if (m.temperatuur != null) delen.push(graden(m.temperatuur));
  if (m.vochtigheid != null) delen.push(`${getal(m.vochtigheid, 0)}%`);
  const doel = bed(a, "temp_set");
  if (doel?.waarde != null && a.soort === "klimaat") delen.push(`naar ${graden(doel.waarde)}`);
  return delen.join(" · ");
}

/** Wat het apparaat nu kost per uur, met de stroomprijs van dit kwartier. */
const perUur = (a, p) => (p != null && a.metingen.vermogen_w != null && a.aan !== false ? (a.metingen.vermogen_w / 1000) * p : null);

// ── pagina ────────────────────────────────────────────────────────────────────

let staat = null; // {lijst, bijgewerkt, prijs, niveau, vandaag, tijd}
let zetSub = () => {}; // de regel naast de paginatitel (van app.js)
let filter = "alle";
let peiling = null;
let actief = Date.now(); // laatste keer dat je iets deed: zonder actie houdt het verversen na 10 minuten op
const PEIL_MS = 60_000;
const STIL_MS = 10 * 60_000;
const CONTROLE_MS = 3_500; // na bedienen: zo lang wachten voor Tuya de nieuwe stand meldt

export async function toon(main, params, ctx) {
  const id = params.get("id");
  zetSub = ctx.sub;
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">
      <div class="kpi-rij b-12">${'<div class="kpi" aria-busy="true"><div class="skelet regel" style="width:50%"></div><div class="skelet groot-blok"></div></div>'.repeat(4)}</div>
      ${skeletKaart("b-12", { titel: "Apparaten", regels: 6 })}</div>`;
  }
  const v = vandaag();
  const vers = !staat || ctx.ververs || Date.now() - staat.tijd > 15_000;
  const [live, dag, verbruik] = await Promise.all([
    vers ? api("apparaten", { vers: true }) : Promise.resolve({ gekoppeld: true, apparaten: staat.lijst, bijgewerkt: staat.bijgewerkt }),
    api(`dag?datum=${v}`).catch(() => null),
    api("apparaten/vandaag").catch(() => null),
  ]);
  if (!ctx.actueel()) return;
  const blokken = dag?.prijzen.stroom || [];
  const blok = huidigBlok(blokken);
  staat = {
    lijst: live.apparaten,
    bijgewerkt: live.bijgewerkt,
    tijd: vers ? Date.now() : staat.tijd,
    prijs: blok?.prijs ?? null,
    niveau: blok ? niveau(blok.prijs, gemiddelde(blokken)) : null,
    vandaag: verbruik,
  };
  ruimOp();
  if (!live.gekoppeld) {
    ctx.sub("");
    main.innerHTML = nietGekoppeld();
    return;
  }
  const apparaat = id && staat.lijst.find((a) => a.id === id);
  if (id && !apparaat) {
    main.innerHTML = `<div class="raster">${kaart({ titel: "Apparaat niet gevonden", klasse: "b-12", inhoud: `<p class="leeg">Tuya kent dit apparaat niet (meer). ${pijl("Alle apparaten", "#/apparaten")}</p>` })}</div>`;
    return;
  }
  const ander = (apparaat?.id ?? null) !== getoond; // naar een ander apparaat, of terug naar de lijst
  const terug = ander && !apparaat && !ctx.nieuw;
  if (ander && apparaat && getoond === null && !ctx.nieuw) lijstPlek = scrollY;
  getoond = apparaat?.id ?? null;
  if (apparaat) {
    ctx.sub(apparaat.naam);
    tekenDetail(main, apparaat);
    if (ander) scrollTo({ top: 0 });
  } else {
    ctx.sub(subtitel());
    tekenLijst(main);
    if (terug) scrollTo({ top: lijstPlek }); // terug in de lijst waar je was
  }
  peil();
}

function subtitel() {
  const aan = staat.lijst.filter((a) => a.aan).length;
  return `${staat.lijst.length} ${staat.lijst.length === 1 ? "apparaat" : "apparaten"} · ${aan} aan`;
}

function nietGekoppeld() {
  return `<div class="raster">${kaart({
    titel: "Slimme apparaten",
    klasse: "b-12",
    id: "k-apparaten",
    inhoud: `<div class="leeg-blok">
      <span class="rond">${icoon("apparaten")}</span>
      <p class="titel">Nog geen apparaten gekoppeld</p>
      <p class="zacht">Koppel Tuya om je slimme stekkers, lampen, thermostaten en sensoren hier te zien en te bedienen.
        Dat werkt voor alles wat in de app Smart Life of Tuya Smart staat, ook van merken als LSC Smart Connect (Action), Nedis, Calex en Silvercrest (Lidl).</p>
      <a class="knop primair" href="#/koppelingen">Koppel Tuya</a>
    </div>`,
  })}</div>`;
}

// ── lijst ─────────────────────────────────────────────────────────────────────

function tekenLijst(main) {
  const { lijst } = staat;
  const soorten = Object.keys(SOORTEN).filter((s) => lijst.some((a) => a.soort === s));
  if (filter !== "alle" && filter !== "aan" && !soorten.includes(filter)) filter = "alle";
  const knoppen = [["alle", "Alle"], ["aan", "Aan"], ...(soorten.length > 1 ? soorten.map((s) => [s, SOORTEN[s].naam]) : [])];
  main.innerHTML = `<div class="raster" id="apparaten">
    <div class="kpi-rij b-12" id="apparaten-kpi">${kpis()}</div>
    <section class="kaart b-12" id="k-apparaten" aria-labelledby="k-apparaten-titel">
      <header class="kaart-kop"><h2 id="k-apparaten-titel">Apparaten</h2><span class="sub" data-bijgewerkt>${bijgewerkt()}</span>
        <div class="rechts filter-rij"><div class="segment" role="group" aria-label="Toon">
          ${knoppen.map(([k, n]) => `<button type="button" data-filter="${k}" aria-pressed="${k === filter}">${n}</button>`).join("")}
        </div></div>
      </header>
      <ul class="apparaten" id="apparaten-lijst">${lijst.map(tegel).join("")}</ul>
      <p class="leeg" id="apparaten-leeg" hidden>Er staat nu niets aan.</p>
      <p class="kaart-voet">Bedienen gaat via de cloud van Tuya: een apparaat reageert meestal binnen een tel. Het verbruik van vandaag is geschat uit de metingen van elk kwartier.</p>
    </section>
    <p class="verborgen" aria-live="polite" id="apparaten-melding"></p>
  </div>`;
  pasFilterToe();
  koppel($("#apparaten", main));
}

function bijgewerkt() {
  return staat.bijgewerkt ? `bijgewerkt ${relatief(staat.bijgewerkt)}` : "";
}

function kpis() {
  const { lijst, prijs: p, niveau: niv, vandaag: v } = staat;
  const aan = lijst.filter((a) => a.aan).length;
  const offline = lijst.filter((a) => !a.online).length;
  const meters = lijst.filter((a) => a.metingen.vermogen_w != null && a.online);
  const vermogen = meters.reduce((s, a) => s + (a.aan === false ? 0 : a.metingen.vermogen_w), 0);
  const kost = p != null ? (vermogen / 1000) * p : null;
  const kpi = (naam, waarde, sub) => `<div class="kpi"><div class="kpi-naam">${naam}</div><div class="kpi-waarde">${waarde}</div><div class="kpi-sub">${sub}</div></div>`;
  return [
    kpi("Aan", `${aan} <small>van ${lijst.length}</small>`, offline ? `${offline} offline` : "alles bereikbaar"),
    kpi("Vermogen nu", meters.length ? `${getal(vermogen, 0)} <small>W</small>` : "–", meters.length ? `${meters.length} ${meters.length === 1 ? "stekker meet" : "stekkers meten"} mee` : "geen stekker met meting"),
    kpi("Kost nu", kost != null && meters.length ? `${prijs(kost)} <small>per uur</small>` : "–",
      niv ? `<span class="niveau"><i style="background:var(${niv.kleur})"></i>${niv.naam}: ${prijs(p)} per kWh</span>` : "nog geen stroomprijs"),
    kpi("Vandaag", v && Object.keys(v.apparaten).length ? `${hoeveelheid(v.kwh)} <small>kWh</small>` : "–",
      v && Object.keys(v.apparaten).length ? `${v.kosten != null ? `${euro(v.kosten)} · ` : ""}geschat${v.tot ? ` tot ${klok(v.tot)}` : ""}` : "na een paar metingen"),
  ].join("");
}

/** Eén apparaat als tegel: icoon, naam, stand en de belangrijkste bediening. */
function tegel(a) {
  const schakel = hoofd(a);
  const sw = schakel.length && a.aan != null
    ? `<span class="schakelaar"><input type="checkbox" role="switch" data-schakel="${esc(schakel.join(","))}" ${a.aan ? "checked" : ""} ${a.online ? "" : "disabled"} aria-label="${esc(a.naam)} ${a.aan ? "uitzetten" : "aanzetten"}"><span></span></span>`
    : "";
  const klasse = [!a.online ? "offline" : a.aan ? "aan" : "", a.toestand && TOESTAND_SOORT[a.toestand] ? `t-${TOESTAND_SOORT[a.toestand]}` : ""].join(" ");
  return `<li class="apparaat ${klasse}" data-id="${esc(a.id)}" data-soort="${a.soort}" data-aan="${a.aan ? 1 : 0}">
    <div class="apparaat-rij">
      <a class="apparaat-kop" href="#/apparaten?id=${encodeURIComponent(a.id)}">
        <span class="icoon">${icoon(icoonVan(a))}</span>
        <span class="tekst"><span class="naam">${esc(a.naam)}</span><span class="stand">${esc(stand(a))}</span></span>
      </a>
      ${sw}
    </div>
    ${a.online ? snelBediening(a) : ""}
    ${voet(a)}
  </li>`;
}

/** Onder de tegel: wat je het vaakst wilt doen, als het apparaat het kan. */
function snelBediening(a) {
  const kanalen = a.schakelaars.filter((c) => bed(a, c));
  if (kanalen.length > 1) {
    return `<div class="kanalen" role="group" aria-label="Stopcontacten van ${esc(a.naam)}">${kanalen
      .map((c) => {
        const naam = kanaalNaam(c, a);
        const kort = naam.replace(/^(Stopcontact|Kanaal) /, "");
        return `<button type="button" class="kanaal" data-kanaal="${c}" aria-pressed="${bed(a, c).waarde === true}" aria-label="${esc(naam)}" title="${esc(naam)}">${esc(kort)}</button>`;
      })
      .join("")}</div>`;
  }
  const licht = bed(a, "bright_value_v2") || bed(a, "bright_value");
  if (a.soort === "lamp" && licht && a.aan) return `<div class="snel">${schuif(a, licht, true)}</div>`;
  const doel = bed(a, "temp_set");
  if (doel) return `<div class="snel">${stapper(a, doel, true)}</div>`;
  const rolluik = bed(a, "control");
  if (rolluik) return `<div class="snel">${keuzeKnoppen(a, rolluik, true)}</div>`;
  return "";
}

function voet(a) {
  const delen = [];
  const kost = perUur(a, staat.prijs);
  if (kost != null && a.metingen.vermogen_w >= 0.5) delen.push(`${prijs(kost)} per uur`);
  const v = staat.vandaag?.apparaten[a.id];
  if (v && v.kwh >= 0.005) delen.push(`vandaag ${hoeveelheid(v.kwh)} kWh${v.kosten >= 0.005 ? ` · ${euro(v.kosten)}` : ""}`);
  if (a.metingen.accu_pct != null && a.soort === "sensor") delen.push(`batterij ${getal(a.metingen.accu_pct, 0)}%`);
  if (a.metingen.accu_pct != null && a.metingen.accu_pct < 15) delen.push("batterij bijna leeg");
  return delen.length ? `<p class="apparaat-voet">${delen.map((d) => `<span>${esc(d)}</span>`).join("")}</p>` : "";
}

function pasFilterToe() {
  const ul = $("#apparaten-lijst");
  if (!ul) return;
  let zichtbaar = 0;
  for (const li of $$(".apparaat", ul)) {
    const toon = filter === "alle" || (filter === "aan" ? li.dataset.aan === "1" : li.dataset.soort === filter);
    li.hidden = !toon;
    zichtbaar += toon;
  }
  $("#apparaten-leeg").hidden = zichtbaar > 0;
  $("#apparaten-leeg").textContent = filter === "aan" ? "Er staat nu niets aan." : "Geen apparaten van deze soort.";
}

// ── één apparaat ──────────────────────────────────────────────────────────────

let periode = 1; // dagen in de grafiek
let getoond = null; // id van het apparaat dat open staat (null: de lijst)
let lijstPlek = 0; // waar je in de lijst was, voor de weg terug

function tekenDetail(main, a) {
  main.innerHTML = `<div class="raster" id="apparaten">
    <p class="b-12 terug"><a class="pijl" href="#/apparaten">← Alle apparaten</a></p>
    ${detailKaart(a)}
    ${gegevensKaart(a)}
    ${heeftHistorie(a) ? kaart({
      titel: grafiekTitel(a),
      sub: "uit de metingen van elk kwartier",
      klasse: "b-12",
      id: "k-historie",
      rechts: `<div class="segment" role="group" aria-label="Periode">
        <button type="button" data-periode="1" aria-pressed="${periode === 1}">24 uur</button>
        <button type="button" data-periode="7" aria-pressed="${periode === 7}">7 dagen</button></div>`,
      inhoud: '<div class="grafiek" id="g-apparaat" role="img"></div><div class="legenda" id="g-apparaat-legenda"></div>',
    }) : ""}
    <p class="verborgen" aria-live="polite" id="apparaten-melding"></p>
  </div>`;
  koppel($("#apparaten", main));
  if (heeftHistorie(a)) laadHistorie(a);
}

function detailKaart(a) {
  const m = a.metingen;
  const kost = perUur(a, staat.prijs);
  const schakel = hoofd(a);
  const groot = !a.online
    ? '<div class="groot zacht">Offline</div>'
    : m.vermogen_w != null && a.aan !== false
      ? `<div class="groot">${getal(m.vermogen_w, m.vermogen_w < 10 ? 1 : 0)}<small>W</small></div>`
      : m.temperatuur != null
        ? `<div class="groot">${getal(m.temperatuur, 1)}<small>°C</small></div>`
        : a.toestand
          ? `<div class="groot">${esc(TOESTAND[a.toestand] || mens(a.toestand))}</div>`
          : a.soort === "gordijn" && positie(a) != null
            ? `<div class="groot">${getal(positie(a), 0)}<small>% open</small></div>`
            : a.aan != null
              ? `<div class="groot">${a.aan ? "Aan" : "Uit"}${a.soort === "lamp" && a.aan && helderheid(a) != null ? `<small>${helderheid(a)}%</small>` : ""}</div>`
              : "";
  const onder = [
    kost != null && m.vermogen_w >= 0.5 ? `${prijs(kost)} per uur bij de stroomprijs van nu` : null,
    m.vochtigheid != null ? `luchtvochtigheid ${getal(m.vochtigheid, 0)}%` : null,
    bed(a, "temp_set")?.waarde != null ? `gewenst ${graden(bed(a, "temp_set").waarde)}` : null,
  ].filter(Boolean);
  const pilKlasse = !a.online ? "" : a.toestand ? TOESTAND_SOORT[a.toestand] || "" : a.aan ? "accent" : "";
  const pilTekst = !a.online ? "Offline" : a.toestand ? TOESTAND[a.toestand] : a.aan == null ? "Online" : a.aan ? "Aan" : "Uit";
  const regels = a.bediening.filter((b) => !(schakel.length === 1 && b.code === schakel[0])).map((b) => bedieningRegel(a, b)).filter(Boolean);
  return `<section class="kaart b-8 apparaat-detail ${a.aan ? "aan" : ""}" id="k-apparaat" data-id="${esc(a.id)}" aria-labelledby="k-apparaat-titel">
    <header class="kaart-kop"><h2 id="k-apparaat-titel">${esc(a.naam)}</h2>${a.product ? `<span class="sub">${esc(a.product)}</span>` : ""}
      <div class="rechts"><span class="pil ${pilKlasse}"><span class="stip"></span>${esc(pilTekst)}</span></div></header>
    <div class="apparaat-held">
      <span class="icoon groot-icoon">${icoon(icoonVan(a))}</span>
      <div class="held-tekst">${groot}${onder.length ? `<p class="zacht">${esc(onder.join(" · "))}</p>` : ""}</div>
      ${schakel.length && a.aan != null ? `<span class="schakelaar groot"><input type="checkbox" role="switch" data-schakel="${esc(schakel.join(","))}" ${a.aan ? "checked" : ""} ${a.online ? "" : "disabled"} aria-label="${esc(a.naam)} ${a.aan ? "uitzetten" : "aanzetten"}"><span></span></span>` : ""}
    </div>
    ${!a.online ? melding("Het apparaat is offline: Tuya kan het niet bereiken. Kijk of het stroom heeft en verbonden is met de wifi.", "let_op") : ""}
    ${regels.length ? `<h3 class="tussenkop">Bediening</h3><div class="formulier">${regels.join("")}</div>` : ""}
    ${!a.bediening.length && a.online && a.soort !== "sensor" ? '<p class="kaart-voet">Tuya gaf (nog) niet door wat je bij dit apparaat kunt bedienen. De verzamelaar vraagt het bij de volgende ronde opnieuw.</p>' : ""}
  </section>`;
}

/** Eén regel in Bediening: label links, de juiste knop rechts. */
function bedieningRegel(a, b) {
  const info = BEDIENING[b.code] || {};
  const label = /^switch/.test(b.code) ? kanaalNaam(b.code, a) : info.label || mens(b.code);
  let uitleg = info.uitleg || "";
  let invoer;
  if (/^countdown/.test(b.code)) {
    if (b.waarde > 0) uitleg = `Gaat ${a.aan ? "uit" : "aan"} over ${b.waarde >= 3600 ? `${getal(b.waarde / 3600, 1)} uur` : `${Math.round(b.waarde / 60)} min`}`;
    else uitleg = `Zet het apparaat na een tijd ${a.aan ? "uit" : "aan"}`;
    const knoppen = TIMER.filter(([s]) => s <= b.max);
    invoer = `<div class="segment" role="group" aria-label="Timer">${knoppen
      .map(([s, n]) => `<button type="button" data-code="${b.code}" data-waarde="${s}" aria-pressed="${s === 0 ? !(b.waarde > 0) : false}" ${a.online ? "" : "disabled"}>${n}</button>`)
      .join("")}</div>`;
    return regel2("Timer", uitleg, invoer, true);
  }
  if (b.type === "Boolean") {
    invoer = `<span class="schakelaar"><input type="checkbox" role="switch" data-schakel="${b.code}" ${b.waarde ? "checked" : ""} ${a.online ? "" : "disabled"} aria-label="${esc(label)}"><span></span></span>`;
  } else if (b.type === "Enum") {
    invoer = b.keuzes.length <= 4 || b.code === "control" ? keuzeKnoppen(a, b) : keuzeLijst(a, b, label);
  } else if (b.type === "Integer") {
    if (b.code === "temp_set" || (!info.procent && (b.max - b.min) / b.stap <= 60)) invoer = stapper(a, b);
    else invoer = schuif(a, b);
  }
  return invoer ? regel2(label, uitleg, invoer, b.type === "Enum" || b.type === "Integer") : "";
}

const regel2 = (label, uitleg, invoer, breed = false) =>
  `<div class="veld${breed ? " breed" : ""}"><span class="veld-label">${esc(label)}${uitleg ? `<span class="uitleg">${esc(uitleg)}</span>` : ""}</span>${invoer}</div>`;

function keuzeKnoppen(a, b, kort = false) {
  return `<div class="segment${kort ? " vol" : ""}" role="group" aria-label="${esc(BEDIENING[b.code]?.label || mens(b.code))}">${b.keuzes
    .map((k) => `<button type="button" data-code="${b.code}" data-waarde="${esc(k)}" aria-pressed="${b.code !== "control" && b.waarde === k}" ${a.online ? "" : "disabled"}>${esc(keuzeNaam(b.code, k))}</button>`)
    .join("")}</div>`;
}

function keuzeLijst(a, b, label) {
  return `<select class="keuzelijst" data-code="${b.code}" aria-label="${esc(label)}" ${a.online ? "" : "disabled"}>${b.keuzes
    .map((k) => `<option value="${esc(k)}" ${b.waarde === k ? "selected" : ""}>${esc(keuzeNaam(b.code, k))}</option>`)
    .join("")}</select>`;
}

/** Schuif in procenten (helderheid, positie) of in de eenheid van het apparaat. */
function schuif(a, b, kort = false) {
  const procent = BEDIENING[b.code]?.procent;
  const w = procent ? pct(b) ?? 0 : b.waarde ?? b.min;
  const [laag, hoog, stap] = procent ? [b.min > 0 ? 1 : 0, 100, 1] : [b.min, b.max, b.stap];
  const tekst = procent ? `${w}%` : `${getal(w, stap < 1 ? 1 : 0)}${b.eenheid ? ` ${b.eenheid}` : ""}`;
  const label = BEDIENING[b.code]?.label || mens(b.code);
  return `<span class="schuif${kort ? " kort" : ""}">
    <input type="range" min="${laag}" max="${hoog}" step="${stap}" value="${w}" data-schuif="${b.code}" ${procent ? 'data-procent="1"' : ""}
      aria-label="${esc(label)}${kort ? ` ${esc(a.naam)}` : ""}" aria-valuetext="${esc(tekst)}" style="--vul:${((w - laag) / (hoog - laag || 1)) * 100}%" ${a.online ? "" : "disabled"}>
    <output>${esc(tekst)}</output></span>`;
}

/** − 18,5 °C +: voor een temperatuur of een klein bereik. */
function stapper(a, b, kort = false) {
  const tekst = b.waarde == null ? "–" : `${getal(b.waarde, b.stap < 1 ? 1 : 0)}${b.eenheid ? ` ${b.eenheid}` : ""}`;
  const label = BEDIENING[b.code]?.label || mens(b.code);
  return `<span class="stapper${kort ? " kort" : ""}" data-code="${b.code}" role="group" aria-label="${esc(label)}${kort ? ` ${esc(a.naam)}` : ""}">
    <button type="button" class="icoonknop" data-stap="-1" aria-label="Lager" ${a.online && b.waarde > b.min ? "" : "disabled"}>${icoon("min")}</button>
    <output aria-live="polite">${esc(tekst)}</output>
    <button type="button" class="icoonknop" data-stap="1" aria-label="Hoger" ${a.online && b.waarde < b.max ? "" : "disabled"}>${icoon("plus")}</button></span>`;
}

function gegevensKaart(a) {
  const m = a.metingen;
  const r = [
    ["Vermogen", m.vermogen_w != null ? `${getal(m.vermogen_w, 1)} <small>W</small>` : null],
    ["Spanning", m.spanning_v != null ? `${getal(m.spanning_v, 1)} <small>V</small>` : null],
    ["Stroom", m.stroom_a != null ? `${getal(m.stroom_a, 2)} <small>A</small>` : null],
    ["Teller", m.energie_kwh != null ? `${hoeveelheid(m.energie_kwh)} <small>kWh</small>` : null],
    ["Temperatuur", m.temperatuur != null ? `${getal(m.temperatuur, 1)} <small>°C</small>` : null],
    ["Luchtvochtigheid", m.vochtigheid != null ? `${getal(m.vochtigheid, 0)} <small>%</small>` : null],
    ["Batterij", m.accu_pct != null ? `${getal(m.accu_pct, 0)} <small>%</small>` : null],
  ];
  for (const s of a.status) {
    if (GEMETEN.has(s.code)) continue;
    const info = STATUS[s.code] || {};
    const w = info.keuzes ? info.keuzes[String(s.waarde)] ?? mens(s.waarde) : typeof s.waarde === "boolean" ? (s.waarde ? "Ja" : "Nee") : typeof s.waarde === "number" ? getal(s.waarde, Number.isInteger(s.waarde) ? 0 : 1) : mens(s.waarde);
    const eenheid = info.eenheid || s.eenheid;
    r.push([info.label || mens(s.code), `${esc(w)}${eenheid && typeof s.waarde === "number" ? ` <small>${esc(eenheid)}</small>` : ""}`]);
  }
  const v = staat.vandaag?.apparaten[a.id];
  if (v) r.push(["Vandaag (geschat)", `${hoeveelheid(v.kwh)} <small>kWh</small>${v.kosten != null ? ` · ${euro(v.kosten)}` : ""}`]);
  r.push(["Verbinding", a.online ? "Online" : '<span class="tekst-let-op">Offline</span>']);
  r.push(["Bijgewerkt", esc(relatief(staat.bijgewerkt))]);
  const lijst = r.filter(([, w]) => w != null);
  return kaart({
    titel: "Gegevens",
    sub: "zoals het apparaat ze meldt",
    klasse: "b-4",
    id: "k-gegevens",
    inhoud: `<dl class="gegevens">${lijst.map(([l, w]) => `<dt>${esc(l)}</dt><dd>${w}</dd>`).join("")}</dl>`,
  });
}

// ── historie ──────────────────────────────────────────────────────────────────

const heeftHistorie = (a) => a.metingen.vermogen_w != null || a.metingen.temperatuur != null || a.aan != null;
const grafiekTitel = (a) => (a.metingen.vermogen_w != null ? "Vermogen" : a.metingen.temperatuur != null ? "Temperatuur" : "Aan en uit");

async function laadHistorie(a) {
  const el = $("#g-apparaat");
  let h;
  try {
    h = await api(`apparaten/${encodeURIComponent(a.id)}/historie?dagen=${periode}`);
  } catch (err) {
    meldFout(err);
    return;
  }
  if (!el.isConnected) return;
  if (!h.tijden.length) {
    el.outerHTML = leeg("Nog geen metingen: de verzamelaar bewaart elk kwartier de stand.");
    return;
  }
  const label = (iso) => (periode > 1 ? `${dagnaam(iso)} ${klok(iso)}` : klok(iso));
  const x = h.tijden;
  let reeksen;
  let legenda;
  let aria;
  if (a.metingen.vermogen_w != null) {
    const k = css("--c-stroom");
    reeksen = [lijn("Vermogen", h.vermogen_w, k, { step: "end", areaStyle: { color: doorzichtig(k, 0.18) }, showSymbol: false })];
    legenda = `<span><i style="background:${k}"></i>Vermogen (W)</span>`;
    const max = Math.max(...h.vermogen_w.filter((w) => w != null));
    aria = `Vermogen van ${a.naam}, ${periode === 1 ? "laatste 24 uur" : "laatste 7 dagen"}; hoogste ${wattTekst(max)}`;
  } else if (a.metingen.temperatuur != null) {
    const t = css("--c-temp");
    const zacht = css("--inkt-3");
    reeksen = [lijn("Temperatuur", h.temperatuur, t)];
    legenda = `<span><i class="lijn" style="background:${t}"></i>Temperatuur (°C)</span>`;
    if (h.vochtigheid.some((w) => w != null)) {
      reeksen.push(lijn("Luchtvochtigheid", h.vochtigheid, zacht, { yAxisIndex: 1, lineStyle: { color: zacht, width: 1.5, type: "dashed" } }));
      legenda += `<span><i class="lijn" style="background:${zacht}"></i>Luchtvochtigheid (%)</span>`;
    }
    aria = `Temperatuur van ${a.naam}, ${periode === 1 ? "laatste 24 uur" : "laatste 7 dagen"}`;
  } else {
    const k = css("--accent");
    reeksen = [lijn("Aan", h.aan.map((w) => (w == null ? null : w ? 1 : 0)), k, { step: "end", areaStyle: { color: doorzichtig(k, 0.2) }, showSymbol: false })];
    legenda = `<span><i style="background:${k}"></i>Aan</span>`;
    aria = `Wanneer ${a.naam} aan stond, ${periode === 1 ? "laatste 24 uur" : "laatste 7 dagen"}`;
  }
  el.setAttribute("aria-label", aria);
  el.classList.toggle("laag", a.metingen.vermogen_w == null && a.metingen.temperatuur == null); // aan of uit: lage grafiek
  $("#g-apparaat-legenda").innerHTML = legenda;
  const aanUit = a.metingen.vermogen_w == null && a.metingen.temperatuur == null;
  const as = basis().yAxis; // twee assen: basis() vult een lijst niet aan, dus zelf de opmaak meegeven
  // Een label bij het eerste kwartier van elke dag (7 dagen) of van elk vierde uur (24 uur).
  const asLabel = (_i, iso) => {
    const [u, m] = klok(iso).split(":").map(Number);
    return m < 15 && (periode > 1 ? u === 0 : u % 4 === 0);
  };
  grafiek(el).setOption(
    basis({
      grid: { top: 16, right: reeksen.length > 1 ? 8 : 8 },
      tooltip: {
        axisPointer: { type: "line", lineStyle: { color: css("--lijn-sterk") } },
        formatter: (punten) =>
          `${label(x[punten[0].dataIndex])}${punten
            .map((p) => regel(p.color, p.seriesName, p.value == null ? "–" : aanUit ? (p.value ? "aan" : "uit") : p.seriesName === "Vermogen" ? wattTekst(p.value) : p.seriesName === "Temperatuur" ? graden(p.value) : `${getal(p.value, 0)}%`))
            .join("")}`,
      },
      xAxis: { data: x, boundaryGap: false, axisLabel: { formatter: (iso) => (periode > 1 ? dagnaam(iso) : klok(iso)), interval: asLabel } },
      yAxis: aanUit
        ? { min: 0, max: 1, interval: 1, axisLabel: { formatter: (w) => (w ? "aan" : "uit") } }
        : [
            { ...as, scale: a.metingen.temperatuur != null && a.metingen.vermogen_w == null },
            { ...as, show: false, min: 0, max: 100 }, // luchtvochtigheid: de waarden staan in de tooltip
          ],
      series: reeksen,
    }),
  );
}

// ── bedienen ──────────────────────────────────────────────────────────────────

/** Eén keer per tekening: alle knoppen binnen #apparaten via deze luisteraars. */
function koppel(wortel) {
  wortel.addEventListener("pointerdown", () => (actief = Date.now()));
  wortel.addEventListener("keydown", () => (actief = Date.now()));
  wortel.addEventListener("click", (e) => {
    const f = e.target.closest("[data-filter]");
    if (f) {
      filter = f.dataset.filter;
      for (const b of $$("[data-filter]", wortel)) b.setAttribute("aria-pressed", String(b === f));
      return pasFilterToe();
    }
    const p = e.target.closest("[data-periode]");
    if (p) {
      periode = Number(p.dataset.periode);
      for (const b of $$("[data-periode]", wortel)) b.setAttribute("aria-pressed", String(b === p));
      ruimOp();
      const a = staat.lijst.find((x) => x.id === $("#k-apparaat").dataset.id);
      if (a) laadHistorie(a);
      return;
    }
    const kanaal = e.target.closest("[data-kanaal]");
    if (kanaal) return wissel(kanaal, [{ code: kanaal.dataset.kanaal, waarde: kanaal.getAttribute("aria-pressed") !== "true" }]);
    const keuze = e.target.closest("button[data-code][data-waarde]");
    if (keuze) {
      const b = bed(apparaatVan(keuze), keuze.dataset.code);
      const waarde = b?.type === "Integer" ? Number(keuze.dataset.waarde) : keuze.dataset.waarde;
      return stuur(keuze, [{ code: keuze.dataset.code, waarde }], () => {
        if (keuze.dataset.code === "control") return;
        for (const k of $$("button", keuze.parentElement)) k.setAttribute("aria-pressed", String(k === keuze));
      });
    }
    const stap = e.target.closest("[data-stap]");
    if (stap) return stapOp(stap);
  });
  wortel.addEventListener("change", (e) => {
    const t = e.target;
    if (t.matches("input[data-schakel]")) {
      return stuur(t, t.dataset.schakel.split(",").map((code) => ({ code, waarde: t.checked })), null, () => (t.checked = !t.checked));
    }
    if (t.matches("input[data-schuif]")) {
      const b = bed(apparaatVan(t), t.dataset.schuif);
      const waarde = t.dataset.procent ? vanPct(b, Number(t.value)) : Number(t.value);
      return stuur(t, [{ code: b.code, waarde }]);
    }
    if (t.matches("select[data-code]")) return stuur(t, [{ code: t.dataset.code, waarde: t.value }]);
  });
  wortel.addEventListener("input", (e) => {
    const t = e.target;
    if (!t.matches("input[data-schuif]")) return;
    const b = bed(apparaatVan(t), t.dataset.schuif);
    const tekst = t.dataset.procent ? `${t.value}%` : `${getal(Number(t.value), b.stap < 1 ? 1 : 0)}${b.eenheid ? ` ${b.eenheid}` : ""}`;
    t.nextElementSibling.textContent = tekst;
    t.setAttribute("aria-valuetext", tekst);
    t.style.setProperty("--vul", `${((t.value - t.min) / (t.max - t.min || 1)) * 100}%`);
  });
}

const apparaatVan = (el) => staat.lijst.find((a) => a.id === el.closest("[data-id]")?.dataset.id);

function wissel(knop, wensen) {
  knop.setAttribute("aria-pressed", String(wensen[0].waarde));
  stuur(knop, wensen, null, () => knop.setAttribute("aria-pressed", String(!wensen[0].waarde)));
}

// Stapper: elke klik meteen zichtbaar, en pas na een korte pauze één opdracht naar Tuya.
const stapWacht = new Map();
function stapOp(knop) {
  const groep = knop.closest(".stapper");
  const a = apparaatVan(groep);
  const b = bed(a, groep.dataset.code);
  const huidig = Number(groep.dataset.nieuw ?? b.waarde ?? b.min);
  const nieuw = Math.round(Math.max(b.min, Math.min(b.max, huidig + Number(knop.dataset.stap) * b.stap)) * 100) / 100;
  groep.dataset.nieuw = nieuw;
  $("output", groep).textContent = `${getal(nieuw, b.stap < 1 ? 1 : 0)}${b.eenheid ? ` ${b.eenheid}` : ""}`;
  $('[data-stap="-1"]', groep).disabled = nieuw <= b.min;
  $('[data-stap="1"]', groep).disabled = nieuw >= b.max;
  const sleutel = `${a.id}:${b.code}`;
  clearTimeout(stapWacht.get(sleutel));
  stapWacht.set(sleutel, setTimeout(() => {
    stapWacht.delete(sleutel);
    stuur(groep, [{ code: b.code, waarde: nieuw }]);
  }, 700));
}

/** Opdrachten naar Tuya. Het element is meteen bijgewerkt (`voor`); mislukt het, dan gaat het terug (`terug`). */
async function stuur(el, wensen, voor = null, terug = null) {
  const houder = el.closest("[data-id]");
  const id = houder.dataset.id;
  actief = Date.now();
  voor?.();
  houder.setAttribute("aria-busy", "true");
  try {
    const { apparaat } = await api(`apparaten/${encodeURIComponent(id)}`, { methode: "POST", body: { opdrachten: wensen }, legen: false });
    werkApparaatBij(apparaat);
    meld(`${apparaat.naam}: ${stand(apparaat) || "opdracht verstuurd"}`);
    setTimeout(() => ververs({ stil: true }), CONTROLE_MS);
  } catch (err) {
    terug?.();
    houder.removeAttribute("aria-busy");
    meldFout(err);
  }
}

function meld(tekst) {
  const el = $("#apparaten-melding");
  if (el) el.textContent = tekst;
}

/** Eén apparaat opnieuw tekenen (tegel of detail), zonder de focus kwijt te raken. */
function werkApparaatBij(a, { peiling = false } = {}) {
  const i = staat.lijst.findIndex((x) => x.id === a.id);
  if (i >= 0) staat.lijst[i] = a;
  const oud = $(`.apparaat[data-id="${CSS.escape(a.id)}"]`);
  const detail = $(`#k-apparaat[data-id="${CSS.escape(a.id)}"]`);
  const doel = oud || detail;
  if (!doel) return;
  if (peiling && doel.contains(document.activeElement) && document.activeElement.matches('input[type="range"]')) return;
  const focus = sleutelVan(document.activeElement, doel);
  doel.outerHTML = oud ? tegel(a) : detailKaart(a);
  const nieuw = oud ? $(`.apparaat[data-id="${CSS.escape(a.id)}"]`) : $("#k-apparaat");
  if (oud) {
    pasFilterToe();
    const kpi = $("#apparaten-kpi");
    if (kpi) kpi.innerHTML = kpis();
    zetSub(subtitel());
  }
  if (focus) $(focus, nieuw)?.focus();
}

/** Selector om na het opnieuw tekenen hetzelfde element de focus terug te geven. */
function sleutelVan(el, binnen) {
  if (!el || !binnen.contains(el)) return null;
  for (const a of ["data-schakel", "data-kanaal", "data-schuif", "data-stap"]) {
    if (el.hasAttribute(a)) return `[${a}="${CSS.escape(el.getAttribute(a))}"]`;
  }
  if (el.dataset.code && el.dataset.waarde != null) return `[data-code="${CSS.escape(el.dataset.code)}"][data-waarde="${CSS.escape(el.dataset.waarde)}"]`;
  if (el.dataset.code) return `[data-code="${CSS.escape(el.dataset.code)}"]`;
  return null;
}

/** Verse stand van Tuya; alleen apparaten die veranderd zijn worden opnieuw getekend. */
async function ververs({ stil = false } = {}) {
  if ($("#inhoud").dataset.pagina !== "apparaten" || !staat) return;
  let live;
  try {
    live = await api("apparaten", { vers: true });
  } catch (err) {
    if (!stil) meldFout(err);
    return;
  }
  if (!live.gekoppeld || $("#inhoud").dataset.pagina !== "apparaten") return;
  const oud = new Map(staat.lijst.map((a) => [a.id, JSON.stringify(a)]));
  staat.bijgewerkt = live.bijgewerkt;
  staat.tijd = Date.now();
  const nieuwIds = live.apparaten.map((a) => a.id).join();
  if (nieuwIds !== staat.lijst.map((a) => a.id).join() && $("#apparaten-lijst")) {
    staat.lijst = live.apparaten; // apparaat erbij of weg: alles opnieuw
    return tekenLijst($("#inhoud"));
  }
  for (const a of live.apparaten) {
    // Niet terwijl er een opdracht loopt of je een schuif vasthoudt: dan wint wat je net deed.
    if (oud.get(a.id) !== JSON.stringify(a) && !$(`[data-id="${CSS.escape(a.id)}"][aria-busy="true"]`)) werkApparaatBij(a, { peiling: true });
  }
  for (const el of $$("[data-bijgewerkt]")) el.textContent = bijgewerkt();
}

function peil() {
  clearInterval(peiling);
  actief = Date.now();
  peiling = setInterval(() => {
    if ($("#inhoud").dataset.pagina !== "apparaten") return clearInterval(peiling);
    if (document.visibilityState !== "visible" || Date.now() - actief > STIL_MS) {
      for (const el of $$("[data-bijgewerkt]")) el.textContent = bijgewerkt();
      return;
    }
    ververs({ stil: true });
  }, PEIL_MS);
}
