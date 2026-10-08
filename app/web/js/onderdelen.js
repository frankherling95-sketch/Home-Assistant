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
