// Koppelingen: je accounts koppelen (zonder dat Thuis je wachtwoord bewaart), en hoe het met
// elke bron gaat volgens de rondelog van de verzamelaar.

import { $, $$, api, datumKort, esc, icoon, isoDatum, klok, meldFout, relatief, toast } from "../basis.js";
import { kaart, melding, skeletKaart } from "../onderdelen.js";

const TABELNAMEN = {
  prijs: "Prijzen",
  verbruik: "Verbruik (meter)",
  lader_meting: "Metingen lader",
  auto_meting: "Metingen auto",
  auto_details: "Details auto",
  auto_laadsessie: "Laadbeurten auto",
  instelling: "Instellingen",
  stuuractie: "Stuuracties",
  weer: "Weer",
  melding: "Meldingen",
  apparaat_meting: "Metingen apparaten",
  ronde: "Rondelog",
};

const STATUS = {
  ok: ["goed", "vink", "Gekoppeld"],
  opnieuw: ["fout", "let_op", "Opnieuw koppelen"],
  script: ["", "vink", "Via het installatiescript"],
  niet: ["", "pauze", "Niet gekoppeld"],
};

const HULP = {
  google_chat: "Maak in Google Chat een ruimte, kies Apps en integraties → Webhooks → Webhook toevoegen, en kopieer het adres.",
  bmw: "Log in op de BMW-site, ga naar BMW CarData en maak een client aan met 'CarData API' aan. Kopieer de Client-ID. Daarna geeft Thuis je een code om bij BMW te bevestigen.",
};

// Koppelen in stappen (eigen tekst, dus HTML met links mag).
const STAPPEN_HULP = {
  tuya: {
    stappen: [
      'Maak een gratis account op <a href="https://platform.tuya.com" target="_blank" rel="noopener noreferrer">platform.tuya.com</a>. Dat is een ander account dan dat van Smart Life.',
      "Ga naar Cloud → Development → Create Cloud Project. Kies bij Development Method <i>Smart Home</i> en bij Data Center het datacenter van je Smart Life-account (in Nederland: Central Europe).",
      "Open in het project Devices → Link App Account → Add App Account en scan de QR-code met Smart Life of Tuya Smart (Ik → scanknop rechtsboven).",
      "Kopieer bij Overview de Access ID en de Access Secret naar dit formulier.",
    ],
    voet: "Je Smart Life-wachtwoord heeft Thuis niet nodig. De Access ID en Access Secret van je project bewaart Thuis in de kluis: daarmee ondertekent het elk verzoek aan Tuya. Het gratis proefabonnement (IoT Core) verleng je om de paar maanden op platform.tuya.com; verloopt het, dan zie je dat hieronder bij de verzamelaar.",
  },
};

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) {
    main.innerHTML = `<div class="raster">${skeletKaart("b-12", { titel: "Koppelingen", regels: 6 })}
      ${skeletKaart("b-8", { titel: "Verzamelaar", regels: 6 })}${skeletKaart("b-4", { titel: "Tabellen", regels: 6 })}</div>`;
  }
  const [koppelingen, s] = await Promise.all([api("koppelingen", { vers: true }), api("status?tabellen=true", { vers: true })]);
  if (!ctx.actueel()) return;

  const laatste = s.bronnen.map((b) => b.tijd).filter(Boolean).sort().at(-1);
  const minuten = laatste ? (Date.now() - new Date(laatste)) / 60e3 : null;
  const waarschuwing =
    minuten == null
      ? melding("De verzamelaar heeft nog geen ronde gedraaid. Na de eerste ronde (elke 15 minuten) verschijnt hier de status per bron.")
      : minuten > 40
        ? melding(`De laatste ronde was ${esc(relatief(laatste))}. Normaal draait de verzamelaar elke 15 minuten; kijk in Cloud Scheduler en Cloud Run of de job nog loopt.`, "let_op")
        : "";

  main.innerHTML = `<div class="raster">
    ${kaart({
      titel: "Accounts",
      sub: "je accounts bij Frank Energie, Easee, je auto en je apparaten",
      klasse: "b-12",
      id: "k-koppelingen",
      inhoud: `${melding("Thuis bewaart je wachtwoord niet. Je logt één keer in; daarna gebruikt Thuis alleen de sleutel (token) die de dienst teruggeeft.", "", "vink")}
        <ul class="koppel-raster" id="koppelingen"></ul>`,
    })}
    ${kaart({
      titel: "Verzamelaar",
      sub: laatste ? `laatste ronde ${relatief(laatste)} · elke 15 minuten` : "elke 15 minuten",
      klasse: "b-8",
      id: "k-bronnen",
      inhoud: `${waarschuwing}<ul class="bronlijst">${s.bronnen.map(bron).join("")}</ul>`,
    })}
    ${kaart({
      titel: "Tabellen",
      sub: "laatst bijgewerkt · BigQuery",
      klasse: "b-4",
      id: "k-tabellen",
      inhoud: `<div class="tabel-wrap"><table class="tabel"><tbody>
        ${Object.entries(s.tabellen).map(([t, tijd]) => `<tr><td>${esc(TABELNAMEN[t] || t)}</td><td class="zacht">${tijd ? esc(relatief(tijd)) : "leeg"}</td></tr>`).join("")}
      </tbody></table></div>`,
    })}
  </div>`;
  toonKoppelingen(koppelingen);
}

