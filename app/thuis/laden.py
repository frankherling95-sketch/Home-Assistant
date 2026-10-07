"""Slim laden: plan maken met de planner en (optioneel) de Easee-lader sturen."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

from .config import TZ
from .connectors.easee import VERBONDEN
from .inzicht import laatste, prijzen
from .opslag import Opslag, lees_instellingen, nu
from .planner import Plan, PlanInput, PriceSlot, make_plan, next_deadline
from .schema import STUURACTIE

_LOG = logging.getLogger(__name__)

STANDAARD: dict[str, Any] = {
    "doel_pct": 80,
    "vertrek": "07:30",
    "capaciteit_kwh": 77.4,
    "vermogen_kw": 11.0,
    "rendement_pct": 90,
    "altijd_onder": 0.0,  # €/kWh
    "sturen": False,  # pas aan na een proefperiode waarin het plan klopt
}


def maak_plan(opslag: Opslag, instellingen: dict[str, Any], moment: datetime | None = None) -> dict[str, Any]:
    moment = moment or nu()
    lokaal = moment.astimezone(TZ)
    deadline = next_deadline(lokaal, time.fromisoformat(instellingen["vertrek"]))
    blokken = prijzen(opslag, "stroom", moment - timedelta(hours=1), moment + timedelta(days=2))
    auto = laatste(opslag, "auto_meting")
    soc = auto["accu_pct"] if auto else None

    plan: Plan = make_plan(
        PlanInput(
            now=moment,
            deadline=deadline,
            slots=[PriceSlot(b["van"], b["tot"], b["allin"]) for b in blokken],
            soc=soc,
            target_soc=float(instellingen["doel_pct"]),
            capacity_kwh=float(instellingen["capaciteit_kwh"]),
            power_kw=float(instellingen["vermogen_kw"]),
            efficiency=float(instellingen["rendement_pct"]) / 100,
            cheap_threshold=float(instellingen["altijd_onder"]),
        )
    )
    return {
        "nu_laden": plan.charge_now,
        "reden": plan.reason,
        "nodig_kwh": plan.needed_kwh,
        "kosten": plan.estimated_cost,
        "volledig": plan.complete,
        "vertrek": deadline.isoformat(),
        "prijs_nu": plan.current_price,
        "accu_pct": soc,
        "blokken": [
            {"van": s.start.isoformat(), "tot": s.end.isoformat(), "prijs": s.price} for s in plan.slots
        ],
    }


def stuur(opslag: Opslag, easee: Any, moment: datetime | None = None) -> str | None:
    """Pauzeer of hervat de lader volgens het plan. Geeft de uitgevoerde actie terug.

    Doet niets als sturen uit staat, als er geen auto aan de lader hangt, of als de
    vorige actie al dezelfde was (geen herhaalde commando's elke 15 minuten).
    """
    instellingen = lees_instellingen(opslag, STANDAARD)
    if not instellingen["sturen"]:
        return None
    lader = laatste(opslag, "lader_meting")
    if lader is None or lader["status"] not in VERBONDEN:
        return None

    plan = maak_plan(opslag, instellingen, moment)
    actie = "hervat" if plan["nu_laden"] else "pauzeer"
    vorige = opslag.lees(
        "SELECT actie FROM {stuuractie} WHERE lader_id = @id ORDER BY tijd DESC LIMIT 1", id=lader["lader_id"]
    )
    al_gedaan = vorige and vorige[0]["actie"] == actie
    # Na een nieuwe sessie (status springt) kan de lader zelf weer laden: dan opnieuw sturen.
    if al_gedaan and not (actie == "pauzeer" and lader["status"] == "laden"):
        return None

    (easee.hervat if actie == "hervat" else easee.pauzeer)(lader["lader_id"])
    opslag.voeg_toe(
        STUURACTIE,
        [{"tijd": moment or nu(), "lader_id": lader["lader_id"], "actie": actie, "reden": plan["reden"]}],
    )
    _LOG.info("Lader %s: %s (%s)", lader["lader_id"], actie, plan["reden"])
    return actie
