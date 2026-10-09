"""Kia / Hyundai Connect (Europa) via de community-bibliotheek hyundai_kia_connect_api.

Dezelfde bibliotheek die de Home Assistant-integratie gebruikt; de API is onofficieel en
verandert soms. Een update van de bibliotheek is dan meestal genoeg.

We lezen alleen de gecachte status: dat maakt de auto niet wakker en spaart de 12V-accu
en het dagelijkse API-quotum.

Inloggen kan met wachtwoord (eenmalig bij het koppelen) of met het bewaarde token. Het token
wordt zonder wachtwoord en pincode opgeslagen; de bibliotheek ververst het zelf.
"""

from __future__ import annotations

import json
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
        self.details: list[dict[str, Any]] = []

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
        """Rijen voor auto_meting; de rest staat daarna klaar in `details` (voor auto_details)."""
        self._ververs()
        self.vm.update_all_vehicles_with_cached_state()
        tijd = datetime.now(UTC)
        voertuigen = list(self.vm.vehicles.values())
        self.details = [
            {"tijd": tijd, "auto_id": str(v.id), "gegevens": json.dumps(d)}
            for v in voertuigen
            if (d := naar_details(v, self.merk))
        ]
        return [naar_rij(v, tijd) for v in voertuigen]

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
    laadt = getattr(v, "ev_battery_is_charging", None)
    return {
        "tijd": tijd,
        "auto_id": str(v.id),
        "naam": getattr(v, "name", None) or getattr(v, "model", None) or str(v.id),
        "accu_pct": _getal(getattr(v, "ev_battery_percentage", None)),
        "bereik_km": _km(v, "ev_driving_range"),
        "ingeplugd": getattr(v, "ev_battery_is_plugged_in", None),
        "laadt": laadt,
        "bijgewerkt": bijgewerkt if isinstance(bijgewerkt, datetime) else None,
        "km_stand": _km(v, "odometer"),
        "laadvermogen_kw": _getal(getattr(v, "ev_charging_power", None))
        if laadt
        else 0.0
        if laadt is False
        else None,
        "laadtijd_min": _getal(getattr(v, "ev_estimated_current_charge_duration", None)) if laadt else None,
        "kwh_tot_vol": None,
        "doel_pct": _getal(getattr(v, "ev_charge_limits_ac", None)),
        "capaciteit_kwh": _capaciteit(v),
    }


def _getal(x: Any) -> float | None:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _km(v: Any, naam: str) -> float | None:
    """Afstand in km; de bibliotheek geeft de eenheid apart (km of mi)."""
    x = _getal(getattr(v, naam, None))
    if x is None:
        return None
    eenheid = str(getattr(v, f"{naam}_unit", "") or "").lower()
    return round(x * 1.609344 if eenheid in ("mi", "miles") else x, 1)


def _capaciteit(v: Any) -> float | None:
    """Accu-inhoud in kWh. De bibliotheek geeft geen eenheid: wat niet past, laten we weg."""
    x = _getal(getattr(v, "ev_battery_capacity", None))
    if x is None:
        return None
    if 10_000 <= x <= 200_000:  # Wh
        x /= 1000
    return round(x, 1) if 10 <= x <= 200 else None


def _bar(waarde: Any, eenheid: Any) -> float | None:
    """Bandenspanning in bar; de auto toont psi, kPa of bar (PressureUnit 0, 1, 2)."""
    x = _getal(waarde)
    if x is None or eenheid is None:
        return None
    factor = {0: 0.0689476, 1: 0.01, 2: 1.0}.get(int(eenheid))
    return round(x * factor, 2) if factor else None


def _open(x: Any) -> str | None:
    return None if x is None else "OPEN" if x else "CLOSED"


WAARSCHUWINGEN = {
    "tire_pressure_all_warning_is_on": "Bandenspanning te laag",
    "washer_fluid_warning_is_on": "Ruitensproeiervloeistof bijvullen",
    "brake_fluid_warning_is_on": "Remvloeistof controleren",
    "oil_level_warning_is_on": "Oliepeil te laag",
    "smart_key_battery_warning_is_on": "Batterij van de sleutel bijna leeg",
    "battery_auxiliary_fail_warning_is_on": "Storing 12V-accu",
}


