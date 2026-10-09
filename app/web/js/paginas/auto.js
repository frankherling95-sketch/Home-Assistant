// Auto: alles wat de auto doorgeeft (BMW CarData, Kia/Hyundai Connect): accu en laden, rijden,
// onderhoud, deuren en ramen, locatie en laadhistorie. Wat de auto niet doorgeeft, blijft weg.

import { api, autoFoto, css, datumKort, esc, euro, getal, isoDatum, klok, meldFout, relatief, toast } from "../basis.js";
import { basis, grafiek, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, melding, pil, skeletKaart, tegel } from "../onderdelen.js";

// ── vertalingen van wat de auto doorgeeft ─────────────────────────────────────

const SLOT = { SECURED: "Op slot", LOCKED: "Op slot", "SELECTIVE-LOCKED": "Deels op slot", UNLOCKED: "Niet op slot" };
const ALARM = { unarmed: "Uit", doorsOnly: "Aan (alleen deuren)", doorsTiltCabin: "Aan" };
const RAAM = { CLOSED: "Dicht", INTERMEDIATE: "Op een kier", OPEN: "Open" };
const DAK = { CLOSED: "Dicht", OPEN: "Open", OPEN_TILT: "Gekanteld", INTERMEDIATE_TILT: "Half gekanteld", INTERMEDIATE: "Half open" };
const METHODE = { AC_TYPE2PLUG: "AC (type 2)", AC_TYPE1PLUG: "AC (type 1)", DC: "DC (snelladen)", NOCHARGING: "Niet aan het laden" };
const FASEN = { "1-PHASES": "1 fase", "2-PHASES": "2 fasen", "3-PHASES": "3 fasen", NO_CHARGING: null };
const VOORKEUR = { CHARGING_WINDOW: "Laadvenster", SMART_CHARGING: "Slim laden van BMW", NO_PRESELECTION: "Direct laden" };
const EINDE = {
  CHARGING_GOAL_REACHED: "Laaddoel bereikt",
  END_REQUESTED_BY_DRIVER: "Gestopt door jou",
  CONNECTOR_REMOVED: "Stekker eruit",
  POWERGRID_FAILED: "Stroomstoring",
  HV_SYSTEM_FAILURE: "Storing in de auto",
  CHARGING_STATION_FAILURE: "Storing in het laadpunt",
  PARKING_LOCK_FAILED: "Auto niet in de parkeerstand",
  NO_PARKING_LOCK: "Auto niet in de parkeerstand",
};
const KABEL = { CHARGING_CABLE_LOCKED: "Vergrendeld", CHARGING_CABLE_NOT_LOCKED: "Niet vergrendeld", CHARGING_CABLE_LOCKING_ERROR_DETECTED: "Storing" };
// Onderhoud volgens de auto (Condition Based Service van BMW).
const SERVICE = {
  OIL: "Motorolie",
  BRAKE_FLUID: "Remvloeistof",
  VEHICLE_CHECK: "Onderhoudsbeurt",
  VEHICLE_TUV: "APK",
  BRAKE_PADS_FRONT: "Remblokken voor",
  BRAKE_PADS_REAR: "Remblokken achter",
  MICRO_FILTER: "Interieurfilter",
  CABIN_FILTER: "Interieurfilter",
  TIRE_WEAR: "Banden",
  COOLANT: "Koelvloeistof",
};
const SERVICESTATUS = { OK: "in orde", PENDING: "binnenkort", OVERDUE: "te laat" };
const KLIMAAT = { standby: "Klaar", heating: "Verwarmen", cooling: "Koelen", ventilation: "Ventileren", inactive: "Uit", active: "Aan" };
const PLEKKEN = [["linksvoor", "Linksvoor"], ["rechtsvoor", "Rechtsvoor"], ["linksachter", "Linksachter"], ["rechtsachter", "Rechtsachter"]];

