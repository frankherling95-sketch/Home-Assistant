// Thuis — web-app. Leest alles uit de eigen API (/api/...); inloggen regelt IAP vóór Cloud Run.
"use strict";

const TZ = "Europe/Amsterdam";
const css = (naam) => getComputedStyle(document.documentElement).getPropertyValue(naam).trim();
const $ = (sel) => document.querySelector(sel);

const fmt = {
  getal: (v, d = 2) => (v ?? 0).toLocaleString("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d }),
  euro: (v) => (v ?? 0).toLocaleString("nl-NL", { style: "currency", currency: "EUR" }),
  prijs: (v) => (v == null ? "–" : `€ ${fmt.getal(v, 3)}`),
  uur: (iso) => new Date(iso).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit", timeZone: TZ }),
  dag: (d) => d.toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "short", timeZone: TZ }),
  iso: (d) => d.toLocaleDateString("sv-SE", { timeZone: TZ }), // YYYY-MM-DD
};

const STATUS = {
  laden: "Laden", wacht_op_start: "Wacht op start", klaar_om_te_laden: "Klaar om te laden",
  niet_verbonden: "Geen auto", klaar: "Klaar", offline: "Offline", fout: "Fout",
  wacht_op_smart_start: "Wacht (smart)", wacht_op_schema: "Wacht (schema)",
};
const REDEN = {
  gepland: "Gepland", onder_drempel: "Onder prijsdrempel", wachten: "Wacht op goedkoop blok",
  doel_bereikt: "Doel bereikt", geen_prijzen: "Geen prijzen", uitgeschakeld: "Uit",
};

const staat = { tab: "samenvatting", datum: new Date(), grafieken: {} };

async function api(pad, opties = {}) {
  const r = await fetch(`api/${pad}`, { headers: { "content-type": "application/json" }, ...opties });
  if (!r.ok) throw new Error(`${pad}: HTTP ${r.status}`);
  return r.json();
}

function melding(tekst) {
  const el = $("#melding");
  el.hidden = !tekst;
  el.textContent = tekst || "";
}

// ── grafieken ────────────────────────────────────────────────────────────────

function grafiek(id) {
  if (!staat.grafieken[id]) staat.grafieken[id] = echarts.init(document.getElementById(id));
  return staat.grafieken[id];
}

function basis(extra = {}) {
  const tekst = css("--zacht"), lijn = css("--lijn");
  return {
    animationDuration: 300,
    grid: { left: 44, right: 12, top: 28, bottom: 28 },
    tooltip: { trigger: "axis", backgroundColor: css("--kaart"), borderColor: lijn, textStyle: { color: css("--tekst") } },
    legend: { top: 0, textStyle: { color: tekst }, itemWidth: 12, itemHeight: 12 },
    xAxis: { type: "time", axisLabel: { color: tekst, hideOverlap: true, formatter: (v) => fmt.uur(v) },
             axisLine: { lineStyle: { color: lijn } }, splitLine: { show: false } },
    yAxis: { type: "value", axisLabel: { color: tekst }, splitLine: { lineStyle: { color: lijn } } },
    ...extra,
  };
}

const balken = (naam, uren, waarden, kleur, extra = {}) => ({
  name: naam, type: "bar", stack: extra.stack, barMaxWidth: 22, itemStyle: { color: kleur, borderRadius: 3 },
  data: uren.map((u, i) => [new Date(u).getTime() + 30 * 60e3, waarden[i]]), ...extra,
});

const nuLijn = () => ({
  type: "line", name: "nu", silent: true, data: [],
  markLine: { symbol: "none", label: { show: false }, lineStyle: { color: css("--zacht"), type: "dashed" },
              data: [{ xAxis: Date.now() }] },
});

function prijsReeks(prijzen, kleur, naam = "Prijs") {
  // Stapgrafiek: elk blok (uur of kwartier) houdt zijn prijs tot het volgende.
  const punten = prijzen.flatMap((p) => [[p.van, p.prijs], [p.tot, p.prijs]]);
  return { name: naam, type: "line", symbol: "none", data: punten, itemStyle: { color: kleur },
           lineStyle: { color: kleur, width: 2 }, areaStyle: { color: kleur, opacity: 0.12 } };
}

