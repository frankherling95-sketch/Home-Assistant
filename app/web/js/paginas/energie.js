// Energie: stroom, teruglevering, gas, laden, kosten en temperatuur per dag/week/maand/jaar.

import {
  $, $$, api, css, datumKort, datumLang, esc, euro, getal, hoeveelheid, icoon, klok, plusDagen, plusJaren,
  plusMaanden, vandaag, weekdag,
} from "../basis.js";
import { basis, gekleurd, grafiek, lijn, markering, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, melding, skeletKaart, totalenTabel } from "../onderdelen.js";

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

export async function toon(main, params, ctx) {
  const soort = SOORTEN[params.get("p")] ? params.get("p") : "dag";
  const v = vandaag();
  const d = /^\d{4}-\d{2}-\d{2}$/.test(params.get("d") || "") ? params.get("d") : v;
  const weergave = params.get("w") === "tabel" ? "tabel" : "grafiek";
  const ga = (extra) => ctx.navigeer("energie", { p: soort, d, w: weergave === "tabel" ? "tabel" : "", ...extra });

  const bevatVandaag = begin(soort, d) === begin(soort, v);
  const volgendeKan = verschuif(soort, d, 1) <= v;

  if (ctx.nieuw || !$(".werkbalk", main)) {
    main.innerHTML = `<div class="werkbalk"></div><div class="raster" id="energie-inhoud">
      ${skeletKaart("b-12", { titel: "Elektriciteit", grafiek: true })}
      ${skeletKaart("b-6", { titel: "Gas", grafiek: true })}${skeletKaart("b-6", { titel: "Laden", grafiek: true })}
    </div>`;
  } else {
    $("#energie-inhoud").style.opacity = "0.55";
  }
  const balk = $(".werkbalk", main);
  balk.innerHTML = `
    <div class="segment" role="group" aria-label="Periode">
      ${Object.entries(SOORTEN).map(([k, n]) => `<button type="button" data-soort="${k}" aria-pressed="${k === soort}">${n}</button>`).join("")}
    </div>
    <div class="datumnav">
      <button class="icoonknop" type="button" data-stap="-1" aria-label="Vorige ${SOORTEN[soort].toLowerCase()}">${icoon("vorige")}</button>
      <span class="label" aria-live="polite">${esc(label(soort, d))}</span>
      <button class="icoonknop" type="button" data-stap="1" aria-label="Volgende ${SOORTEN[soort].toLowerCase()}" ${volgendeKan ? "" : "disabled"}>${icoon("volgende")}</button>
    </div>
    <div class="rechts">
      <button class="knop" type="button" data-vandaag ${bevatVandaag ? "disabled" : ""}>Vandaag</button>
      <div class="segment" role="group" aria-label="Weergave">
        <button type="button" data-weergave="grafiek" aria-pressed="${weergave === "grafiek"}">Grafiek</button>
        <button type="button" data-weergave="tabel" aria-pressed="${weergave === "tabel"}">Tabel</button>
      </div>
    </div>`;
  for (const b of $$("[data-soort]", balk)) b.onclick = () => ga({ p: b.dataset.soort, d: bevatVandaag ? v : begin(b.dataset.soort, d) });
  for (const b of $$("[data-stap]", balk)) b.onclick = () => ga({ d: verschuif(soort, d, Number(b.dataset.stap)) });
  $("[data-vandaag]", balk).onclick = () => ga({ d: v });
  for (const b of $$("[data-weergave]", balk)) b.onclick = () => ga({ w: b.dataset.weergave === "tabel" ? "tabel" : "" });

  const data = soort === "dag" ? await api(`dag?datum=${d}`) : await api(`periode?type=${soort}&datum=${d}`);
  if (!ctx.actueel()) return;
  const r = normaliseer(soort, data);
  ruimOp();
  const inhoud = $("#energie-inhoud");
  inhoud.style.opacity = "";
  const geenMeter = r.reeksen.stroom.every((x) => x == null || x === 0) && r.reeksen.gas.every((x) => x == null || x === 0);
  const waarschuwing = geenMeter
    ? `<div class="b-12">${melding("Nog geen meterdata voor deze periode. Frank Energie levert het verbruik met ongeveer een dag vertraging.")}</div>`
    : "";
  const totalen = kaart({
    titel: "Totalen",
    sub: r.label,
    klasse: "b-12",
    id: "k-totalen",
    inhoud: totalenTabel(r.totalen, r.vorige, r.vorigeLabel),
  });

  if (weergave === "tabel") {
    inhoud.innerHTML = `${waarschuwing}${kaart({ titel: `Per ${r.eenheid}`, sub: r.label, klasse: "b-12", inhoud: tabel(r) })}${totalen}`;
    return;
  }
  const t = r.totalen;
  inhoud.innerHTML = `${waarschuwing}
    ${kaart({
      titel: "Elektriciteit",
      klasse: "b-12",
      id: "k-elek",
      rechts: `<span class="pil">${euro(t.stroom.kosten + t.teruglevering.kosten)}</span>`,
      inhoud: `<div class="grafiek hoog" id="g-elek" role="img" aria-label="Stroom per ${r.eenheid}"></div>
        <div class="legenda">
          <span><i style="background:var(--c-stroom)"></i>Afgenomen ${hoeveelheid(t.stroom.hoeveelheid)} kWh</span>
          <span><i style="background:var(--c-terug)"></i>Teruggeleverd ${hoeveelheid(t.teruglevering.hoeveelheid)} kWh</span>
        </div>`,
    })}
    ${kaart({ titel: "Gas", klasse: "b-6", id: "k-gas", rechts: `<span class="pil">${hoeveelheid(t.gas.hoeveelheid)} m³</span>`, inhoud: '<div class="grafiek" id="g-gas"></div>' })}
    ${kaart({ titel: "Laden", klasse: "b-6", id: "k-laden", rechts: `<span class="pil">${hoeveelheid(t.laden.hoeveelheid)} kWh</span>`, inhoud: '<div class="grafiek" id="g-laden"></div>' })}
    ${kaart({ titel: r.kostenTitel, klasse: "b-6", id: "k-kosten", inhoud: '<div class="grafiek" id="g-kosten"></div>' })}
    ${kaart({
      titel: "Temperatuur",
      klasse: "b-6",
      id: "k-temp",
      sub: "gemiddeld, Open-Meteo",
      inhoud: r.reeksen.temperatuur.some((x) => x != null) ? '<div class="grafiek" id="g-temp"></div>' : leeg("Geen temperatuur voor deze periode."),
    })}
    ${totalen}`;
  tekenen(r);
}

