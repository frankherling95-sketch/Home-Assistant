// Energie: stroom, teruglevering, gas, laden, kosten en temperatuur per dag/week/maand/jaar.

import {
  $, $$, api, css, datumKort, datumLang, esc, euro, getal, hoeveelheid, icoon, klok, plusDagen, plusJaren,
  plusMaanden, vandaag, weekdag,
} from "../basis.js";
import { basis, grafiek, lijn, markering, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, melding, skeletKaart, stromen, totalenTabel } from "../onderdelen.js";

const SOORTEN = { dag: "Dag", week: "Week", maand: "Maand", jaar: "Jaar" };
const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];

/** Eerste dag van de periode waar `d` in valt. */
function begin(soort, d) {
  if (soort === "week") return plusDagen(d, -weekdag(d));
  if (soort === "maand") return `${d.slice(0, 7)}-01`;
  if (soort === "jaar") return `${d.slice(0, 4)}-01-01`;
  return d;
}

function verschuif(soort, d, n) {
  if (soort === "week") return plusDagen(begin(soort, d), 7 * n);
  if (soort === "maand") return plusMaanden(d, n);
  if (soort === "jaar") return plusJaren(d, n);
  return plusDagen(d, n);
}

/**
 * De gegevens van de periode, met de vorige periode om mee te vergelijken. Zonder gekozen dag is
 * de standaarddag de laatste dag met meterdata: de slimme meter komt via Frank met een dag vertraging.
 */
async function haal(soort, gekozen) {
  const v = vandaag();
  if (soort !== "dag") return { d: gekozen || v, data: await api(`periode?type=${soort}&datum=${gekozen || v}`) };
  let d = gekozen || v;
  let [data, ervoor] = await Promise.all([api(`dag?datum=${d}`), api(`dag?datum=${plusDagen(d, -1)}`)]);
  if (!gekozen && !data.compleet.verbruik) {
    d = plusDagen(v, -1);
    [data, ervoor] = [ervoor, await api(`dag?datum=${plusDagen(d, -1)}`)];
  }
  return { d, data, ervoor };
}