// ── samenvatting ─────────────────────────────────────────────────────────────

function toonTotalen(t) {
  const rijen = [
    ["Stroom afgenomen", t.stroom, css("--c-stroom")],
    ["Teruggeleverd", t.teruglevering, css("--c-terug")],
    ["Gas", t.gas, css("--c-gas")],
    ["Laden", t.laden, css("--c-laden")],
  ];
  const kosten = t.stroom.kosten + t.teruglevering.kosten + t.gas.kosten;
  $("#totalen").innerHTML =
    `<tr><th></th><th>Bron</th><th>Energie</th><th>Kosten</th></tr>` +
    rijen.map(([naam, r, kleur]) => `<tr>
      <td><span class="stip" style="background:${kleur}33;border-color:${kleur}"></span></td>
      <td>${naam}</td>
      <td>${fmt.getal(r.hoeveelheid)} ${r.eenheid}</td>
      <td>${fmt.euro(r.kosten)}</td></tr>`).join("") +
    `<tr><td></td><td>Totaal</td><td></td><td>${fmt.euro(kosten)}</td></tr>`;
  // Laden zit al in "Stroom afgenomen" en telt daarom niet mee in het totaal.
}

function toonPrijs(dag) {
  const p = dag.prijzen.stroom;
  const reeks = [prijsReeks(p, css("--c-prijs"))];
  if (fmt.iso(staat.datum) === fmt.iso(new Date())) reeks.push(nuLijn());
  grafiek("g-prijs").setOption(basis({ legend: { show: false }, series: reeks,
    yAxis: { type: "value", axisLabel: { color: css("--zacht"), formatter: (v) => `€${v.toFixed(2)}` },
             splitLine: { lineStyle: { color: css("--lijn") } } } }), true);
  const waarden = p.map((x) => x.prijs);
  const laagste = p.reduce((a, b) => (b.prijs < a.prijs ? b : a), p[0] || {});
  $("#prijs-sub").textContent = p.length ? `${p.length > 30 ? "per kwartier" : "per uur"}, all-in` : "";
  $("#prijs-cijfers").innerHTML = p.length ? [
    ["Laagste", `${fmt.prijs(laagste.prijs)} · ${fmt.uur(laagste.van)}`],
    ["Hoogste", fmt.prijs(Math.max(...waarden))],
    ["Gemiddeld", fmt.prijs(waarden.reduce((a, b) => a + b, 0) / waarden.length)],
  ].map(tegel).join("") : `<p class="sub">Nog geen prijzen voor deze dag.</p>`;
}

function tegel([label, waarde, klasse = ""]) {
  return `<div class="tegel"><div class="label">${label}</div><div class="waarde ${klasse}">${waarde}</div></div>`;
}

function toonNu(nu) {
  const { auto, lader, plan } = nu;
  $("#nu-tegels").innerHTML = [
    ["Stroomprijs", fmt.prijs(plan.prijs_nu)],
    ["Accu auto", auto ? `${Math.round(auto.accu_pct)}%` : "–"],
    ["Lader", lader ? STATUS[lader.status] || lader.status : "–"],
    ["Slim laden", plan.nu_laden ? "Laden" : REDEN[plan.reden] || plan.reden, plan.nu_laden ? "goed" : ""],
  ].map(tegel).join("");
}

// ── elektriciteit & gas ──────────────────────────────────────────────────────

