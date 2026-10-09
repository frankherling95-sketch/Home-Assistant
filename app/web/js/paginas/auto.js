// Auto & laden: de auto (BMW CarData, Kia/Hyundai Connect), de Easee-lader, het laadplan van
// Slim laden, laadsessies en de instellingen op één pagina. Wat de auto niet doorgeeft, blijft weg.

import {
  $, LADER_STATUS, PLAN_REDEN, TZ, api, autoFoto, autoStand, css, dagnaam, datumKort, esc, euro, getal, hoeveelheid, huidigBlok,
  isoDatum, klok, meldFout, plusDagen, prijs, relatief, toast, vandaag,
} from "../basis.js";
import { basis, gekleurd, grafiek, nuLijn, regel, ruimOp, staven, stippel } from "../grafiek.js";
import { accuBalk, kaart, leeg, melding, pil, skeletKaart, tegel } from "../onderdelen.js";

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
/** "wo 7 okt" */
const dagKort = (iso) => new Date(iso).toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "short", timeZone: TZ });

/** Rijtjes label/waarde; regels zonder waarde vallen weg. Waarden zijn al veilige HTML. */
function gegevens(regels) {
  const r = regels.filter(([, w]) => w != null && w !== "");
  if (!r.length) return "";
  return `<dl class="gegevens">${r.map(([l, w]) => `<dt>${esc(l)}</dt><dd>${w}</dd>`).join("")}</dl>`;
}

// ── pagina ────────────────────────────────────────────────────────────────────