export async function toon(main, params, ctx) {
  const soort = SOORTEN[params.get("p")] ? params.get("p") : "dag";
  const v = vandaag();
  const gekozen = /^\d{4}-\d{2}-\d{2}$/.test(params.get("d") || "") ? params.get("d") : null;

  if (ctx.nieuw || !$(".werkbalk", main)) {
    main.innerHTML = `<div class="werkbalk"></div><div class="raster" id="energie-inhoud">
      <div class="b-12 kpi-rij">${skeletKaart("kpi", { regels: 2 }).repeat(4)}</div>
      ${skeletKaart("b-12", { titel: "Elektriciteit", grafiek: true })}
      ${skeletKaart("b-6", { titel: "Gas en temperatuur", grafiek: true })}${skeletKaart("b-6", { titel: "Kosten", grafiek: true })}
    </div>`;
  } else {
    $("#energie-inhoud").style.opacity = "0.55";
  }
  // De werkbalk staat er meteen; het label volgt als bekend is welke dag het wordt.
  const balk = $(".werkbalk", main);
  const werkbalk = (d) => {
    const ga = (extra) => ctx.navigeer("energie", { p: soort, d, ...extra });
    balk.innerHTML = `
      <div class="segment" role="group" aria-label="Periode">
        ${Object.entries(SOORTEN).map(([k, n]) => `<button type="button" data-soort="${k}" aria-pressed="${k === soort}">${n}</button>`).join("")}
      </div>
      <div class="datumnav">
        <button class="icoonknop" type="button" data-stap="-1" aria-label="Vorige ${SOORTEN[soort].toLowerCase()}" ${d ? "" : "disabled"}>${icoon("vorige")}</button>
        <span class="label" aria-live="polite">${d ? esc(label(soort, d)) : ""}</span>
        <button class="icoonknop" type="button" data-stap="1" aria-label="Volgende ${SOORTEN[soort].toLowerCase()}" ${d && verschuif(soort, d, 1) <= v ? "" : "disabled"}>${icoon("volgende")}</button>
      </div>
      <p class="werkbalk-uitleg">Meterdata loopt een dag achter (Frank Energie)</p>`;
    // Een andere periodesoort: de periode van de gekozen dag; zonder keuze de standaard.
    for (const b of $$("[data-soort]", balk)) b.onclick = () => ctx.navigeer("energie", { p: b.dataset.soort, d: gekozen ? begin(b.dataset.soort, gekozen) : "" });
    if (d) for (const b of $$("[data-stap]", balk)) b.onclick = () => ga({ d: verschuif(soort, d, Number(b.dataset.stap)) });
  };
  if (ctx.nieuw || !balk.childElementCount) werkbalk(gekozen);

  const { d, data, ervoor } = await haal(soort, gekozen);
  if (!ctx.actueel()) return;
  werkbalk(d);
  const r = normaliseer(soort, data, ervoor);
  ruimOp();
  const inhoud = $("#energie-inhoud");
  inhoud.style.opacity = "";
  const geenMeter = r.reeksen.stroom.every((x) => x == null || x === 0) && r.reeksen.gas.every((x) => x == null || x === 0);
  const t = r.totalen;
  const temperatuur = r.reeksen.temperatuur.filter((x) => x != null);

  inhoud.innerHTML = `
    ${geenMeter ? `<div class="b-12">${melding("Nog geen meterdata voor deze periode. Frank Energie levert het verbruik met ongeveer een dag vertraging.")}</div>` : ""}
    <div class="b-12 kpi-rij">${kpis(t, r.vorige, geenMeter)}</div>
    ${kaart({
      titel: "Elektriciteit",
      sub: "afname boven de lijn, teruglevering eronder",
      klasse: "b-12",
      id: "k-elek",
      rechts: legenda([["--c-stroom", "Afgenomen"], ["--c-laden", "waarvan laden"], ["--c-terug", "Teruggeleverd"]]),
      inhoud: `<div class="grafiek" id="g-elek" role="img" aria-label="Afgenomen en teruggeleverde stroom per ${r.eenheid}, met het deel voor laden"></div>`,
    })}
    ${kaart({
      titel: "Gas en temperatuur",
      klasse: "b-6",
      id: "k-gas",
      rechts: legenda([["--c-gas", "Gas m³"], ["--c-temp", "Buiten °C", "lijn"]], temperatuur.length ? `${getal(Math.min(...temperatuur), 0)}° – ${getal(Math.max(...temperatuur), 0)}°` : ""),
      inhoud: `<div class="grafiek" id="g-gas" role="img" aria-label="Gasverbruik per ${r.eenheid} met de buitentemperatuur"></div>`,
    })}
    ${kaart({
      titel: "Kosten",
      sub: `per ${r.eenheid}`,
      klasse: "b-6",
      id: "k-kosten",
      rechts: legenda([["--c-stroom", "Stroom"], ["--c-gas", "Gas"]]),
      inhoud: `<div class="grafiek" id="g-kosten" role="img" aria-label="Kosten van stroom en gas per ${r.eenheid}"></div>`,
    })}
    ${kaart({ titel: "Energiestromen", sub: r.label, klasse: "b-5", id: "k-stromen", inhoud: stromen(t) })}
    ${kaart({
      titel: "Totalen",
      sub: r.vorige && r.vorigeLabel ? `t.o.v. ${r.vorigeLabel}` : r.label,
      klasse: "b-7",
      id: "k-totalen",
      inhoud: totalenTabel(t, r.vorige, r.vorigeLabel),
    })}`;
  tekenen(r);
}

function label(soort, d) {
  const b = begin(soort, d);
  if (soort === "dag") {
    const v = vandaag();
    return d === v ? `vandaag, ${datumLang(d)}` : d === plusDagen(v, -1) ? `gisteren, ${datumLang(d)}` : datumLang(d);
  }
  if (soort === "week") {
    const e = plusDagen(b, 6);
    return `${datumKort(b)} – ${datumKort(e)} ${e.slice(0, 4)}`;
  }
  if (soort === "maand") return `${MAANDEN[Number(b.slice(5, 7)) - 1]} ${b.slice(0, 4)}`;
  return b.slice(0, 4);
}

