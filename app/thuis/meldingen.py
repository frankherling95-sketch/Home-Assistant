"""Meldingen in een Google Chat-ruimte (inkomende webhook).

Elke melding heeft een sleutel; wat al in de tabel `melding` staat, gaat niet nog een keer.
Zo kan de verzamelaar elke 15 minuten kijken zonder dat je dubbele berichten krijgt.

- Negatieve stroomprijzen morgen (zodra de prijzen van morgen er zijn, ±13:00)
- De lader meldt een fout
- Een laadsessie is klaar (auto vol of uitgeplugd)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from .inzicht import dag_grenzen, lader_metingen, lokaal, prijzen
from .inzichten import aaneengesloten, euro, getal, klok
from .laden import STANDAARD
from .opslag import Opslag, lees_instellingen, nu
from .schema import MELDING
from .sessies import laadsessies

_LOG = logging.getLogger(__name__)


class GoogleChat:
    def __init__(self, webhook: str, client: httpx.Client | None = None) -> None:
        self.webhook = webhook
        self.client = client or httpx.Client(timeout=30)

    def stuur(self, tekst: str) -> None:
        r = self.client.post(self.webhook, json={"text": tekst})
        r.raise_for_status()


Kandidaat = tuple[str, str, str]  # (sleutel, soort, tekst)


def negatief_morgen(opslag: Opslag, moment: datetime) -> list[Kandidaat]:
    morgen = lokaal(moment) + timedelta(days=1)
    negatief = [b for b in prijzen(opslag, "stroom", *dag_grenzen(morgen)) if b["allin"] < 0]
    if not negatief:
        return []
    tijden = ", ".join(f"{klok(g[0]['van'])}–{klok(g[-1]['tot'])}" for g in aaneengesloten(negatief))
    laagste = min(b["allin"] for b in negatief)
    tekst = (
        f"Morgen negatieve stroomprijs: {tijden} (laagste {euro(laagste, 3)}/kWh). "
        "Een goed moment om te laden of de wasmachine te laten draaien."
    )
    return [(f"negatief:{morgen.isoformat()}", "negatieve_prijzen", tekst)]


def lader_fout(opslag: Opslag, moment: datetime) -> list[Kandidaat]:
    metingen = lader_metingen(opslag, moment - timedelta(hours=24), moment + timedelta(seconds=1))
    uit: list[Kandidaat] = []
    for lid in {m["lader_id"] for m in metingen}:
        eigen = [m for m in metingen if m["lader_id"] == lid]
        if eigen[-1]["status"] != "fout" or eigen[-1]["tijd"] < moment - timedelta(hours=1):
            continue
        begin = eigen[-1]
        for m in reversed(eigen):  # begin van de huidige reeks foutmeldingen
            if m["status"] != "fout":
                break
            begin = m
        naam = begin.get("naam") or lid
        uit.append(
            (
                f"laderfout:{lid}:{begin['tijd'].isoformat()}",
                "lader_fout",
                f"Lader {naam} meldt een fout (sinds {klok(begin['tijd'])}). Kijk in de Easee-app.",
            )
        )
    return uit


def sessie_klaar(opslag: Opslag, moment: datetime) -> list[Kandidaat]:
    vermogen = float(lees_instellingen(opslag, STANDAARD)["vermogen_kw"])
    uit: list[Kandidaat] = []
    for s in laadsessies(opslag, moment - timedelta(days=2), moment, vermogen):
        if not s["klaar"] or s["kwh"] < 1 or s["eind"] < moment - timedelta(hours=6):
            continue  # nog bezig, te klein, of al lang geleden (bijv. bij de eerste ronde)
        tekst = f"Laden klaar: {getal(s['kwh'])} kWh voor {euro(s['kosten'])} (gemiddeld {euro(s['gem_prijs'], 3)}/kWh)"
        if s["besparing"] is not None and s["besparing"] >= 0.01:
            tekst += f", {euro(s['besparing'])} goedkoper dan direct laden"
        uit.append((f"sessie:{s['lader_id']}:{s['start'].isoformat()}", "sessie_klaar", tekst + "."))
    return uit


CONTROLES = (negatief_morgen, lader_fout, sessie_klaar)


def controleer(opslag: Opslag, chat: Any, moment: datetime | None = None) -> list[str]:
    """Stuur nieuwe meldingen; geeft de sleutels van wat er verstuurd is terug."""
    moment = moment or nu()
    al = {
        r["sleutel"]
        for r in opslag.lees(
            "SELECT sleutel FROM {melding} WHERE tijd >= @sinds", sinds=moment - timedelta(days=14)
        )
    }
    verstuurd, fouten = [], []
    for controle in CONTROLES:
        for sleutel, soort, tekst in controle(opslag, moment):
            if sleutel in al:
                continue
            try:
                chat.stuur(tekst)
            except Exception as err:  # noqa: BLE001 — de andere meldingen gaan gewoon door
                _LOG.exception("Melding %s niet verstuurd", sleutel)
                fouten.append(f"{soort}: {err}")
                continue
            opslag.voeg_toe(MELDING, [{"sleutel": sleutel, "tijd": moment, "soort": soort, "tekst": tekst}])
            verstuurd.append(sleutel)
    if fouten:
        raise RuntimeError("; ".join(fouten))
    return verstuurd
