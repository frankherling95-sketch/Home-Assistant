// Weer: de verwachting voor thuis van Open-Meteo (KNMI, DWD, ECMWF). Nu, de komende 48 uur, de
// komende 7 dagen, en wat het weer betekent voor je gasverbruik (geschat uit je eigen meterdata).

import { api, css, dagnaam, esc, euro, getal, hoeveelheid, klok } from "../basis.js";
import { basis, doorzichtig, grafiek, lijn, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, melding, skeletKaart, tegel } from "../onderdelen.js";
import {
  beaufort, graden, plekTekst, regenBalk, regenTekst, richtingLang, uurStrook, uvNaam, weerNaam, weerSvg, wind, windNaam, windPijl,
} from "../weer.js";

const DAG = new Intl.DateTimeFormat("nl-NL", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const middag = (iso) => new Date(`${iso}T12:00:00Z`);
/** "Vandaag", "Morgen", "za 11 okt" voor een datum (YYYY-MM-DD). */
function dagLabel(iso, i) {
  if (i === 0) return "Vandaag";
  if (i === 1) return "Morgen";
  return DAG.format(middag(iso));
}
const uren = (s) => (s == null ? null : s / 3600);

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-5", { titel: "Nu", regels: 5 })}${skeletKaart("b-7", { titel: "Komende 48 uur", grafiek: true })}
      ${skeletKaart("b-7", { titel: "Komende 7 dagen", regels: 7 })}${skeletKaart("b-5", { titel: "Weer en je energie", regels: 4 })}</div>`;
  }
  const w = await api("weer", { vers: ctx.ververs });
  if (!ctx.actueel()) return;
  ctx.sub(`voor ${plekTekst(w.locatie)} · bijgewerkt ${klok(w.bijgewerkt)}`);
  ruimOp();
  main.innerHTML = `<div class="raster weer">
    ${nuKaart(w)}
    ${kaart({
      titel: "Komende 48 uur",
      klasse: "b-7",
      id: "k-uren",
      rechts: `<div class="legenda kop-legenda"><span><i class="lijn" style="background:var(--c-temp)"></i>Temperatuur</span><span><i style="background:var(--c-regen)"></i>Neerslag</span></div>`,
      inhoud: `<div class="grafiek" id="g-weer" role="img" aria-label="${esc(urenAria(w.uren))}"></div>${uurStrook(w.uren, 24)}`,
    })}
    ${dagenKaart(w)}
    ${energieKaart(w)}
    <p class="b-12 weerbron">Weer van <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo.com</a> (KNMI, DWD en ECMWF), CC BY 4.0. ${w.locatie.bron === "thuis" ? "Voor de plek die je bij Auto &amp; laden als thuis hebt ingesteld, afgerond op een kilometer." : `Voor ${esc(plekTekst(w.locatie))}. <a href="#/auto">Stel bij Auto &amp; laden je thuis in</a> voor het weer op je eigen plek.`}</p>
  </div>`;
  urenGrafiek(w.uren);
}

// ── nu ────────────────────────────────────────────────────────────────────────

function nuKaart(w) {
  const n = w.nu;
  const vandaag = w.dagen[0] || {};
  const dag = n.dag !== 0;
  return kaart({
    titel: "Nu",
    sub: `${plekTekst(w.locatie)} · ${klok(n.tijd)}`,
    klasse: "b-5",
    id: "k-weer-nu",
    inhoud: `<div class="weer-held">
        <span class="weer-icoon">${weerSvg(n.weercode, dag)}</span>
        <div><div class="groot">${getal(n.temperatuur, 0)}<small>°C</small></div>
          <p class="weer-naam">${esc(weerNaam(n.weercode))}</p>
          <p class="zacht">voelt als ${graden(n.gevoel)} · vandaag ${graden(vandaag.temp_min)} tot ${graden(vandaag.temp_max)}</p></div>
      </div>
      <div class="regen">
        <p class="regen-tekst">${esc(regenTekst(w.kwartieren))}</p>
        ${regenBalk(w.kwartieren)}
      </div>
      <div class="tegels drie">
        ${tegel("Wind", `${windPijl(n.windrichting)}${beaufort(n.wind)} <small>Bft ${esc(richtingLang(n.windrichting))}</small>`)}
        ${tegel("Windstoten", `${getal(n.windstoten, 0)} <small>km/u</small>`)}
        ${tegel("Luchtvochtigheid", `${getal(n.vochtigheid, 0)}<small>%</small>`)}
        ${tegel("Bewolking", `${getal(n.bewolking, 0)}<small>%</small>`)}
        ${tegel("Zon", vandaag.zon_op ? `${klok(vandaag.zon_op)}–${klok(vandaag.zon_onder)}` : "–")}
        ${tegel("UV-index", vandaag.uv != null ? `${getal(vandaag.uv, 0)} <small>${uvNaam(vandaag.uv)}</small>` : "–")}
      </div>`,
  });
}

// ── 48 uur ────────────────────────────────────────────────────────────────────

function urenAria(u) {
  const temps = u.map((x) => x.temperatuur).filter((t) => t != null);
  const mm = u.reduce((s, x) => s + (x.neerslag || 0), 0);
  return `Temperatuur de komende 48 uur van ${graden(Math.min(...temps))} tot ${graden(Math.max(...temps))}, samen ${getal(mm, 1)} mm neerslag`;
}

function urenGrafiek(u) {
  const el = document.getElementById("g-weer");
  if (!el) return;
  const temp = css("--c-temp");
  const regen = css("--c-regen");
  const as = basis().yAxis;
  // De nacht als zacht vlak achter de grafiek.
  const nachten = [];
  u.forEach((x, i) => {
    if (x.dag !== 0) return;
    const laatst = nachten.at(-1);
    if (laatst && laatst[1].xAxis === i - 1) laatst[1].xAxis = i;
    else nachten.push([{ xAxis: i }, { xAxis: i }]);
  });
  const x = u.map((p) => p.tijd);
  grafiek(el).setOption(
    basis({
      grid: { top: 16, left: 4, right: 4, bottom: 0 },
      tooltip: {
        formatter: (punten) => {
          const p = u[punten[0].dataIndex];
          return `${dagnaam(p.tijd)} ${klok(p.tijd)} · ${esc(weerNaam(p.weercode))}${regel(temp, "Temperatuur", graden(p.temperatuur, 1))}${regel(regen, "Neerslag", `${getal(p.neerslag ?? 0, 1)} mm${p.neerslagkans != null ? ` (${p.neerslagkans}%)` : ""}`)}${regel(css("--inkt-3"), "Wind", wind(p.wind, p.windrichting))}`;
        },
      },
      xAxis: {
        data: x,
        axisLabel: {
          // Op een smal scherm alleen middernacht en het middaguur, anders lopen de labels in elkaar.
          interval: (_i, iso) => (el.clientWidth < 560 ? ["00:00", "12:00"] : ["00:00", "06:00", "12:00", "18:00"]).includes(klok(iso)),
          formatter: (iso) => (klok(iso) === "00:00" ? `{dag|${dagnaam(iso)}}` : klok(iso)),
          rich: { dag: { fontWeight: 500, color: css("--inkt-2"), fontSize: 12 } },
        },
      },
      yAxis: [
        { ...as, scale: true, axisLabel: { ...as.axisLabel, formatter: (w) => `${w}°` } },
        { ...as, min: 0, max: (m) => Math.max(4, Math.ceil(m.max)), splitLine: { show: false }, axisLabel: { ...as.axisLabel, formatter: (w) => (w ? `${w} mm` : "") } },
      ],
      series: [
        staven("Neerslag", u.map((p) => p.neerslag ?? 0), regen, { yAxisIndex: 1, barMaxWidth: 8, barCategoryGap: "35%" }),
        lijn("Temperatuur", u.map((p) => p.temperatuur), temp, {
          smooth: true,
          markArea: { silent: true, itemStyle: { color: doorzichtig(css("--inkt-3"), 0.08) }, data: nachten },
        }),
      ],
    }),
  );
}

// ── 7 dagen ───────────────────────────────────────────────────────────────────

function dagenKaart(w) {
  const d = w.dagen;
  const laag = Math.min(...d.map((x) => x.temp_min ?? Infinity));
  const hoog = Math.max(...d.map((x) => x.temp_max ?? -Infinity));
  const plek = (t) => ((t - laag) / Math.max(hoog - laag, 1)) * 100;
  const rij = (x, i) => {
    const zon = uren(x.zon_s);
    const details = [
      ["Zon op en onder", x.zon_op ? `${klok(x.zon_op)} – ${klok(x.zon_onder)}` : null],
      ["Zon", zon != null ? `${getal(zon, 1)} <small>uur</small>` : null],
      ["Neerslag", x.neerslag != null ? `${getal(x.neerslag, 1)} <small>mm</small>${x.neerslagkans != null ? ` <small>· kans ${x.neerslagkans}%</small>` : ""}` : null],
      ["Wind", x.wind != null ? `${beaufort(x.wind)} <small>Bft ${esc(richtingLang(x.windrichting))} · stoten ${getal(x.windstoten, 0)} km/u</small>` : null],
      ["UV-index", x.uv != null ? `${getal(x.uv, 0)} <small>${uvNaam(x.uv)}</small>` : null],
      ["Graaddagen", x.graaddagen != null ? getal(x.graaddagen, 1) : null],
      ["Gas (geschat)", x.gas_m3 != null ? `${hoeveelheid(x.gas_m3)} <small>m³${x.gas_kosten != null ? ` · ${euro(x.gas_kosten)}` : ""}</small>` : null],
    ].filter(([, v]) => v != null);
    const nat = (x.neerslag ?? 0) >= 0.2;
    return `<details class="dagrij">
      <summary>
        <span class="dag-naam">${esc(dagLabel(x.datum, i))}</span>
        <span class="dag-icoon" title="${esc(weerNaam(x.weercode))}">${weerSvg(x.weercode)}<span class="verborgen">${esc(weerNaam(x.weercode))}</span></span>
        <span class="dag-regen${nat ? " nat" : ""}">${nat ? `${getal(x.neerslag, 1)} mm` : ""}</span>
        <span class="dag-min">${graden(x.temp_min)}</span>
        <span class="bereik" aria-hidden="true"><i style="left:${plek(x.temp_min)}%;right:${100 - plek(x.temp_max)}%"></i>${i === 0 && w.nu.temperatuur != null ? `<b style="left:${plek(w.nu.temperatuur)}%"></b>` : ""}</span>
        <span class="dag-max">${graden(x.temp_max)}</span>
        <span class="dag-wind" title="${esc(`${windNaam(x.wind)}, ${richtingLang(x.windrichting)}`)}">${windPijl(x.windrichting)}${beaufort(x.wind) ?? "–"}</span>
      </summary>
      <dl class="gegevens">${details.map(([l, v]) => `<dt>${esc(l)}</dt><dd>${v}</dd>`).join("")}</dl>
    </details>`;
  };
  return kaart({
    titel: "Komende 7 dagen",
    sub: "tik op een dag voor meer",
    klasse: "b-7",
    id: "k-dagen",
    inhoud: `<div class="dagen">${d.map(rij).join("")}</div>`,
  });
}

// ── weer en energie ───────────────────────────────────────────────────────────

function energieKaart(w) {
  const g = w.gas;
  const d = w.dagen;
  const zonWind = zonEnWind(d);
  if (!g) {
    return kaart({
      titel: "Weer en je energie",
      klasse: "b-5",
      id: "k-weer-energie",
      inhoud: `${leeg("Nog geen schatting van je gasverbruik: daarvoor zijn minstens tien dagen meterdata nodig.")}
        <p class="kaart-voet"><a href="#/koppelingen">Koppel Frank Energie</a> voor je verbruik per dag.</p>${zonWind}`,
    });
  }
  const week = d.reduce((s, x) => s + (x.gas_m3 ?? 0), 0);
  const kosten = d.every((x) => x.gas_kosten != null) ? d.reduce((s, x) => s + x.gas_kosten, 0) : null;
  const max = Math.max(...d.map((x) => x.gas_m3 ?? 0), 0.1);
  const koudste = d.reduce((a, x) => ((x.graaddagen ?? -1) > (a.graaddagen ?? -1) ? x : a), d[0]);
  return kaart({
    titel: "Weer en je energie",
    sub: "geschat uit je eigen meterdata",
    klasse: "b-5",
    id: "k-weer-energie",
    inhoud: `<div class="netto"><div class="groot">±${hoeveelheid(week)}<small>m³ gas</small></div>
        <span class="verschil">${kosten != null ? `${euro(kosten)} · ` : ""}komende 7 dagen</span></div>
      <div class="gasdagen" role="img" aria-label="${esc(`Verwacht gas per dag: ${d.map((x, i) => `${dagLabel(x.datum, i)} ${hoeveelheid(x.gas_m3)} m³`).join(", ")}`)}">
        ${d.map((x, i) => `<div class="gasdag"><span class="m3">${hoeveelheid(x.gas_m3)}</span><i style="height:${((x.gas_m3 ?? 0) / max) * 100}%"></i><span class="naam">${esc(i === 0 ? "vandaag" : DAG.format(middag(x.datum)).split(" ")[0])}</span></div>`).join("")}
      </div>
      <p class="zacht klein">Je verbruikt ongeveer ${hoeveelheid(g.basis_m3)} m³ per dag voor warm water en koken, plus ${hoeveelheid(g.per_graaddag_m3)} m³ per graaddag voor de verwarming (uit ${g.dagen} dagen meterdata).${koudste?.graaddagen > 0 ? ` Het koudst wordt ${esc(dagLabel(koudste.datum, d.indexOf(koudste)).toLowerCase())}, met ${getal(koudste.graaddagen, 1)} graaddagen.` : ""}</p>
      ${zonWind}`,
  });
}

/** Veel wind of zon: dan is stroom vaak goedkoop. Alleen de komende drie dagen, alleen als het opvalt. */
function zonEnWind(dagen) {
  const opvallend = dagen.slice(0, 3).filter((x) => (x.zon_s ?? 0) >= 6 * 3600 || beaufort(x.wind) >= 5);
  if (!opvallend.length) return "";
  const x = opvallend[0];
  const i = dagen.indexOf(x);
  const delen = [(x.zon_s ?? 0) >= 6 * 3600 ? `${getal(uren(x.zon_s), 0)} uur zon` : null, beaufort(x.wind) >= 5 ? `${windNaam(x.wind)} wind (${beaufort(x.wind)} Bft)` : null].filter(Boolean);
  return melding(`${esc(dagLabel(x.datum, i))} ${esc(delen.join(" en "))}: dan is stroom vaak goedkoop, soms zelfs negatief. <a href="#/prijzen">Bekijk de prijzen</a>`, "", "zon");
}