const vertaal = (tabel, w) => (w == null ? null : w in tabel ? tabel[w] : mens(w));
/** "BRAKE_FLUID" → "Brake fluid": leesbaar als we de waarde (nog) niet kennen. */
const mens = (w) => {
  const s = String(w).replace(/[_-]+/g, " ").toLowerCase().trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const eenheid = (v, d, e) => (v == null ? null : `${getal(v, d)} <small>${e}</small>`);
const minuten = (m) => (m == null ? null : m >= 60 ? `${Math.floor(m / 60)} u ${Math.round(m % 60)} min` : `${Math.round(m)} min`);
const datum = (iso) => (iso ? datumKort(isoDatum(new Date(iso))) + (iso.slice(0, 4) !== String(new Date().getFullYear()) ? ` ${iso.slice(0, 4)}` : "") : null);
const sterren = (n) => (n == null ? null : `${"★".repeat(Math.round(n))}${"☆".repeat(5 - Math.round(n))} <small>${getal(n, 1)}</small>`);
const opDicht = (open) => (open == null ? null : open ? "Open" : "Dicht");

/** Rijtjes label/waarde; regels zonder waarde vallen weg. Waarden zijn al veilige HTML. */
function gegevens(regels) {
  const r = regels.filter(([, w]) => w != null && w !== "");
  if (!r.length) return "";
  return `<dl class="gegevens">${r.map(([l, w]) => `<dt>${esc(l)}</dt><dd>${w}</dd>`).join("")}</dl>`;
}

// ── pagina ────────────────────────────────────────────────────────────────────

export async function toon(main, params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-8", { titel: "Auto", regels: 4 })}${skeletKaart("b-4", { titel: "Locatie" })}
      ${skeletKaart("b-8", { titel: "Accu", grafiek: true })}${skeletKaart("b-4", { titel: "Laden", regels: 6 })}</div>`;
  }
  const a = await api("auto");
  if (!ctx.actueel()) return;
  teken(main, a, params, ctx);
}

function teken(main, a, params, ctx) {
  ruimOp();
  if (!a.auto) {
    main.innerHTML = `<div class="raster"><div class="b-12">${melding('Nog geen gegevens van een auto. <a href="#/koppelingen">Koppel je auto</a> (BMW, Kia of Hyundai); de eerste gegevens komen binnen een kwartier.', "", "auto")}</div></div>`;
    return;
  }
  const d = a.details || {};
  main.innerHTML = `<div class="raster">
    <div class="stapel b-8">
      ${hoofdKaart(a.auto, d)}
      ${kaart({ titel: "Accu", sub: "laatste 7 dagen", id: "k-accu", inhoud: '<div class="grafiek" id="g-accu" role="img" aria-label="Accuniveau over de laatste zeven dagen; groen gearceerd is laden"></div><div class="legenda"><span><i style="background:var(--c-laden)"></i>Accu</span><span><i style="background:color-mix(in srgb, var(--c-laden) 25%, transparent)"></i>Laden</span></div>' })}
      ${kaart({ titel: "Kilometers per dag", sub: kmSub(a.km), id: "k-km", inhoud: a.km_per_dag.length ? '<div class="grafiek laag" id="g-km" role="img" aria-label="Gereden kilometers per dag"></div>' : leeg("Nog geen kilometerstand: die komt na een paar dagen meten.") })}
      ${beveiligingKaart(d.beveiliging, d.klimaat)}
    </div>
    <div class="stapel b-4">
      ${locatieKaart(d.locatie, a.thuis)}
      ${ladenKaart(d.laden, a.auto)}
      ${rijdenKaart(d.rijden)}
    </div>
    ${onderhoudKaart(d.onderhoud)}
    ${overKaart(d.basis, a.auto)}
    ${laadhistorieKaart(a.laadsessies, a.laden_30_dagen)}
  </div>`;
  accuGrafiek(a.accu);
  if (a.km_per_dag.length) kmGrafiek(a.km_per_dag);
  koppelThuis(main, params, ctx);
}

// ── kaarten ───────────────────────────────────────────────────────────────────

/** Met een foto van de auto (zie autoFoto in basis.js) staat die rechts naast het percentage. */
function fotoErbij(auto, kop) {
  const foto = autoFoto(auto.naam);
  if (!foto) return kop;
  return `<div class="auto-held">${kop}<div class="auto-foto"><img src="${foto}" alt="${esc(auto.naam)}" width="688" height="336"></div></div>`;
}

function hoofdKaart(auto, d) {
  const l = d.laden || {};
  const pct = auto.accu_pct;
  const doel = auto.doel_pct ?? l.doel_pct;
  const status = auto.laadt ? pil("Laadt", "goed", true) : auto.ingeplugd ? pil("Ingeplugd", "accent", true) : pil("Geparkeerd");
  const tegels = auto.laadt
    ? [
        tegel("Laadvermogen", eenheid(auto.laadvermogen_kw ?? l.vermogen_kw, 1, "kW") ?? "–"),
        tegel("Klaar over", minuten(auto.laadtijd_min ?? l.resttijd_min) ?? "–"),
        tegel("Nog tot vol", eenheid(auto.kwh_tot_vol ?? l.kwh_tot_vol, 1, "kWh") ?? "–"),
        tegel("Kilometerstand", eenheid(auto.km_stand, 0, "km") ?? "–"),
      ]
    : [
        tegel("Bereik", eenheid(auto.bereik_km, 0, "km") ?? "–"),
        tegel("Stekker", auto.ingeplugd ? "Erin" : "Eruit"),
        tegel("Laaddoel", doel != null ? `${getal(doel, 0)}%` : "–"),
        tegel("Kilometerstand", eenheid(auto.km_stand, 0, "km") ?? "–"),
      ];
  return kaart({
    titel: auto.naam || "Auto",
    sub: auto.bijgewerkt ? `bijgewerkt ${relatief(auto.bijgewerkt)}` : "",
    id: "k-auto",
    rechts: status,
    inhoud: `${fotoErbij(auto, `<div class="auto-kop">
        <div class="groot">${getal(pct, 0)}<small>%</small></div>
        <div class="zacht">${auto.bereik_km != null ? `${getal(auto.bereik_km, 0)} km bereik` : ""}${l.bereik_bij_doel_km != null ? `, ${getal(l.bereik_bij_doel_km, 0)} km bij ${getal(doel, 0)}%` : ""}</div>
      </div>`)}
      <div class="accu" role="meter" aria-label="Accu" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct ?? 0)}">
        <div class="vulling" style="width:${pct ?? 0}%"></div>
        ${doel != null ? `<div class="doel" style="left:${doel}%" title="Laaddoel ${doel}%"></div>` : ""}
      </div>
      <div class="tegels" style="margin-top:12px">${tegels.join("")}</div>`,
    voet: "De auto wordt niet gewekt: dit is de laatste stand die de auto zelf heeft doorgegeven.",
  });
}

function locatieKaart(loc, thuis) {
  let inhoud;
  if (!loc) {
    inhoud = leeg("De auto heeft geen locatie doorgegeven.");
  } else {
    const kaartLink = `https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lon}#map=16/${loc.lat}/${loc.lon}`;
    const waar = loc.thuis ? "Thuis" : loc.afstand_km != null ? `${getal(loc.afstand_km, loc.afstand_km < 10 ? 1 : 0)} km van huis` : "Locatie bekend";
    inhoud = `<div class="groot locatie-waar">${esc(waar)}</div>
      <p class="zacht klein">${loc.bijgewerkt ? `Doorgegeven ${esc(relatief(loc.bijgewerkt))}` : ""}</p>
      <div class="formulier-acties" style="margin-top:12px">
        <a class="knop" href="${esc(kaartLink)}" target="_blank" rel="noopener noreferrer">Bekijk op de kaart</a>
        ${thuis ? (loc.thuis ? "" : '<button class="knop" type="button" data-thuis="zet">Dit is thuis</button>') + '<button class="knop" type="button" data-thuis="wis">Thuis vergeten</button>' : '<button class="knop primair" type="button" data-thuis="zet">Dit is thuis</button>'}
      </div>
      ${thuis ? "" : '<p class="zacht klein" style="margin-top:12px">Staat de auto nu thuis? Klik dan op "Dit is thuis". Daarna ziet Thuis ook welke laadbeurten thuis waren.</p>'}`;
  }
  return kaart({ titel: "Locatie", id: "k-locatie", inhoud });
}

