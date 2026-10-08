// Laden: auto, lader, laadplan (Slim laden), laadsessies en instellingen.

import {
  $, LADER_STATUS, PLAN_REDEN, api, css, datumKort, dagnaam, euro, getal, hoeveelheid, huidigBlok, isoDatum,
  klok, meldFout, plusDagen, prijs, relatief, toast, vandaag,
} from "../basis.js";
import { basis, gekleurd, grafiek, regel, ruimOp, staven } from "../grafiek.js";
import { kaart, leeg, melding, skeletKaart, tegel } from "../onderdelen.js";

export async function toon(main, params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-6 half-tablet", { titel: "Auto" })}${skeletKaart("b-6 half-tablet", { titel: "Lader" })}
      ${skeletKaart("b-12", { titel: "Laadplan", grafiek: true })}</div>`;
  }
  const v = vandaag();
  const [nu, d0, d1, sessies] = await Promise.all([
    api("nu"),
    api(`dag?datum=${v}`),
    api(`dag?datum=${plusDagen(v, 1)}`),
    api("laadsessies"),
  ]);
  if (!ctx.actueel()) return;
  const { auto, lader, plan, instellingen } = nu;

  ruimOp();
  main.innerHTML = `<div class="raster">
    ${autoKaart(auto, instellingen)}
    ${laderKaart(lader)}
    ${planKaart(plan, instellingen)}
    ${kaart({ titel: "Laadsessies", sub: "laatste 30 dagen", klasse: "b-8", id: "k-sessies", inhoud: sessieTabel(sessies) })}
    ${kaart({ titel: "Instellingen", klasse: "b-4", id: "k-instellingen", inhoud: formulier(instellingen) })}
  </div>`;
  planGrafiek(plan, [...d0.prijzen.stroom, ...d1.prijzen.stroom]);

  $("#instellingen").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const waarden = {};
    for (const veld of f.elements) {
      if (!veld.name) continue;
      waarden[veld.name] = veld.type === "checkbox" ? veld.checked : veld.type === "number" ? Number(veld.value) : veld.value;
    }
    const knop = f.querySelector("button[type=submit]");
    knop.disabled = true;
    try {
      await api("instellingen", { methode: "PUT", body: waarden });
      toast("Instellingen opgeslagen");
      await toon(main, params, { ...ctx, nieuw: false });
    } catch (err) {
      knop.disabled = false;
      meldFout(err.message?.startsWith("Fout 422") ? new Error("Niet opgeslagen: een van de waarden valt buiten het toegestane bereik.") : err);
    }
  });
}

function autoKaart(auto, instellingen) {
  if (!auto) return kaart({ titel: "Auto", klasse: "b-6 half-tablet", inhoud: leeg("Nog geen gegevens van de auto. Staat Kia Connect ingesteld?") });
  const pct = auto.accu_pct ?? 0;
  return kaart({
    titel: auto.naam || "Auto",
    klasse: "b-6 half-tablet",
    id: "k-auto",
    rechts: auto.laadt ? '<span class="pil goed"><span class="stip"></span>Laadt</span>' : "",
    inhoud: `<div class="accu" role="meter" aria-label="Accu" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}">
        <div class="vulling" style="width:${pct}%"></div>
        <div class="doel" style="left:${instellingen.doel_pct}%" title="Doel ${instellingen.doel_pct}%"></div>
        <span><b>${getal(pct, 0)}%</b><span class="zacht">doel ${getal(instellingen.doel_pct, 0)}%</span></span>
      </div>
      <div class="tegels" style="margin-top:12px">
        ${tegel("Bereik", auto.bereik_km != null ? `${getal(auto.bereik_km, 0)} <small>km</small>` : "–")}
        ${tegel("Stekker", auto.ingeplugd ? "Ingeplugd" : "Los")}
        ${tegel("Bijgewerkt", auto.bijgewerkt ? relatief(auto.bijgewerkt) : "–")}
      </div>`,
    voet: "De auto wordt niet gewekt: dit is de laatste stand die de auto zelf heeft doorgegeven.",
  });
}

function laderKaart(lader) {
  if (!lader) return kaart({ titel: "Lader", klasse: "b-6 half-tablet", inhoud: leeg("Nog geen gegevens van de lader. Staat Easee ingesteld?") });
  const klasse = lader.status === "laden" ? "goed" : lader.status === "fout" ? "fout" : "";
  return kaart({
    titel: lader.naam || "Lader",
    klasse: "b-6 half-tablet",
    id: "k-lader",
    rechts: `<span class="pil ${klasse}"><span class="stip"></span>${LADER_STATUS[lader.status] || lader.status}</span>`,
    inhoud: `<div class="tegels">
        ${tegel("Vermogen", `${getal(lader.vermogen_kw, 1)} <small>kW</small>`)}
        ${tegel("Deze sessie", `${getal(lader.sessie_kwh, 1)} <small>kWh</small>`)}
        ${tegel("Meterstand", `${getal(lader.totaal_kwh, 0)} <small>kWh</small>`)}
        ${tegel("Meting", relatief(lader.tijd))}
      </div>`,
  });
}

function planKaart(plan, instellingen) {
  const b = plan.blokken;
  const status = plan.nu_laden ? "goed" : plan.reden === "geen_prijzen" ? "let_op" : "accent";
  return kaart({
    titel: "Laadplan",
    sub: `klaar vóór ${klok(plan.vertrek)} ${dagnaam(plan.vertrek)}, doel ${getal(instellingen.doel_pct, 0)}%`,
    klasse: "b-12",
    id: "k-plan",
    rechts: `<span class="pil ${status}"><span class="stip"></span>${PLAN_REDEN[plan.reden] || plan.reden}</span>`,
    inhoud: `
      ${instellingen.sturen ? "" : melding("Automatisch sturen staat uit: dit plan is een advies en de lader laadt zoals hij zelf wil. Zet sturen aan bij de instellingen als het plan een paar dagen klopt.", "", "klok")}
      <div class="grafiek" id="g-plan" role="img" aria-label="Prijzen en geplande laadmomenten" style="margin-top:12px"></div>
      <div class="legenda">
        <span><i style="background:var(--c-laden)"></i>Gepland laden</span>
        <span><i style="background:var(--p-gedimd)"></i>Niet gepland</span>
      </div>
      <div class="tegels" style="margin-top:12px">
        ${tegel("Nodig", `${getal(plan.nodig_kwh, 1)} <small>kWh</small>`)}
        ${tegel("Geschatte kosten", euro(plan.kosten))}
        ${tegel("Start", b.length ? `${klok(b[0].van)} <small>${dagnaam(b[0].van)}</small>` : "–")}
        ${tegel("Klaar", b.length ? `${klok(b.at(-1).tot)} <small>${dagnaam(b.at(-1).tot)}</small>` : "–")}
        ${tegel("Prijs nu", prijs(plan.prijs_nu))}
      </div>
      ${plan.volledig ? "" : `<p class="kaart-voet">Het plan is nog niet compleet: de prijzen van morgen komen rond 13:00.</p>`}`,
  });
}

function planGrafiek(plan, alles) {
  const el = document.getElementById("g-plan");
  const nu = Date.now();
  const blokken = alles.filter((b) => new Date(b.tot) > nu - 3600e3);
  if (!blokken.length) {
    el.outerHTML = leeg("Nog geen prijzen.");
    return;
  }
  const gepland = (b) => plan.blokken.some((p) => new Date(p.van) < new Date(b.tot) && new Date(p.tot) > new Date(b.van));
  const labels = blokken.map((b) => `${klok(b.van)}\n${dagnaam(b.van)}`);
  const huidig = huidigBlok(blokken);
  const vertrek = blokken.find((b) => new Date(b.tot) > new Date(plan.vertrek));
  const lijnen = [];
  if (huidig) lijnen.push({ xAxis: labels[blokken.indexOf(huidig)], label: { formatter: "nu" } });
  if (vertrek) lijnen.push({ xAxis: labels[blokken.indexOf(vertrek)], label: { formatter: "vertrek" } });
  grafiek(el).setOption(
    basis({
      xAxis: {
        data: labels,
        axisLabel: { interval: (i, w) => w.startsWith("00:00") || w.startsWith("06:00") || w.startsWith("12:00") || w.startsWith("18:00"), formatter: (w) => w.split("\n")[0] },
      },
      yAxis: { axisLabel: { formatter: (w) => `€ ${getal(w, 2)}` } },
      tooltip: {
        formatter: ([p]) => {
          const b = blokken[p.dataIndex];
          const ja = gepland(b);
          return `${dagnaam(b.van)} ${klok(b.van)}–${klok(b.tot)}${regel(ja ? css("--c-laden") : css("--p-gedimd"), ja ? "Gepland laden" : "Prijs", prijs(b.prijs))}`;
        },
      },
      series: [
        staven("Prijs", blokken.map((b) => gekleurd(b.prijs, gepland(b) ? css("--c-laden") : css("--p-gedimd"))), null, {
          barMaxWidth: 8,
          barCategoryGap: "18%",
          markLine: {
            symbol: "none",
            silent: true,
            animation: false,
            label: { color: css("--inkt-2"), fontSize: 11, position: "end" },
            lineStyle: { color: css("--inkt-3"), type: "dashed", width: 1 },
            data: lijnen,
          },
        }),
      ],
    }),
  );
}

function sessieTabel(sessies) {
  if (!sessies.length) return leeg("Geen laadsessies in de laatste 30 dagen.");
  const som = (k) => sessies.reduce((a, s) => a + (s[k] || 0), 0);
  const kwh = som("kwh");
  const rijen = sessies
    .map((s) => {
      const dag = isoDatum(new Date(s.start));
      const eind = s.eind ? `${klok(s.eind)}${isoDatum(new Date(s.eind)) !== dag ? ` ${datumKort(isoDatum(new Date(s.eind)))}` : ""}` : "";
      return `<tr>
        <td>${datumKort(dag)}${s.slim ? ' <span class="slim" title="Slim laden heeft deze sessie gestuurd">slim</span>' : ""}${s.klaar ? "" : ' <span class="pil goed">bezig</span>'}</td>
        <td class="r" data-label="">${klok(s.start)}–${eind}</td>
        <td data-label="Geladen">${hoeveelheid(s.kwh)} kWh</td>
        <td class="r" data-label="Kosten">${euro(s.kosten)}</td>
        <td data-label="Gemiddeld">${prijs(s.gem_prijs)}</td>
        <td class="r" data-label="Bespaard">${s.besparing == null ? "–" : euro(s.besparing)}</td>
      </tr>`;
    })
    .join("");
  return `<div class="tabel-wrap"><table class="tabel sessies">
    <thead><tr><th>Datum</th><th>Ingeplugd – klaar</th><th>Geladen</th><th>Kosten</th><th>Gem. prijs</th><th>Bespaard</th></tr></thead>
    <tbody>${rijen}</tbody>
    <tfoot><tr><td>${sessies.length} sessies</td><td></td><td>${hoeveelheid(kwh)} kWh</td><td>${euro(som("kosten"))}</td>
      <td>${kwh ? prijs(som("kosten") / kwh) : "–"}</td><td>${euro(som("besparing"))}</td></tr></tfoot>
  </table></div>
  <p class="kaart-voet">Bespaard: wat dezelfde kWh hadden gekost als de auto direct na het inpluggen op vol vermogen had geladen.</p>`;
}

function formulier(i) {
  const veld = (naam, label, uitleg, invoer) =>
    `<div class="veld"><label for="v-${naam}">${label}<span class="uitleg">${uitleg}</span></label>${invoer}</div>`;
  const getalVeld = (naam, min, max, stap, eenheid, voor = "") =>
    `<span class="invoer">${voor}<input id="v-${naam}" name="${naam}" type="number" min="${min}" max="${max}" step="${stap}" value="${i[naam]}" required inputmode="decimal">${eenheid}</span>`;
  return `<form id="instellingen" class="formulier">
    ${veld("doel_pct", "Doel accu", "Tot hoever Slim laden laadt", getalVeld("doel_pct", 10, 100, 5, "%"))}
    ${veld("vertrek", "Vertrektijd", "Vóór dit tijdstip is de auto klaar", `<span class="invoer"><input id="v-vertrek" name="vertrek" type="time" value="${i.vertrek}" required></span>`)}
    ${veld("capaciteit_kwh", "Accucapaciteit", "Bruikbaar, volgens de fabrikant", getalVeld("capaciteit_kwh", 5, 200, 0.1, "kWh"))}
    ${veld("vermogen_kw", "Laadvermogen", "Wat de lader levert", getalVeld("vermogen_kw", 1, 22, 0.1, "kW"))}
    ${veld("rendement_pct", "Laadrendement", "Verlies tussen net en accu", getalVeld("rendement_pct", 50, 100, 1, "%"))}
    ${veld("altijd_onder", "Altijd laden onder", "Ook als het doel al bereikt is", getalVeld("altijd_onder", -1, 1, 0.01, "/kWh", "€"))}
    <div class="veld"><label for="v-sturen">Lader automatisch sturen<span class="uitleg">Pauzeert en hervat de Easee volgens het plan</span></label>
      <span class="schakelaar"><input id="v-sturen" name="sturen" type="checkbox" role="switch" ${i.sturen ? "checked" : ""}><span></span></span></div>
    <div class="acties"><button class="knop primair" type="submit">Instellingen opslaan</button></div>
  </form>`;
}