function normaliseer(soort, data, ervoor) {
  if (soort === "dag") {
    const nu = Date.now();
    const i = data.uren.findIndex((u) => new Date(u) <= nu && nu < +new Date(u) + 3600e3);
    const vorige = ervoor?.compleet.verbruik ? ervoor.totalen : null;
    return {
      labels: data.uren.map(klok),
      titels: data.uren.map((u) => `${klok(u)}–${klok(+new Date(u) + 3600e3)}`),
      reeksen: data.reeksen,
      totalen: data.totalen,
      vorige,
      vorigeLabel: vorige ? datumLang(ervoor.datum) : "",
      label: datumLang(data.datum),
      eenheid: "uur",
      nu: i >= 0 ? i : null,
      dag: true,
    };
  }
  const v = vandaag();
  const i = data.bakjes.findIndex((b) => (soort === "jaar" ? v.startsWith(b) : b === v));
  return {
    labels: data.bakje_labels,
    titels: data.bakjes.map((b) => (soort === "jaar" ? `${MAANDEN[Number(b.slice(5, 7)) - 1]} ${b.slice(0, 4)}` : datumLang(b))),
    reeksen: data.reeksen,
    totalen: data.totalen,
    vorige: data.vorige,
    vorigeLabel: data.vorige_label,
    label: data.label,
    eenheid: soort === "jaar" ? "maand" : "dag",
    nu: i >= 0 ? i : null,
    dag: false,
  };
}

/** Legenda in de kop van een kaart; `soort` "lijn" voor een lijnreeks, met optioneel een regel eronder. */
const legenda = (items, onder = "") =>
  `<div class="legenda kop-legenda">${items.map(([k, n, soort]) => `<span><i class="${soort || ""}" style="background:var(${k})"></i>${esc(n)}</span>`).join("")}${onder ? `<span class="onder">${esc(onder)}</span>` : ""}</div>`;

/** Verschil met de vorige periode. Bij verbruik en kosten is minder goed en ≥10% meer let op. */
function verschil(nu, toen, { zuinig = true } = {}) {
  if (!toen || nu == null) return "";
  const r = nu / toen - 1;
  if (!Number.isFinite(r)) return "";
  const kleur = !zuinig ? "" : r < -0.005 ? "tekst-goed" : r >= 0.1 ? "tekst-let-op" : "";
  return ` · <span class="${kleur}">${r > 0 ? "+" : r < 0 ? "−" : ""}${getal(Math.abs(r) * 100, 0)}%</span>`;
}

function kpis(t, vorige, geenMeter) {
  const netto = (x) => x.stroom.kosten + x.gas.kosten + x.teruglevering.kosten;
  const kaartje = (kleur, naam, waarde, eenheid, sub) => `<section class="kpi">
      <h2 class="kpi-naam"><i style="background:var(${kleur})"></i>${naam}</h2>
      <div class="kpi-waarde">${waarde}${eenheid ? ` <small>${eenheid}</small>` : ""}</div>
      <div class="kpi-sub">${sub}</div>
    </section>`;
  if (geenMeter) {
    return [["--c-stroom", "Afgenomen"], ["--c-terug", "Teruggeleverd"], ["--c-gas", "Gas"], ["--inkt-3", "Netto kosten"]]
      .map(([k, n]) => kaartje(k, n, "–", "", "nog geen meterdata")).join("");
  }
  const v = vorige || null;
  return [
    kaartje("--c-stroom", "Afgenomen", hoeveelheid(t.stroom.hoeveelheid), "kWh", `${euro(t.stroom.kosten)}${verschil(t.stroom.hoeveelheid, v?.stroom.hoeveelheid)}`),
    kaartje("--c-terug", "Teruggeleverd", hoeveelheid(t.teruglevering.hoeveelheid), "kWh", `${euro(t.teruglevering.kosten)}${verschil(t.teruglevering.hoeveelheid, v?.teruglevering.hoeveelheid, { zuinig: false })}`),
    kaartje("--c-gas", "Gas", hoeveelheid(t.gas.hoeveelheid), "m³", `${euro(t.gas.kosten)}${verschil(t.gas.hoeveelheid, v?.gas.hoeveelheid)}`),
    kaartje("--inkt-3", "Netto kosten", euro(netto(t)), "", `waarvan laden ${euro(t.laden.kosten)}${verschil(netto(t), v ? netto(v) : null)}`),
  ].join("");
}