export async function toon(main, params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-8", { titel: "Auto", regels: 4 })}${skeletKaart("b-4", { titel: "Lader" })}
      ${skeletKaart("b-12", { titel: "Laadplan", grafiek: true })}</div>`;
  }
  const v = vandaag();
  const [a, nu, d0, d1, sessies] = await Promise.all([
    api("auto"),
    api("nu"),
    api(`dag?datum=${v}`),
    api(`dag?datum=${plusDagen(v, 1)}`),
    api("laadsessies"),
  ]);
  if (!ctx.actueel()) return;
  teken(main, { a, nu, prijzen: [...d0.prijzen.stroom, ...d1.prijzen.stroom], sessies }, params, ctx);
}

function teken(main, data, params, ctx) {
  const { a, nu, prijzen, sessies } = data;
  const { lader, plan, instellingen } = nu;
  const auto = a.auto;
  const d = a.details || {};
  ctx.sub([auto?.naam, lader && "Easee-lader"].filter(Boolean).join(" en "));
  ruimOp();
  main.innerHTML = `<div class="raster">
    ${heldKaart(auto, d, plan)}
    <div class="stapel naast b-4">
      ${laderKaart(lader)}
      ${auto ? locatieKaart(d.locatie, a.thuis) : ""}
      ${auto && watOpen(d.beveiliging).length ? beveiligingKaart(d.beveiliging, d.klimaat) : ""}
    </div>
    ${planKaart(plan, instellingen)}
    ${sessieKaart(a.laadsessies, sessies)}
    ${kaart({ titel: "Slim laden", klasse: "b-4 eerder-stapelen", id: "k-instellingen", inhoud: formulier(instellingen, plan) })}
    ${auto ? `
      ${kaart({ titel: "Accu", sub: "laatste 7 dagen, laadmomenten gemarkeerd", klasse: "b-6 half-tablet", id: "k-accu", inhoud: '<div class="grafiek" id="g-accu" role="img" aria-label="Accuniveau over de laatste zeven dagen; de banden zijn laadmomenten"></div>' })}
      ${kmKaart(a.km_per_dag)}
      <div class="b-12 lijsten-rij">
        ${ladenKaart(d.laden, auto)}
        ${rijdenKaart(d.rijden)}
        ${onderhoudKaart(d.onderhoud)}
      </div>` : ""}
  </div>`;
  planGrafiek(plan, prijzen);
  if (auto) {
    accuGrafiek(a.accu, plan.doel_pct);
    kmGrafiek(a.km_per_dag.slice(-14));
  }
  koppelThuis(main, data, params, ctx);
  koppelFormulier(main, params, ctx);
}

// ── auto, lader en locatie ────────────────────────────────────────────────────

/** Wat er openstaat volgens de auto, als namen ("Raam linksvoor", "Kofferbak"). */
function watOpen(b = {}) {
  const open = [];
  for (const [p, naam] of PLEKKEN) {
    if (b.deuren_open?.[p]) open.push(`Deur ${naam.toLowerCase()}`);
    if (b.ramen?.[p] && b.ramen[p] !== "CLOSED") open.push(`Raam ${naam.toLowerCase()}`);
  }
  if (b.kofferbak_open) open.push("Kofferbak");
  if (b.motorkap_open) open.push("Motorkap");
  if (b.dak && b.dak !== "CLOSED") open.push("Schuifdak");
  return open;
}

/** De samenvatting van slot, deuren en ramen als pil. */
function slotPil(b = {}) {
  const open = watOpen(b);
  if (open.length) return pil(open.length === 1 ? `${open[0]} open` : `${open[0]} en nog ${open.length - 1} open`, "let_op", true);
  if (b.slot === "UNLOCKED") return pil("Niet op slot", "let_op", true);
  if (b.slot) return pil(`${vertaal(SLOT, b.slot)}, alles dicht`, "goed", true);
  return "";
}

function heldKaart(auto, d, plan) {
  if (!auto) {
    return kaart({ titel: "Auto", klasse: "b-8", id: "k-auto", inhoud: melding('Nog geen gegevens van een auto. <a href="#/koppelingen">Koppel je auto</a> (BMW, Kia of Hyundai); de eerste gegevens komen binnen een kwartier.', "", "auto") });
  }
  const l = d.laden || {};
  const r = d.rijden || {};
  const loc = d.locatie;
  const pct = auto.accu_pct;
  const doel = plan.doel_pct;
  const capaciteit = auto.capaciteit_kwh ?? l.capaciteit_kwh;

  const waar = loc ? (loc.thuis ? "Thuis" : loc.afstand_km != null ? `${getal(loc.afstand_km, loc.afstand_km < 10 ? 1 : 0)} km van huis` : null) : null;
  const stekker = auto.laadt
    ? pil("Laadt nu", "goed", true)
    : auto.ingeplugd
      ? pil("Ingeplugd", "accent", true)
      : pil("Stekker los", plan.blokken.length ? "let_op" : "", true);
  const pillen = `<div class="pillen">${auto.laadt ? "" : pil(["Geparkeerd", waar].filter(Boolean).join(" · "))}${slotPil(d.beveiliging)}${stekker}</div>`;

  const bereik = [
    auto.bereik_km != null ? `${getal(auto.bereik_km, 0)} km elektrisch bereik` : null,
    l.bereik_bij_doel_km != null && l.doel_pct != null ? `${getal(l.bereik_bij_doel_km, 0)} km bij ${getal(l.doel_pct, 0)}%` : null,
  ].filter(Boolean).join(" · ");
  const inhoud = pct != null && capaciteit ? `${getal((pct / 100) * capaciteit, 1)} van ${getal(capaciteit, 1)} kWh` : "";
  const stand = `<div class="auto-stand">
      <div class="groot">${getal(pct, 0)}<small>%</small></div>
      ${bereik ? `<div class="bereik">${esc(bereik)}</div>` : ""}
      ${inhoud ? `<div class="zacht">${inhoud}</div>` : ""}
    </div>`;
  const foto = autoFoto(auto.naam);
  const labels = [];
  if (pct != null && (doel == null || Math.abs(doel - pct) >= 18)) labels.push({ pct, tekst: "nu" });
  if (doel != null) labels.push({ pct: doel, tekst: `doel ${getal(doel, 0)}%${doel > (pct ?? 0) ? ` · ${dagnaam(plan.vertrek)} ${klok(plan.vertrek)}` : ""}` });

  const rit = r.rit || {};
  const tegels = [
    tegel("Kilometerstand", eenheid(auto.km_stand ?? r.km_stand, 0, "km") ?? "–"),
    tegel("Laatste rit", rit.eind ? esc(relatief(rit.eind)) : "–"),
    tegel("Gemiddeld per week", eenheid(r.week_km, 0, "km") ?? "–"),
    tegel("Laaddoel in de auto", (auto.doel_pct ?? l.doel_pct) != null ? `${getal(auto.doel_pct ?? l.doel_pct, 0)}%` : "–"),
  ];
  if (auto.laadt) {
    tegels.splice(1, 2,
      tegel("Laadvermogen", eenheid(auto.laadvermogen_kw ?? l.vermogen_kw, 1, "kW") ?? "–"),
      tegel("Klaar over", minuten(auto.laadtijd_min ?? l.resttijd_min) ?? "–"));
  }

  return kaart({
    titel: auto.naam || "Auto",
    sub: autoStand(auto),
    klasse: "b-8",
    id: "k-auto",
    inhoud: `${pillen}
      ${foto ? `<div class="held-auto omgekeerd">${stand}<div class="auto-foto"><img src="${foto}" alt="${esc(auto.naam)}" width="688" height="336"></div></div>` : stand}
      ${accuBalk(pct, doel, labels)}
      <div class="tegels vier">${tegels.join("")}</div>`,
    voet: "De auto wordt niet gewekt: dit is de laatste stand die de auto zelf heeft doorgegeven.",
  });
}

function laderKaart(lader) {
  if (!lader) return kaart({ titel: "Lader", id: "k-lader", inhoud: '<p class="leeg">Nog geen gegevens van de lader. <a href="#/koppelingen">Koppel je Easee</a></p>' });
  const klasse = lader.status === "laden" ? "goed" : lader.status === "fout" ? "fout" : "";
  return kaart({
    titel: "Lader",
    sub: ["Easee", lader.naam].filter(Boolean).join(" · "),
    id: "k-lader",
    rechts: pil(LADER_STATUS[lader.status] || lader.status, klasse, true),
    inhoud: `<div class="tegels">
        ${tegel("Vermogen", eenheid(lader.vermogen_kw, 1, "kW") ?? "–")}
        ${tegel("Meterstand", eenheid(lader.totaal_kwh, 0, "kWh") ?? "–")}
      </div>`,
  });
}

function locatieKaart(loc, thuis) {
  let inhoud;
  if (!loc) {
    inhoud = leeg("De auto heeft geen locatie doorgegeven.");
  } else {
    const kaartLink = `https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lon}#map=16/${loc.lat}/${loc.lon}`;
    const waar = loc.thuis ? "Thuis" : loc.afstand_km != null ? `${getal(loc.afstand_km, loc.afstand_km < 10 ? 1 : 0)} km van huis` : "Locatie bekend";
    inhoud = `<div class="locatie-waar">${esc(waar)}</div>
      <div class="formulier-acties" style="margin-top:12px">
        <a class="knop" href="${esc(kaartLink)}" target="_blank" rel="noopener noreferrer">Bekijk op de kaart</a>
        ${thuis ? (loc.thuis ? "" : '<button class="knop" type="button" data-thuis="zet">Dit is thuis</button>') + '<button class="knop" type="button" data-thuis="wis">Thuis vergeten</button>' : '<button class="knop primair" type="button" data-thuis="zet">Dit is thuis</button>'}
      </div>
      ${thuis ? "" : '<p class="zacht klein" style="margin-top:12px">Staat de auto nu thuis? Klik dan op "Dit is thuis". Daarna ziet Thuis ook welke laadbeurten thuis waren.</p>'}`;
  }
  return kaart({ titel: "Locatie", sub: loc?.bijgewerkt ? relatief(loc.bijgewerkt) : "", id: "k-locatie", inhoud });
}

