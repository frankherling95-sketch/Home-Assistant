"""Nagebootste Tuya-apparaten: een gewoon huishouden, om de pagina Apparaten zonder account te bekijken.

Lokaal met THUIS_DEMO_APPARATEN=1 (en Tuya als koppeling in de lokale kluis): de app vraagt dan
niet de cloud van Tuya maar `DemoTuya`, die opdrachten onthoudt zolang de server draait.
`vul_apparaten` zet een week aan metingen in de demo-database, zoals de verzamelaar ze elk
kwartier bewaart.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

from .apparaten import meting
from .config import TZ
from .opslag import Opslag
from .schema import APPARAAT

_B = {"type": "Boolean"}


def _getal(laag: int, hoog: int, schaal: int = 0, stap: int = 1, eenheid: str = "") -> dict[str, Any]:
    d = {"type": "Integer", "min": laag, "max": hoog, "scale": schaal, "step": stap}
    return d | ({"eenheid": eenheid} if eenheid else {})


def _keuze(*keuzes: str) -> dict[str, Any]:
    return {"type": "Enum", "keuzes": list(keuzes)}


_METING = {
    "cur_power": _getal(0, 99999, 1, eenheid="W"),
    "cur_voltage": _getal(0, 3000, 1, eenheid="V"),
    "cur_current": _getal(0, 30000, eenheid="mA"),
    "add_ele": _getal(0, 50000, 3, 100, "kWh"),
}
_STEKKER = {
    "functies": {
        "switch_1": _B,
        "countdown_1": _getal(0, 86400, eenheid="s"),
        "relay_status": _keuze("power_off", "power_on", "last"),
        "light_mode": _keuze("relay", "pos", "none"),
        "child_lock": _B,
    },
    "status": _METING,
}
_LAMP = {
    "functies": {
        "switch_led": _B,
        "work_mode": _keuze("white", "colour", "scene", "music"),
        "bright_value_v2": _getal(10, 1000),
        "temp_value_v2": _getal(0, 1000),
        "countdown_1": _getal(0, 86400, eenheid="s"),
    },
    "status": {},
}
DEMO_SPECS: dict[str, dict[str, Any]] = {
    "demo-wasmachine": _STEKKER,
    "demo-vaatwasser": _STEKKER,
    "demo-netwerk": _STEKKER,
    "demo-tv": {
        "functies": {"switch_1": _B, "switch_2": _B, "switch_3": _B, "switch_usb1": _B, "child_lock": _B},
        "status": _METING,
    },
    "demo-lamp-woonkamer": _LAMP,
    "demo-ledstrip": _LAMP,
    "demo-lamp-hal": _LAMP,
    "demo-radiator": {
        "functies": {
            "mode": _keuze("auto", "manual", "eco", "comfort"),
            "temp_set": _getal(50, 300, 1, 5, "℃"),
            "child_lock": _B,
            "window_check": _B,
        },
        "status": {
            "temp_current": _getal(-100, 500, 1, eenheid="℃"),
            "battery_percentage": _getal(0, 100, eenheid="%"),
        },
    },
    "demo-zolder": {
        "functies": {},
        "status": {
            "va_temperature": _getal(-200, 600, 1, eenheid="℃"),
            "va_humidity": _getal(0, 100, eenheid="%"),
            "battery_percentage": _getal(0, 100, eenheid="%"),
        },
    },
    "demo-achterdeur": {
        "functies": {},
        "status": {"doorcontact_state": _B, "battery_percentage": _getal(0, 100, eenheid="%")},
    },
    "demo-rolluik": {
        "functies": {
            "control": _keuze("open", "stop", "close"),
            "percent_control": _getal(0, 100, eenheid="%"),
        },
        "status": {"percent_state": _getal(0, 100, eenheid="%"), "work_state": _keuze("opening", "closing")},
    },
}
DEMO_APPARATEN: list[dict[str, Any]] = [
    {
        "id": "demo-wasmachine",
        "name": "Wasmachine",
        "category": "cz",
        "product_name": "Slimme stekker met meting",
    },
    {
        "id": "demo-vaatwasser",
        "name": "Vaatwasser",
        "category": "cz",
        "product_name": "Slimme stekker met meting",
    },
    {
        "id": "demo-netwerk",
        "name": "Netwerkkast",
        "category": "cz",
        "product_name": "Slimme stekker met meting",
    },
    {"id": "demo-tv", "name": "Tv-meubel", "category": "pc", "product_name": "Stekkerdoos 3 + USB"},
    {
        "id": "demo-lamp-woonkamer",
        "name": "Lamp woonkamer",
        "category": "dj",
        "product_name": "Lamp E27 wit en kleur",
    },
    {"id": "demo-ledstrip", "name": "Ledstrip keuken", "category": "dd", "product_name": "Ledstrip 5 m"},
    {
        "id": "demo-lamp-hal",
        "name": "Plafondlamp hal",
        "category": "dj",
        "product_name": "Lamp E27 wit",
        "online": False,
    },
    {
        "id": "demo-radiator",
        "name": "Radiator slaapkamer",
        "category": "wkf",
        "product_name": "Radiatorkraan",
    },
    {
        "id": "demo-zolder",
        "name": "Zolder",
        "category": "wsdcg",
        "product_name": "Temperatuur- en vochtsensor",
    },
    {"id": "demo-achterdeur", "name": "Achterdeur", "category": "mcs", "product_name": "Deur- en raamsensor"},
    {"id": "demo-rolluik", "name": "Rolluik slaapkamer", "category": "cl", "product_name": "Rolluikmotor"},
]
# Stand nu, in ruwe waarden zoals Tuya ze geeft.
BEGINSTAND: dict[str, dict[str, Any]] = {
    "demo-wasmachine": {"switch_1": True, "cur_power": 4862, "cur_voltage": 2314, "cur_current": 2190,
                        "add_ele": 128, "countdown_1": 0, "relay_status": "last", "light_mode": "relay",
                        "child_lock": False},
    "demo-vaatwasser": {"switch_1": False, "cur_power": 0, "cur_voltage": 2316, "cur_current": 0, "add_ele": 0,
                        "countdown_1": 0, "relay_status": "last", "light_mode": "relay", "child_lock": False},
    "demo-netwerk": {"switch_1": True, "cur_power": 236, "cur_voltage": 2311, "cur_current": 118, "add_ele": 6,
                     "countdown_1": 0, "relay_status": "power_on", "light_mode": "none", "child_lock": True},
    "demo-tv": {"switch_1": True, "switch_2": True, "switch_3": False, "switch_usb1": True, "cur_power": 843,
                "cur_voltage": 2312, "cur_current": 402, "add_ele": 21, "child_lock": False},
    "demo-lamp-woonkamer": {"switch_led": True, "work_mode": "white", "bright_value_v2": 620, "temp_value_v2": 280,
                            "countdown_1": 0},
    "demo-ledstrip": {"switch_led": False, "work_mode": "colour", "bright_value_v2": 1000, "temp_value_v2": 500,
                      "countdown_1": 0},
    "demo-lamp-hal": {"switch_led": False, "work_mode": "white", "bright_value_v2": 800, "temp_value_v2": 0,
                      "countdown_1": 0},
    "demo-radiator": {"mode": "auto", "temp_set": 185, "temp_current": 192, "child_lock": False,
                      "window_check": True, "battery_percentage": 74},
    "demo-zolder": {"va_temperature": 168, "va_humidity": 61, "battery_percentage": 80},
    "demo-achterdeur": {"doorcontact_state": False, "battery_percentage": 90},
    "demo-rolluik": {"control": "stop", "percent_control": 100, "percent_state": 100, "work_state": "opening"},
}  # fmt: skip
# Vermogen (ruw, W × 10) als het stopcontact aan is en het apparaat niets bijzonders doet.
_AAN = {"demo-wasmachine": 12, "demo-vaatwasser": 18, "demo-netwerk": 236}
_TV = {"switch_1": 600, "switch_2": 220, "switch_3": 150, "switch_usb1": 23}

_stand: dict[str, dict[str, Any]] = {}  # gedeeld: de app maakt soms een nieuwe DemoTuya


class DemoTuya:
    """Zelfde gedrag als connectors.tuya.Tuya, zonder cloud."""

    def __init__(self, record: dict[str, Any] | None = None, client: Any = None) -> None:
        self.specs = dict(DEMO_SPECS)
        self.gewijzigd = False
        if not _stand:
            _stand.update({k: dict(v) for k, v in BEGINSTAND.items()})

    @property
    def record(self) -> dict[str, Any]:
        return {"specs": self.specs}

    def apparaten(self) -> list[dict[str, Any]]:
        return [
            {"online": True, **a, "status": [{"code": c, "value": w} for c, w in _stand[a["id"]].items()]}
            for a in DEMO_APPARATEN
        ]

    def zorg_voor_specs(self, apparaten: list[dict[str, Any]]) -> None:
        pass

    def stuur(self, apparaat_id: str, opdrachten: list[dict[str, Any]]) -> None:
        s = _stand[apparaat_id]
        for o in opdrachten:
            s[o["code"]] = o["value"]
        if apparaat_id == "demo-tv":
            s["cur_power"] = sum(w for code, w in _TV.items() if s.get(code))
        elif "switch_1" in s and "cur_power" in s:
            s["cur_power"] = (s["cur_power"] or _AAN.get(apparaat_id, 0)) if s["switch_1"] else 0
        if "cur_power" in s:
            s["cur_current"] = round(s["cur_power"] / 10 / 231 * 1000)
        if apparaat_id == "demo-rolluik":
            if s.get("control") in ("open", "close"):
                s["percent_control"] = 100 if s["control"] == "open" else 0
            s["percent_state"] = s["percent_control"]


def vul_apparaten(opslag: Opslag, eind: datetime, dagen: int = 8, seed: int = 11) -> None:
    """Metingen per kwartier tot `eind`, zoals de verzamelaar ze bewaart; de laatste is de stand nu."""
    rnd = random.Random(seed)
    specs = DEMO_SPECS
    eind = eind.replace(minute=eind.minute // 15 * 15, second=40, microsecond=0)
    begin = eind - timedelta(days=dagen)
    was_start = eind - timedelta(minutes=50)  # nu bezig met wassen
    wasdagen = {
        (eind - timedelta(days=d)).astimezone(TZ).date(): rnd.uniform(9, 18) for d in range(1, dagen, 2)
    }
    rijen = []
    t = begin
    while t <= eind:
        lok = t.astimezone(TZ)
        uur = lok.hour + lok.minute / 60
        avond = 18 <= uur < 23
        golf = math.sin((uur - 9) / 24 * 2 * math.pi)  # warmst rond 15:00
        stand: dict[str, dict[str, Any]] = {k: dict(v) for k, v in BEGINSTAND.items()}

        # Wasmachine: om de dag een was van anderhalf uur (eerst opwarmen, dan wassen, dan centrifugeren).
        w = stand["demo-wasmachine"]
        start = wasdagen.get(lok.date())
        minuten = (uur - start) * 60 if start is not None else (t - was_start).total_seconds() / 60
        if 0 <= minuten < 90:
            w["cur_power"] = 21000 if minuten < 15 else 4500 if minuten >= 75 else rnd.randint(1800, 3200)
        else:
            w["cur_power"] = 12
        # Vaatwasser: elke avond om half tien, twee uur; sinds vanochtend staat het stopcontact uit.
        v = stand["demo-vaatwasser"]
        minuten = (uur - 21.5) * 60 if uur >= 21.5 else (uur + 2.5) * 60
        v["switch_1"] = t < eind - timedelta(hours=10)
        v["cur_power"] = (
            0
            if not v["switch_1"]
            else 19000
            if minuten < 20 or 100 <= minuten < 115
            else 900
            if minuten < 120
            else 18
        )
        stand["demo-netwerk"]["cur_power"] = 230 + rnd.randint(0, 14)
        tv = stand["demo-tv"]
        tv["switch_3"] = False
        tv["cur_power"] = rnd.randint(780, 1100) if avond else 60
        lamp = stand["demo-lamp-woonkamer"]
        lamp["switch_led"] = avond or 7 <= uur < 8
        stand["demo-ledstrip"]["switch_led"] = 17.5 <= uur < 19.5
        r = stand["demo-radiator"]
        r["temp_set"] = 185 if 6 <= uur < 23 else 160
        r["temp_current"] = round(r["temp_set"] + 4 * golf + rnd.uniform(-2, 2))
        z = stand["demo-zolder"]
        z["va_temperature"] = round(165 + 25 * golf + rnd.uniform(-3, 3))
        z["va_humidity"] = round(62 - 6 * golf + rnd.uniform(-1.5, 1.5))
        stand["demo-achterdeur"]["doorcontact_state"] = rnd.random() < 0.04 and 7 <= uur < 22
        stand["demo-rolluik"]["percent_state"] = 0 if uur < 7.5 or uur >= 22.5 else 100

        for a in DEMO_APPARATEN:
            s = BEGINSTAND[a["id"]] if t == eind else stand[a["id"]]
            online = a.get("online", True) or t < eind - timedelta(days=2)
            ruw = {**a, "online": online, "status": [{"code": c, "value": w} for c, w in s.items()]}
            rijen.append(meting(ruw, specs[a["id"]], t))
        t += timedelta(minutes=15)
    opslag.voeg_toe(APPARAAT, rijen)
