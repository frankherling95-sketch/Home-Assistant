// Thuis — web-app. Leest alles uit de eigen API (/api/...); inloggen regelt IAP vóór Cloud Run.

import { $, $$, api, esc, icoon, legeCache, meldFout, relatief, thema, zetThema } from "./basis.js";
import { herschaal, ruimOp } from "./grafiek.js";
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
  inzichten: { titel: "Inzichten", module: inzichten },
  bronnen: { titel: "Bronnen", module: bronnen },
};

let huidige = null;
let teller = 0;

function leesRoute() {
  const [pad, query] = location.hash.replace(/^#\/?/, "").split("?");
  return { naam: PAGINAS[pad] ? pad : "overzicht", params: new URLSearchParams(query || "") };
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

async function gezondheid() {
  let status = "onbekend", tekst = "Status van de bronnen onbekend";
  try {
    const s = await api("status", { vers: true });
    const fouten = s.bronnen.filter((b) => b.uitslag?.startsWith("fout"));
    const laatste = s.bronnen.map((b) => b.tijd).filter(Boolean).sort().at(-1);
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
  $("#gezondheid").setAttribute("aria-label", `Bronnen: ${tekst}`);
  $("#gezondheid").title = tekst;
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
  setInterval(() => {
    if (document.visibilityState === "visible") {
      herteken({ vers: true });
      gezondheid();
    }
  }, 5 * 60e3);

  toonThema();
  toon();
  gezondheid();
  api("gebruiker")
    .then((g) => ($("#gebruiker").textContent = `Ingelogd als ${g.email}`))
    .catch(() => {});

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
});