/** Alleen als er iets openstaat; anders staat de samenvatting als pil bij de auto. */
function beveiligingKaart(b = {}, k = {}) {
  const deuren = b.deuren_open || {};
  const ramen = b.ramen || {};
  const rijen = PLEKKEN.filter(([p]) => deuren[p] != null || ramen[p] != null)
    .map(([p, naam]) => `<tr><td>${naam}</td><td>${opDicht(deuren[p]) ?? "–"}</td><td>${esc(vertaal(RAAM, ramen[p]) ?? "–")}</td></tr>`)
    .join("");
  const lijst = gegevens([
    ["Slot", esc(vertaal(SLOT, b.slot))],
    ["Alarm", esc(vertaal(ALARM, b.alarm))],
    ["Kofferbak", opDicht(b.kofferbak_open)],
    ["Motorkap", opDicht(b.motorkap_open)],
    ["Schuifdak", esc(vertaal(DAK, b.dak))],
    ["Klimaat", k.activiteit ? esc(vertaal(KLIMAAT, k.activiteit) + (k.resttijd_min ? `, nog ${minuten(k.resttijd_min)}` : "")) : null],
  ]);
  return kaart({
    titel: "Deuren en ramen",
    sub: b.bijgewerkt ? relatief(b.bijgewerkt) : "",
    id: "k-beveiliging",
    inhoud: `${rijen ? `<div class="tabel-wrap"><table class="tabel"><thead><tr><th>Plek</th><th>Deur</th><th>Raam</th></tr></thead><tbody>${rijen}</tbody></table></div>` : ""}${lijst}`,
  });
}