function tekenen(r) {
  const as = (extra = {}) => ({
    data: r.labels,
    axisLabel: r.dag ? { interval: (i, w) => Number(w.slice(0, 2)) % 3 === 0 && w.endsWith(":00") } : {},
    ...extra,
  });
  const nu = r.nu != null ? markering(r.labels[r.nu], r.dag ? "nu" : "vandaag") : undefined;
  const titel = (i) => `<b style="font-weight:500">${r.titels[i]}</b>`;
  const k = { stroom: css("--c-stroom"), terug: css("--c-terug"), gas: css("--c-gas"), laden: css("--c-laden"), temp: css("--c-temp") };
  const s = r.reeksen;
  const waarde = (x, eenheid) => (x == null ? "–" : `${hoeveelheid(x)} ${eenheid}`);

  // Afname boven de nullijn met het laaddeel als onderste stuk; teruglevering eronder.
  const laden = s.stroom.map((x, i) => (x == null ? null : Math.min(s.laden[i] ?? 0, x)));
  const rest = s.stroom.map((x, i) => (x == null ? null : x - laden[i]));
  grafiek(document.getElementById("g-elek")).setOption(
    basis({
      xAxis: as(),
      yAxis: { axisLabel: { formatter: (w) => `${getal(w, Math.abs(w) < 10 ? 1 : 0)}` } },
      tooltip: {
        formatter: ([p]) => {
          const i = p.dataIndex;
          return `${titel(i)}${regel(k.stroom, "Afgenomen", waarde(s.stroom[i], "kWh"))}${regel(k.laden, "waarvan laden", waarde(s.laden[i], "kWh"))}${regel(k.terug, "Teruggeleverd", waarde(s.teruglevering[i], "kWh"))}`;
        },
      },
      series: [
        staven("waarvan laden", laden, k.laden, { stapel: "e", markLine: nu, itemStyle: { color: k.laden, borderRadius: 0, shadowBlur: 0 } }),
        staven("Afgenomen", rest, k.stroom, { stapel: "e" }),
        staven("Teruggeleverd", s.teruglevering.map((x) => (x == null ? null : -x)), k.terug, { stapel: "e", negatief: true }),
      ],
    }),
  );

  const temperatuur = s.temperatuur.some((x) => x != null);
  grafiek(document.getElementById("g-gas")).setOption(
    basis({
      xAxis: as(),
      yAxis: [
        { type: "value", splitNumber: 4, splitLine: { lineStyle: { color: css("--lijn") } }, axisLabel: { color: css("--inkt-3"), fontSize: 12, formatter: (w) => getal(w, w < 10 ? 1 : 0) } },
        { type: "value", scale: true, show: temperatuur, splitLine: { show: false }, axisLabel: { color: css("--inkt-3"), fontSize: 12, formatter: (w) => `${w}°` } },
      ],
      tooltip: {
        formatter: ([p]) => {
          const i = p.dataIndex;
          return `${titel(i)}${regel(k.gas, "Gas", waarde(s.gas[i], "m³"))}${temperatuur ? regel(k.temp, "Buiten", s.temperatuur[i] == null ? "–" : `${getal(s.temperatuur[i], 1)} °C`) : ""}`;
        },
      },
      series: [
        staven("Gas", s.gas, k.gas, { markLine: nu }),
        ...(temperatuur ? [lijn("Buiten", s.temperatuur, k.temp, { yAxisIndex: 1, smooth: true, lineStyle: { color: k.temp, width: 1.5 } })] : []),
      ],
    }),
  );

  const stroomKosten = s.kosten_stroom;
  grafiek(document.getElementById("g-kosten")).setOption(
    basis({
      xAxis: as(),
      yAxis: { axisLabel: { formatter: (w) => `€ ${getal(w, Math.abs(w) < 10 ? 2 : 0)}` } },
      tooltip: {
        formatter: ([p]) => {
          const i = p.dataIndex;
          const st = stroomKosten[i];
          const g = s.kosten_gas[i];
          return `${titel(i)}${regel(k.stroom, st < 0 ? "Stroom (opbrengst)" : "Stroom", euro(st == null ? null : Math.abs(st)))}${regel(k.gas, "Gas", euro(g))}`;
        },
      },
      series: [
        staven("Stroom", stroomKosten, k.stroom, { stapel: "k", markLine: nu, itemStyle: { color: k.stroom, borderRadius: 0, shadowBlur: 0 } }),
        staven("Gas", s.kosten_gas, k.gas, { stapel: "k" }),
      ],
    }),
  );
}
