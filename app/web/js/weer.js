// Het weer in gewone woorden: weercodes (WMO, zoals Open-Meteo ze geeft), wind in Beaufort, de regen
// van de komende uren. Gedeeld door het overzicht en de pagina Weer.

import { esc, getal, icoon, klok } from "./basis.js";

// WMO-code → naam en icoon (overdag, 's nachts).
const CODES = {
  0: ["Onbewolkt", "zon", "maan"],
  1: ["Vrijwel onbewolkt", "zon", "maan"],
  2: ["Half bewolkt", "zon-wolk", "maan-wolk"],
  3: ["Bewolkt", "wolk"],
  45: ["Mist", "mist"],
  48: ["Mist met rijp", "mist"],
  51: ["Lichte motregen", "motregen"],
  53: ["Motregen", "motregen"],
  55: ["Dichte motregen", "motregen"],
  56: ["Lichte ijzel", "motregen"],
  57: ["IJzel", "motregen"],
  61: ["Lichte regen", "regen"],
  63: ["Regen", "regen"],
  65: ["Zware regen", "regen"],
  66: ["Lichte ijzel", "regen"],
  67: ["Zware ijzel", "regen"],
  71: ["Lichte sneeuw", "sneeuw"],
  73: ["Sneeuw", "sneeuw"],
  75: ["Zware sneeuw", "sneeuw"],
  77: ["Korrelsneeuw", "sneeuw"],
  80: ["Lichte buien", "bui", "regen"],
  81: ["Buien", "bui", "regen"],
  82: ["Zware buien", "bui", "regen"],
  85: ["Sneeuwbuien", "sneeuw"],
  86: ["Zware sneeuwbuien", "sneeuw"],
  95: ["Onweer", "onweer"],
  96: ["Onweer met hagel", "onweer"],
  97: ["Zwaar onweer", "onweer"],
  99: ["Onweer met hagel", "onweer"],
};

export const weerNaam = (code) => CODES[code]?.[0] ?? "Onbekend";
/** Icoonnaam voor een weercode; 's nachts een maan in plaats van de zon. */
export const weerIcoon = (code, dag = true) => {
  const c = CODES[code];
  if (!c) return "wolk";
  return !dag && c[2] ? c[2] : c[1];
};
export const weerSvg = (code, dag = true, klasse = "ic") => icoon(weerIcoon(code, dag), klasse);

const BEAUFORT = [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]; // km/u: ondergrens van 1 t/m 12 Bft
const BFT_NAAM = ["windstil", "zwak", "zwak", "matig", "matig", "vrij krachtig", "krachtig", "hard", "stormachtig", "storm", "zware storm", "zeer zware storm", "orkaan"];
export const beaufort = (kmh) => (kmh == null ? null : BEAUFORT.filter((g) => kmh >= g).length);
export const windNaam = (kmh) => BFT_NAAM[beaufort(kmh)] ?? "";

const RICHTING = ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"];
const RICHTING_LANG = ["noord", "noordoost", "oost", "zuidoost", "zuid", "zuidwest", "west", "noordwest"];
export const richting = (graden) => (graden == null ? "" : RICHTING[Math.round(graden / 45) % 8]);
export const richtingLang = (graden) => (graden == null ? "" : RICHTING_LANG[Math.round(graden / 45) % 8]);

/** "4 Bft ZW" */
export const wind = (kmh, graden) => (kmh == null ? "–" : `${beaufort(kmh)} Bft ${richting(graden)}`.trim());

/** Windpijl die meewijst met de wind (Open-Meteo geeft waar hij vandaan komt). */
export const windPijl = (graden) =>
  graden == null ? "" : `<svg class="ic windpijl" viewBox="0 0 24 24" aria-hidden="true" style="transform:rotate(${(graden + 180) % 360}deg)"><path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/></svg>`;

export const graden = (t, d = 0) => (t == null ? "–" : `${getal(t, d)}°`);

export function uvNaam(uv) {
  if (uv == null) return "";
  if (uv < 3) return "laag";
  if (uv < 6) return "matig";
  if (uv < 8) return "hoog";
  if (uv < 11) return "zeer hoog";
  return "extreem";
}

const NAT = 0.05; // mm per kwartier: vanaf hier telt het als regen

/** De komende uren in één zin, uit de neerslag per kwartier: "Droog tot 16:15", "Regen tot 15:30". */
export function regenTekst(kwartieren) {
  if (!kwartieren?.length) return "";
  const nat = (k) => (k.neerslag ?? 0) >= NAT;
  const uur = Math.round((kwartieren.length * 15) / 60);
  if (nat(kwartieren[0])) {
    const droog = kwartieren.find((k) => !nat(k));
    return droog ? `Regen tot ${klok(droog.tijd)}` : `Regen, de komende ${uur} uur`;
  }
  const regen = kwartieren.find(nat);
  return regen ? `Droog tot ${klok(regen.tijd)}` : `Droog, de komende ${uur} uur`;
}

/** Staafjes per kwartier, zoals een buienradar: hoog = veel regen. */
export function regenBalk(kwartieren) {
  if (!kwartieren?.length) return "";
  const max = Math.max(1, ...kwartieren.map((k) => k.neerslag ?? 0));
  const staaf = (k) => {
    const mm = k.neerslag ?? 0;
    const h = mm >= NAT ? Math.max(18, Math.min(100, (Math.sqrt(mm) / Math.sqrt(max)) * 100)) : 6;
    return `<i class="${mm >= NAT ? "nat" : ""}" style="height:${h.toFixed(0)}%" title="${esc(`${klok(k.tijd)}: ${mm >= NAT ? `${getal(mm * 4, 1)} mm per uur` : "droog"}`)}"></i>`;
  };
  const labels = [0, 4, 8].filter((i) => i < kwartieren.length).map((i) => `<span style="left:${(i / kwartieren.length) * 100}%">${i ? klok(kwartieren[i].tijd) : "nu"}</span>`);
  return `<div class="regenbalk" role="img" aria-label="${esc(regenTekst(kwartieren))}">${kwartieren.map(staaf).join("")}</div>
    <div class="regenbalk-labels" aria-hidden="true">${labels.join("")}</div>`;
}

/** Een strook met de komende uren: tijd, icoon, temperatuur en de kans op regen. */
export function uurStrook(uren, aantal = 24) {
  return `<ol class="uurstrook" aria-label="Verwachting per uur">${uren
    .slice(0, aantal)
    .map((u, i) => `<li>
      <span class="tijd">${i ? klok(u.tijd) : "Nu"}</span>
      ${weerSvg(u.weercode, u.dag !== 0)}
      <span class="temp">${graden(u.temperatuur)}</span>
      <span class="kans${(u.neerslagkans ?? 0) >= 30 ? " nat" : ""}" title="Kans op neerslag">${(u.neerslagkans ?? 0) >= 10 ? `${u.neerslagkans}%` : ""}</span>
      <span class="verborgen">${esc(weerNaam(u.weercode))}</span>
    </li>`)
    .join("")}</ol>`;
}

/** Waar het weer voor is: "thuis" (ingesteld bij Auto & laden), "De Bilt" (standaard) of "je ingestelde plek". */
export const plekTekst = (locatie) => locatie?.naam || "thuis";