// ── laadplan ──────────────────────────────────────────────────────────────────

function planKaart(plan, instellingen) {
  const b = plan.blokken;
  const status = plan.nu_laden ? "goed" : plan.reden === "geen_prijzen" ? "let_op" : plan.reden === "doel_bereikt" ? "" : "accent";
  const bespaard = plan.kosten_direct != null && b.length ? Math.max(0, plan.kosten_direct - plan.kosten) : null;
  const sturen = instellingen.sturen
    ? b.length && !plan.nu_laden
      ? `Automatisch sturen staat aan: Thuis pauzeert de Easee tot ${klok(b[0].van)} en hervat hem in de geplande kwartieren.`
      : "Automatisch sturen staat aan: Thuis pauzeert en hervat de Easee volgens het plan."
    : "Automatisch sturen staat uit: dit plan is een advies en de lader laadt zoals hij zelf wil. Zet sturen aan als het plan een paar dagen klopt.";
  return kaart({
    titel: "Laadplan",
    sub: `klaar vóór ${klok(plan.vertrek)} ${dagnaam(plan.vertrek)}, doel ${getal(plan.doel_pct, 0)}%${plan.doel_van_auto ? " (laaddoel van de auto)" : ""}`,
    klasse: "b-12",
    id: "k-plan",
    rechts: pil(PLAN_REDEN[plan.reden] || plan.reden, status, true),
    inhoud: `<div class="tegels">
        ${tegel("Nodig", eenheid(plan.nodig_kwh, 1, "kWh"))}
        ${tegel("Geschatte kosten", euro(plan.kosten))}
        ${tegel("Start", b.length ? `${klok(b[0].van)} <small>${dagnaam(b[0].van)}</small>` : "–")}
        ${tegel("Klaar", b.length ? `${klok(b.at(-1).tot)} <small>${dagnaam(b.at(-1).tot)}</small>` : "–")}
        ${tegel("Bespaard t.o.v. nu", bespaard != null ? euro(bespaard) : "–", bespaard ? "tekst-goed" : "")}
      </div>
      <div class="grafiek-scroll"><div class="grafiek" id="g-plan" role="img" aria-label="Prijzen per kwartier tot en met morgen; de geplande laadkwartieren zijn gemarkeerd"></div></div>
      ${melding(sturen, "", "klok")}
      ${plan.volledig ? "" : '<p class="kaart-voet">Het plan is nog niet compleet: de prijzen van morgen komen rond 13:00.</p>'}`,
  });
}