function ladenKaart(l = {}, auto) {
  const inhoud = gegevens([
    ["Laaddoel in de auto", l.doel_pct != null ? `${getal(l.doel_pct, 0)}%` : null],
    ["Laaddoel snelladen", l.doel_snelladen_pct != null ? `${getal(l.doel_snelladen_pct, 0)}%` : null],
    ["Accu-inhoud", eenheid(l.capaciteit_kwh ?? auto.capaciteit_kwh, 1, "kWh")],
    ["Accu-inhoud nieuw", eenheid(l.capaciteit_nieuw_kwh, 1, "kWh")],
    ["Accugezondheid", l.gezondheid_pct != null ? `${getal(l.gezondheid_pct, 0)}%` : null],
    ["Laadmethode", esc(vertaal(METHODE, l.methode))],
    ["Fasen", esc(vertaal(FASEN, l.fasen))],
    ["Laadstroom", l.ac_stroom_a ? eenheid(l.ac_stroom_a, 0, "A") : null],
    ["Netspanning", l.ac_spanning_v ? eenheid(l.ac_spanning_v, 0, "V") : null],
    ["Maximale laadstroom", eenheid(l.ac_limiet_a, 0, "A")],
    ["Voorkeur in de auto", esc(vertaal(VOORKEUR, l.voorkeur))],
    ["Laatste laadbeurt", l.laatste_einde ? esc(vertaal(EINDE, l.laatste_einde) + (l.laatste_resultaat === "FAILED" ? " (mislukt)" : "")) : null],
    ["Laadkabel", esc(vertaal(KABEL, l.kabelslot))],
    ["Laadklep", opDicht(l.klep_open)],
  ]);
  return kaart({
    titel: "Laden",
    sub: l.bijgewerkt ? relatief(l.bijgewerkt) : "",
    id: "k-laden",
    inhoud: inhoud || leeg("De auto geeft hier niets over door."),
    voet: '<a href="#/laden">Naar Slim laden</a>',
  });
}

