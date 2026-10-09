// Prijzen: all-in stroomprijs per kwartier, gekleurd per prijsniveau (zoals Tibber).

import {
  $, $$, NIVEAUS, api, css, datumLang, dagnaam, gemiddelde, getal, goedkoopsteVenster, huidigBlok, isoDatum, klok,
  niveau, plusDagen, prijs, vandaag,
} from "../basis.js";
import { basis, doorzichtig, gekleurd, grafiek, nuLijn, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, pil, skeletKaart, tegel } from "../onderdelen.js";

export async function toon(main, params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-12", { titel: "Stroomprijs per kwartier", grafiek: true })}
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
  const negatief = negatiefVenster(blokken);
  const toelichting = !morgenBekend
    ? "De prijzen voor morgen komen rond 13:00."
    : keuze === "morgen" && negatief
      ? `Negatieve prijzen van ${klok(negatief.van)} tot ${klok(negatief.tot)}.`
      : "";

  ruimOp();
  main.innerHTML = `
    <div class="werkbalk">
      <div class="segment" role="group" aria-label="Dag">
        <button type="button" data-dag="vandaag" aria-pressed="${keuze === "vandaag"}">Vandaag</button>
        <button type="button" data-dag="morgen" aria-pressed="${keuze === "morgen"}" ${morgenBekend ? "" : "disabled"}>Morgen</button>
      </div>
      <span class="werkbalk-sub">${datumLang(dag.datum)}${toelichting ? ` · ${toelichting}` : ""}</span>
    </div>
    <div class="raster">
      ${kaart({
        titel: "Stroomprijs per kwartier",
        sub: "all-in, incl. btw en energiebelasting",
        klasse: "b-12",
        id: "k-prijzen",
        rechts: blokken.length ? `<div class="legenda kop-legenda">${NIVEAUS.map((n) => `<span><i style="background:var(${n.kleur})"></i>${n.naam}</span>`).join("")}</div>` : "",
        inhoud: blokken.length
          ? '<div class="grafiek-scroll"><div class="grafiek" id="g-prijzen" role="img" aria-label="Stroomprijs per kwartier, gekleurd per prijsniveau"></div></div>'
          : leeg("Nog geen prijzen voor deze dag."),
        voet: blokken.length
          ? `Kleur ten opzichte van het daggemiddelde van ${prijs(gem)}: normaal is binnen 7%, (zeer) goedkoop of duur ligt 7% (20%) of meer lager of hoger. Onder nul krijg je geld voor elke kWh die je afneemt.`
          : "",
      })}
      <div class="b-12 prijzen-rij">
        ${keuze === "vandaag" ? nuKaart(d0.prijzen.stroom, alles) : morgenKaart(blokken, d0.prijzen.stroom)}
        ${kaart({ titel: "Goedkoopste moment", sub: `vanaf nu, tot ${morgenBekend ? "morgen" : "vandaag"} 24:00`, id: "k-venster", inhoud: '<div id="venster"></div>' })}
        ${dagKaart(dag, keuze, negatief)}
      </div>
    </div>`;
  for (const b of $$("[data-dag]", main)) b.onclick = () => ctx.navigeer("prijzen", { dag: b.dataset.dag === "morgen" ? "morgen" : "" });
  venster(alles, Number(params.get("uren")) || 3);
  if (blokken.length) tekenen(blokken, gem, keuze === "vandaag");
}

/** Het tijdvak met negatieve prijzen (eerste tot laatste negatieve kwartier), of null. */
function negatiefVenster(blokken) {
  const neg = blokken.filter((b) => b.prijs < 0);
  if (!neg.length) return null;
  const kwartier = new Date(neg[0].tot) - new Date(neg[0].van);
  return { van: neg[0].van, tot: neg.at(-1).tot, uren: (neg.length * kwartier) / 3600e3 };
}

/** Een prijsregel: tijd, stip in de niveaukleur en de prijs. */
const prijsRegel = (b, gem) => {
  const n = niveau(b.prijs, gem);
  return `<li><span class="tijd">${klok(b.van)}</span><i style="background:var(${n.kleur})" title="${n.naam}"></i><span>${prijs(b.prijs)}</span></li>`;
};