/** Prijzen vanaf nu tot het einde van morgen; geplande kwartieren in de laadkleur. */
function planGrafiek(plan, alles) {
  const el = document.getElementById("g-plan");
  const nu = Date.now();
  const blokken = alles.filter((b) => new Date(b.tot) > nu);
  if (!blokken.length) {
    el.parentElement.outerHTML = leeg("Nog geen prijzen.");
    return;
  }
  const gepland = (b) => plan.blokken.some((p) => new Date(p.van) < new Date(b.tot) && new Date(p.tot) > new Date(b.van));
  const laden = css("--c-laden");
  const gedimd = css("--p-gedimd");
  const data = blokken.map((b) => {
    const item = gekleurd(b.prijs, gepland(b) ? laden : gedimd);
    if (!gepland(b)) item.itemStyle.shadowBlur = 0;
    return item;
  });
  const huidig = huidigBlok(blokken);
  const vertrek = blokken.find((b) => new Date(b.tot) > new Date(plan.vertrek));
  const morgen = plusDagen(vandaag(), 1);
  const lijnen = [];
  if (huidig) lijnen.push(nuLijn(huidig.van));
  if (vertrek) lijnen.push(stippel(vertrek.van, `vertrek ${klok(plan.vertrek)}`));
  grafiek(el).setOption(
    basis({
      grid: { top: 30, left: 4, right: 8, bottom: 0 },
      xAxis: {
        data: blokken.map((b) => b.van),
        axisLabel: {
          interval: (i, iso) => /^(00|04|08|12|16|20):00$/.test(klok(iso)),
          formatter: (iso) => (klok(iso) === "00:00" && isoDatum(new Date(iso)) === morgen ? "{morgen|morgen 00:00}" : klok(iso)),
          rich: { morgen: { fontWeight: 500, color: css("--inkt-2"), fontSize: 12 } },
        },
      },
      yAxis: { axisLabel: { formatter: (w) => (w === 0 ? "€ 0" : `€ ${getal(w, 2)}`) } },
      tooltip: {
        formatter: ([p]) => {
          const b = blokken[p.dataIndex];
          const ja = gepland(b);
          return `${dagnaam(b.van)} ${klok(b.van)}–${klok(b.tot)}${regel(ja ? laden : gedimd, ja ? "Gepland laden" : "Prijs", prijs(b.prijs))}`;
        },
      },
      series: [
        staven("Prijs", data, null, {
          barMaxWidth: 8,
          barCategoryGap: "18%",
          markLine: { symbol: "none", silent: true, animation: false, data: lijnen },
        }),
      ],
    }),
  );
}

// ── laadsessies ───────────────────────────────────────────────────────────────

/**
 * De laadbeurten van de auto zelf (ook onderweg, met accu-percentages) aangevuld met de
 * sessies van de Easee (kosten en besparing thuis). Zonder gegevens van de auto: alleen de Easee.
 */
function sessieRijen(autoSessies, easee) {
  const grens = Date.now() - 30 * 86400e3;
  const overlapt = (s, e) => new Date(e.start) < new Date(s.eind || s.start) && new Date(e.eind || Date.now()) > new Date(s.start);
  const gebruikt = new Set();
  const rijen = autoSessies
    .filter((s) => new Date(s.start) >= grens)
    .map((s) => {
      const e = s.publiek && !s.thuis ? null : easee.find((x) => !gebruikt.has(x) && overlapt(s, x));
      if (e) gebruikt.add(e);
      return {
        start: s.start,
        eind: s.eind,
        waar: s.thuis ? "Thuis" : s.plaats || (s.publiek ? "Openbaar laadpunt" : "Onbekend"),
        accu: s.start_pct != null && s.eind_pct != null ? `${getal(s.start_pct, 0)} → ${getal(s.eind_pct, 0)}%` : null,
        kwh: e ? e.kwh : s.kwh,
        kosten: e ? e.kosten : s.kosten != null && (s.valuta || "EUR") === "EUR" ? s.kosten : null,
        besparing: e ? e.besparing : null,
        slim: e?.slim,
        klaar: e ? e.klaar : true,
      };
    });
  for (const e of easee) {
    if (gebruikt.has(e) || new Date(e.start) < grens) continue;
    rijen.push({ start: e.start, eind: e.eind, waar: "Thuis", accu: null, kwh: e.kwh, kosten: e.kosten, besparing: e.besparing, slim: e.slim, klaar: e.klaar });
  }
  return rijen.sort((x, y) => new Date(y.start) - new Date(x.start));
}