def naar_details(v: Any, merk: str = "kia") -> dict[str, Any]:
    """Dezelfde vorm als bij BMW (bmw_gegevens.naar_details), zodat de pagina Auto beide toont."""
    from .bmw_gegevens import zonder_leeg

    g = lambda naam: getattr(v, naam, None)  # noqa: E731
    meldingen = [{"naam": tekst} for attr, tekst in WAARSCHUWINGEN.items() if g(attr)]
    meldingen += [{"naam": str(d)} for d in (g("dtc_descriptions") or {}).values()]
    eenheid = g("tire_pressure_unit")
    lat, lon = _getal(g("location_latitude")), _getal(g("location_longitude"))
    jaar = g("year")
    uit = {
        "laden": {
            "vermogen_kw": _getal(g("ev_charging_power")),
            "resttijd_min": _getal(g("ev_estimated_current_charge_duration")),
            "doel_pct": _getal(g("ev_charge_limits_ac")),
            "doel_snelladen_pct": _getal(g("ev_charge_limits_dc")),
            "bereik_bij_doel_km": _km(v, "ev_target_range_charge_AC"),
            "capaciteit_kwh": _capaciteit(v),
            "gezondheid_pct": _getal(g("ev_battery_soh_percentage")),
            "klep_open": g("ev_charge_port_door_is_open"),
        },
        "rijden": {"km_stand": _km(v, "odometer")},
        "onderhoud": {
            "service_km": _km(v, "next_service_distance"),
            "meldingen": meldingen,
            "banden": {
                plek: {"bar": _bar(g(f"tire_pressure_{kant}"), eenheid)}
                for plek, kant in (
                    ("linksvoor", "front_left"),
                    ("rechtsvoor", "front_right"),
                    ("linksachter", "rear_left"),
                    ("rechtsachter", "rear_right"),
                )
            },
            "accu_12v_pct": _getal(g("car_battery_percentage")),
        },
        "beveiliging": {
            "slot": None if g("is_locked") is None else "LOCKED" if g("is_locked") else "UNLOCKED",
            "deuren_open": {
                "linksvoor": g("front_left_door_is_open"),
                "rechtsvoor": g("front_right_door_is_open"),
                "linksachter": g("back_left_door_is_open"),
                "rechtsachter": g("back_right_door_is_open"),
            },
            "ramen": {
                "linksvoor": _open(g("front_left_window_is_open")),
                "rechtsvoor": _open(g("front_right_window_is_open")),
                "linksachter": _open(g("back_left_window_is_open")),
                "rechtsachter": _open(g("back_right_window_is_open")),
            },
            "kofferbak_open": g("trunk_is_open"),
            "motorkap_open": g("hood_is_open"),
            "dak": _open(g("sunroof_is_open")),
        },
        "klimaat": {
            "activiteit": None
            if g("air_control_is_on") is None
            else "active"
            if g("air_control_is_on")
            else "inactive",
            "binnen_c": _getal(g("air_temperature")) if g("air_control_is_on") else None,
            "buiten_c": _getal(g("outside_temperature")),
        },
        "locatie": {"lat": round(lat, 5), "lon": round(lon, 5)} if lat and lon else None,
        "basis": {
            "merk": merk.capitalize(),
            "model": g("model"),
            "bouwdatum": str(jaar) if jaar else None,
            "software": g("software_version"),
        },
    }
    uit = zonder_leeg(uit)
    bijgewerkt = g("last_updated_at")
    if isinstance(bijgewerkt, datetime):
        if bijgewerkt.tzinfo is None:
            bijgewerkt = bijgewerkt.replace(tzinfo=UTC)
        for groep in ("laden", "rijden", "onderhoud", "beveiliging", "klimaat"):
            if groep in uit:
                uit[groep]["bijgewerkt"] = bijgewerkt.isoformat()
    return uit if set(uit) - {"basis"} else {}
