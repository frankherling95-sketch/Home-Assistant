// Inzichten: alle uitgerekende inzichten, plus kosten en laden per maand dit jaar.

import { api, css, euro, hoeveelheid, vandaag } from "../basis.js";
import { basis, gekleurd, grafiek, regel, ruimOp, staven } from "../grafiek.js";
import { inzichtTegel, kaart, leeg, skeletKaart } from "../onderdelen.js";

const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-12", { titel: "Inzichten", regels: 4 })}
      ${skeletKaart("b-6", { titel: "Kosten per maand", grafiek: true })}${skeletKaart("b-6", { titel: "Laden per maand", grafiek: true })}</div>`;
  }
  const v = vandaag();
  const [lijst, jaar] = await Promise.all([api(`inzichten?datum=${v}`), api(`periode?type=jaar&datum=${v}`)]);
  if (!ctx.actueel()) return;
  const t = jaar.totalen;
  const kosten = t.stroom.kosten + t.gas.kosten + t.teruglevering.kosten;

  ruimOp();
  main.innerHTML = `<div class="raster">
    ${kaart({
      titel: "Inzichten",
      sub: "uitgerekend uit je eigen meter-, laad- en prijsdata",
      klasse: "b-12",
      id: "k-inzichten",
      inhoud: lijst.length ? `<div class="inzichten">${lijst.map(inzichtTegel).join("")}</div>` : leeg("Nog te weinig gegevens voor inzichten. Na een paar dagen verzamelen verschijnen ze hier."),
    })}
    ${kaart({ titel: "Kosten per maand", sub: jaar.label, klasse: "b-6", id: "k-kosten", rechts: `<span class="pil">${euro(kosten)} dit jaar</span>`, inhoud: '<div class="grafiek" id="g-kosten"></div>' })}
    ${kaart({ titel: "Laden per maand", sub: jaar.label, klasse: "b-6", id: "k-laden", rechts: `<span class="pil">${hoeveelheid(t.laden.hoeveelheid)} kWh, ${euro(t.laden.kosten)}</span>`, inhoud: '<div class="grafiek" id="g-laden"></div>' })}
  </div>`;

  const titel = (i) => `<b style="font-weight:500">${MAANDEN[i]} ${jaar.label}</b>`;
  grafiek(document.getElementById("g-kosten")).setOption(
    basis({
      xAxis: { data: jaar.bakje_labels },
      yAxis: { axisLabel: { formatter: (w) => `€${w}` } },
      tooltip: { formatter: ([p]) => `${titel(p.dataIndex)}${regel(p.color, p.value < 0 ? "Opbrengst" : "Kosten", p.value == null ? "–" : euro(Math.abs(p.value)))}` },
      series: [staven("Kosten", jaar.reeksen.kosten.map((x) => (x == null ? null : gekleurd(x, css(x < 0 ? "--c-terug" : "--c-prijs")))), css("--c-prijs"))],
    }),
  );
  grafiek(document.getElementById("g-laden")).setOption(
    basis({
      xAxis: { data: jaar.bakje_labels },
      tooltip: { formatter: ([p]) => `${titel(p.dataIndex)}${regel(p.color, "Geladen", p.value == null ? "–" : `${hoeveelheid(p.value)} kWh`)}` },
      series: [staven("Laden", jaar.reeksen.laden, css("--c-laden"))],
    }),
  );
}