// ── koppelingen ───────────────────────────────────────────────────────────────

function toonKoppelingen(lijst) {
  const ul = $("#koppelingen");
  ul.innerHTML = lijst.map(koppelingItem).join("");
  for (const k of lijst) {
    const li = $(`[data-dienst="${k.dienst}"]`, ul);
    $("[data-koppel]", li).onclick = () => openFormulier(li, k);
    const los = $("[data-ontkoppel]", li);
    if (los) los.onclick = () => ontkoppel(k);
  }
}

function koppelingItem(k) {
  const [klasse, ic, tekst] = STATUS[k.status] || STATUS.niet;
  const sinds = k.sinds ? `gekoppeld op ${datumKort(isoDatum(new Date(k.sinds)))}` : "";
  const detail = [k.account, sinds].filter(Boolean).map(esc).join(", ");
  const knop = k.status === "ok" ? "Opnieuw koppelen" : k.status === "opnieuw" ? "Opnieuw koppelen" : k.status === "script" ? "Koppel hier" : "Koppelen";
  return `<li class="koppel-kaart ${klasse}" data-dienst="${esc(k.dienst)}">
    <span class="icoon">${icoon(ic)}</span>
    <span class="koppel-kop"><span class="naam">${esc(k.naam)}</span><span class="pil ${klasse}">${tekst}</span></span>
    <span class="detail">${esc(k.uitleg)}${detail ? `<br>${detail}` : ""}${k.status === "opnieuw" ? '<br><span class="tekst">De bewaarde sleutel werkt niet meer. Koppel opnieuw om verder te gaan.</span>' : ""}</span>
    <span class="acties">
      <button class="knop ${k.status === "niet" || k.status === "opnieuw" ? "primair" : ""}" type="button" data-koppel>${knop}</button>
      ${k.status === "ok" || k.status === "opnieuw" ? '<button class="knop" type="button" data-ontkoppel>Ontkoppelen</button>' : ""}
    </span>
    <div class="koppel-vak" hidden></div>
  </li>`;
}

function veld(v, dienst) {
  const id = `v-${dienst}-${v.naam}`;
  if (v.type === "keuze") {
    const naam = (k) => (typeof k === "object" ? k.label : k === "kia" ? "Kia" : k === "hyundai" ? "Hyundai" : k);
    const waarde = (k) => (typeof k === "object" ? k.waarde : k);
    return `<label class="koppel-veld" for="${id}"><span>${esc(v.label)}</span>
      <select id="${id}" name="${v.naam}">${v.keuzes.map((k) => `<option value="${esc(waarde(k))}">${esc(naam(k))}</option>`).join("")}</select></label>`;
  }
  // Een Access Secret is geen wachtwoord van jou: de browser hoeft hem niet te bewaren.
  const auto = v.naam === "access_secret" ? "off" : v.type === "password" ? "current-password" : v.type === "email" || v.naam === "gebruiker" ? "username" : "off";
  return `<label class="koppel-veld" for="${id}"><span>${esc(v.label)}</span>
    <input id="${id}" name="${v.naam}" type="${v.type === "email" ? "email" : v.type === "password" ? "password" : v.type === "url" ? "url" : "text"}"
      autocomplete="${auto}" required spellcheck="false"></label>`;
}