function label(soort, d) {
  const b = begin(soort, d);
  if (soort === "dag") return d === vandaag() ? `Vandaag, ${datumLang(d)}` : datumLang(d);
  if (soort === "week") {
    const e = plusDagen(b, 6);
    return `${datumKort(b)} – ${datumKort(e)} ${e.slice(0, 4)}`;
  }
  if (soort === "maand") return `${MAANDEN[Number(b.slice(5, 7)) - 1]} ${b.slice(0, 4)}`;
  return b.slice(0, 4);
}

function normaliseer(soort, data) {
  if (soort === "dag") {
    const nu = Date.now();
    const i = data.uren.findIndex((u) => new Date(u) <= nu && nu < +new Date(u) + 3600e3);
    return {
      labels: data.uren.map(klok),
      titels: data.uren.map((u) => `${klok(u)}–${klok(+new Date(u) + 3600e3)}`),
      reeksen: { ...data.reeksen, kosten: data.reeksen.kosten_stroom },
      totalen: data.totalen,
      vorige: null,
      label: datumLang(data.datum),
      kostenTitel: "Stroomkosten per uur",
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
    kostenTitel: soort === "jaar" ? "Kosten per maand" : "Kosten per dag",
    eenheid: soort === "jaar" ? "maand" : "dag",
    nu: i >= 0 ? i : null,
    dag: false,
  };
}

function tekenen(r) {
  const as = (extra = {}) => ({
    data: r.labels,
    axisLabel: r.dag ? { interval: (i, w) => Number(w.slice(0, 2)) % 3 === 0 && w.endsWith(":00") } : {},
    ...extra,
  });
  const nu = r.nu != null ? markering(r.labels[r.nu], r.dag ? "nu" : "vandaag") : undefined;
  const tip = (eenheid, maak) => ({
    formatter: (punten) => `<b style="font-weight:500">${r.titels[punten[0].dataIndex]}</b>${punten.map(maak || ((p) => regel(p.color, p.seriesName, p.value == null ? "–" : `${hoeveelheid(Math.abs(p.value))} ${eenheid}`))).join("")}`,
  });
  const k = { stroom: css("--c-stroom"), terug: css("--c-terug"), gas: css("--c-gas"), laden: css("--c-laden"), prijs: css("--c-prijs"), temp: css("--c-temp") };

  grafiek(document.getElementById("g-elek")).setOption(
    basis({
      xAxis: as(),
      tooltip: tip("kWh"),
      series: [
        staven("Afgenomen", r.reeksen.stroom, k.stroom, { stapel: "e", markLine: nu }),
        staven("Teruggeleverd", r.reeksen.teruglevering.map((x) => (x == null ? null : -x)), k.terug, { stapel: "e", negatief: true }),
      ],
    }),
  );
  grafiek(document.getElementById("g-gas")).setOption(
    basis({ xAxis: as(), tooltip: tip("m³"), series: [staven("Gas", r.reeksen.gas, k.gas, { markLine: nu })] }),
  );
  grafiek(document.getElementById("g-laden")).setOption(
    basis({ xAxis: as(), tooltip: tip("kWh"), series: [staven("Laden", r.reeksen.laden, k.laden, { markLine: nu })] }),
  );
  grafiek(document.getElementById("g-kosten")).setOption(
    basis({
      xAxis: as(),
      yAxis: { axisLabel: { formatter: (w) => `€${getal(w, Math.abs(w) < 10 ? 2 : 0)}` } },
      tooltip: tip("", (p) => regel(p.color, p.value < 0 ? "Opbrengst" : "Kosten", euro(p.value == null ? null : Math.abs(p.value)))),
      series: [
        staven("Kosten", r.reeksen.kosten.map((x) => (x == null ? null : gekleurd(x, x < 0 ? k.terug : k.prijs))), k.prijs, { markLine: nu }),
      ],
    }),
  );
  const temp = document.getElementById("g-temp");
  if (temp) {
    grafiek(temp).setOption(
      basis({
        xAxis: as({ boundaryGap: !r.dag }),
        yAxis: { scale: true, axisLabel: { formatter: (w) => `${w}°` } },
        tooltip: { ...tip("°C", (p) => regel(p.color, "Temperatuur", p.value == null ? "–" : `${getal(p.value, 1)} °C`)), axisPointer: { type: "line", lineStyle: { color: css("--lijn-sterk") } } },
        series: [lijn("Temperatuur", r.reeksen.temperatuur, k.temp, { markLine: nu })],
      }),
    );
  }
}

function tabel(r) {
  const c = (x, d = null) => (x == null ? "–" : d == null ? hoeveelheid(x) : getal(x, d));
  const rijen = r.labels
    .map((_, i) => {
      const s = r.reeksen;
      return `<tr><td>${r.titels[i]}</td><td>${c(s.stroom[i])}</td><td>${c(s.teruglevering[i])}</td><td>${c(s.gas[i])}</td>
        <td>${c(s.laden[i])}</td><td>${s.kosten[i] == null ? "–" : euro(s.kosten[i])}</td><td>${c(s.temperatuur[i], 1)}</td></tr>`;
    })
    .join("");
  return `<div class="tabel-wrap"><table class="tabel">
    <thead><tr><th>${r.dag ? "Uur" : r.eenheid === "maand" ? "Maand" : "Dag"}</th><th>Afgenomen (kWh)</th><th>Teruggeleverd (kWh)</th>
      <th>Gas (m³)</th><th>Laden (kWh)</th><th>${r.dag ? "Stroomkosten" : "Kosten"}</th><th>Temp. (°C)</th></tr></thead>
    <tbody>${rijen}</tbody></table></div>`;
}