const kmSub = (km) =>
  km.zeven_dagen == null ? "" : `7 dagen ${getal(km.zeven_dagen, 0)} km, 30 dagen ${getal(km.dertig_dagen, 0)} km`;

function rijdenKaart(r = {}) {
  const rit = r.rit || {};
  const stijl = r.rijstijl || {};
  const inhoud = gegevens([
    ["Kilometerstand", eenheid(r.km_stand, 0, "km")],
    ["Gemiddeld verbruik", eenheid(r.verbruik_kwh_100km, 1, "kWh/100 km")],
    ["Gemiddeld per week", eenheid(r.week_km, 0, "km")],
    ["Gemiddeld per week (lang)", eenheid(r.week_km_lang, 0, "km")],
    ["Laatste rit", rit.eind ? esc(relatief(rit.eind)) : null],
    ["Accu na de laatste rit", rit.accu_pct != null ? `${getal(rit.accu_pct, 0)}%` : null],
    ["Teruggewonnen", eenheid(rit.teruggewonnen, 1, "kWh")],
    ["Rijstijl: optrekken", sterren(stijl.optrekken)],
    ["Rijstijl: vooruitzien", sterren(stijl.anticiperen)],
  ]);
  return kaart({ titel: "Rijden", sub: r.bijgewerkt ? relatief(r.bijgewerkt) : "", id: "k-rijden", inhoud: inhoud || leeg("De auto geeft hier niets over door.") });
}

