// Bouwstenen voor de pagina's: kaarten, tegels, tabellen en skeletons (als HTML-tekst).

import { esc, euro, hoeveelheid, icoon, procent } from "./basis.js";

/** Kaart met kop. `inhoud` is al-veilige HTML; titel en sub worden ge-escaped. */
export function kaart({ titel, sub = "", rechts = "", inhoud = "", klasse = "", id = "", voet = "" }) {
  const kopId = id ? `${id}-titel` : "";
  return `<section class="kaart ${klasse}"${id ? ` id="${id}"` : ""}${kopId ? ` aria-labelledby="${kopId}"` : ""}>
    <header class="kaart-kop"><h2${kopId ? ` id="${kopId}"` : ""}>${esc(titel)}</h2>${sub ? `<span class="sub">${esc(sub)}</span>` : ""}${rechts ? `<div class="rechts">${rechts}</div>` : ""}</header>
    ${inhoud}
    ${voet ? `<div class="kaart-voet">${voet}</div>` : ""}
  </section>`;
}

export const tegel = (label, waarde, klasse = "") =>
  `<div class="tegel"><div class="label">${esc(label)}</div><div class="waarde ${klasse}">${waarde}</div></div>`;

export const pil = (tekst, klasse = "", stip = false) =>
  `<span class="pil ${klasse}">${stip ? '<span class="stip"></span>' : ""}${esc(tekst)}</span>`;

export const leeg = (tekst) => `<p class="leeg">${esc(tekst)}</p>`;

export const melding = (tekst, soort = "", ic = "let_op") =>
  `<div class="melding ${soort}">${icoon(ic)}<div>${tekst}</div></div>`;

/** Skeleton-kaart in dezelfde vorm als de echte, zodat de pagina niet verspringt. */
export function skeletKaart(klasse = "b-6", { grafiek = false, regels = 3, titel = "" } = {}) {
  const inhoud = grafiek
    ? '<div class="skelet grafiek"></div>'
    : `<div class="skelet groot-blok"></div>${'<div class="skelet regel"></div>'.repeat(regels)}`;
  return `<section class="kaart ${klasse}" aria-busy="true">
    <header class="kaart-kop">${titel ? `<h2>${esc(titel)}</h2>` : '<div class="skelet regel" style="width:40%"></div>'}</header>
    ${inhoud}</section>`;
}

const BRONNEN = [
  ["stroom", "Stroom afgenomen", "--c-stroom"],
  ["teruglevering", "Teruggeleverd", "--c-terug"],
  ["gas", "Gas", "--c-gas"],
];

/** Totalentabel zoals het HA-energiedashboard; met `vorige` een vergelijkingskolom. */
export function totalenTabel(t, vorige = null, vorigeLabel = "") {
  const kosten = (x) => x.stroom.kosten + x.gas.kosten + x.teruglevering.kosten;
  const verschil = (nu, toen) => (toen ? procent(nu / toen - 1) : "–");
  const kop = vorige
    ? `<tr><th>Bron</th><th>Energie</th><th>Kosten</th><th title="${esc(vorigeLabel)}">Vorige periode</th><th>Verschil</th></tr>`
    : "<tr><th>Bron</th><th>Energie</th><th>Kosten</th></tr>";
  const rij = (soort, naam, kleur, extra = "") => {
    const x = t[soort];
    const v = vorige?.[soort];
    return `<tr${extra}>
      <td><span class="bron"><i style="border-color:var(${kleur});background:color-mix(in srgb, var(${kleur}) 30%, transparent)"></i>${naam}</span></td>
      <td>${hoeveelheid(x.hoeveelheid)} ${x.eenheid}</td><td>${euro(x.kosten)}</td>
      ${v ? `<td>${hoeveelheid(v.hoeveelheid)} ${v.eenheid}</td><td class="verschil">${verschil(x.hoeveelheid, v.hoeveelheid)}</td>` : ""}
    </tr>`;
  };
  return `<div class="tabel-wrap"><table class="tabel">
    <thead>${kop}</thead>
    <tbody>
      ${BRONNEN.map(([s, n, k]) => rij(s, n, k)).join("")}
      ${rij("laden", "waarvan laden", "--c-laden", ' class="deel"')}
    </tbody>
    <tfoot><tr><td>Totaal</td><td></td><td>${euro(kosten(t))}</td>
      ${vorige ? `<td>${euro(kosten(vorige))}</td><td class="verschil">${verschil(kosten(t), kosten(vorige))}</td>` : ""}</tr></tfoot>
  </table></div>
  <p class="kaart-voet">${vorige && vorigeLabel ? `Vergeleken met ${esc(vorigeLabel)}. ` : ""}Laden zit al in de stroom die je afneemt en telt niet apart mee in het totaal.</p>`;
}

export const inzichtTegel = (i) =>
  `<article class="inzicht ${esc(i.toon)}">
    <span class="icoon">${icoon(i.icoon)}</span>
    <span class="titel">${esc(i.titel)}</span>
    <span class="waarde">${esc(i.waarde)}</span>
    <span class="toelichting">${esc(i.toelichting)}</span>
  </article>`;

/** Dunne accubalk: vulling tot `pct`, gearceerd tot het doel, met een streepje bij het doel.
 * `labels`: [{ pct, tekst }] onder de balk, gecentreerd op hun plek (bijv. "nu", "doel 80%"). */