function nuKaart(blokken, alles) {
  const nu = huidigBlok(blokken);
  if (!nu) return kaart({ titel: "Nu", inhoud: leeg("Geen prijs voor dit moment.") });
  const gem = gemiddelde(blokken);
  const n = niveau(nu.prijs, gem);
  // De komende prijzen: over een kwartier, een uur en twee uur.
  const start = new Date(nu.van).getTime();
  const dagGemiddelde = (b) => gemiddelde(alles.filter((x) => isoDatum(new Date(x.van)) === isoDatum(new Date(b.van))));
  const komend = [15, 60, 120]
    .map((m) => huidigBlok(alles, start + m * 60e3 + 1))
    .filter(Boolean)
    .filter((b, i, a) => a.indexOf(b) === i);
  return kaart({
    titel: "Nu",
    id: "k-nu",
    rechts: `<span class="pil"><span class="stip" style="background:var(${n.kleur})"></span>${n.naam}</span>`,
    inhoud: `<div class="prijs-nu">${prijs(nu.prijs)} <small>per kWh</small></div>
      <p class="zacht">${klok(nu.van)}–${klok(nu.tot)}</p>
      ${komend.length ? `<h3 class="tussenkop">Komende prijzen</h3><ul class="prijsregels">${komend.map((b) => prijsRegel(b, dagGemiddelde(b) ?? gem)).join("")}</ul>` : ""}`,
  });
}

function morgenKaart(blokken, vandaagBlokken) {
  const gem = gemiddelde(blokken);
  const gisteren = gemiddelde(vandaagBlokken);
  const verschil = gisteren ? gem / gisteren - 1 : null;
  return kaart({
    titel: "Morgen gemiddeld",
    id: "k-nu",
    rechts: verschil == null ? "" : pil(`${getal(Math.abs(verschil) * 100, 0)}% ${verschil > 0 ? "duurder" : "goedkoper"}`, verschil > 0 ? "let_op" : "goed"),
    inhoud: `<div class="prijs-nu">${prijs(gem)} <small>per kWh</small></div>
      <p class="zacht">${verschil == null ? "" : `dan vandaag (${prijs(gisteren)})`}</p>`,
  });
}

function dagKaart(dag, keuze, negatief) {
  const b = dag.prijzen.stroom;
  const titel = keuze === "morgen" ? "Morgen in cijfers" : "Vandaag in cijfers";
  if (!b.length) return kaart({ titel, inhoud: leeg("Nog geen prijzen.") });
  const laag = b.reduce((a, x) => (x.prijs < a.prijs ? x : a));
  const hoog = b.reduce((a, x) => (x.prijs > a.prijs ? x : a));
  // De gasdag wisselt om 06:00: vandaag de prijs van nu, morgen die van de nieuwe gasdag.
  const gas = (keuze === "vandaag" && huidigBlok(dag.prijzen.gas)) || dag.prijzen.gas.at(-1);
  return kaart({
    titel,
    id: "k-cijfers",
    inhoud: `<div class="tegels twee">
      ${tegel("Laagste", `${prijs(laag.prijs)} <small>${klok(laag.van)}</small>`)}
      ${tegel("Hoogste", `${prijs(hoog.prijs)} <small>${klok(hoog.van)}</small>`)}
      ${tegel("Gemiddeld", prijs(gemiddelde(b)))}
      ${tegel("Negatief", negatief ? `${getal(negatief.uren, negatief.uren % 1 ? 2 : 0)} uur <small>${klok(negatief.van)}–${klok(negatief.tot)}</small>` : "geen", negatief ? "tekst-negatief" : "")}
      ${tegel("Gas", gas ? `${prijs(gas.prijs)} <small>per m³</small>` : "–")}
      ${tegel("Spreiding", `${prijs(hoog.prijs - laag.prijs)} <small>hoog − laag</small>`)}
    </div>`,
  });
}