/** Het vak met het formulier dicht; een brede kaart (met stappen) wordt weer gewoon. */
function sluit(vak) {
  vak.hidden = true;
  vak.closest(".koppel-kaart")?.classList.remove("breed");
}

function openFormulier(li, k) {
  const vak = $(".koppel-vak", li);
  if (!vak.hidden) return sluit(vak);
  for (const ander of $$(".koppel-vak")) sluit(ander);
  const verstuur = k.methode === "code" ? "Code aanvragen" : "Koppelen";
  const bezig = k.methode === "code" ? "Code aanvragen…" : k.dienst === "tuya" ? "Apparaten zoeken…" : "Bezig met inloggen…";
  const stappen = STAPPEN_HULP[k.dienst];
  const velden = `${k.velden.map((v) => veld(v, k.dienst)).join("")}
    ${HULP[k.dienst] ? `<p class="zacht klein">${esc(HULP[k.dienst])}</p>` : ""}
    <div class="formulier-acties">
      <button class="knop primair" type="submit">${verstuur}</button>
      <button class="knop" type="button" data-annuleer>Annuleren</button>
    </div>`;
  // Met stappen (Tuya): de kaart over de volle breedte, de stappen naast de velden.
  vak.innerHTML = stappen
    ? `<form class="koppel-form met-stappen">
        <div class="koppel-uitleg"><ol class="stappen">${stappen.stappen.map((st) => `<li>${st}</li>`).join("")}</ol>
          <p class="zacht klein">${esc(stappen.voet)}</p></div>
        <div class="koppel-velden">${velden}</div>
      </form>`
    : `<form class="koppel-form">${velden}</form>`;
  li.classList.toggle("breed", Boolean(stappen));
  vak.hidden = false;
  const form = $("form", vak);
  form.querySelector("input, select")?.focus({ preventScroll: Boolean(stappen) }); // de stappen blijven in beeld
  $("[data-annuleer]", form).onclick = () => sluit(vak);
  form.onsubmit = async (e) => {
    e.preventDefault();
    const knop = $("button[type=submit]", form);
    knop.disabled = true;
    knop.textContent = bezig;
    const gegevens = Object.fromEntries(new FormData(form).entries());
    try {
      const r = await api(`koppelingen/${k.dienst}`, { methode: "POST", body: gegevens });
      form.reset();
      if (r.code) return toonCode(vak, k, r.code);
      gekoppeld(k, r);
    } catch (err) {
      knop.disabled = false;
      knop.textContent = verstuur;
      meldFout(err);
    }
  };
}

function gekoppeld(k, r) {
  toast(`${k.naam} gekoppeld. ${r.bericht}. De eerste gegevens komen binnen een paar minuten.`);
  dispatchEvent(new Event("koppelingen")); // het blok Koppelingen in de zijbalk telt opnieuw
  toonKoppelingen(r.koppelingen);
}