function sessieKaart(autoSessies, easee) {
  const rijen = sessieRijen(autoSessies || [], easee);
  if (!rijen.length) return kaart({ titel: "Laadsessies", sub: "laatste 30 dagen", klasse: "b-8 eerder-stapelen", id: "k-sessies", inhoud: leeg("Geen laadsessies in de laatste 30 dagen.") });
  const som = (k) => rijen.reduce((a, s) => a + (s[k] || 0), 0);
  const tijd = (s) => {
    const dag = isoDatum(new Date(s.start));
    const eind = s.eind ? `${klok(s.eind)}${isoDatum(new Date(s.eind)) !== plusDagen(dag, 1) && isoDatum(new Date(s.eind)) !== dag ? ` ${datumKort(isoDatum(new Date(s.eind)))}` : ""}` : "nu";
    return `${dagKort(s.start)}, ${klok(s.start)} – ${eind}`;
  };
  const html = rijen
    .slice(0, 20)
    .map((s) => `<tr>
        <td>${esc(tijd(s))}${s.slim ? ' <span class="slim" title="Slim laden heeft deze sessie gestuurd">slim</span>' : ""}${s.klaar ? "" : ` ${pil("bezig", "goed")}`}</td>
        <td class="links" data-label="">${esc(s.waar)}</td>
        <td data-label="Accu">${s.accu ?? "–"}</td>
        <td class="r" data-label="Geladen">${s.kwh != null ? `${hoeveelheid(s.kwh)} kWh` : "–"}</td>
        <td data-label="Kosten">${euro(s.kosten)}</td>
        <td class="r${s.besparing == null ? "" : " bespaard"}" data-label="Bespaard">${s.besparing == null ? "–" : euro(s.besparing)}</td>
      </tr>`)
    .join("");
  return kaart({
    titel: "Laadsessies",
    sub: `laatste 30 dagen · ${rijen.length} ${rijen.length === 1 ? "sessie" : "sessies"}, ${hoeveelheid(som("kwh"))} kWh, ${euro(som("kosten"))}`,
    klasse: "b-8 eerder-stapelen",
    id: "k-sessies",
    inhoud: `<div class="tabel-wrap"><table class="tabel sessies">
      <thead><tr><th>Wanneer</th><th class="links">Waar</th><th>Accu</th><th>Geladen</th><th>Kosten</th><th>Bespaard</th></tr></thead>
      <tbody>${html}</tbody></table></div>`,
    voet: "Bespaard: wat dezelfde kWh hadden gekost als de auto direct na het inpluggen op vol vermogen had geladen. Onderweg laden telt niet mee.",
  });
}

// ── instellingen ──────────────────────────────────────────────────────────────

function formulier(i, plan) {
  const veld = (naam, label, uitleg, invoer) =>
    `<div class="veld"><label for="v-${naam}">${label}<span class="uitleg">${uitleg}</span></label>${invoer}</div>`;
  const getalVeld = (naam, min, max, stap, eenheid, voor = "") =>
    `<span class="invoer">${voor}<input id="v-${naam}" name="${naam}" type="number" min="${min}" max="${max}" step="${stap}" value="${i[naam]}" required inputmode="decimal">${eenheid}</span>`;
  return `<form id="instellingen" class="formulier">
    ${veld("doel_pct", "Doel accu", plan.doel_van_auto ? `In de auto staat ${getal(plan.doel_pct, 0)}%: verder laadt hij niet` : "Tot hoever Slim laden laadt", getalVeld("doel_pct", 10, 100, 5, "%"))}
    ${veld("vertrek", "Vertrektijd", "Vóór dit tijdstip is de auto klaar", `<span class="invoer"><input id="v-vertrek" name="vertrek" type="time" value="${i.vertrek}" required></span>`)}
    ${veld("capaciteit_kwh", "Accucapaciteit", plan.capaciteit_van_auto ? `Je auto geeft ${getal(plan.capaciteit_kwh, 1)} kWh door; daar rekent Thuis mee` : "Bruikbaar, volgens de fabrikant", getalVeld("capaciteit_kwh", 5, 200, 0.1, "kWh"))}
    ${veld("vermogen_kw", "Laadvermogen", "Wat de lader levert", getalVeld("vermogen_kw", 1, 22, 0.1, "kW"))}
    ${veld("rendement_pct", "Laadrendement", "Verlies tussen net en accu", getalVeld("rendement_pct", 50, 100, 1, "%"))}
    ${veld("altijd_onder", "Altijd laden onder", "Ook als het doel al bereikt is", getalVeld("altijd_onder", -1, 1, 0.01, "/kWh", "€"))}
    <div class="veld"><label for="v-sturen">Lader automatisch sturen<span class="uitleg">Pauzeert en hervat de Easee volgens het plan</span></label>
      <span class="schakelaar"><input id="v-sturen" name="sturen" type="checkbox" role="switch" ${i.sturen ? "checked" : ""}><span></span></span></div>
    <div class="acties"><button class="knop primair" type="submit">Opslaan</button></div>
  </form>`;
}

