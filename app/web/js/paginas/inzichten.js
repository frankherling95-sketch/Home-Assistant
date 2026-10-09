// Inzichten: alle uitgerekende inzichten, plus kosten en laden per maand dit jaar.

import { api, css, euro, getal, hoeveelheid, prijs, vandaag } from "../basis.js";
import { basis, grafiek, regel, ruimOp, staven } from "../grafiek.js";
import { inzichtTegel, kaart, leeg, pil, skeletKaart } from "../onderdelen.js";

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
  const laadprijs = t.laden.hoeveelheid ? t.laden.kosten / t.laden.hoeveelheid : null;

  ruimOp();
  main.innerHTML = `<div class="raster">
    <div class="b-12">${
      lijst.length
        ? `<div class="inzichten kaarten">${lijst.map(inzichtTegel).join("")}</div>`
        : kaart({ titel: "Inzichten", inhoud: leeg("Nog te weinig gegevens voor inzichten. Na een paar dagen verzamelen verschijnen ze hier.") })
    }</div>
    ${kaart({
      titel: "Kosten per maand",
      sub: jaar.label,
      klasse: "b-6",
      id: "k-kosten",
      rechts: pil(`€ ${getal(kosten, 0)} dit jaar`),
      inhoud: `<div class="grafiek" id="g-kosten" role="img" aria-label="Kosten van stroom en gas per maand"></div>
        <div class="legenda"><span><i style="background:var(--c-stroom)"></i>Stroom (netto)</span><span><i style="background:var(--c-gas)"></i>Gas</span></div>`,
    })}
    ${kaart({
      titel: "Laden per maand",
      sub: jaar.label,
      klasse: "b-6",
      id: "k-laden",
      rechts: pil(`${getal(t.laden.hoeveelheid, 0)} kWh, € ${getal(t.laden.kosten, 0)}`),
      inhoud: '<div class="grafiek" id="g-laden" role="img" aria-label="Geladen kWh per maand"></div>',
      voet: `kWh per maand, geladen met de lader thuis${laadprijs != null ? ` · gemiddeld ${prijs(laadprijs)} per kWh` : ""}`,
    })}
  </div>`;

  const r = jaar.reeksen;
  const titel = (i) => `<b style="font-weight:500">${MAANDEN[i]} ${jaar.label}</b>`;
  // Het getal boven een staaf; lege maanden krijgen geen "0".
  const erboven = (formatter) => ({ show: true, position: "top", fontSize: 11, color: css("--inkt-2"), formatter });
  const k = { stroom: css("--c-stroom"), gas: css("--c-gas"), laden: css("--c-laden") };

  grafiek(document.getElementById("g-kosten")).setOption(
    basis({
      grid: { top: 24 },
      xAxis: { data: jaar.bakje_labels },
      yAxis: { axisLabel: { formatter: (w) => `€ ${getal(w, 0)}` } },
      tooltip: {
        formatter: ([p]) => {
          const i = p.dataIndex;
          if (r.kosten[i] == null) return `${titel(i)}<br>Nog geen meterdata`;
          return `${titel(i)}${regel(k.stroom, "Stroom (netto)", euro(r.kosten_stroom[i]))}${regel(k.gas, "Gas", euro(r.kosten_gas[i]))}${regel(css("--inkt-3"), "Totaal", euro(r.kosten[i]))}`;
        },
      },
      series: [
        staven("Stroom (netto)", r.kosten_stroom, k.stroom, { stapel: "k", itemStyle: { color: k.stroom, borderRadius: 0, shadowBlur: 0 } }),
        staven("Gas", r.kosten_gas, k.gas, {
          stapel: "k",
          label: erboven((p) => (r.kosten[p.dataIndex] ? getal(r.kosten[p.dataIndex], 0) : "")),
        }),
      ],
    }),
  );
  grafiek(document.getElementById("g-laden")).setOption(
    basis({
      grid: { top: 24 },
      xAxis: { data: jaar.bakje_labels },
      yAxis: { axisLabel: { formatter: (w) => getal(w, 0) } },
      tooltip: { formatter: ([p]) => `${titel(p.dataIndex)}${regel(k.laden, "Geladen", p.value == null ? "–" : `${hoeveelheid(p.value)} kWh`)}` },
      series: [staven("Laden", r.laden, k.laden, { label: erboven((p) => (p.value ? getal(p.value, 0) : "")) })],
    }),
  );
}
