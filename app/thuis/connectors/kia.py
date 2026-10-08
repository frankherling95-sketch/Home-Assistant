"""Kia / Hyundai Connect (Europa) via de community-bibliotheek hyundai_kia_connect_api.

Dezelfde bibliotheek die de Home Assistant-integratie gebruikt; de API is onofficieel en
verandert soms. Een update van de bibliotheek is dan meestal genoeg.

We lezen alleen de gecachte status: dat maakt de auto niet wakker en spaart de 12V-accu
en het dagelijkse API-quotum.

Inloggen kan met wachtwoord (eenmalig bij het koppelen) of met het bewaarde token. Het token
wordt zonder wachtwoord en pincode opgeslagen; de bibliotheek ververst het zelf.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import KoppelFout, KoppelingVerlopen

REGIO_EUROPA = 1
MERK = {"kia": 1, "hyundai": 2, "genesis": 3}
NAAM = {"kia": "Kia Connect", "hyundai": "Hyundai Bluelink", "genesis": "Genesis Connected"}


def _zonder_geheimen(token: dict[str, Any]) -> dict[str, Any]:
    return {**token, "password": "", "pin": ""}


class Kia:
    def __init__(
        self,
        gebruiker: str = "",
        wachtwoord: str = "",
        pin: str = "",
        merk: str = "kia",
        token: dict[str, Any] | None = None,
    ) -> None:
        from hyundai_kia_connect_api import Token, VehicleManager

        self.merk = (merk or "kia").lower()
        self.met_wachtwoord = bool(wachtwoord)
        self.vm = VehicleManager(
            region=REGIO_EUROPA,
            brand=MERK.get(self.merk, 1),
            username=gebruiker or (token or {}).get("username", ""),
            password=wachtwoord,
            pin=pin,
            language="nl",
            token=Token.from_dict(token) if token else None,
        )
        self.gewijzigd = False

    @property
    def tokens(self) -> dict[str, Any]:
        return _zonder_geheimen(self.vm.token.to_dict()) if self.vm.token else {}

    def _ververs(self) -> None:
        try:
            if self.vm.check_and_refresh_token():
                self.gewijzigd = True
        except Exception as err:
            if self.met_wachtwoord:
                raise
            raise KoppelingVerlopen(NAAM.get(self.merk, "Kia"), type(err).__name__) from err

    def metingen(self) -> list[dict[str, Any]]:
        self._ververs()
        self.vm.update_all_vehicles_with_cached_state()
        tijd = datetime.now(UTC)
        return [naar_rij(v, tijd) for v in self.vm.vehicles.values()]

    @classmethod
    def koppel(cls, gebruiker: str, wachtwoord: str, merk: str = "kia") -> dict[str, Any]:
        """Eenmalig inloggen; geeft het token zonder wachtwoord en een bevestiging."""
        merk = (merk or "kia").lower()
        dienst = NAAM.get(merk, "Kia")
        try:
            k = cls(gebruiker, wachtwoord, "", merk)
            k._ververs()
        except Exception as err:
            if "OTP" in type(err).__name__:
                raise KoppelFout(f"{dienst} vraagt om een extra code (OTP); dat kan Thuis nog niet.") from err
            raise KoppelFout(
                f"Inloggen bij {dienst} mislukt: controleer je e-mailadres en wachtwoord."
            ) from err
        namen = [
            getattr(v, "name", None) or getattr(v, "model", None) or "auto" for v in k.vm.vehicles.values()
        ]
        return {
            "token": k.tokens,
            "merk": merk,
            "account": gebruiker,
            "bericht": f"Auto's: {', '.join(namen) or 'geen'}",
        }


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
