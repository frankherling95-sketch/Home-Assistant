// Overzicht: van wat je nu kunt doen naar terugblikken. Bovenaan de stroomprijs met vandaag en
// morgen, dan de auto en het verbruik van de laatste dag met meterdata, je slimme apparaten (als
// Tuya gekoppeld is) en onderaan de inzichten. Het stromendiagram en de totalentabel staan op Energie.

import {
  $, LADER_STATUS, PLAN_REDEN, api, autoFoto, autoStand, css, dagnaam, esc, euro, gemiddelde, getal, goedkoopsteVenster,
  hoeveelheid, huidigBlok, icoon, klok, meldFout, niveau, plusDagen, prijs, vandaag,
} from "../basis.js";
import { basis, doorzichtig, gekleurd, grafiek, nuLijn, regel, ruimOp, scheiding, staven } from "../grafiek.js";
import { accuBalk, inzichtTegel, kaart, leeg, melding, pijl, skeletKaart, tegel } from "../onderdelen.js";
import { hoofd, icoonVan, stand as apparaatStand } from "./apparaten.js";

const WEEKDAG = new Intl.DateTimeFormat("nl-NL", { weekday: "long", timeZone: "UTC" });
const DATUM = new Intl.DateTimeFormat("nl-NL", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const middag = (iso) => new Date(`${iso}T12:00:00Z`);

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="overzicht">
      ${skeletKaart("", { titel: "Stroomprijs nu", grafiek: true })}
      <div class="overzicht-rij">${skeletKaart("", { titel: "Auto en lader", regels: 5 })}${skeletKaart("", { titel: "Verbruik", regels: 5 })}</div>
    </div>`;
  }
  const v = vandaag();
  const [nu, dag, morgen, inzichten, apparaten] = await Promise.all([
    api("nu"),
    api(`dag?datum=${v}`),
    api(`dag?datum=${plusDagen(v, 1)}`),
    api(`inzichten?datum=${v}`).catch(() => []),
    api("apparaten").catch(() => null), // Tuya onbereikbaar: het overzicht gewoon zonder apparaten
  ]);
  // De slimme meter komt via Frank met een dag vertraging: dan gisteren tonen, vergeleken met de dag ervoor.
  const meterdag = dag.compleet.verbruik ? dag : await api(`dag?datum=${plusDagen(v, -1)}`);
  const ervoor = meterdag.compleet.verbruik ? await api(`dag?datum=${plusDagen(meterdag.datum, -1)}`).catch(() => null) : null;
  if (!ctx.actueel()) return;

  ruimOp();
  main.innerHTML = `<div class="overzicht">
    ${prijsKaart(dag, morgen)}
    <div class="overzicht-rij">
      ${autoKaart(nu)}
      ${verbruikKaart(meterdag, ervoor, meterdag === dag)}
    </div>
    ${apparaten?.gekoppeld && apparaten.apparaten.length ? apparatenKaart(apparaten.apparaten) : ""}
    ${inzichten.length
      ? kaart({
          titel: "Inzichten",
          id: "k-inzichten",
          rechts: inzichten.length > 3 ? pijl(`Alle ${inzichten.length} inzichten`, "#/inzichten") : "",
          inhoud: `<div class="inzichten breed">${inzichten.slice(0, 3).map(inzichtTegel).join("")}</div>`,
        })
      : ""}
  </div>`;
  prijsGrafiek(dag.prijzen.stroom, morgen.prijzen.stroom, nu.plan);
  koppelSnelknoppen(main, apparaten?.apparaten || []);
}

// ── stroomprijs ───────────────────────────────────────────────────────────────

/** Eerste aaneengesloten stuk met een negatieve prijs in de komende 36 uur, of null. */
function negatiefVenster(blokken) {
  const nu = Date.now();
  const komend = blokken.filter((b) => new Date(b.tot) > nu && new Date(b.van) < nu + 36 * 3600e3);
  const i = komend.findIndex((b) => b.prijs < 0);
  if (i < 0) return null;
  let j = i;
  while (j + 1 < komend.length && komend[j + 1].prijs < 0 && komend[j + 1].van === komend[j].tot) j++;
  const stuk = komend.slice(i, j + 1);
  return { van: stuk[0].van, tot: stuk.at(-1).tot, laagste: Math.min(...stuk.map((b) => b.prijs)) };
}

const LEGENDA = [
  ["--p-negatief", "Negatief"], ["--p-zeer-goedkoop", "Zeer goedkoop"], ["--p-goedkoop", "Goedkoop"],
  ["--p-normaal", "Normaal"], ["--p-duur", "Duur"], ["--p-zeer-duur", "Zeer duur"],
];

function prijsKaart(dag, morgen) {
  const blokken = dag.prijzen.stroom;
  if (!blokken.length) return kaart({ titel: "Stroomprijs nu", klasse: "o-prijs", inhoud: leeg("Nog geen prijzen voor vandaag.") });
  const gem = gemiddelde(blokken);
  const nu = huidigBlok(blokken);
  const niv = nu ? niveau(nu.prijs, gem) : null;
  const metMorgen = morgen.prijzen.stroom.length > 0;
  const alle = [...blokken, ...morgen.prijzen.stroom];
  const neg = negatiefVenster(alle);
  const venster = neg ? null : goedkoopsteVenster(alle, 1);
  const feit = neg
    ? `<span class="feit-label">Negatieve prijs</span>
       <span class="feit-waarde" style="color:var(--p-negatief)">${dagnaam(neg.van)} ${klok(neg.van)}–${klok(neg.tot)}</span>
       <span class="feit-uitleg">laagste ${prijs(neg.laagste)} per kWh</span>`
    : venster
      ? `<span class="feit-label">Goedkoopste uur</span>
         <span class="feit-waarde">${dagnaam(venster.van)} ${klok(venster.van)}–${klok(venster.tot)}</span>
         <span class="feit-uitleg">gemiddeld ${prijs(venster.prijs)}</span>`
      : "";
  return `<section class="kaart o-prijs" id="k-prijs" aria-labelledby="k-prijs-titel">
    <div class="held-prijs">
      <div class="prijs-blok">
        <header class="kaart-kop"><h2 id="k-prijs-titel">Stroomprijs nu</h2>
          ${niv ? `<div class="rechts"><span class="pil"><span class="stip" style="background:var(${niv.kleur})"></span>${niv.naam}</span></div>` : ""}</header>
        <div class="prijs-groot">${prijs(nu?.prijs)}</div>
        <p class="zacht">per kWh all-in${nu ? ` · tot ${klok(nu.tot)}` : ""}</p>
        <p class="zacht">daggemiddelde ${prijs(gem)}</p>
        ${feit ? `<div class="feit">${feit}</div>` : ""}
        <p class="prijs-link">${pijl("Alle prijzen", "#/prijzen")}</p>
      </div>
      <div class="prijs-grafiek">
        <div class="grafiek-kop"><span class="titel">Vandaag${metMorgen ? " en morgen" : ""}</span>
          <div class="legenda">${LEGENDA.map(([k, n]) => `<span><i style="background:var(${k})"></i>${n}</span>`).join("")}<span><i class="omlijnd"></i>Laadplan</span></div>
        </div>
        <div class="grafiek-scroll"><div class="grafiek" id="g-prijs" style="height:210px" role="img" aria-label="Stroomprijs per kwartier, vandaag${metMorgen ? " en morgen" : ""}"></div></div>
        ${metMorgen ? "" : '<p class="kaart-voet">De prijzen voor morgen komen rond 13:00.</p>'}
      </div>
    </div>
  </section>`;
}

function prijsGrafiek(vandaagB, morgenB, plan) {
  const el = document.getElementById("g-prijs");
  if (!el || !vandaagB.length) return;
  const blokken = [...vandaagB, ...morgenB];
  const gemV = gemiddelde(vandaagB);
  const gemM = morgenB.length ? gemiddelde(morgenB) : null;
  const vanMorgen = new Set(morgenB);
  const nu = Date.now();
  const huidig = huidigBlok(blokken);
  const morgenStart = morgenB[0]?.van;
  const vandaagStart = vandaagB[0].van;
  const gloed = Number(css("--gloed-grafiek")) || 0;
  const niv = (b) => niveau(b.prijs, vanMorgen.has(b) ? gemM : gemV);
  const data = blokken.map((b) => {
    const k = css(niv(b).kleur);
    const item = gekleurd(b.prijs, k);
    item.itemStyle = { ...item.itemStyle, shadowBlur: gloed, shadowColor: k, opacity: new Date(b.tot) <= nu ? 0.3 : 1 };
    return item;
  });

  // Het laadplan als omlijnde vlakken. Slim laden kiest losse kwartieren; kwartieren met
  // hooguit een half uur ertussen worden één vlak. Eén label boven het eerste vlak.
  const index = new Map(blokken.map((b, i) => [new Date(b.van).getTime(), i]));
  const groepen = [];
  for (const p of plan.blokken) {
    const i = index.get(new Date(p.van).getTime());
    if (i == null) continue;
    const laatst = groepen.at(-1);
    if (laatst && i - laatst.tot <= 2) laatst.tot = i;
    else groepen.push({ van: i, tot: i });
  }
  const laden = css("--c-laden");
  // Bij staven lijnt ECharts een vlak uit op de ticks; met een (onzichtbare) tick per kwartier
  // (axisTick.interval 0 hieronder) beslaat het vlak precies de kwartieren van van t/m tot.
  const vlakken = groepen.map((g, n) => [
    { xAxis: g.van, name: n ? "" : `Laadplan ${klok(plan.blokken[0].van)}–${klok(plan.blokken.at(-1).tot)}` },
    { xAxis: g.tot },
  ]);

  const asTekst = (iso) => {
    const t = klok(iso);
    if (iso === morgenStart) return "{morgen|morgen 00:00}";
    if (iso === vandaagStart) return "vandaag 00:00";
    return t;
  };
  const lijnen = [];
  if (huidig) lijnen.push(nuLijn(huidig.van));
  if (morgenStart) lijnen.push(scheiding(morgenStart));

  grafiek(el).setOption(
    basis({
      grid: { top: 46, left: 4, right: 8, bottom: 0 },
      xAxis: {
        data: blokken.map((b) => b.van),
        axisTick: { interval: 0 },
        axisLabel: {
          interval: (i, iso) => ["00:00", "12:00"].includes(klok(iso)),
          formatter: asTekst,
          rich: { morgen: { fontWeight: 500, color: css("--inkt-2"), fontSize: 12 } },
        },
      },
      yAxis: {
        min: Math.floor(Math.min(0, ...blokken.map((b) => b.prijs)) * 10) / 10,
        interval: 0.1,
        axisLabel: { formatter: (w) => (w === 0 ? "€ 0" : `€ ${getal(w, 2)}`) },
      },
      tooltip: {
        formatter: ([p]) => {
          const b = blokken[p.dataIndex];
          const n = niv(b);
          return `${dagnaam(b.van)} ${klok(b.van)}–${klok(b.tot)}${regel(css(n.kleur), n.naam, prijs(b.prijs))}`;
        },
      },
      series: [
        staven("Prijs", data, null, {
          barMaxWidth: 6,
          barCategoryGap: "20%",
          markLine: { symbol: "none", silent: true, animation: false, data: lijnen },
          markArea: {
            silent: true,
            itemStyle: { color: doorzichtig(laden, 0.12), borderColor: laden, borderWidth: 2 },
            label: { show: true, position: "top", distance: 24, color: laden, fontSize: 12, fontWeight: 500 },
            data: vlakken,
          },
        }),
      ],
    }),
  );
  // Op een smal scherm scrollt de grafiek; begin bij "nu".
  const scroll = el.parentElement;
  if (huidig && scroll.scrollWidth > scroll.clientWidth) {
    scroll.scrollLeft = Math.max(0, (blokken.indexOf(huidig) / blokken.length) * scroll.scrollWidth - 40);
  }
}

// ── auto en lader ─────────────────────────────────────────────────────────────

/** "vannacht" voor een tijdstip tussen middernacht en 6:00 dat binnen 18 uur valt, anders vandaag/morgen/datum. */
function wanneer(iso) {
  const uur = Number(klok(iso).slice(0, 2));
  const over = new Date(iso) - Date.now();
  return uur < 6 && over > 0 && over < 18 * 3600e3 ? "vannacht" : dagnaam(iso);
}

function autoKaart({ auto, lader, plan }) {
  if (!auto) {
    return kaart({ titel: "Auto en lader", klasse: "o-auto", inhoud: '<p class="leeg">Nog geen gegevens van de auto. <a href="#/koppelingen">Koppel je auto</a></p>' });
  }
  const pct = auto.accu_pct;
  const b = plan.blokken;
  const stekkerLos = !auto.ingeplugd;
  const status = plan.nu_laden
    ? '<span class="pil goed"><span class="stip"></span>Laadt nu</span>'
    : stekkerLos
      ? `<span class="pil ${b.length ? "let_op" : ""}"><span class="stip"></span>Stekker los</span>`
      : '<span class="pil"><span class="stip"></span>Ingeplugd</span>';
  const foto = autoFoto(auto.naam);
  const doel = plan.doel_pct;
  const stand = `<div class="auto-stand">
      <div class="stand-kop"><div class="groot">${getal(pct, 0)}<small>%</small></div>
        ${auto.bereik_km != null ? `<span class="bereik">${getal(auto.bereik_km, 0)} km bereik</span>` : ""}</div>
      ${accuBalk(pct, doel, doel != null ? [{ pct: doel, tekst: `doel ${getal(doel, 0)}%` }] : [])}
    </div>`;
  const laderStatus = lader ? LADER_STATUS[lader.status] || lader.status : "–";
  const tegels = b.length
    ? [
        tegel("Laadplan", `${klok(b[0].van)}–${klok(b.at(-1).tot)}`),
        tegel("Kosten plan", euro(plan.kosten)),
        tegel("Klaar vóór", klok(plan.vertrek)),
        tegel("Lader", laderStatus),
      ]
    : [
        tegel("Slim laden", PLAN_REDEN[plan.reden] || plan.reden),
        tegel("Vertrek", `${klok(plan.vertrek)} <small>${dagnaam(plan.vertrek)}</small>`),
        tegel("Lader", laderStatus),
      ];
  return kaart({
    titel: "Auto en lader",
    sub: [auto.naam, autoStand(auto)].filter(Boolean).join(" · "),
    klasse: "o-auto",
    id: "k-auto",
    rechts: status,
    inhoud: `${foto
      ? `<div class="held-auto"><div class="auto-foto"><img src="${foto}" alt="${esc(auto.naam)}" width="688" height="336"></div>${stand}</div>`
      : stand}
      ${stekkerLos && b.length ? melding(`Het laadplan start ${wanneer(b[0].van)} om ${klok(b[0].van)}. Steek de stekker erin, anders laadt de auto niet.`, "let_op") : ""}
      <div class="tegels vier">${tegels.join("")}</div>`,
    voet: pijl("Naar auto & laden", "#/auto"),
  });
}

// ── slimme apparaten: aan- en uitzetten zonder de pagina Apparaten te openen ───

const SNEL = 6;

function apparatenSub(lijst) {
  const aan = lijst.filter((a) => a.aan).length;
  const meters = lijst.filter((a) => a.online && a.metingen.vermogen_w != null && a.aan !== false);
  const vermogen = meters.reduce((s, a) => s + a.metingen.vermogen_w, 0);
  return `${aan} van ${lijst.length} aan${meters.length ? ` · ${getal(vermogen, 0)} W` : ""}`;
}

function apparatenKaart(lijst) {
  // Wat je kunt schakelen; wat aan staat eerst (de volgorde blijft staan tot de pagina opnieuw laadt).
  const knoppen = lijst.filter((a) => hoofd(a).length && a.aan != null).sort((x, y) => Number(y.aan) - Number(x.aan)).slice(0, SNEL);
  return kaart({
    titel: "Apparaten",
    sub: apparatenSub(lijst),
    id: "k-apparaten",
    rechts: pijl("Alle apparaten", "#/apparaten"),
    inhoud: knoppen.length
      ? `<div class="snelknoppen">${knoppen.map(snelknop).join("")}</div>`
      : leeg("Geen apparaten die je aan en uit kunt zetten."),
  });
}

const snelknop = (a) =>
  `<button type="button" class="snelknop" data-snel="${esc(a.id)}" aria-pressed="${Boolean(a.aan)}" ${a.online ? "" : "disabled"}
    aria-label="${esc(a.naam)}: ${esc(apparaatStand(a))}. ${a.aan ? "Uitzetten" : "Aanzetten"}">
    <span class="icoon">${icoon(icoonVan(a))}</span>
    <span class="tekst"><span class="naam">${esc(a.naam)}</span><span class="stand">${esc(apparaatStand(a))}</span></span>
  </button>`;

function koppelSnelknoppen(main, lijst) {
  const vak = $(".snelknoppen", main);
  if (!vak) return;
  vak.addEventListener("click", async (e) => {
    const knop = e.target.closest("[data-snel]");
    if (!knop || knop.getAttribute("aria-busy")) return;
    const a = lijst.find((x) => x.id === knop.dataset.snel);
    const aan = !a.aan;
    knop.setAttribute("aria-pressed", String(aan));
    knop.setAttribute("aria-busy", "true");
    try {
      const r = await api(`apparaten/${encodeURIComponent(a.id)}`, {
        methode: "POST",
        body: { opdrachten: hoofd(a).map((code) => ({ code, waarde: aan })) },
        legen: false,
      });
      Object.assign(a, r.apparaat);
      knop.outerHTML = snelknop(a);
      $("#k-apparaten .kaart-kop .sub", main).textContent = apparatenSub(lijst);
      $(`[data-snel="${CSS.escape(a.id)}"]`, vak)?.focus();
    } catch (err) {
      knop.setAttribute("aria-pressed", String(a.aan));
      knop.removeAttribute("aria-busy");
      meldFout(err);
    }
  });
}

// ── verbruik van de laatste dag met meterdata ─────────────────────────────────

function verbruikKaart(dag, ervoor, isVandaag) {
  if (!dag.compleet.verbruik) {
    return kaart({
      titel: "Verbruik",
      klasse: "o-verbruik",
      id: "k-verbruik",
      inhoud: `<div class="leeg-blok">
        <span class="rond"><svg class="ic" aria-hidden="true"><use href="#i-net"/></svg></span>
        <p class="titel">Nog geen meterdata</p>
        <p class="zacht">Koppel Frank Energie om je stroom, gas en kosten per dag te zien. De slimme meter loopt een dag achter.</p>
        <a class="knop primair" href="#/koppelingen">Koppel Frank Energie</a>
      </div>`,
    });
  }
  const t = dag.totalen;
  const stroomKosten = t.stroom.kosten + t.teruglevering.kosten;
  const netto = stroomKosten + t.gas.kosten;
  let verschil = "";
  if (ervoor?.compleet.verbruik) {
    const e = ervoor.totalen;
    const vorig = e.stroom.kosten + e.teruglevering.kosten + e.gas.kosten;
    if (vorig > 0) {
      const r = netto / vorig - 1;
      const kleur = r < 0 ? "var(--goed)" : r >= 0.1 ? "var(--let-op)" : "var(--inkt-3)";
      const teken = r > 0.005 ? "+" : r < -0.005 ? "−" : "";
      verschil = `<span class="verschil" style="color:${kleur}">${teken}${getal(Math.abs(r) * 100, 0)}% t.o.v. ${WEEKDAG.format(middag(ervoor.datum))}</span>`;
    }
  }
  const regels = [
    ["--c-stroom", "Stroom afgenomen", `${hoeveelheid(t.stroom.hoeveelheid)} kWh`, euro(t.stroom.kosten), ""],
    ["--c-terug", "Teruggeleverd", `${hoeveelheid(t.teruglevering.hoeveelheid)} kWh`, euro(t.teruglevering.kosten), ""],
    ["--c-gas", "Gas", `${hoeveelheid(t.gas.hoeveelheid)} m³`, euro(t.gas.kosten), ""],
    ["--c-laden", "waarvan laden", `${hoeveelheid(t.laden.hoeveelheid)} kWh`, euro(t.laden.kosten), " deel"],
  ];
  return kaart({
    titel: `Verbruik ${isVandaag ? "vandaag" : "gisteren"}`,
    sub: DATUM.format(middag(dag.datum)),
    klasse: "o-verbruik",
    id: "k-verbruik",
    inhoud: `<div class="netto"><div class="groot">${euro(netto)}<small>netto</small></div>${verschil}</div>
      <div class="verdeel" role="img" aria-label="Stroom ${euro(stroomKosten)}, gas ${euro(t.gas.kosten)}">
        <i style="flex:${Math.max(stroomKosten, 0)};background:var(--c-stroom)"></i><i style="flex:${Math.max(t.gas.kosten, 0)};background:var(--c-gas)"></i>
      </div>
      <div class="regels">${regels
        .map(([k, naam, hoeveel, kosten, extra]) => `<div class="regel${extra}"><i style="background:var(${k})"></i><span>${naam}</span><span class="hoeveel">${hoeveel}</span><span class="kosten">${kosten}</span></div>`)
        .join("")}</div>`,
    voet: pijl("Energiestromen en details", "#/energie"),
  });
}