function koppelFormulier(main, params, ctx) {
  $("#instellingen", main).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const waarden = {};
    for (const veld of f.elements) {
      if (!veld.name) continue;
      waarden[veld.name] = veld.type === "checkbox" ? veld.checked : veld.type === "number" ? Number(veld.value) : veld.value;
    }
    const knop = f.querySelector("button[type=submit]");
    knop.disabled = true;
    try {
      await api("instellingen", { methode: "PUT", body: waarden });
      toast("Instellingen opgeslagen");
      await toon(main, params, { ...ctx, nieuw: false });
    } catch (err) {
      knop.disabled = false;
      meldFout(err.message?.startsWith("Fout 422") ? new Error("Niet opgeslagen: een van de waarden valt buiten het toegestane bereik.") : err);
    }
  });
}

// ── wat de auto doorgeeft ─────────────────────────────────────────────────────

function kmKaart(dagen) {
  const veertien = dagen.slice(-14);
  const totaal = veertien.reduce((a, d) => a + (d.km || 0), 0);
  return kaart({
    titel: "Kilometers per dag",
    sub: veertien.length ? `laatste 14 dagen · ${getal(totaal, 0)} km` : "",
    klasse: "b-6 half-tablet",
    id: "k-km",
    inhoud: veertien.length ? '<div class="grafiek" id="g-km" role="img" aria-label="Gereden kilometers per dag, de laatste veertien dagen"></div>' : leeg("Nog geen kilometerstand: die komt na een paar dagen meten."),
  });
}

function ladenKaart(l = {}, auto) {
  const capaciteit = l.capaciteit_kwh ?? auto.capaciteit_kwh;
  const inhoud = gegevens([
    ["Accu-inhoud", capaciteit != null && auto.accu_pct != null ? `${getal((auto.accu_pct / 100) * capaciteit, 1)} / ${getal(capaciteit, 1)} <small>kWh</small>` : eenheid(capaciteit, 1, "kWh")],
    ["Accu-inhoud nieuw", eenheid(l.capaciteit_nieuw_kwh, 1, "kWh")],
    ["Accugezondheid", l.gezondheid_pct != null ? `${getal(l.gezondheid_pct, 0)}%` : null],
    ["Laaddoel snelladen", l.doel_snelladen_pct != null ? `${getal(l.doel_snelladen_pct, 0)}%` : null],
    ["Laadmethode", esc(vertaal(METHODE, l.methode))],
    ["Fasen", esc(vertaal(FASEN, l.fasen))],
    ["Laadstroom", l.ac_stroom_a ? eenheid(l.ac_stroom_a, 0, "A") : null],
    ["Netspanning", l.ac_spanning_v ? eenheid(l.ac_spanning_v, 0, "V") : null],
    ["Maximale laadstroom", eenheid(l.ac_limiet_a, 0, "A")],
    ["Voorkeur in de auto", esc(vertaal(VOORKEUR, l.voorkeur))],
    ["Laadkabel", esc(vertaal(KABEL, l.kabelslot))],
    ["Laadklep", opDicht(l.klep_open)],
    ["Laatste laadbeurt", l.laatste_einde
      ? `<span class="${l.laatste_resultaat === "FAILED" ? "tekst-let-op" : l.laatste_einde === "CHARGING_GOAL_REACHED" ? "tekst-goed" : ""}">${esc(vertaal(EINDE, l.laatste_einde) + (l.laatste_resultaat === "FAILED" ? " (mislukt)" : ""))}</span>`
      : null],
  ]);
  return kaart({ titel: "Laden", sub: l.bijgewerkt ? relatief(l.bijgewerkt) : "", id: "k-laden", inhoud: inhoud || leeg("De auto geeft hier niets over door.") });
}

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
  // Een band meer dan 0,2 bar onder de doelspanning is te zacht.
  const banden = PLEKKEN.filter(([p]) => o.banden?.[p]?.bar != null).map(([p, naam]) => {
    const b = o.banden[p];
    const laag = b.doel_bar != null && b.bar < b.doel_bar - 0.2;
    return [`Band ${naam.toLowerCase()}`, `<span class="${laag ? "tekst-let-op" : ""}">${getal(b.bar, 1)} bar${b.doel_bar != null ? ` <small>(doel ${getal(b.doel_bar, 1)})</small>` : ""}</span>`];
  });
  const meldingen = o.meldingen || [];
  const lijst = gegevens([
    ["Service over", o.service_km != null ? `${getal(o.service_km, 0)} <small>km</small>` : null],
    ["APK", o.apk ? esc(datum(o.apk)) : null],
    ["12V-accu", o.accu_12v_pct != null ? `${getal(o.accu_12v_pct, 0)}%` : o.accu_12v_volt != null ? eenheid(o.accu_12v_volt, 1, "V") : null],
    ...(o.services || []).map(service),
    ...banden,
  ]);
  return kaart({
    titel: "Onderhoud en banden",
    sub: o.bijgewerkt ? relatief(o.bijgewerkt) : "",
    id: "k-onderhoud",
    rechts: meldingen.length ? pil(`${meldingen.length} ${meldingen.length === 1 ? "melding" : "meldingen"}`, "let_op") : "",
    inhoud: lijst || meldingen.length ? `${meldingen.map((m) => melding(meldingTekst(m), "let_op")).join("")}${lijst}` : leeg("De auto geeft hier niets over door."),
  });
}