function venster(blokken, uren) {
  const el = $("#venster");
  const teken = (u) => {
    const v = goedkoopsteVenster(blokken, u);
    const gem = gemiddelde(blokken.filter((b) => new Date(b.tot) > Date.now()));
    el.innerHTML = `
      <div class="segment vol" role="group" aria-label="Duur" style="margin-bottom:16px">
        ${[1, 2, 3, 4].map((n) => `<button type="button" data-uren="${n}" aria-pressed="${n === u}">${n} uur</button>`).join("")}
      </div>
      ${
        v
          ? `<div class="venster-tijd">${klok(v.van)}–${klok(v.tot)} <small>${dagnaam(v.van)}</small></div>
             <p class="zacht">Gemiddeld ${prijs(v.prijs)} per kWh${gem != null ? `, ${prijs(Math.abs(gem - v.prijs))} ${v.prijs <= gem ? "onder" : "boven"} het gemiddelde van de komende uren` : ""}.</p>`
          : leeg(`Geen ${u} uur aaneengesloten prijzen meer bekend.`)
      }`;
    for (const b of $$("[data-uren]", el)) b.onclick = () => teken(Number(b.dataset.uren));
  };
  teken([1, 2, 3, 4].includes(uren) ? uren : 3);
}

function tekenen(blokken, gem, metNu) {
  const nu = metNu ? huidigBlok(blokken) : null;
  const nuTijd = Date.now();
  const negatief = css("--p-negatief");
  const gloed = Number(css("--gloed-grafiek")) || 0;
  const data = blokken.map((b) => {
    const k = css(niveau(b.prijs, gem).kleur);
    const item = gekleurd(b.prijs, k);
    item.itemStyle = { ...item.itemStyle, shadowBlur: gloed, shadowColor: k };
    if (metNu && new Date(b.tot) <= nuTijd) item.itemStyle.opacity = 0.35; // al voorbij
    if (b.prijs < 0) Object.assign(item.itemStyle, { color: doorzichtig(k, 0.35), borderColor: negatief, borderWidth: 1.5 });
    return item;
  });
  const el = document.getElementById("g-prijzen");
  grafiek(el).setOption(
    basis({
      grid: { top: 34, left: 4, right: 8, bottom: 0 },
      xAxis: {
        data: blokken.map((b) => b.van),
        axisLabel: { interval: (i, iso) => /^(00|02|04|06|08|10|12|14|16|18|20|22):00$/.test(klok(iso)), formatter: (iso) => klok(iso) },
      },
      yAxis: { axisLabel: { formatter: (w) => (w === 0 ? "€ 0" : `€ ${getal(w, 2)}`) } },
      tooltip: {
        formatter: ([p]) => {
          const b = blokken[p.dataIndex];
          const n = niveau(b.prijs, gem);
          return `${klok(b.van)}–${klok(b.tot)}${regel(css(n.kleur), n.naam, prijs(b.prijs))}`;
        },
      },
      series: [
        staven("Prijs", data, null, {
          barMaxWidth: 12,
          barCategoryGap: "18%",
          markLine: {
            symbol: "none",
            silent: true,
            animation: false,
            data: [
              {
                yAxis: gem,
                lineStyle: { color: css("--inkt-3"), type: "dashed", width: 1 },
                label: {
                  formatter: `gemiddeld ${prijs(gem)}`, position: "insideEndTop", color: css("--inkt-2"), fontSize: 11,
                  backgroundColor: css("--oppervlak"), padding: [1, 4], borderRadius: 3,
                },
              },
              ...(nu ? [nuLijn(nu.van)] : []),
            ],
          },
        }),
      ],
    }),
  );
  // Op een smal scherm scrollt de grafiek; begin bij "nu".
  const scroll = el.parentElement;
  if (nu && scroll.scrollWidth > scroll.clientWidth) {
    scroll.scrollLeft = Math.max(0, (blokken.indexOf(nu) / blokken.length) * scroll.scrollWidth - 40);
  }
}