/** Service- of Check Control-melding: BMW geeft een dict (of tekst); we tonen wat er is. */
function meldingTekst(m) {
  if (typeof m !== "object" || m === null) return esc(m);
  const naam = m.naam || m.name || m.title || m.text || m.description || (m.type ? mens(m.type) : "Melding");
  const extra = [
    m.status && mens(m.status),
    m.dateTime || m.date ? datum(m.dateTime || m.date) : null,
    m.distance != null ? `${getal(m.distance, 0)} km` : null,
  ].filter(Boolean);
  return `${esc(naam)}${extra.length ? ` <span class="zacht">(${esc(extra.join(", "))})</span>` : ""}`;
}

/** Een onderhoudspunt van de auto als [label, waarde]. */
function service(s) {
  if (typeof s !== "object" || s === null) return ["Onderhoud", esc(s)];
  const naam = s.naam || s.name || (s.type ? vertaal(SERVICE, s.type) : "Onderhoud");
  const wanneer = [s.dateTime || s.date ? datum(s.dateTime || s.date) : null, s.distance != null ? `over ${getal(s.distance, 0)} km` : null]
    .filter(Boolean)
    .join(" of ");
  const status = s.status ? vertaal(SERVICESTATUS, s.status) : null;
  return [naam, `${esc(wanneer || status || "–")}${wanneer && status ? ` <small>${esc(status)}</small>` : ""}`];
}

function onderhoudKaart(o = {}) {
  const banden = PLEKKEN.filter(([p]) => o.banden?.[p]?.bar != null).map(([p, naam]) => {
    const b = o.banden[p];
    const laag = b.doel_bar != null && b.bar < b.doel_bar - 0.2;
    return tegel(naam, `${getal(b.bar, 1)} <small>bar${b.doel_bar != null ? `, hoort ${getal(b.doel_bar, 1)}` : ""}</small>`, laag ? "tekst-let-op" : "");
  });
  const meldingen = o.meldingen || [];
  const lijst = gegevens([
    ["Volgende servicebeurt", o.service_km != null ? `over ${getal(o.service_km, 0)} <small>km</small>` : null],
    ["APK", o.apk ? esc(datum(o.apk)) : null],
    ["12V-accu", o.accu_12v_pct != null ? `${getal(o.accu_12v_pct, 0)}%` : o.accu_12v_volt != null ? eenheid(o.accu_12v_volt, 1, "V") : null],
    ...(o.services || []).map(service),
  ]);
  const inhoud = `${meldingen.length ? meldingen.map((m) => melding(meldingTekst(m), "let_op")).join("") : ""}
    ${lijst}
    ${banden.length ? `<h3 class="tussenkop">Bandenspanning</h3><div class="tegels banden">${banden.join("")}</div>` : ""}`;
  return kaart({
    titel: "Onderhoud",
    sub: o.bijgewerkt ? relatief(o.bijgewerkt) : "",
    klasse: "b-6",
    id: "k-onderhoud",
    rechts: meldingen.length ? pil(`${meldingen.length} ${meldingen.length === 1 ? "melding" : "meldingen"}`, "let_op") : "",
    inhoud: lijst || banden.length || meldingen.length ? inhoud : leeg("De auto geeft hier niets over door."),
  });
}

