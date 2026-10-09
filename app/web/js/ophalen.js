// Nu ophalen: de knop in de kop. Start meteen een ronde van de verzamelaar bij alle bronnen (ook de
// auto, binnen het dagmaximum van BMW) en tekent de pagina opnieuw zodra die ronde klaar is.
// Wanneer de server een ronde start en wanneer hij wacht op de geplande: thuis/ophalen.py.

import { api, meldFout, toast } from "./basis.js";

const EERSTE_KIJK_MS = 20_000; // eerder is een ronde nooit klaar (de job moet nog opstarten)
const KIJK_MS = 10_000; // daarna zo vaak kijken; elke keer één kleine query
const HOOGSTENS_MS = 5 * 60_000;

const slaap = (ms) => new Promise((klaar) => setTimeout(klaar, ms));
let bezig = false;

/**
 * @param {HTMLElement} knop draait zolang het ophalen duurt
 * @param {{laatsteRonde: () => Promise<string|null>, ververs: () => Promise<void>}} app
 *   laatsteRonde: begin van de nieuwste ronde volgens de rondelog; ververs: de pagina met verse gegevens
 */
export async function ophalen(knop, { laatsteRonde, ververs }) {
  if (bezig) return;
  bezig = true;
  knop.classList.add("bezig");
  knop.setAttribute("aria-busy", "true");
  try {
    let a = await api("ophalen", { methode: "POST" });
    for (let i = 0; a.actie === "wacht" && i < 3; i++) {
      toast(`Er loopt net een ronde. Over ${a.wacht_s} seconden haalt Thuis alles nog eens op.`);
      await slaap(a.wacht_s * 1000);
      a = await api("ophalen", { methode: "POST" });
    }
    toast(a.actie === "gepland" ? "De volgende ronde begint zo en haalt alles op." : "Alles wordt opgehaald…");
    if (await wachtOpRonde(a.vanaf, laatsteRonde)) {
      await ververs();
      toast("Alles is opnieuw opgehaald");
    } else {
      toast("Het ophalen duurt langer dan normaal. Kijk bij Koppelingen of de verzamelaar loopt.", { soort: "fout" });
    }
  } catch (err) {
    meldFout(err);
  } finally {
    bezig = false;
    knop.classList.remove("bezig");
    knop.removeAttribute("aria-busy");
  }
}

/** Wacht tot er een ronde is die na `vanaf` begon (de rondelog schrijft een ronde pas als hij klaar is). */
async function wachtOpRonde(vanaf, laatsteRonde) {
  const eind = Date.now() + HOOGSTENS_MS;
  await slaap(EERSTE_KIJK_MS);
  while (Date.now() < eind) {
    const laatste = await laatsteRonde();
    if (laatste && new Date(laatste) > new Date(vanaf)) return true;
    await slaap(KIJK_MS);
  }
  return false;
}