// ── grafieken ─────────────────────────────────────────────────────────────────

function accuGrafiek(punten, doel) {
  const el = document.getElementById("g-accu");
  if (!punten.length) {
    el.outerHTML = leeg("Nog geen metingen deze week.");
    return;
  }
  // Aaneengesloten stukken waarin de auto laadde, als banden.
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
        axisLabel: { formatter: (w) => dagKort(new Date(w).toISOString()).replace(/ \S+$/, "") },
        splitNumber: 7,
      },
      yAxis: { min: 0, max: 100, interval: 50, axisLabel: { formatter: (w) => `${w}%` } },
      series: [
        {
          name: "Accu",
          type: "line",
          data: punten.map((p) => [p.tijd, p.pct]),
          showSymbol: false,
          lineStyle: { color: kleur, width: 2.5, shadowBlur: Number(css("--gloed-grafiek")) || 0, shadowColor: kleur },
          itemStyle: { color: kleur },
          markArea: { silent: true, itemStyle: { color: kleur, opacity: 0.16 }, data: vlakken },
          markLine: doel != null
            ? { symbol: "none", silent: true, animation: false, label: { show: false }, lineStyle: { color: css("--inkt-3"), type: "dashed", width: 1 }, data: [{ yAxis: doel }] }
            : undefined,
        },
      ],
    }),
  );
}

function kmGrafiek(dagen) {
  const el = document.getElementById("g-km");
  if (!el) return;
  const kleur = css("--accent");
  grafiek(el).setOption(
    basis({
      grid: { top: 24 },
      tooltip: { formatter: (p) => `${esc(datumKort(dagen[p[0].dataIndex].dag))}<br><b>${getal(p[0].value, 0)} km</b>` },
      xAxis: { data: dagen.map((d) => dagKort(`${d.dag}T12:00:00Z`).split(" ")[0]) },
      yAxis: { show: false },
      series: [
        staven("Kilometers", dagen.map((d) => d.km), kleur, {
          itemStyle: { color: kleur, opacity: 0.85, borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: "top", fontSize: 11, color: css("--inkt-2"), formatter: (p) => getal(p.value, 0) },
        }),
      ],
    }),
  );
}

// ── thuis ─────────────────────────────────────────────────────────────────────

function koppelThuis(main, data, params, ctx) {
  for (const knop of main.querySelectorAll("[data-thuis]")) {
    knop.onclick = async () => {
      const zet = knop.dataset.thuis === "zet";
      knop.disabled = true;
      try {
        const a = await api("auto/thuis", { methode: zet ? "PUT" : "DELETE" });
        toast(zet ? "Onthouden: hier is thuis" : "Thuis is vergeten");
        teken(main, { ...data, a }, params, ctx);
      } catch (err) {
        knop.disabled = false;
        meldFout(err);
      }
    };
  }
}