function beveiligingKaart(b = {}, k = {}) {
  const deuren = b.deuren_open || {};
  const ramen = b.ramen || {};
  const rijen = PLEKKEN.filter(([p]) => deuren[p] != null || ramen[p] != null)
    .map(([p, naam]) => `<tr><td>${naam}</td><td>${opDicht(deuren[p]) ?? "–"}</td><td>${esc(vertaal(RAAM, ramen[p]) ?? "–")}</td></tr>`)
    .join("");
  const slot = b.slot ? vertaal(SLOT, b.slot) : null;
  const lijst = gegevens([
    ["Alarm", esc(vertaal(ALARM, b.alarm))],
    ["Kofferbak", opDicht(b.kofferbak_open)],
    ["Motorkap", opDicht(b.motorkap_open)],
    ["Schuifdak", esc(vertaal(DAK, b.dak))],
    ["Klimaat", k.activiteit ? esc(vertaal(KLIMAAT, k.activiteit) + (k.resttijd_min ? `, nog ${minuten(k.resttijd_min)}` : "")) : null],
    ["Binnen", eenheid(k.binnen_c, 0, "°C")],
    ["Buiten", eenheid(k.buiten_c, 0, "°C")],
  ]);
  const inhoud = `${rijen ? `<div class="tabel-wrap"><table class="tabel"><thead><tr><th>Plek</th><th>Deur</th><th>Raam</th></tr></thead><tbody>${rijen}</tbody></table></div>` : ""}${lijst}`;
  return kaart({
    titel: "Deuren en ramen",
    sub: b.bijgewerkt ? relatief(b.bijgewerkt) : "",
    id: "k-beveiliging",
    rechts: slot ? pil(slot, b.slot === "UNLOCKED" ? "let_op" : "goed", true) : "",
    inhoud: rijen || lijst ? inhoud : leeg("De auto geeft hier niets over door."),
  });
}

function laadhistorieKaart(sessies, totaal) {
  if (!sessies.length) {
    return kaart({ titel: "Laadhistorie", klasse: "b-12", id: "k-historie", inhoud: leeg("Nog geen laadbeurten van de auto zelf. BMW geeft ze één keer per dag door; bij Kia en Hyundai staan je laadsessies op de pagina Laden.") });
  }
  const rij = (s) => {
    const duur = s.eind ? (new Date(s.eind) - new Date(s.start)) / 60e3 : null;
    const waar = s.thuis ? "Thuis" : s.plaats || (s.publiek ? "Openbaar laadpunt" : "Onbekend");
    return `<tr>
      <td>${esc(datum(s.start))} <span class="zacht">${esc(klok(s.start))}</span></td>
      <td class="links">${esc(waar)}${s.publiek && !s.thuis ? ' <span class="zacht">openbaar</span>' : ""}</td>
      <td>${s.kwh != null ? `${getal(s.kwh, 1)} kWh` : "–"}</td>
      <td>${s.start_pct != null && s.eind_pct != null ? `${getal(s.start_pct, 0)}% → ${getal(s.eind_pct, 0)}%` : "–"}</td>
      <td>${minuten(duur) ?? "–"}</td>
      <td>${s.kosten != null && (s.valuta || "EUR") === "EUR" ? euro(s.kosten) : "–"}</td>
    </tr>`;
  };
  return kaart({
    titel: "Laadhistorie",
    sub: `30 dagen: ${totaal.sessies} keer, ${getal(totaal.kwh, 0)} kWh${totaal.kwh_onderweg ? `, waarvan ${getal(totaal.kwh_onderweg, 0)} kWh onderweg` : ""}`,
    klasse: "b-12",
    id: "k-historie",
    inhoud: `<div class="tabel-wrap"><table class="tabel">
      <thead><tr><th>Wanneer</th><th class="links">Waar</th><th>Geladen</th><th>Accu</th><th>Duur</th><th>Kosten</th></tr></thead>
      <tbody>${sessies.slice(0, 20).map(rij).join("")}</tbody></table></div>`,
    voet: "Zoals de auto het bijhoudt, ook laden onderweg. De kosten zijn de schatting van de auto zelf.",
  });
}

