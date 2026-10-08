"""Kia / Hyundai Connect (Europa) via de community-bibliotheek hyundai_kia_connect_api.

Dezelfde bibliotheek die de Home Assistant-integratie gebruikt; de API is onofficieel en
verandert soms. Een update van de bibliotheek is dan meestal genoeg.

We lezen alleen de gecachte status: dat maakt de auto niet wakker en spaart de 12V-accu
en het dagelijkse API-quotum.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

REGIO_EUROPA = 1
MERK = {"kia": 1, "hyundai": 2, "genesis": 3}


class Kia:
    def __init__(self, gebruiker: str, wachtwoord: str, pin: str = "", merk: str = "kia") -> None:
        from hyundai_kia_connect_api import VehicleManager

        self.vm = VehicleManager(
            region=REGIO_EUROPA,
            brand=MERK.get(merk.lower(), 1),
            username=gebruiker,
            password=wachtwoord,
            pin=pin,
            language="nl",
        )

    def metingen(self) -> list[dict[str, Any]]:
        self.vm.check_and_refresh_token()
        self.vm.update_all_vehicles_with_cached_state()
        tijd = datetime.now(UTC)
        return [naar_rij(v, tijd) for v in self.vm.vehicles.values()]


def naar_rij(v: Any, tijd: datetime) -> dict[str, Any]:
    bijgewerkt = getattr(v, "last_updated_at", None)
    if isinstance(bijgewerkt, datetime) and bijgewerkt.tzinfo is None:
        bijgewerkt = bijgewerkt.replace(tzinfo=UTC)
    bereik = getattr(v, "ev_driving_range", None)
    return {
        "tijd": tijd,
        "auto_id": str(v.id),
        "naam": getattr(v, "name", None) or getattr(v, "model", None) or str(v.id),
        "accu_pct": _getal(getattr(v, "ev_battery_percentage", None)),
        "bereik_km": _getal(bereik),
        "ingeplugd": getattr(v, "ev_battery_is_plugged_in", None),
        "laadt": getattr(v, "ev_battery_is_charging", None),
        "bijgewerkt": bijgewerkt if isinstance(bijgewerkt, datetime) else None,
    }


def _getal(x: Any) -> float | None:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None
