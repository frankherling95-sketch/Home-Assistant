// Prijzen: all-in stroomprijs per kwartier, gekleurd per prijsniveau (zoals Tibber).

import {
  $, $$, NIVEAUS, api, css, datumLang, dagnaam, gemiddelde, getal, goedkoopsteVenster, huidigBlok, klok,
  niveau, plusDagen, prijs, vandaag,
} from "../basis.js";
import { basis, gekleurd, grafiek, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, skeletKaart, tegel } from "../onderdelen.js";

export async function toon(main, params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-12", { titel: "Stroomprijs", grafiek: true })}
      ${skeletKaart("b-4")}${skeletKaart("b-4")}${skeletKaart("b-4")}</div>`;
  }
  const v = vandaag();
  const [d0, d1] = await Promise.all([api(`dag?datum=${v}`), api(`dag?datum=${plusDagen(v, 1)}`)]);
  if (!ctx.actueel()) return;
  const morgenBekend = d1.prijzen.stroom.length > 0;
  const keuze = params.get("dag") === "morgen" && morgenBekend ? "morgen" : "vandaag";
  const dag = keuze === "morgen" ? d1 : d0;
  const blokken = dag.prijzen.stroom;
  const gem = gemiddelde(blokken);
  const alles = [...d0.prijzen.stroom, ...d1.prijzen.stroom];

  ruimOp();
  main.innerHTML = `
    <div class="werkbalk">
      <div class="segment" role="group" aria-label="Dag">
        <button type="button" data-dag="vandaag" aria-pressed="${keuze === "vandaag"}">Vandaag</button>
        <button type="button" data-dag="morgen" aria-pressed="${keuze === "morgen"}" ${morgenBekend ? "" : "disabled"}>Morgen</button>
      </div>
      ${morgenBekend ? "" : '<span class="zacht klein">De prijzen voor morgen komen rond 13:00.</span>'}
    </div>
    <div class="raster">
      ${kaart({
        titel: "Stroomprijs per kwartier",
        sub: `${datumLang(dag.datum)}, all-in`,
        klasse: "b-12",
        id: "k-prijzen",
        inhoud: blokken.length
          ? `<div class="grafiek hoog" id="g-prijzen" role="img" aria-label="Stroomprijs per kwartier"></div>
             <div class="legenda">${NIVEAUS.map((n) => `<span><i style="background:var(${n.kleur})"></i>${n.naam}</span>`).join("")}</div>
             <p class="kaart-voet">Kleur ten opzichte van het daggemiddelde van ${prijs(gem)}: normaal is binnen 7%, (zeer) goedkoop of duur ligt 7% (20%) of meer lager of hoger. Onder nul krijg je geld voor elke kWh die je afneemt.</p>`
          : leeg("Nog geen prijzen voor deze dag."),
      })}
      ${keuze === "vandaag" ? nuKaart(d0.prijzen.stroom) : morgenKaart(blokken, d0.prijzen.stroom)}
      ${kaart({ titel: "Goedkoopste moment", sub: "vanaf nu", klasse: "b-4", id: "k-venster", inhoud: '<div id="venster"></div>' })}
      ${dagKaart(dag, keuze)}
    </div>`;
  for (const b of $$("[data-dag]", main)) b.onclick = () => ctx.navigeer("prijzen", { dag: b.dataset.dag === "morgen" ? "morgen" : "" });
  venster(alles, Number(params.get("uren")) || 3);
  if (blokken.length) tekenen(blokken, gem, keuze === "vandaag");
}

function nuKaart(blokken) {
  const nu = huidigBlok(blokken);
  if (!nu) return kaart({ titel: "Nu", klasse: "b-4", inhoud: leeg("Geen prijs voor dit moment.") });
  const gem = gemiddelde(blokken);
  const n = niveau(nu.prijs, gem);
  const i = blokken.indexOf(nu);
  const volgende = blokken.slice(i + 1).find((b) => Math.abs(b.prijs - nu.prijs) > 0.0005);
  return kaart({
    titel: "Nu",
    klasse: "b-4",
    id: "k-nu",
    rechts: `<span class="pil"><span class="stip" style="background:var(${n.kleur})"></span>${n.naam}</span>`,
    inhoud: `<div class="groot">${prijs(nu.prijs)}<small>per kWh</small></div>
      <p class="zacht klein">${klok(nu.van)}–${klok(nu.tot)}</p>`,
    voet: volgende ? `Om ${klok(volgende.van)} ${volgende.prijs > nu.prijs ? "duurder" : "goedkoper"}: ${prijs(volgende.prijs)}` : "",
  });
}

function morgenKaart(blokken, vandaagBlokken) {
  const gem = gemiddelde(blokken);
  const gisteren = gemiddelde(vandaagBlokken);
  const verschil = gisteren ? gem / gisteren - 1 : null;
  return kaart({
    titel: "Morgen gemiddeld",
    klasse: "b-4",
    inhoud: `<div class="groot">${prijs(gem)}<small>per kWh</small></div>
      <p class="zacht klein">${verschil == null ? "" : `${getal(Math.abs(verschil) * 100, 0)}% ${verschil > 0 ? "duurder" : "goedkoper"} dan vandaag`}</p>`,
  });
}

function dagKaart(dag, keuze) {
  const b = dag.prijzen.stroom;
  if (!b.length) return kaart({ titel: "In cijfers", klasse: "b-4", inhoud: leeg("Nog geen prijzen.") });
  const laag = b.reduce((a, x) => (x.prijs < a.prijs ? x : a));
  const hoog = b.reduce((a, x) => (x.prijs > a.prijs ? x : a));
  const negatief = b.filter((x) => x.prijs < 0);
  // De gasdag wisselt om 06:00: vandaag de prijs van nu, morgen die van de nieuwe gasdag.
  const gas = (keuze === "vandaag" && huidigBlok(dag.prijzen.gas)) || dag.prijzen.gas.at(-1);
  return kaart({
    titel: keuze === "morgen" ? "Morgen in cijfers" : "Vandaag in cijfers",
    klasse: "b-4",
    id: "k-cijfers",
    inhoud: `<div class="tegels">
      ${tegel("Laagste", `${prijs(laag.prijs)} <small>${klok(laag.van)}</small>`)}
      ${tegel("Hoogste", `${prijs(hoog.prijs)} <small>${klok(hoog.van)}</small>`)}
      ${tegel("Gemiddeld", prijs(gemiddelde(b)))}
      ${tegel("Negatief", negatief.length ? `${getal((negatief.length * (new Date(b[0].tot) - new Date(b[0].van))) / 3600e3, 2)} <small>uur</small>` : "geen")}
      ${gas ? tegel("Gas", `${prijs(gas.prijs)} <small>per m³</small>`) : ""}
    </div>`,
  });
}

function venster(blokken, uren) {
  const el = $("#venster");
  const teken = (u) => {
    const v = goedkoopsteVenster(blokken, u);
    const gem = gemiddelde(blokken.filter((b) => new Date(b.tot) > Date.now()));
    el.innerHTML = `
      <div class="segment vol" role="group" aria-label="Duur" style="margin-bottom:14px">
        ${[1, 2, 3, 4].map((n) => `<button type="button" data-uren="${n}" aria-pressed="${n === u}">${n} uur</button>`).join("")}
      </div>
      ${
        v
          ? `<div class="groot" style="font-size:28px">${klok(v.van)}–${klok(v.tot)} <small>${dagnaam(v.van)}</small></div>
             <p class="zacht klein">Gemiddeld ${prijs(v.prijs)} per kWh${gem != null ? `, ${prijs(Math.abs(gem - v.prijs))} ${v.prijs <= gem ? "onder" : "boven"} het gemiddelde van de komende uren` : ""}.</p>`
          : leeg(`Geen ${u} uur aaneengesloten prijzen meer bekend.`)
      }`;
    for (const b of $$("[data-uren]", el)) b.onclick = () => teken(Number(b.dataset.uren));
  };
  teken([1, 2, 3, 4].includes(uren) ? uren : 3);
}

function tekenen(blokken, gem, metNu) {
  const nu = metNu ? huidigBlok(blokken) : null;
  const labels = blokken.map((b) => klok(b.van));
  grafiek(document.getElementById("g-prijzen")).setOption(
    basis({
      xAxis: { data: labels, axisLabel: { interval: (i, w) => w.endsWith(":00") && Number(w.slice(0, 2)) % 2 === 0 } },
      yAxis: { axisLabel: { formatter: (w) => `€ ${getal(w, 2)}` } },
      tooltip: {
        formatter: ([p]) => {
          const b = blokken[p.dataIndex];
          const n = niveau(b.prijs, gem);
          return `${klok(b.van)}–${klok(b.tot)}${regel(css(n.kleur), n.naam, prijs(b.prijs))}`;
        },
      },
      series: [
        staven("Prijs", blokken.map((b) => gekleurd(b.prijs, css(niveau(b.prijs, gem).kleur))), null, {
          barMaxWidth: 12,
          barCategoryGap: "18%",
          markLine: {
            symbol: "none",
            silent: true,
            animation: false,
            label: { color: css("--inkt-2"), fontSize: 11, position: "insideEndTop" },
            lineStyle: { color: css("--inkt-3"), type: "dashed", width: 1 },
            data: [
              { yAxis: gem, label: { formatter: "gemiddeld" } },
              ...(nu ? [{ xAxis: klok(nu.van), label: { formatter: "nu", position: "end" } }] : []),
            ],
          },
        }),
      ],
    }),
  );
}