export function accuBalk(pct, doel, labels = []) {
  const p = Math.max(0, Math.min(100, pct ?? 0));
  const d = doel == null ? null : Math.max(0, Math.min(100, doel));
  const gepland = d != null && d > p ? `<div class="gepland" style="left:${p}%;width:${d - p}%"></div>` : "";
  const plek = (x) => (x > 88 ? "eind" : x < 12 ? "begin" : "");
  return `<div class="accu dun" role="meter" aria-label="Accu" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(p)}">
      <div class="vulling" style="width:${p}%"></div>${gepland}
      ${d != null ? `<div class="doel" style="left:${d}%" title="Doel ${Math.round(d)}%"></div>` : ""}
    </div>
    ${labels.length ? `<div class="accu-labels">${labels.map((l) => `<span class="${plek(l.pct)}" style="left:${l.pct}%">${esc(l.tekst)}</span>`).join("")}</div>` : ""}`;
}

/** Link met een pijl erachter, voor "Alle prijzen →" en dergelijke. */
export const pijl = (tekst, href) => `<a class="pijl" href="${href}">${esc(tekst)} →</a>`;

/** Energiestromen: net, huis, gas en auto met de energie van een dag of periode (zoals Home Assistant).
 * `t` zijn de totalen uit /api/dag of /api/periode. */
export function stromen(t) {
  const beweeg = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lijn = (d, kleur, waarde) => {
    const aan = waarde > 0.005;
    const duur = Math.max(1.4, 4.5 - Math.log10(1 + waarde) * 1.8); // meer energie, snellere stippen
    const stippen = aan && beweeg
      ? [0, 0.5].map((f) => `<circle r="4" style="fill:${kleur}"><animateMotion dur="${duur.toFixed(2)}s" begin="${(-f * duur).toFixed(2)}s" repeatCount="indefinite" path="${d}"/></circle>`).join("")
      : "";
    return `<path class="lijn${aan ? "" : " uit"}" d="${d}" style="stroke:${kleur}"/>${stippen}`;
  };
  const knoop = (x, y, r, kleur, ic, regels) => `
    <circle class="knoop" cx="${x}" cy="${y}" r="${r}" style="stroke:${kleur}"/>
    <use href="#i-${ic}" x="${x - 11}" y="${y - r + 8}" width="22" height="22" class="ico" style="stroke:${kleur}"/>
    ${regels.map((tekst, i) => `<text class="waarde${i ? " zacht" : ""}" x="${x}" y="${y + 8 + i * 16}">${tekst}</text>`).join("")}`;
  const naam = (x, y, tekst, anker = "middle") => `<text class="naam" x="${x}" y="${y}" style="text-anchor:${anker}">${tekst}</text>`;
  const kosten = t.stroom.kosten + t.gas.kosten + t.teruglevering.kosten;
  const C = { stroom: "var(--c-stroom)", terug: "var(--c-terug)", gas: "var(--c-gas)", laden: "var(--c-laden)", huis: "var(--inkt-3)" };
  return `<svg class="stromen" viewBox="0 0 400 300" role="img" aria-label="${[
    `Afgenomen ${hoeveelheid(t.stroom.hoeveelheid)} kWh`,
    `teruggeleverd ${hoeveelheid(t.teruglevering.hoeveelheid)} kWh`,
    `gas ${hoeveelheid(t.gas.hoeveelheid)} m³`,
    `laden ${hoeveelheid(t.laden.hoeveelheid)} kWh`,
    `netto ${euro(kosten)}`,
  ].join(", ")}">
    <defs><!-- gloed in donker (--stromen-gloed); over de hele viewBox, anders verdwijnen rechte lijnen -->
      <filter id="gloed" filterUnits="userSpaceOnUse" x="0" y="0" width="400" height="300">
        <feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter></defs>
    ${lijn("M126,142 H258", C.stroom, t.stroom.hoeveelheid)}
    ${lijn("M258,158 H126", C.terug, t.teruglevering.hoeveelheid)}
    ${lijn("M300,78 V108", C.gas, t.gas.hoeveelheid)}
    ${lijn("M300,192 V222", C.laden, t.laden.hoeveelheid)}
    ${knoop(84, 150, 42, C.stroom, "net", [
      `<tspan style="fill:${C.stroom}">↓</tspan> ${hoeveelheid(t.stroom.hoeveelheid)} kWh`,
      `<tspan style="fill:${C.terug}">↑</tspan> ${hoeveelheid(t.teruglevering.hoeveelheid)} kWh`,
    ])}
    ${naam(84, 212, "Net")}
    ${knoop(300, 150, 42, C.huis, "huis", [euro(kosten), "netto"])}
    ${naam(352, 154, "Huis", "start")}
    ${knoop(300, 44, 34, C.gas, "vlam", [`${hoeveelheid(t.gas.hoeveelheid)} m³`])}
    ${naam(344, 48, "Gas", "start")}
    ${knoop(300, 256, 34, C.laden, "auto", [`${hoeveelheid(t.laden.hoeveelheid)} kWh`])}
    ${naam(344, 260, "Auto", "start")}
  </svg>`;
}