// Koppelen met een code (BMW): jij bevestigt de code op de site van BMW, Thuis vraagt ondertussen
// steeds of dat al gebeurd is.
function toonCode(vak, k, code) {
  vak.innerHTML = `<div class="koppel-form koppel-code">
    <p>Open de site van BMW, log in met je BMW-account en bevestig deze code:</p>
    <p class="code" aria-label="Code ${esc(code.code.split("").join(" "))}">${esc(code.code)}</p>
    <div class="formulier-acties">
      <a class="knop primair" href="${esc(code.link)}" target="_blank" rel="noopener noreferrer">Open BMW en bevestig</a>
      <button class="knop" type="button" data-annuleer>Annuleren</button>
    </div>
    <p class="zacht klein" aria-live="polite" data-wacht>Wachten op je bevestiging. De code is geldig tot ${esc(klok(code.verloopt))}.</p>
  </div>`;
  let gestopt = false;
  $("[data-annuleer]", vak).onclick = () => {
    gestopt = true;
    sluit(vak);
  };
  const vraag = async (seconden) => {
    await new Promise((klaar) => setTimeout(klaar, seconden * 1000));
    if (gestopt || vak.hidden || !vak.isConnected) return;
    try {
      const r = await api(`koppelingen/${k.dienst}/controleer`, { methode: "POST" });
      if (gestopt || !vak.isConnected) return;
      if (r.wacht) return vraag(r.interval);
      gekoppeld(k, r);
    } catch (err) {
      if (!vak.isConnected) return;
      meldFout(err);
      $("[data-wacht]", vak).textContent = "Dit is niet gelukt. Klik op Annuleren en begin opnieuw met koppelen.";
    }
  };
  vraag(code.interval);
}

async function ontkoppel(k) {
  if (!confirm(`${k.naam} ontkoppelen? Thuis haalt dan geen gegevens meer op bij ${k.naam}. Je historie blijft bewaard.`)) return;
  try {
    toonKoppelingen(await api(`koppelingen/${k.dienst}`, { methode: "DELETE" }));
    toast(`${k.naam} ontkoppeld`);
    dispatchEvent(new Event("koppelingen"));
  } catch (err) {
    meldFout(err);
  }
}

// ── verzamelaar ───────────────────────────────────────────────────────────────

// Korte namen per stap; de bron (Frank Energie, Easee, …) staat erachter.
const STAPPEN = { prijzen: "Prijzen", verbruik: "Verbruik", lader: "Lader", auto: "Auto", bmw: "BMW", apparaten: "Apparaten", weer: "Weer", sturen: "Sturen", meldingen: "Meldingen" };
const HISTORIE = 8;

/** De laatste rondes als staafjes: hoog bij gelukt of mislukt, laag bij overgeslagen of niet gedraaid. */
function historie(lijst = []) {
  const soort = (u) => (u === "ok" ? "ok" : u?.startsWith("fout") ? "fout" : "");
  const titel = (h) => `${relatief(h.tijd)}: ${h.uitslag === "ok" ? "gelukt" : h.uitslag === "overgeslagen" ? "niet ingesteld" : "mislukt"}`;
  const leeg = Array(Math.max(0, HISTORIE - lijst.length)).fill('<i title="Niet gedraaid"></i>');
  const staafjes = lijst.slice(-HISTORIE).map((h) => `<i class="${soort(h.uitslag)}" title="${esc(titel(h))}"></i>`);
  const gelukt = lijst.filter((h) => h.uitslag === "ok").length;
  return `<span class="historie" role="img" aria-label="Laatste ${lijst.length} rondes: ${gelukt} gelukt">${[...leeg, ...staafjes].join("")}</span>`;
}

function bron(b) {
  const u = b.uitslag;
  const [klasse, ic, tekst] = !u
    ? ["", "pauze", "Nog niet gedraaid"]
    : u === "ok"
      ? ["ok", "vink", "Gelukt"]
      : u === "overgeslagen"
        ? ["", "pauze", "Niet ingesteld"]
        : ["fout", "kruis", "Mislukt"];
  const fout = u?.startsWith("fout") ? `<span class="tekst">${esc(u.replace(/^fout:\s*/, ""))}</span>` : "";
  const ok = u?.startsWith("fout") && b.laatst_ok ? `Laatst gelukt ${esc(relatief(b.laatst_ok))}` : "";
  const detail = [esc(b.naam.split(" · ")[0]), ok].filter(Boolean).join(" · ");
  return `<li class="${klasse}">
    <span class="icoon">${icoon(ic)}</span>
    <span class="tekst-regel"><span class="naam">${esc(STAPPEN[b.stap] || b.naam)}</span><span class="detail">${fout ? `${detail}<br>${fout}` : detail}</span></span>
    ${historie(b.historie)}
    <span class="pil ${klasse === "ok" ? "goed" : klasse}">${tekst}</span>
  </li>`;
}
