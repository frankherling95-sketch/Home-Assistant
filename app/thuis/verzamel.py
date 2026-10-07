"""Verzamelaar: één ronde ophalen bij alle ingestelde bronnen en opslaan.

Draait in Google Cloud elke 15 minuten als Cloud Run-job (Cloud Scheduler start hem).
Lokaal: `python -m thuis.verzamel`.

Elke bron staat los: valt Kia uit, dan komen Frank en Easee gewoon binnen. De job eindigt
met exit-code 1 als er iets misging, zodat de fout zichtbaar is in Cloud Run.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import timedelta

from .config import TZ, Config
from .connectors.easee import Easee
from .connectors.frank import Frank, dagen
from .laden import stuur
from .opslag import Opslag, maak_opslag, nu, voeg_toe_gewijzigd
from .schema import AUTO, LADER, PRIJS, VERBRUIK

_LOG = logging.getLogger("thuis.verzamel")


def ronde(
    cfg: Config,
    opslag: Opslag,
    frank: Frank | None = None,
    easee: Easee | None = None,
    kia: object | None = None,
) -> dict[str, str]:
    """Voert alle stappen uit; geeft per stap 'ok', 'overgeslagen' of de fout terug."""
    vandaag = nu().astimezone(TZ).date()
    frank = frank or Frank(cfg.frank_email, cfg.frank_wachtwoord, cfg.frank_site)
    if easee is None and cfg.easee:
        easee = Easee(cfg.easee_gebruiker, cfg.easee_wachtwoord)
    if kia is None and cfg.kia:
        from .connectors.kia import Kia

        kia = Kia(cfg.kia_gebruiker, cfg.kia_wachtwoord, cfg.kia_pin, cfg.kia_merk)

    def prijzen() -> None:
        # Vandaag en morgen (morgen is er vanaf ±13:00).
        voeg_toe_gewijzigd(opslag, PRIJS, frank.prijzen(vandaag, vandaag + timedelta(days=2)))

    def verbruik() -> None:
        # Frank levert meterdata met vertraging; gisteren opnieuw ophalen maakt hem definitief.
        rijen = [r for dag in dagen(vandaag, terug=2, vooruit=0) for r in frank.verbruik(dag)]
        voeg_toe_gewijzigd(opslag, VERBRUIK, rijen)  # één laadtaak per ronde

    def lader() -> None:
        laders = easee.laders()
        if cfg.easee_lader:
            laders = [lad for lad in laders if lad["id"] == cfg.easee_lader]
        opslag.voeg_toe(LADER, [easee.meting(lad["id"], lad["naam"]) for lad in laders])

    def auto() -> None:
        opslag.voeg_toe(AUTO, kia.metingen())

    def sturen() -> None:
        stuur(opslag, easee)

    stappen: list[tuple[str, bool, Callable[[], None]]] = [
        ("prijzen", True, prijzen),
        ("verbruik", cfg.frank_login, verbruik),
        ("lader", easee is not None, lader),
        ("auto", kia is not None, auto),
        ("sturen", easee is not None, sturen),  # na lader en auto: rekent met verse metingen
    ]
    uitslag: dict[str, str] = {}
    for naam, actief, stap in stappen:
        if not actief:
            uitslag[naam] = "overgeslagen"
            continue
        try:
            stap()
            uitslag[naam] = "ok"
        except Exception as err:  # noqa: BLE001 — elke bron los laten falen
            _LOG.exception("Stap %s mislukt", naam)
            uitslag[naam] = f"fout: {err}"
    return uitslag


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config()
    opslag = maak_opslag(cfg)
    opslag.maak_tabellen()
    uitslag = ronde(cfg, opslag)
    _LOG.info("Uitslag: %s", uitslag)
    return 1 if any(v.startswith("fout") for v in uitslag.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
