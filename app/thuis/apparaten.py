"""Slimme apparaten (Tuya): wat de app toont en bedient, en wat de verzamelaar bewaart.

Tuya beschrijft elk apparaat met codes ("switch_1", "cur_power", "bright_value_v2") en ruwe
getallen. De specificatie zegt per code welk type het is, welk bereik het heeft en met hoeveel
decimalen een getal bedoeld is (scale: 2304 met scale 1 is 230,4). Hier wordt dat één vorm:

    {"id", "naam", "soort", "online", "aan", "schakelaars", "metingen", "toestand", "bediening", "status"}

- `soort`: stekker | schakelaar | lamp | klimaat | sensor | gordijn | overig (uit de categorie);
- `aan`: de hoofdschakelaar (bij een stekkerdoos: aan als één stopcontact aan is), None als er geen is;
- `metingen`: vermogen_w, spanning_v, stroom_a, energie_kwh, temperatuur, vochtigheid, accu_pct;
- `toestand`: wat een sensor meldt (open, dicht, beweging, rust, alarm, normaal);
- `bediening`: alles wat je kunt bedienen, met type, waarde en bereik in gewone eenheden;
- `status`: wat het apparaat verder meldt, ook in gewone eenheden.

De namen van de codes in het Nederlands staan in de web-app (js/paginas/apparaten.js).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from .inzicht import Prijslijst, dag_grenzen, prijzen
from .opslag import Opslag, nu, tegelijk

# Categorie van Tuya → soort in Thuis (https://developer.tuya.com/en/docs/iot/standarddescription).
CATEGORIEEN = {
    "stekker": "cz pc zndb dlq znjdq wkcz",
    "schakelaar": "kg tdq cjkg ckmkzq kgq",
    "lamp": "dj dd xdd fwd dc tgq tgkg sxd gyd tyndj fsd mbd",
    "klimaat": "wk wkf qn kt ktkzq fs kj cs jsq rs dbl nnq",
    "sensor": "wsdcg mcs pir ywbj rqbj sj ldcg co2bj pm25 hjjcy cobj zd sos jwbj",
    "gordijn": "cl clkg mc",
}
SOORT = {categorie: soort for soort, lijst in CATEGORIEEN.items() for categorie in lijst.split()}
SCHAKELAARS = (
    "switch",
    "switch_led",
    *(f"switch_{i}" for i in range(1, 7)),
    "switch_usb1",
    "switch_usb2",
)
METINGEN = {
    "vermogen_w": ("cur_power",),
    "spanning_v": ("cur_voltage",),
    "stroom_a": ("cur_current",),
    "energie_kwh": ("add_ele", "forward_energy_total", "total_forward_energy"),
    "temperatuur": ("va_temperature", "temp_current", "temp_indoor", "temperature"),
    "vochtigheid": ("va_humidity", "humidity_value", "humidity_indoor", "humidity"),
    "accu_pct": ("battery_percentage", "va_battery", "residual_electricity"),
}
# Zonder specificatie: de gebruikelijke decimalen van de standaardcodes.
STANDAARD_SCHAAL = {"cur_power": 1, "cur_voltage": 1, "add_ele": 3, "va_temperature": 1, "temp_current": 1}
TOESTAND: dict[str, Callable[[Any], str]] = {
    "doorcontact_state": lambda v: "open" if v is True else "dicht",
    "pir": lambda v: "beweging" if v == "pir" else "rust",
    "smoke_sensor_status": lambda v: "alarm" if v in ("alarm", "1") else "normaal",
    "smoke_sensor_state": lambda v: "alarm" if v in ("alarm", "1") else "normaal",
    "watersensor_state": lambda v: "alarm" if v == "alarm" else "normaal",
    "gas_sensor_status": lambda v: "alarm" if v == "alarm" else "normaal",
    "gas_sensor_state": lambda v: "alarm" if v in ("alarm", "1") else "normaal",
    "co_status": lambda v: "alarm" if v == "alarm" else "normaal",
}
EENHEDEN = {"℃": "°C", "℉": "°F", "": None}


def _eenheid(spec: dict[str, Any] | None) -> str | None:
    e = (spec or {}).get("eenheid")
    return EENHEDEN.get(e, e) if e is not None else None


def schaal(waarde: Any, spec: dict[str, Any] | None, code: str = "") -> Any:
    """Ruwe waarde → gewone eenheden (2304 met scale 1 → 230,4)."""
    if isinstance(waarde, bool) or not isinstance(waarde, (int, float)):
        return waarde
    s = (spec or {}).get("scale", STANDAARD_SCHAAL.get(code, 0) if not spec else 0)
    return waarde / 10**s if s else waarde


def _definitie(spec: dict[str, Any], code: str) -> dict[str, Any] | None:
    return (spec.get("functies") or {}).get(code) or (spec.get("status") or {}).get(code)


def soort_van(categorie: str, codes: set[str]) -> str:
    if categorie in SOORT:
        return SOORT[categorie]
    if "cur_power" in codes:
        return "stekker"
    if codes & {"bright_value", "bright_value_v2"}:
        return "lamp"
    if "temp_set" in codes:
        return "klimaat"
    if codes & (set(TOESTAND) | {"va_temperature", "va_humidity"}):
        return "sensor"
    return "schakelaar" if codes & set(SCHAKELAARS) else "overig"


def ruwe_status(apparaat: dict[str, Any]) -> dict[str, Any]:
    return {
        s["code"]: s.get("value")
        for s in apparaat.get("status") or []
        if isinstance(s, dict) and isinstance(s.get("code"), str)
    }


def _getoond(waarde: Any) -> bool:
    """Alleen gewone waarden in de lijst: geen JSON (kleuren, scènes) en geen lange teksten."""
    return isinstance(waarde, (bool, int, float)) or (isinstance(waarde, str) and 0 < len(waarde) <= 24)


def maak(apparaat: dict[str, Any], spec: dict[str, Any] | None) -> dict[str, Any]:
    """Een apparaat zoals Tuya het geeft (met status) → de vorm voor de app."""
    spec = spec or {}
    functies: dict[str, dict[str, Any]] = spec.get("functies") or {}
    ruw = ruwe_status(apparaat)
    waarden = {code: schaal(v, _definitie(spec, code), code) for code, v in ruw.items()}
    codes = set(ruw) | set(functies)

    schakelaars = [
        c for c in SCHAKELAARS if c in codes and (functies.get(c) or {}).get("type", "Boolean") == "Boolean"
    ]
    standen = [waarden[c] for c in schakelaars if isinstance(waarden.get(c), bool)]
    aan = any(standen) if standen else None

    metingen: dict[str, float] = {}
    for naam, kandidaten in METINGEN.items():
        code = next((c for c in kandidaten if isinstance(waarden.get(c), (int, float))), None)
        if code is None or isinstance(waarden[code], bool):
            continue
        w = float(waarden[code])
        if naam == "stroom_a" and (_eenheid(_definitie(spec, code)) or "mA") == "mA":
            w /= 1000
        metingen[naam] = round(w, 4)
    toestand = next((TOESTAND[c](ruw[c]) for c in TOESTAND if c in ruw), None)

    bediening = []
    for code, d in functies.items():
        item: dict[str, Any] = {"code": code, "type": d["type"], "waarde": waarden.get(code)}
        if d["type"] == "Integer":
            s = d.get("scale", 0)
            item |= {
                "min": d.get("min", 0) / 10**s,
                "max": d.get("max", 100) / 10**s,
                "stap": (d.get("step") or 1) / 10**s,
                "eenheid": _eenheid(d),
            }
        elif d["type"] == "Enum":
            item["keuzes"] = d.get("keuzes", [])
        bediening.append(item)

    status = [
        {"code": code, "waarde": w, "eenheid": _eenheid(_definitie(spec, code))}
        for code, w in waarden.items()
        if code not in functies and _getoond(w)
    ]
    return {
        "id": apparaat["id"],
        "naam": str(apparaat.get("name") or apparaat.get("product_name") or apparaat["id"]),
        "product": apparaat.get("product_name"),
        "categorie": apparaat.get("category"),
        "soort": soort_van(apparaat.get("category") or "", codes),
        "online": bool(apparaat.get("online", True)),
        "aan": aan,
        "schakelaars": schakelaars,
        "metingen": metingen,
        "toestand": toestand,
        "bediening": bediening,
        "status": status,
    }


def opdracht(spec: dict[str, Any] | None, code: str, waarde: Any) -> dict[str, Any]:
    """Wat de app wil ({code, waarde} in gewone eenheden) → een opdracht voor Tuya, binnen het bereik.

    ValueError als het apparaat die code niet kent of de waarde niet past.
    """
    d = ((spec or {}).get("functies") or {}).get(code)
    if d is None:
        raise ValueError("Dit apparaat kun je zo niet bedienen.")
    if d["type"] == "Boolean":
        if not isinstance(waarde, bool):
            raise ValueError("Verwacht aan of uit.")
        return {"code": code, "value": waarde}
    if d["type"] == "Enum":
        if waarde not in d.get("keuzes", []):
            raise ValueError("Deze keuze kent het apparaat niet.")
        return {"code": code, "value": waarde}
    if isinstance(waarde, bool) or not isinstance(waarde, (int, float)):
        raise ValueError("Verwacht een getal.")
    laag, hoog, stap = d.get("min", 0), d.get("max", 100), d.get("step") or 1
    ruw = round(waarde * 10 ** d.get("scale", 0))
    ruw = laag + round((ruw - laag) / stap) * stap  # op de stappen van het apparaat
    return {"code": code, "value": int(min(hoog, max(laag, ruw)))}


def meting(apparaat: dict[str, Any], spec: dict[str, Any] | None, tijd: datetime) -> dict[str, Any]:
    """Rij voor de tabel apparaat_meting."""
    a = maak(apparaat, spec)
    m = a["metingen"]
    status = {k: v for k, v in ruwe_status(apparaat).items() if not isinstance(v, str) or len(v) <= 200}
    return {
        "tijd": tijd,
        "apparaat_id": a["id"],
        "naam": a["naam"],
        "soort": a["soort"],
        "online": a["online"],
        "aan": a["aan"],
        "vermogen_w": m.get("vermogen_w"),
        "temperatuur": m.get("temperatuur"),
        "vochtigheid": m.get("vochtigheid"),
        "status": json.dumps(status, separators=(",", ":")),
    }


# ── live: wat Tuya nu meldt, voor de app ─────────────────────────────────────


class Live:
    """De apparaten zoals Tuya ze nu meldt, gedeeld door alle verzoeken van deze instantie.

    Hooguit VERS_S oud, zodat twee telefoons met de pagina open Tuya niet dubbel vragen (het
    proefabonnement telt elk verzoek). De sleutels en specificaties komen uit de kluis; die wordt
    opnieuw gelezen na KLUIS_S, of meteen na koppelen of ontkoppelen (`vergeet`).

    Na een opdracht geeft Tuya de nieuwe stand pas een tel later door. Tot VERWACHT_S na de
    opdracht toont de app daarom wat er gevraagd is, ook als Tuya nog de oude stand meldt.
    """

    VERS_S = 15.0
    MIN_S = 3.0  # ook met `vers` niet vaker dan dit
    KLUIS_S = 30 * 60.0
    VERWACHT_S = 10.0

    def __init__(
        self,
        lees_kluis: Callable[[], dict[str, Any]],
        maak_tuya: Callable[..., Any] | None = None,
        klok: Callable[[], float] = time.monotonic,
    ) -> None:
        if maak_tuya is None:
            from .connectors.tuya import Tuya

            maak_tuya = Tuya
        self._lees_kluis = lees_kluis
        self._maak_tuya = maak_tuya
        self._klok = klok
        self._slot = threading.Lock()
        self._tuya: Any = None
        self._sleutels: tuple | None = None
        self._kluis_tijd = float("-inf")
        self._lijst: list[dict[str, Any]] | None = None
        self._lijst_tijd = float("-inf")
        self._bijgewerkt: datetime | None = None
        self._verwacht: dict[tuple[str, str], tuple[Any, float]] = {}

    def vergeet(self) -> None:
        with self._slot:
            self._tuya, self._sleutels, self._lijst = None, None, None
            self._kluis_tijd = self._lijst_tijd = float("-inf")

    def _koppeling(self) -> Any:
        """De Tuya-connector volgens de kluis, of None als Tuya niet gekoppeld is."""
        if self._klok() - self._kluis_tijd < self.KLUIS_S:
            return self._tuya
        record = (self._lees_kluis().get("koppelingen") or {}).get("tuya")
        self._kluis_tijd = self._klok()
        if not record:
            self._tuya, self._sleutels, self._lijst = None, None, None
            return None
        sleutels = (record.get("regio"), record.get("access_id"), record.get("access_secret"))
        if self._tuya is None or sleutels != self._sleutels:
            self._tuya, self._sleutels, self._lijst = self._maak_tuya(record), sleutels, None
        else:
            self._tuya.specs.update(record.get("specs") or {})  # nieuwe apparaten uit de verzamelaar
        return self._tuya

    def lijst(self, vers: bool = False) -> dict[str, Any]:
        """{"gekoppeld", "apparaten", "bijgewerkt"}. Een fout van Tuya gaat door naar de aanroeper."""
        with self._slot:
            t = self._koppeling()
            if t is None:
                return {"gekoppeld": False, "apparaten": [], "bijgewerkt": None}
            leeftijd = self._klok() - self._lijst_tijd
            if self._lijst is None or leeftijd >= (self.MIN_S if vers else self.VERS_S):
                lijst = t.apparaten()
                t.zorg_voor_specs(lijst)
                self._lijst, self._lijst_tijd, self._bijgewerkt = lijst, self._klok(), nu()
            return self._antwoord(t)

    def _antwoord(self, t: Any) -> dict[str, Any]:
        moment = self._klok()
        self._verwacht = {k: v for k, v in self._verwacht.items() if v[1] > moment}
        apparaten = []
        for a in self._lijst or []:
            status = [
                {**s, "value": self._verwacht[(a["id"], s.get("code"))][0]}
                if (a["id"], s.get("code")) in self._verwacht
                else s
                for s in a.get("status") or []
            ]
            apparaten.append(maak({**a, "status": status}, t.specs.get(a["id"])))
        volgorde = ("stekker", "schakelaar", "lamp", "klimaat", "gordijn", "sensor", "overig")
        apparaten.sort(key=lambda a: (volgorde.index(a["soort"]), a["naam"].lower()))
        return {
            "gekoppeld": True,
            "apparaten": apparaten,
            "bijgewerkt": self._bijgewerkt.isoformat() if self._bijgewerkt else None,
        }

    def bedien(self, apparaat_id: str, wensen: list[dict[str, Any]]) -> dict[str, Any]:
        """Opdrachten ({code, waarde}) naar een apparaat; geeft het apparaat met de verwachte stand.

        LookupError: apparaat onbekend of offline; ValueError: opdracht past niet; fouten van Tuya
        gaan door.
        """
        with self._slot:
            t = self._koppeling()
            if t is None:
                raise LookupError("Tuya is niet gekoppeld.")
            if self._lijst is None:
                self._lijst, self._lijst_tijd, self._bijgewerkt = t.apparaten(), self._klok(), nu()
            apparaat = next((a for a in self._lijst if a["id"] == apparaat_id), None)
            if apparaat is None:
                raise LookupError("Dit apparaat kent Tuya niet (meer).")
            if not apparaat.get("online", True):
                raise LookupError(f"{apparaat.get('name') or 'Het apparaat'} is offline.")
            spec = t.specs.get(apparaat_id)
            opdrachten = [opdracht(spec, w.get("code", ""), w.get("waarde")) for w in wensen]
            t.stuur(apparaat_id, opdrachten)
            tot = self._klok() + self.VERWACHT_S
            for o in opdrachten:
                self._verwacht[(apparaat_id, o["code"])] = (o["value"], tot)
                if not any(s.get("code") == o["code"] for s in apparaat.get("status") or []):
                    apparaat.setdefault("status", []).append({"code": o["code"], "value": o["value"]})
            uit = self._antwoord(t)
            return next(a for a in uit["apparaten"] if a["id"] == apparaat_id)


# ── historie: wat de verzamelaar bewaarde ─────────────────────────────────────

GAT = timedelta(minutes=35)  # langer zonder meting: niet doortrekken (de ronde viel uit)


def historie(opslag: Opslag, apparaat_id: str, van: datetime, tot: datetime) -> dict[str, Any]:
    rijen = opslag.lees(
        "SELECT tijd, online, aan, vermogen_w, temperatuur, vochtigheid FROM {apparaat_meting} "
        "WHERE apparaat_id = @id AND tijd >= @van AND tijd < @tot ORDER BY tijd",
        id=apparaat_id,
        van=van,
        tot=tot,
    )
    return {
        "tijden": [r["tijd"].isoformat() for r in rijen],
        **{k: [r[k] for r in rijen] for k in ("online", "aan", "vermogen_w", "temperatuur", "vochtigheid")},
    }


def verbruik_vandaag(opslag: Opslag, dag: date) -> dict[str, Any]:
    """Geschat verbruik en kosten per apparaat met een vermogensmeting, uit de metingen per kwartier.

    Tussen twee metingen telt het gemiddelde vermogen (trapezium), tegen de stroomprijs van het
    kwartier waar het midden in valt. Een gat van meer dan GAT telt niet mee.
    """
    van, tot = dag_grenzen(dag)
    rijen, blokken = tegelijk(
        opslag,
        lambda: opslag.lees(
            "SELECT apparaat_id, tijd, vermogen_w FROM {apparaat_meting} "
            "WHERE tijd >= @van AND tijd < @tot AND vermogen_w IS NOT NULL ORDER BY apparaat_id, tijd",
            van=van,
            tot=tot,
        ),
        lambda: prijzen(opslag, "stroom", van, tot),
    )
    lijst = Prijslijst(blokken)
    per: dict[str, dict[str, float | None]] = {}
    vorige: dict[str, Any] | None = None
    for r in rijen:
        p = per.setdefault(r["apparaat_id"], {"kwh": 0.0, "kosten": 0.0})
        if vorige and vorige["apparaat_id"] == r["apparaat_id"] and r["tijd"] - vorige["tijd"] <= GAT:
            uren = (r["tijd"] - vorige["tijd"]).total_seconds() / 3600
            kwh = (vorige["vermogen_w"] + r["vermogen_w"]) / 2 * uren / 1000
            prijs = lijst.op(vorige["tijd"] + (r["tijd"] - vorige["tijd"]) / 2)
            p["kwh"] = (p["kwh"] or 0) + kwh
            p["kosten"] = None if prijs is None or p["kosten"] is None else p["kosten"] + kwh * prijs
        vorige = r
    afgerond = {
        k: {"kwh": round(v["kwh"] or 0, 4), "kosten": None if v["kosten"] is None else round(v["kosten"], 4)}
        for k, v in per.items()
    }
    kosten = [v["kosten"] for v in afgerond.values()]
    return {
        "datum": dag.isoformat(),
        "apparaten": afgerond,
        "kwh": round(sum(v["kwh"] for v in afgerond.values()), 4),
        "kosten": None if any(k is None for k in kosten) else round(sum(kosten), 4),
        "tot": max(r["tijd"] for r in rijen).isoformat() if rijen else None,  # de laatste meting
    }