function overKaart(b = {}, auto) {
  const id = String(auto.auto_id || "");
  const inhoud = gegevens([
    ["Merk", esc(b.merk === "BMWi" ? "BMW i" : b.merk)],
    ["Model", esc(b.model)],
    ["Serie", esc(b.serie)],
    ["Carrosserie", esc(b.carrosserie)],
    ["Aandrijving", esc(b.aandrijving === "BEV" ? "Elektrisch" : b.aandrijving === "PHEV" ? "Plug-in hybride" : b.aandrijving)],
    ["Bouwdatum", esc(b.bouwdatum)],
    ["Kleurcode", esc(b.kleurcode)],
    ["Software", esc(b.software)],
    ["Chassisnummer", id.length === 17 ? `<span class="zacht">${esc(id.slice(0, 3))}…</span>${esc(id.slice(-6))}` : null],
  ]);
  return kaart({ titel: "Over de auto", klasse: "b-6", id: "k-over", inhoud: inhoud || leeg("Nog geen gegevens over de auto zelf.") });
}

// ── grafieken ─────────────────────────────────────────────────────────────────

function accuGrafiek(punten) {
  const el = document.getElementById("g-accu");
  if (!punten.length) {
    el.outerHTML = leeg("Nog geen metingen deze week.");
    return;
  }
  // Aaneengesloten stukken waarin de auto laadde, als gearceerde vlakken.
  const vlakken = [];
  let start = null;
  punten.forEach((p, i) => {
    if (p.laadt && start == null) start = p.tijd;
    const einde = !p.laadt || i === punten.length - 1;
    if (start != null && einde) {
      vlakken.push([{ xAxis: start }, { xAxis: p.tijd }]);
      start = null;
    }
  });
  const kleur = css("--c-laden");
  grafiek(el).setOption(
    basis({
      tooltip: {
        axisPointer: { type: "line", lineStyle: { color: css("--lijn-sterk") } },
        formatter: (p) => `${esc(datumKort(isoDatum(new Date(p[0].value[0]))))} ${esc(klok(p[0].value[0]))}<br><b>${getal(p[0].value[1], 0)}%</b>`,
      },
      xAxis: {
        type: "time",
        axisLabel: { formatter: (w) => datumKort(isoDatum(new Date(w))) },
        splitNumber: 7,
      },
      yAxis: { min: 0, max: 100, interval: 25, axisLabel: { formatter: (w) => `${w}%` } },
      series: [
        {
          name: "Accu",
          type: "line",
          data: punten.map((p) => [p.tijd, p.pct]),
          showSymbol: false,
          lineStyle: { color: kleur, width: 2 },
          itemStyle: { color: kleur },
          markArea: { silent: true, itemStyle: { color: kleur, opacity: 0.18 }, data: vlakken },
        },
      ],
    }),
  );
}

function kmGrafiek(dagen) {
  grafiek(document.getElementById("g-km")).setOption(
    basis({
      tooltip: { formatter: (p) => `${esc(datumKort(dagen[p[0].dataIndex].dag))}<br><b>${getal(p[0].value, 0)} km</b>` },
      xAxis: { data: dagen.map((d) => datumKort(d.dag)) },
      series: [staven("Kilometers", dagen.map((d) => d.km), css("--accent"))],
    }),
  );
}

// ── thuis ─────────────────────────────────────────────────────────────────────

function koppelThuis(main, params, ctx) {
  for (const knop of main.querySelectorAll("[data-thuis]")) {
    knop.onclick = async () => {
      const zet = knop.dataset.thuis === "zet";
      knop.disabled = true;
      try {
        const a = await api("auto/thuis", { methode: zet ? "PUT" : "DELETE" });
        toast(zet ? "Onthouden: hier is thuis" : "Thuis is vergeten");
        teken(main, a, params, ctx);
      } catch (err) {
        knop.disabled = false;
        meldFout(err);
      }
    };
  }
}
