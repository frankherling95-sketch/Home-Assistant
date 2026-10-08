// Bronnen: hoe het met elke connector gaat, uit de rondelog van de verzamelaar.

import { api, esc, icoon, relatief } from "../basis.js";
import { kaart, melding, skeletKaart } from "../onderdelen.js";

const TABELNAMEN = {
  prijs: "Prijzen",
  verbruik: "Verbruik (meter)",
  lader_meting: "Metingen lader",
  auto_meting: "Metingen auto",
  instelling: "Instellingen",
  stuuractie: "Stuuracties",
  weer: "Weer",
  melding: "Meldingen",
  ronde: "Rondelog",
};

export async function toon(main, _params, ctx) {
  if (ctx.nieuw) main.innerHTML = `<div class="raster">${skeletKaart("b-8", { titel: "Verzamelaar", regels: 6 })}${skeletKaart("b-4", { titel: "Tabellen", regels: 6 })}</div>`;
  const s = await api("status", { vers: true });
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
      titel: "Verzamelaar",
      sub: laatste ? `laatste ronde ${relatief(laatste)}` : "",
      klasse: "b-8",
      id: "k-bronnen",
      inhoud: `${waarschuwing}<ul class="bronlijst">${s.bronnen.map(bron).join("")}</ul>`,
    })}
    ${kaart({
      titel: "Tabellen",
      sub: "laatst bijgewerkt",
      klasse: "b-4",
      id: "k-tabellen",
      inhoud: `<div class="tabel-wrap"><table class="tabel"><tbody>
        ${Object.entries(s.tabellen).map(([t, tijd]) => `<tr><td>${esc(TABELNAMEN[t] || t)}</td><td class="zacht">${tijd ? esc(relatief(tijd)) : "leeg"}</td></tr>`).join("")}
      </tbody></table></div>`,
    })}
  </div>`;
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
  const fout = u?.startsWith("fout") ? `<span class="tekst">${esc(u.replace(/^fout:\s*/, ""))}</span><br>` : "";
  const ok = u?.startsWith("fout") && b.laatst_ok ? `Laatst gelukt ${esc(relatief(b.laatst_ok))}` : "";
  return `<li class="${klasse}">
    <span class="icoon">${icoon(ic)}</span>
    <span class="naam">${esc(b.naam)}</span>
    <span class="pil ${klasse === "ok" ? "goed" : klasse}">${tekst}</span>
    <span class="detail">${fout}${b.tijd ? `Laatste ronde ${esc(relatief(b.tijd))}` : ""}${ok ? `. ${ok}` : ""}</span>
  </li>`;
}
