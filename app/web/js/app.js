// Thuis — web-app. Leest alles uit de eigen API (/api/...); inloggen regelt IAP vóór Cloud Run.

import { $, $$, api, esc, icoon, legeCache, meldFout, relatief, thema, zetThema } from "./basis.js";
import { herschaal, ruimOp } from "./grafiek.js";
import * as auto from "./paginas/auto.js";
import * as bronnen from "./paginas/bronnen.js";
import * as energie from "./paginas/energie.js";
import * as inzichten from "./paginas/inzichten.js";
import * as laden from "./paginas/laden.js";
import * as overzicht from "./paginas/overzicht.js";
import * as prijzen from "./paginas/prijzen.js";

const PAGINAS = {
  overzicht: { titel: "Overzicht", module: overzicht },
  energie: { titel: "Energie", module: energie },
  prijzen: { titel: "Prijzen", module: prijzen },
  laden: { titel: "Laden", module: laden },
  auto: { titel: "Auto", module: auto },
  inzichten: { titel: "Inzichten", module: inzichten },
  koppelingen: { titel: "Koppelingen", module: bronnen },
  bronnen: { titel: "Koppelingen", module: bronnen, als: "koppelingen" }, // oude links
};

let huidige = null;
let teller = 0;

function leesRoute() {
  const [pad, query] = location.hash.replace(/^#\/?/, "").split("?");
  const naam = PAGINAS[pad] ? PAGINAS[pad].als || pad : "overzicht";
  return { naam, params: new URLSearchParams(query || "") };
}

/** Naar een pagina; parameters komen in de hash, zodat terug/vooruit en delen werken. */
export function navigeer(naam, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== "")).toString();
  location.hash = `#/${naam}${q ? `?${q}` : ""}`;
}

async function toon({ ververs = false } = {}) {
  const { naam, params } = leesRoute();
  const pagina = PAGINAS[naam];
  const main = $("#inhoud");
  const nieuw = naam !== huidige;
  const mijn = ++teller;
  if (nieuw) {
    ruimOp();
    main.replaceChildren();
    main.dataset.pagina = naam;
    document.title = `${pagina.titel} – Thuis`;
    $("#paginatitel").textContent = pagina.titel;
    for (const a of $$("[data-pagina]")) {
      if (a.dataset.pagina === naam) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    scrollTo({ top: 0 });
  }
  huidige = naam;
  try {
    await pagina.module.toon(main, params, { nieuw, ververs, actueel: () => mijn === teller, navigeer });
  } catch (err) {
    if (mijn !== teller) return;
    console.error(err);
    if (!main.childElementCount) {
      main.innerHTML = `<div class="melding fout">${icoon("let_op")}<div>Deze pagina kon niet laden: ${esc(err.message)}</div></div>`;
    }
    meldFout(err);
  }
}

/** Opnieuw tekenen (na een thema-wissel, of elke 5 minuten met verse data). */
function herteken({ vers = false } = {}) {
  if (vers) legeCache();
  return toon({ ververs: true });
}

// ── gezondheid van de bronnen (stip in de kop en het menu) ────────────────────

/** Werkt de statusstip bij; geeft het tijdstip van de laatste ronde terug. */
async function gezondheid() {
  let status = "onbekend", tekst = "Status van de bronnen onbekend", laatste = null;
  try {
    const s = await api("status", { vers: true });
    const fouten = s.bronnen.filter((b) => b.uitslag?.startsWith("fout"));
    laatste = s.bronnen.map((b) => b.tijd).filter(Boolean).sort().at(-1) ?? null;
    if (fouten.length) {
      status = "fout";
      tekst = `${fouten.map((b) => b.naam).join(", ")}: mislukt`;
    } else if (!laatste || Date.now() - new Date(laatste) > 40 * 60e3) {
      status = "let_op";
      tekst = `Laatste ronde ${relatief(laatste)}`;
    } else {
      status = "ok";
      tekst = `Alle bronnen in orde (${relatief(laatste)})`;
    }
  } catch { /* stip blijft grijs */ }
  for (const el of $$("[data-gezondheid]")) el.dataset.status = status;
  $("#gezondheid").setAttribute("aria-label", `Koppelingen: ${tekst}`);
  $("#gezondheid").title = tekst;
  return laatste;
}

// Verversen alleen als de verzamelaar een nieuwe ronde heeft gedraaid: elke query kost
// in BigQuery minimaal 10 MB, dus niet elke paar minuten alles opnieuw ophalen.
let gezienRonde = null;
async function kijkVoorNieuweRonde() {
  if (document.visibilityState !== "visible") return;
  const laatste = await gezondheid();
  if (laatste && gezienRonde && laatste !== gezienRonde) herteken({ vers: true });
  gezienRonde = laatste ?? gezienRonde;
}

// ── thema ─────────────────────────────────────────────────────────────────────

const VOLGEND = { systeem: "licht", licht: "donker", donker: "systeem" };

function toonThema() {
  const t = thema();
  for (const b of $$("#thema-keuze button")) b.setAttribute("aria-pressed", String(b.dataset.thema === t));
  const knop = $("#themaknop");
  knop.innerHTML = icoon(`thema-${t}`);
  knop.setAttribute("aria-label", `Weergave: ${t}. Wissel naar ${VOLGEND[t]}`);
  document.querySelector('meta[name="theme-color"]').content = getComputedStyle(document.body).backgroundColor;
}

// ── start ─────────────────────────────────────────────────────────────────────

addEventListener("DOMContentLoaded", () => {
  for (const b of $$("#thema-keuze button")) b.addEventListener("click", () => zetThema(b.dataset.thema));
  $("#themaknop").addEventListener("click", () => zetThema(VOLGEND[thema()]));
  addEventListener("thema", () => {
    toonThema();
    herteken();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (thema() === "systeem") {
      toonThema();
      herteken();
    }
  });
  addEventListener("hashchange", () => toon());
  let wacht;
  addEventListener("resize", () => {
    clearTimeout(wacht);
    wacht = setTimeout(herschaal, 120);
  });
  setInterval(kijkVoorNieuweRonde, 5 * 60e3);
  document.addEventListener("visibilitychange", kijkVoorNieuweRonde); // terug in de app

  toonThema();
  toon();
  kijkVoorNieuweRonde();
  api("gebruiker")
    .then((g) => ($("#gebruiker").textContent = `Ingelogd als ${g.email}`))
    .catch(() => {});

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
});
