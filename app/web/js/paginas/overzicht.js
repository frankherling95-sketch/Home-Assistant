// Overzicht: prijs nu, energiestromen, auto en lader, inzichten en de totalen.

import {
  LADER_STATUS, PLAN_REDEN, api, autoFoto, autoStand, css, dagnaam, esc, euro, gemiddelde, getal, goedkoopsteVenster,
  hoeveelheid, huidigBlok, klok, niveau, plusDagen, prijs, vandaag,
} from "../basis.js";
import { basis, gekleurd, grafiek, markering, regel, ruimOp, staven } from "../grafiek.js";
import { inzichtTegel, kaart, leeg, skeletKaart, tegel, totalenTabel } from "../onderdelen.js";

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="overzicht">
      <div class="kolom">${skeletKaart("o-stromen", { titel: "Energiestromen", regels: 6 })}${skeletKaart("o-totalen", { titel: "Totalen" })}</div>
      <div class="kolom">${skeletKaart("o-prijs", { titel: "Stroomprijs nu", grafiek: true })}${skeletKaart("o-auto", { titel: "Auto en lader" })}</div>
    </div>`;
  }
  const v = vandaag();
  const [nu, dag, morgen, inzichten] = await Promise.all([
    api("nu"),
    api(`dag?datum=${v}`),
    api(`dag?datum=${plusDagen(v, 1)}`),
    api(`inzichten?datum=${v}`).catch(() => []),
  ]);
  // De slimme meter komt via Frank met een dag vertraging: dan gisteren tonen.
  const meterdag = dag.compleet.verbruik ? dag : await api(`dag?datum=${plusDagen(v, -1)}`);
  if (!ctx.actueel()) return;

  const welkeDag = meterdag === dag ? "vandaag" : "gisteren";
  ruimOp();
  main.innerHTML = `<div class="overzicht">
    <div class="kolom">
      ${kaart({
        titel: "Energiestromen",
        sub: welkeDag === "gisteren" ? "gisteren · meterdata van vandaag volgt morgen" : "vandaag",
        klasse: "o-stromen",
        id: "k-stromen",
        inhoud: meterdag.compleet.verbruik || meterdag.totalen.laden.hoeveelheid ? stromen(meterdag.totalen) : '<p class="leeg">Nog geen meterdata. <a href="#/koppelingen">Koppel Frank Energie</a> voor je verbruik.</p>',
      })}
      ${kaart({ titel: `Totalen ${welkeDag}`, klasse: "o-totalen", id: "k-totalen", inhoud: totalenTabel(meterdag.totalen) })}
    </div>
    <div class="kolom">
      ${prijsKaart(dag, morgen)}
      ${autoKaart(nu)}
    </div>
    ${
      inzichten.length
        ? kaart({
            titel: "Inzichten",
            klasse: "vol o-inzichten",
            id: "k-inzichten",
            inhoud: `<div class="inzichten">${inzichten.slice(0, 4).map(inzichtTegel).join("")}</div>`,
            voet: inzichten.length > 4 ? `<a href="#/inzichten">Alle ${inzichten.length} inzichten</a>` : "",
          })
        : ""
    }
  </div>`;
  prijsGrafiek(dag.prijzen.stroom);
}

// ── energiestromen (zoals de energieverdeling in Home Assistant) ──────────────

function stromen(t) {
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

// ── prijs ─────────────────────────────────────────────────────────────────────

function prijsKaart(dag, morgen) {
  const blokken = dag.prijzen.stroom;
  if (!blokken.length) return kaart({ titel: "Stroomprijs nu", klasse: "o-prijs", inhoud: leeg("Nog geen prijzen voor vandaag.") });
  const gem = gemiddelde(blokken);
  const nu = huidigBlok(blokken);
  const niv = nu ? niveau(nu.prijs, gem) : null;
  const venster = goedkoopsteVenster([...blokken, ...morgen.prijzen.stroom], 1);
  return kaart({
    titel: "Stroomprijs nu",
    klasse: "o-prijs",
    id: "k-prijs",
    rechts: niv ? `<span class="pil"><span class="stip" style="background:var(${niv.kleur})"></span>${niv.naam}</span>` : "",
    inhoud: `
      <div class="groot">${prijs(nu?.prijs)}<small>per kWh, all-in</small></div>
      <p class="zacht klein">${nu ? `tot ${klok(nu.tot)}, ` : ""}daggemiddelde ${prijs(gem)}</p>
      <div class="grafiek laag" id="g-prijs" role="img" aria-label="Stroomprijs vandaag per kwartier"></div>`,
    voet: `${venster ? `Goedkoopste uur: <b>${dagnaam(venster.van)} ${klok(venster.van)}–${klok(venster.tot)}</b>, gemiddeld ${prijs(venster.prijs)}. ` : ""}<a href="#/prijzen">Alle prijzen</a>`,
  });
}

function prijsGrafiek(blokken) {
  const el = document.getElementById("g-prijs");
  if (!el || !blokken.length) return;
  const gem = gemiddelde(blokken);
  const nu = huidigBlok(blokken);
  const labels = blokken.map((b) => klok(b.van));
  grafiek(el).setOption(
    basis({
      grid: { top: 18 },
      xAxis: { data: labels, axisLabel: { interval: (i, w) => w.endsWith(":00") && Number(w.slice(0, 2)) % 6 === 0 } },
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
          barMaxWidth: 8,
          barCategoryGap: "20%",
          markLine: nu ? markering(klok(nu.van), "nu") : undefined,
        }),
      ],
    }),
  );
}

// ── auto en lader ─────────────────────────────────────────────────────────────

function autoKaart({ auto, lader, plan, instellingen }) {
  const pct = auto?.accu_pct;
  const doel = plan.doel_pct ?? instellingen.doel_pct;
  const bereik = auto?.bereik_km != null ? `${getal(auto.bereik_km, 0)} km` : "";
  const foto = autoFoto(auto?.naam);
  const balk = (label) => `<div class="accu${(pct ?? 0) < 15 ? " laag" : ""}" role="meter" aria-label="Accu" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct ?? 0)}">
        <div class="vulling" style="width:${pct ?? 0}%"></div>
        <div class="doel" style="left:${doel}%" title="Doel ${doel}%"></div>
        ${label}
      </div>`;
  // Met een foto van de auto: het percentage groot ernaast en een balk zonder tekst, zoals op de pagina Auto.
  const accu = !auto
    ? '<p class="leeg">Nog geen gegevens van de auto. <a href="#/koppelingen">Koppel je auto</a></p>'
    : foto
      ? `<div class="auto-held">
          <div class="auto-kop"><div class="groot">${getal(pct, 0)}<small>%</small></div><div class="zacht">${bereik && `${bereik} bereik`}</div></div>
          <div class="auto-foto"><img src="${foto}" alt="${esc(auto.naam)}" width="688" height="336"></div>
        </div>${balk("")}`
      : balk(`<span><b>${getal(pct, 0)}%</b><span class="zacht">${bereik}</span></span>`);
  const b = plan.blokken;
  const planTekst = b.length ? `${klok(b[0].van)}–${klok(b.at(-1).tot)}` : PLAN_REDEN[plan.reden] || plan.reden;
  return kaart({
    titel: "Auto en lader",
    klasse: "o-auto",
    id: "k-auto",
    rechts: plan.nu_laden ? '<span class="pil goed"><span class="stip"></span>Laadt nu</span>' : "",
    inhoud: `${accu}
      <div class="tegels" style="margin-top:12px">
        ${tegel("Stekker", auto ? (auto.ingeplugd ? "Ingeplugd" : "Los") : "–")}
        ${tegel("Lader", lader ? LADER_STATUS[lader.status] || lader.status : "–")}
        ${tegel(b.length ? "Laadplan" : "Slim laden", planTekst)}
        ${b.length ? tegel("Kosten plan", euro(plan.kosten)) : tegel("Vertrek", `${klok(plan.vertrek)} <small>${dagnaam(plan.vertrek)}</small>`)}
      </div>`,
    voet: `${auto?.bijgewerkt ? `Auto: ${autoStand(auto)}. ` : ""}<a href="#/laden">Naar laden</a>`,
  });
}
