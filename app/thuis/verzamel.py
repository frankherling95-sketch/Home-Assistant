"""Verzamelaar: één ronde ophalen bij alle ingestelde bronnen en opslaan.

Draait in Google Cloud elke 15 minuten als Cloud Run-job (Cloud Scheduler start hem), en
tussendoor als je in de app op Nu ophalen drukt (zie ophalen.py). Lokaal: `python -m thuis.verzamel`.

Elke bron staat los: valt de auto uit, dan komen Frank en Easee gewoon binnen. De uitslag per
stap komt in de rondelog (tabel `ronde`, pagina "Koppelingen"). De job eindigt met exit-code 1
als er iets misging, zodat de fout ook zichtbaar is in Cloud Run.

De accounts komen uit de kluis (gekoppeld in de app). Ververste tokens gaan aan het eind van de
ronde terug de kluis in; werkt een koppeling niet meer, dan krijgt die status "opnieuw".
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from datetime import timedelta

from . import ophalen
from .apparaten import meting
from .config import TZ, Config
from .connectors import KoppelingVerlopen
from .connectors.frank import dagen
from .connectors.weer import OpenMeteo
from .kluis import Kluis, maak_kluis, werk_bij
from .koppelingen import DIENSTEN, maak_connectoren, nieuwe_stand
from .laden import stuur
from .meldingen import controleer
from .opslag import Opslag, maak_opslag, nu, voeg_toe_gewijzigd
from .schema import APPARAAT, AUTO, AUTO_DETAILS, AUTO_LAADSESSIE, LADER, PRIJS, RONDE, VERBRUIK, WEER

_LOG = logging.getLogger("thuis.verzamel")
# Welke koppeling een stap gebruikt (voor de status "opnieuw koppelen").
DIENST_VAN_STAP = {
    "verbruik": "frank",
    "lader": "easee",
    "sturen": "easee",
    "auto": "kia",
    "bmw": "bmw",
    "apparaten": "tuya",
}


def ronde(
    cfg: Config,
    opslag: Opslag,
    frank: object | None = None,
    easee: object | None = None,
    kia: object | None = None,
    weer: OpenMeteo | None = None,
    bmw: object | None = None,
    chat: object | None = None,
    tuya: object | None = None,
    kluis: Kluis | None = None,
) -> dict[str, str]:
    """Voert alle stappen uit; geeft per stap 'ok', 'overgeslagen' of de fout terug."""
    begin = nu()
    vandaag = begin.astimezone(TZ).date()
    data = kluis.lees() if kluis else {}
    cfg = cfg.met_geheimen(data)
    c = maak_connectoren(cfg, data)
    c.frank, c.easee, c.kia, c.chat = frank or c.frank, easee or c.easee, kia or c.kia, chat or c.chat
    c.bmw = bmw or c.bmw
    c.tuya = tuya or c.tuya
    weer = weer or OpenMeteo(cfg.lat, cfg.lon)
    gevraagd = ophalen.gevraagd(data, begin)  # Nu ophalen in de app: de auto ook buiten zijn beurt
    verlopen: set[str] = set()

    def prijzen() -> None:
        # Vandaag en morgen (morgen is er vanaf ±13:00).
        voeg_toe_gewijzigd(opslag, PRIJS, c.frank.prijzen(vandaag, vandaag + timedelta(days=2)))

    def verbruik() -> None:
        # Frank levert meterdata met vertraging; gisteren opnieuw ophalen maakt hem definitief.
        rijen = [r for dag in dagen(vandaag, terug=2, vooruit=0) for r in c.frank.verbruik(dag)]
        voeg_toe_gewijzigd(opslag, VERBRUIK, rijen)  # één laadtaak per ronde

    def lader() -> None:
        laders = c.easee.laders()
        if cfg.easee_lader:
            laders = [lad for lad in laders if lad["id"] == cfg.easee_lader]
        opslag.voeg_toe(LADER, [c.easee.meting(lad["id"], lad["naam"]) for lad in laders])

    def auto() -> None:
        opslag.voeg_toe(AUTO, c.kia.metingen())
        opslag.voeg_toe(AUTO_DETAILS, getattr(c.kia, "details", []))

    def bmw_auto() -> None:
        # Niet elke ronde: BMW staat 50 verzoeken per dag toe (zie connectors/bmw.py).
        opslag.voeg_toe(AUTO, c.bmw.metingen(begin, gevraagd))
        opslag.voeg_toe(AUTO_DETAILS, c.bmw.details)
        voeg_toe_gewijzigd(opslag, AUTO_LAADSESSIE, c.bmw.laadsessies)  # elke dag de laatste 30 dagen

    def apparaten() -> None:
        # Eén verzoek voor alle apparaten met hun status; specificaties alleen van nieuwe apparaten.
        lijst = c.tuya.apparaten()
        c.tuya.zorg_voor_specs(lijst)
        opslag.voeg_toe(APPARAAT, [meting(a, c.tuya.specs.get(a["id"]), begin) for a in lijst])

    def temperatuur() -> None:
        voeg_toe_gewijzigd(opslag, WEER, weer.temperaturen(terug=2, vooruit=2))

    def sturen() -> None:
        stuur(opslag, c.easee)

    def meldingen() -> None:
        datum = vandaag.isoformat()
        extra = [
            (
                f"verlopen:{d}:{datum}",
                "koppeling_verlopen",
                f"De koppeling met {DIENSTEN[d]['naam']} werkt niet meer. Open Thuis, ga naar Koppelingen en koppel opnieuw.",
            )
            for d in sorted(verlopen)
        ]
        controleer(opslag, c.chat, extra=extra)

    stappen: list[tuple[str, bool, Callable[[], None]]] = [
        ("prijzen", True, prijzen),
        ("verbruik", c.frank_account, verbruik),
        ("lader", c.easee is not None, lader),
        ("auto", c.kia is not None, auto),
        ("bmw", c.bmw is not None, bmw_auto),
        ("apparaten", c.tuya is not None, apparaten),
        ("weer", True, temperatuur),
        ("sturen", c.easee is not None, sturen),  # na lader en auto: rekent met verse metingen
        ("meldingen", c.chat is not None, meldingen),  # als laatste: ziet alles van deze ronde
    ]
    uitslag: dict[str, str] = {}
    gelukt: set[str] = set()
    log = []
    for naam, actief, stap in stappen:
        start = time.monotonic()
        if not actief:
            uitslag[naam] = "overgeslagen"
        else:
            try:
                stap()
                uitslag[naam] = "ok"
                if naam in DIENST_VAN_STAP:
                    gelukt.add(DIENST_VAN_STAP[naam])
            except KoppelingVerlopen as err:
                _LOG.warning("Stap %s: %s", naam, err)
                verlopen.add(DIENST_VAN_STAP.get(naam, ""))
                uitslag[naam] = f"fout: {err}"
            except Exception as err:  # noqa: BLE001 — elke bron los laten falen
                _LOG.exception("Stap %s mislukt", naam)
                uitslag[naam] = f"fout: {err}"
        log.append(
            {
                "tijd": begin,
                "stap": naam,
                "uitslag": uitslag[naam][:500],
                "duur_s": round(time.monotonic() - start, 2),
            }
        )
    if kluis is not None:
        wijzig = nieuwe_stand(c, verlopen - {""}, gelukt - verlopen)
        if wijzig:
            try:
                werk_bij(kluis, wijzig)
            except Exception:  # noqa: BLE001 — volgende ronde opnieuw; tokens zijn dan mogelijk één keer oud
                _LOG.exception("Koppelingen niet bijgewerkt in de kluis")
    try:
        opslag.voeg_toe(RONDE, log)
    except Exception:  # noqa: BLE001 — de uitslag staat dan nog in de logs van Cloud Run
        _LOG.exception("Rondelog niet opgeslagen")
    return uitslag


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config()
    opslag = maak_opslag(cfg)
    opslag.maak_tabellen()
    uitslag = ronde(cfg, opslag, kluis=maak_kluis(cfg))
    _LOG.info("Uitslag: %s", uitslag)
    return 1 if any(v.startswith("fout") for v in uitslag.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