function toonStroom(dag) {
  const { uren, reeksen, totalen } = dag;
  $("#stroom-totaal").textContent = `${fmt.getal(totalen.stroom.hoeveelheid)} kWh`;
  grafiek("g-stroom").setOption(basis({
    yAxis: { type: "value", name: "kWh", nameTextStyle: { color: css("--zacht") }, axisLabel: { color: css("--zacht") },
             splitLine: { lineStyle: { color: css("--lijn") } } },
    series: [
      balken("Afgenomen", uren, reeksen.stroom, css("--c-stroom"), { stack: "e" }),
      balken("Teruggeleverd", uren, reeksen.teruglevering.map((v) => -v), css("--c-terug"), { stack: "e" }),
    ],
  }), true);
  grafiek("g-laden").setOption(basis({ legend: { show: false },
    series: [balken("Laden", uren, reeksen.laden, css("--c-laden"))] }), true);
  grafiek("g-kosten").setOption(basis({ legend: { show: false },
    yAxis: { type: "value", axisLabel: { color: css("--zacht"), formatter: (v) => `€${v.toFixed(2)}` },
             splitLine: { lineStyle: { color: css("--lijn") } } },
    tooltip: { trigger: "axis", valueFormatter: fmt.euro },
    series: [balken("Kosten", uren, reeksen.kosten_stroom, css("--c-prijs"))] }), true);
}

function toonGas(dag) {
  $("#gas-totaal").textContent = `${fmt.getal(dag.totalen.gas.hoeveelheid)} m³`;
  grafiek("g-gas").setOption(basis({ legend: { show: false },
    yAxis: { type: "value", name: "m³", nameTextStyle: { color: css("--zacht") }, axisLabel: { color: css("--zacht") },
             splitLine: { lineStyle: { color: css("--lijn") } } },
    series: [balken("Gas", dag.uren, dag.reeksen.gas, css("--c-gas"))] }), true);
}

// ── laden ────────────────────────────────────────────────────────────────────

async function toonLaden() {
  const vandaag = fmt.iso(new Date());
  const morgen = fmt.iso(new Date(Date.now() + 864e5));
  const [nu, d1, d2] = await Promise.all([api("nu"), api(`dag?datum=${vandaag}`), api(`dag?datum=${morgen}`)]);
  const { auto, lader, plan, instellingen } = nu;

  const pct = auto?.accu_pct ?? 0;
  $("#accu-vulling").style.width = `${pct}%`;
  $("#accu-tekst").textContent = auto ? `${Math.round(pct)}%` : "Geen gegevens";
  $("#auto-tegels").innerHTML = auto ? [
    ["Bereik", `${Math.round(auto.bereik_km ?? 0)} km`],
    ["Stekker", auto.ingeplugd ? "Ingeplugd" : "Los"],
    ["Laadt", auto.laadt ? "Ja" : "Nee", auto.laadt ? "goed" : ""],
    ["Bijgewerkt", auto.bijgewerkt ? fmt.uur(auto.bijgewerkt) : "–"],
  ].map(tegel).join("") : "";
  $("#lader-tegels").innerHTML = lader ? [
    ["Status", STATUS[lader.status] || lader.status],
    ["Vermogen", `${fmt.getal(lader.vermogen_kw, 1)} kW`],
    ["Deze sessie", `${fmt.getal(lader.sessie_kwh, 1)} kWh`],
    ["Meting", fmt.uur(lader.tijd)],
  ].map(tegel).join("") : `<p class="sub">Nog geen gegevens van de lader.</p>`;

  $("#plan-status").textContent = plan.nu_laden ? "Nu laden" : REDEN[plan.reden] || plan.reden;
  $("#plan-tegels").innerHTML = [
    ["Nodig", `${fmt.getal(plan.nodig_kwh, 1)} kWh`],
    ["Kosten", fmt.euro(plan.kosten)],
    ["Start", plan.blokken.length ? fmt.uur(plan.blokken[0].van) : "–"],
    ["Vertrek", fmt.uur(plan.vertrek)],
    ["Plan", plan.volledig ? "Volledig" : "Wacht op prijzen morgen", plan.volledig ? "" : "slecht"],
  ].map(tegel).join("");

  const prijzen = [...d1.prijzen.stroom, ...d2.prijzen.stroom].filter((p) => new Date(p.tot) > Date.now() - 36e5);
  const gepland = plan.blokken.flatMap((b) => [[b.van, b.prijs], [b.tot, b.prijs], [b.tot, null]]);
  grafiek("g-plan").setOption(basis({
    legend: { top: 0, data: ["Prijs", "Gepland laden"], textStyle: { color: css("--zacht") } },
    xAxis: { type: "time", axisLabel: { color: css("--zacht"), hideOverlap: true,
             formatter: (v) => `${fmt.uur(v)}\n${new Date(v).toLocaleDateString("nl-NL", { weekday: "short", timeZone: TZ })}` },
             axisLine: { lineStyle: { color: css("--lijn") } } },
    yAxis: { type: "value", axisLabel: { color: css("--zacht"), formatter: (v) => `€${v.toFixed(2)}` },
             splitLine: { lineStyle: { color: css("--lijn") } } },
    series: [
      prijsReeks(prijzen, css("--c-prijs")),
      { name: "Gepland laden", type: "line", symbol: "none", connectNulls: false, data: gepland,
        itemStyle: { color: css("--c-plan") }, lineStyle: { color: css("--c-plan"), width: 4 }, areaStyle: { color: css("--c-plan"), opacity: 0.25 } },
      nuLijn(),
    ],
  }), true);

  const form = $("#instellingen");
  if (!form.dataset.gevuld) {
    for (const [k, v] of Object.entries(instellingen)) {
      const veld = form.elements[k];
      if (veld) veld.type === "checkbox" ? (veld.checked = v) : (veld.value = v);
    }
    form.dataset.gevuld = "1";
  }
}

async function bewaarInstellingen(e) {
  e.preventDefault();
  const f = e.target, uit = {};
  for (const veld of f.elements) {
    if (!veld.name) continue;
    uit[veld.name] = veld.type === "checkbox" ? veld.checked : veld.type === "number" ? Number(veld.value) : veld.value;
  }
  const m = $("#instellingen-melding");
  try {
    await api("instellingen", { method: "PUT", body: JSON.stringify(uit) });
    m.textContent = "Opgeslagen.";
    await toonLaden();
  } catch (err) {
    m.textContent = `Niet opgeslagen: ${err.message}`;
  }
}

// ── navigatie ────────────────────────────────────────────────────────────────

async function ververs() {
  melding("");
  $("#datum").textContent = fmt.iso(staat.datum) === fmt.iso(new Date()) ? `Vandaag · ${fmt.dag(staat.datum)}` : fmt.dag(staat.datum);
  $("#datumbalk").hidden = staat.tab === "laden";
  try {
    if (staat.tab === "laden") return await toonLaden();
    const dag = await api(`dag?datum=${fmt.iso(staat.datum)}`);
    if (staat.tab === "samenvatting") {
      toonTotalen(dag.totalen);
      toonPrijs(dag);
      toonNu(await api("nu"));
    } else if (staat.tab === "elektriciteit") toonStroom(dag);
    else if (staat.tab === "gas") toonGas(dag);
    if (!dag.compleet.verbruik) melding("Nog geen meterdata van Frank Energie voor deze dag (komt met een dag vertraging).");
  } catch (err) {
    melding(`Kon gegevens niet laden: ${err.message}`);
  }
}

function kiesTab(tab) {
  staat.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  document.querySelectorAll("[data-paneel]").forEach((p) => (p.hidden = p.dataset.paneel !== tab));
  try { localStorage.setItem("tab", tab); } catch { /* geen opslag beschikbaar */ }
  ververs().then(() => Object.values(staat.grafieken).forEach((g) => g.resize()));
}

function schuif(dagen) {
  staat.datum = new Date(staat.datum.getTime() + dagen * 864e5);
  ververs();
}

addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => kiesTab(b.dataset.tab)));
  $("#vorige").addEventListener("click", () => schuif(-1));
  $("#volgende").addEventListener("click", () => schuif(1));
  $("#datum").addEventListener("click", () => { staat.datum = new Date(); ververs(); });
  $("#instellingen").addEventListener("submit", bewaarInstellingen);
  addEventListener("resize", () => Object.values(staat.grafieken).forEach((g) => g.resize()));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", ververs);
  setInterval(() => document.visibilityState === "visible" && ververs(), 5 * 60e3);
  let tab = "samenvatting";
  try { tab = localStorage.getItem("tab") || tab; } catch { /* geen opslag beschikbaar */ }
  kiesTab(tab);
});
