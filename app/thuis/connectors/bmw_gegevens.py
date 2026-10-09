"""Welke gegevens Thuis bij BMW CarData vraagt, en hoe die in Thuis terechtkomen.

BMW geeft elke waarde als tekst met een eenheid en een tijdstip, bijvoorbeeld
{"value": "64", "unit": "%", "timestamp": "2026-10-08T11:55:00Z"}. Ongeldige waarden
("INVALID", "-NA-") tellen als ontbrekend. Wat een auto doorgeeft, hangt af van model en
bouwjaar: alles hieronder mag ontbreken.

De namen komen uit de telematicacatalogus van BMW (https://bmw-cardata.bmwgroup.com).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

# ── kern: accu, bereik, stekker (tabel auto_meting) ───────────────────────────
ACCU = (
    "vehicle.powertrain.electric.battery.stateOfCharge.displayed",
    "vehicle.drivetrain.batteryManagement.header",
    "vehicle.drivetrain.electricEngine.charging.level",
)
BEREIK = (
    "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange",
    "vehicle.drivetrain.electricEngine.remainingElectricRange",
)
STEKKER = "vehicle.powertrain.tractionBattery.charging.port.anyPosition.isPlugged"
LAADPOORT = "vehicle.body.chargingPort.status"  # CONNECTED, DISCONNECTED
LAADSTATUS = "vehicle.drivetrain.electricEngine.charging.status"  # CHARGINGACTIVE, NOCHARGING, …
HV_STATUS = "vehicle.drivetrain.electricEngine.charging.hvStatus"  # CHARGING, NOT_CHARGING, …
KERN = (*ACCU, *BEREIK, STEKKER, LAADPOORT, LAADSTATUS, HV_STATUS)

# ── laden ─────────────────────────────────────────────────────────────────────
LAADVERMOGEN = "vehicle.powertrain.electric.battery.charging.power"  # W
LAADTIJD = "vehicle.drivetrain.electricEngine.charging.timeRemaining"  # min
TOT_VOL = "vehicle.drivetrain.electricEngine.charging.smeEnergyDeltaFullyCharged"  # kWh
LAADDOEL = "vehicle.powertrain.electric.battery.stateOfCharge.target"  # %, in stappen van 10
BEREIK_DOEL = "vehicle.powertrain.electric.range.target"  # bereik bij het laaddoel
CAPACITEIT = (
    "vehicle.drivetrain.batteryManagement.maxEnergy",  # bruikbaar, nu
    "vehicle.drivetrain.electricEngine.hvsMaxEnergyAbsolute",
)
CAPACITEIT_NIEUW = "vehicle.drivetrain.batteryManagement.batterySizeMax"
GEZONDHEID = "vehicle.powertrain.electric.battery.stateOfHealth.displayed"  # %
AC_LIMIET = "vehicle.powertrain.electric.battery.charging.acLimit.selected"  # A
AC_STROOM = "vehicle.drivetrain.electricEngine.charging.acAmpere"
AC_SPANNING = "vehicle.drivetrain.electricEngine.charging.acVoltage"
FASEN = "vehicle.drivetrain.electricEngine.charging.phaseNumber"  # 1-PHASES, 3-PHASES, …
LAADMETHODE = "vehicle.drivetrain.electricEngine.charging.method"  # AC_TYPE2PLUG, DC, …
VOORKEUR = "vehicle.drivetrain.electricEngine.charging.profile.preference"
EINDE = "vehicle.drivetrain.electricEngine.charging.lastChargingReason"
RESULTAAT = "vehicle.drivetrain.electricEngine.charging.lastChargingResult"
KABELSLOT = "vehicle.body.chargingPort.lockedStatus"
KLEP = "vehicle.powertrain.tractionBattery.charging.port.anyPosition.flap.isOpen"

# ── rijden ────────────────────────────────────────────────────────────────────
KM_STAND = "vehicle.vehicle.travelledDistance"
VERBRUIK = "vehicle.drivetrain.avgElectricRangeConsumption"  # kWh/100 km
WEEK_KM = "vehicle.vehicle.averageWeeklyDistanceShortTerm"
WEEK_KM_LANG = "vehicle.vehicle.averageWeeklyDistanceLongTerm"
RIT_EIND = "vehicle.trip.segment.end.time"
RIT_KM_STAND = "vehicle.trip.segment.end.travelledDistance"  # kilometerstand na de laatste rit
RIT_ACCU = "vehicle.trip.segment.end.drivetrain.batteryManagement.hvSoc"
RIT_TERUG = "vehicle.trip.segment.accumulated.drivetrain.electricEngine.recuperationTotal"
STIJL_OPTREKKEN = "vehicle.trip.segment.accumulated.acceleration.starsAverage"  # 0–5 sterren
STIJL_ANTICIPEREN = "vehicle.trip.segment.accumulated.chassis.brake.starsAverage"

# ── onderhoud ─────────────────────────────────────────────────────────────────
SERVICE_KM = "vehicle.status.serviceDistance.next"
APK = "vehicle.status.serviceTime.inspectionDateLegal"
SERVICES = "vehicle.status.conditionBasedServices"
MELDINGEN = "vehicle.status.checkControlMessages"
BANDEN = {
    "linksvoor": "vehicle.chassis.axle.row1.wheel.left.tire",
    "rechtsvoor": "vehicle.chassis.axle.row1.wheel.right.tire",
    "linksachter": "vehicle.chassis.axle.row2.wheel.left.tire",
    "rechtsachter": "vehicle.chassis.axle.row2.wheel.right.tire",
}  # + .pressure en .pressureTarget, in kPa
ACCU_12V = "vehicle.electricalSystem.battery.stateOfCharge"
ACCU_12V_VOLT = "vehicle.electricalSystem.battery.voltage"

# ── beveiliging (bestuurder links, zoals in Nederland) ────────────────────────
SLOT = "vehicle.cabin.door.lock.status"  # SECURED, LOCKED, SELECTIVE-LOCKED, UNLOCKED
ALARM = "vehicle.vehicle.antiTheftAlarmSystem.alarm.armStatus"
DEUREN = {
    "linksvoor": "vehicle.cabin.door.row1.driver.isOpen",
    "rechtsvoor": "vehicle.cabin.door.row1.passenger.isOpen",
    "linksachter": "vehicle.cabin.door.row2.driver.isOpen",
    "rechtsachter": "vehicle.cabin.door.row2.passenger.isOpen",
}
RAMEN = {
    "linksvoor": "vehicle.cabin.window.row1.driver.status",
    "rechtsvoor": "vehicle.cabin.window.row1.passenger.status",
    "linksachter": "vehicle.cabin.window.row2.driver.status",
    "rechtsachter": "vehicle.cabin.window.row2.passenger.status",
}
KOFFERBAK = "vehicle.body.trunk.isOpen"
MOTORKAP = "vehicle.body.hood.isOpen"
DAK = "vehicle.cabin.sunroof.overallStatus"

# ── klimaat en locatie ────────────────────────────────────────────────────────
VOORKLIMATISEREN = "vehicle.vehicle.preConditioning.activity"
VOORKLIMATISEREN_TIJD = "vehicle.vehicle.preConditioning.remainingTime"
LAT = "vehicle.cabin.infotainment.navigation.currentLocation.latitude"
LON = "vehicle.cabin.infotainment.navigation.currentLocation.longitude"

DESCRIPTORS = tuple(
    dict.fromkeys(
        [
            *KERN,
            LAADVERMOGEN,
            LAADTIJD,
            TOT_VOL,
            LAADDOEL,
            BEREIK_DOEL,
            *CAPACITEIT,
            CAPACITEIT_NIEUW,
            GEZONDHEID,
            AC_LIMIET,
            AC_STROOM,
            AC_SPANNING,
            FASEN,
            LAADMETHODE,
            VOORKEUR,
            EINDE,
            RESULTAAT,
            KABELSLOT,
            KLEP,
            KM_STAND,
            VERBRUIK,
            WEEK_KM,
            WEEK_KM_LANG,
            RIT_EIND,
            RIT_KM_STAND,
            RIT_ACCU,
            RIT_TERUG,
            STIJL_OPTREKKEN,
            STIJL_ANTICIPEREN,
            SERVICE_KM,
            APK,
            SERVICES,
            MELDINGEN,
            *(f"{b}.{k}" for b in BANDEN.values() for k in ("pressure", "pressureTarget")),
            ACCU_12V,
            ACCU_12V_VOLT,
            SLOT,
            ALARM,
            *DEUREN.values(),
            *RAMEN.values(),
            KOFFERBAK,
            MOTORKAP,
            DAK,
            VOORKLIMATISEREN,
            VOORKLIMATISEREN_TIJD,
            LAT,
            LON,
        ]
    )
)

ONGELDIG = {"", "INVALID", "-NA-", "UNKNOWN", "NA"}
WAAR = {"true", "open", "asn_istrue", "1", "yes"}
ONWAAR = {"false", "closed", "asn_isfalse", "0", "no"}
MIJL = 1.609344


class Lezer:
    """Leest waarden uit telematicData en onthoudt per groep het nieuwste tijdstip."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.groep = ""
        self.tijden: dict[str, datetime] = {}

    def ruw(self, *sleutels: str) -> tuple[str, dict[str, Any]] | None:
        for s in sleutels:
            e = self.data.get(s)
            if isinstance(e, dict) and e.get("value") is not None and str(e["value"]).strip() not in ONGELDIG:
                t = tijd(e.get("timestamp"))
                if t and (self.groep not in self.tijden or t > self.tijden[self.groep]):
                    self.tijden[self.groep] = t
                return str(e["value"]).strip(), e
        return None

    def tekst(self, *sleutels: str) -> str | None:
        w = self.ruw(*sleutels)
        return w[0] if w else None

    def getal(self, *sleutels: str) -> float | None:
        w = self.ruw(*sleutels)
        return getal(w[0]) if w else None

    def km(self, *sleutels: str) -> float | None:
        """Afstand in km; BMW geeft soms mijlen (dan staat dat in `unit`)."""
        w = self.ruw(*sleutels)
        if not w or (x := getal(w[0])) is None:
            return None
        return round(x * MIJL if _eenheid(w[1]) in ("mi", "miles") else x, 1)

    def waar(self, sleutel: str) -> bool | None:
        w = self.tekst(sleutel)
        if w is None:
            return None
        w = w.lower()
        return True if w in WAAR else False if w in ONWAAR else None

    def datum(self, sleutel: str) -> str | None:
        w = self.tekst(sleutel)
        t = tijd(w) if w else None
        return t.isoformat() if t else None

    def json(self, sleutel: str) -> Any:
        w = self.tekst(sleutel)
        if w is None:
            return None
        try:
            return json.loads(w)
        except ValueError:
            return w


def getal(x: Any) -> float | None:
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _eenheid(e: dict[str, Any]) -> str:
    return str(e.get("unit") or "").strip().lower()


def tijd(x: Any) -> datetime | None:
    """ISO 8601, "30.09.2026 23:00 UTC", "09/30/2026 23:00:00 UTC" of epoch (s of ms)."""
    if x is None or x == "":
        return None
    if isinstance(x, (int, float)) or str(x).isdigit():
        n = float(x)
        return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, UTC)
    s = str(x).strip()
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    except ValueError:
        pass
    kaal = s.removesuffix("UTC").strip()
    for vorm in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(kaal, vorm).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def zonder_leeg(d: dict[str, Any]) -> dict[str, Any]:
    uit = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = zonder_leeg(v)
        if v not in (None, {}, [], ""):
            uit[k] = v
    return uit


# ── naar Thuis ────────────────────────────────────────────────────────────────


def naar_rij(vin: str, naam: str, data: dict[str, Any], moment: datetime) -> dict[str, Any]:
    """Eén rij voor auto_meting."""
    lees = Lezer(data)
    accu = lees.getal(*ACCU)
    bereik = lees.km(*BEREIK)
    stekker = lees.waar(STEKKER)
    if stekker is None and (poort := lees.tekst(LAADPOORT)) is not None:
        stekker = poort.upper() == "CONNECTED"
    status = lees.tekst(LAADSTATUS)
    if status is not None:
        laadt = status.upper() == "CHARGINGACTIVE"
    else:
        hv = lees.tekst(HV_STATUS)
        laadt = None if hv is None else hv.upper() == "CHARGING"
    if laadt:
        stekker = True
    bijgewerkt = lees.tijden.get("")
    # Extra's: niet meetellen voor "bijgewerkt", dat gaat over accu en stekker.
    lees.groep = "extra"
    vermogen = _laadvermogen(lees)
    return {
        "tijd": moment,
        "auto_id": vin,
        "naam": naam,
        "accu_pct": accu,
        "bereik_km": bereik,
        "ingeplugd": stekker,
        "laadt": laadt,
        "bijgewerkt": bijgewerkt,
        "km_stand": lees.km(KM_STAND),
        "laadvermogen_kw": 0.0 if laadt is False else vermogen,
        "laadtijd_min": lees.getal(LAADTIJD) if laadt else None,
        "kwh_tot_vol": lees.getal(TOT_VOL),
        "doel_pct": lees.getal(LAADDOEL),
        "capaciteit_kwh": lees.getal(*CAPACITEIT),
    }


def _laadvermogen(lees: Lezer) -> float | None:
    w = lees.ruw(LAADVERMOGEN)
    if not w or (x := getal(w[0])) is None:
        return None
    eenheid = _eenheid(w[1])
    kw = x if eenheid == "kw" or (not eenheid and x < 500) else x / 1000
    return round(kw, 2)


def naar_details(data: dict[str, Any], basis: dict[str, Any] | None = None) -> dict[str, Any]:
    """Alles behalve de kern, per groep, voor de pagina Auto (tabel auto_details)."""
    lees = Lezer(data)
    uit: dict[str, Any] = {}

    lees.groep = "laden"
    uit["laden"] = {
        "vermogen_kw": _laadvermogen(lees),
        "resttijd_min": lees.getal(LAADTIJD),
        "kwh_tot_vol": lees.getal(TOT_VOL),
        "doel_pct": lees.getal(LAADDOEL),
        "bereik_bij_doel_km": lees.km(BEREIK_DOEL),
        "capaciteit_kwh": lees.getal(*CAPACITEIT),
        "capaciteit_nieuw_kwh": lees.getal(CAPACITEIT_NIEUW),
        "gezondheid_pct": lees.getal(GEZONDHEID),
        "ac_limiet_a": lees.getal(AC_LIMIET),
        "ac_stroom_a": lees.getal(AC_STROOM),
        "ac_spanning_v": lees.getal(AC_SPANNING),
        "fasen": lees.tekst(FASEN),
        "methode": lees.tekst(LAADMETHODE),
        "voorkeur": lees.tekst(VOORKEUR),
        "laatste_einde": lees.tekst(EINDE),
        "laatste_resultaat": lees.tekst(RESULTAAT),
        "kabelslot": lees.tekst(KABELSLOT),
        "klep_open": lees.waar(KLEP),
    }

    lees.groep = "rijden"
    uit["rijden"] = {
        "km_stand": lees.km(KM_STAND),
        "verbruik_kwh_100km": _verbruik(lees),
        "week_km": lees.km(WEEK_KM),
        "week_km_lang": lees.km(WEEK_KM_LANG),
        "rit": {
            "eind": lees.datum(RIT_EIND),
            "km_stand": lees.km(RIT_KM_STAND),
            "accu_pct": lees.getal(RIT_ACCU),
            "teruggewonnen": lees.getal(RIT_TERUG),
        },
        "rijstijl": {"optrekken": lees.getal(STIJL_OPTREKKEN), "anticiperen": lees.getal(STIJL_ANTICIPEREN)},
    }

    lees.groep = "onderhoud"
    banden = {}
    for plek, pad in BANDEN.items():
        druk, doel = lees.getal(f"{pad}.pressure"), lees.getal(f"{pad}.pressureTarget")
        banden[plek] = {
            "bar": round(druk / 100, 2) if druk is not None else None,  # kPa → bar
            "doel_bar": round(doel / 100, 2) if doel is not None else None,
        }
    uit["onderhoud"] = {
        "service_km": lees.km(SERVICE_KM),
        "apk": lees.datum(APK),
        "services": _lijst_van(lees.json(SERVICES)),
        "meldingen": _lijst_van(lees.json(MELDINGEN)),
        "banden": banden,
        "accu_12v_pct": lees.getal(ACCU_12V),
        "accu_12v_volt": lees.getal(ACCU_12V_VOLT),
    }

    lees.groep = "beveiliging"
    uit["beveiliging"] = {
        "slot": lees.tekst(SLOT),
        "alarm": lees.tekst(ALARM),
        "deuren_open": {plek: lees.waar(pad) for plek, pad in DEUREN.items()},
        "ramen": {plek: lees.tekst(pad) for plek, pad in RAMEN.items()},
        "kofferbak_open": lees.waar(KOFFERBAK),
        "motorkap_open": lees.waar(MOTORKAP),
        "dak": lees.tekst(DAK),
    }

    lees.groep = "klimaat"
    uit["klimaat"] = {
        "activiteit": lees.tekst(VOORKLIMATISEREN),
        "resttijd_min": lees.getal(VOORKLIMATISEREN_TIJD),
    }

    lees.groep = "locatie"
    lat, lon = lees.getal(LAT), lees.getal(LON)
    if lat is not None and lon is not None and (lat, lon) != (0, 0):
        uit["locatie"] = {"lat": round(lat, 5), "lon": round(lon, 5)}

    uit["basis"] = basis or {}
    uit = zonder_leeg(uit)
    for groep, t in lees.tijden.items():
        if groep in uit and isinstance(uit[groep], dict):
            uit[groep]["bijgewerkt"] = t.isoformat()
    return uit


def _verbruik(lees: Lezer) -> float | None:
    w = lees.ruw(VERBRUIK)
    if not w or (x := getal(w[0])) is None or x <= 0:
        return None
    if "mi" in _eenheid(w[1]):  # mi/kWh → kWh/100 km
        return round(100 / (x * MIJL), 1)
    return round(x, 1)


def _lijst_van(x: Any) -> list[Any]:
    """Servicemeldingen en Check Control: een lijst (of één melding), elk een dict of tekst."""
    if x is None:
        return []
    if isinstance(x, dict):
        for k in ("messages", "items", "services", "conditionBasedServices", "checkControlMessages"):
            if isinstance(x.get(k), list):
                return x[k]
        return [x]
    return x if isinstance(x, list) else [x]


def basisgegevens(d: dict[str, Any]) -> dict[str, Any]:
    """Uit /basicData: wat de pagina Auto bij "Over de auto" toont."""
    return zonder_leeg(
        {
            "merk": d.get("brand"),
            "model": d.get("modelName"),
            "serie": d.get("series"),
            "carrosserie": d.get("bodyType"),
            "aandrijving": d.get("propulsionType") or d.get("driveTrain"),
            "bouwdatum": d.get("constructionDate"),
            "kleurcode": d.get("colourCode"),
            "land": d.get("countryCodeISO"),
        }
    )


def naar_laadsessies(vin: str, sessies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Laadhistorie van BMW (ook laden onderweg) → tabel auto_laadsessie."""
    uit = []
    for s in sessies:
        start, eind = tijd(s.get("startTime")), tijd(s.get("endTime"))
        if start is None:
            continue
        plek = s.get("chargingLocation") or {}
        punten = (s.get("publicChargingPoint") or {}).get("potentialChargingPointMatches") or []
        aanbieder = next((p.get("providerName") for p in punten if p.get("providerName")), None)
        plaats = plek.get("municipality") or plek.get("formattedAddress") or None
        kosten = s.get("chargingCostInformation") or {}
        km = getal(s.get("mileage"))
        if km is not None and str(s.get("mileageUnits", "")).endswith("MI"):
            km = round(km * MIJL, 1)
        uit.append(
            {
                "start": start,
                "auto_id": vin,
                "eind": eind,
                "kwh": getal(s.get("energyConsumedFromPowerGridKwh")),
                "start_pct": getal(s.get("displayedStartSoc")),
                "eind_pct": getal(s.get("displayedSoc")),
                "plaats": ", ".join(x for x in (aanbieder, plaats) if x) or None,
                "publiek": bool(punten),
                "kosten": getal(kosten.get("calculatedChargingCost")),
                "valuta": kosten.get("currency"),
                "km_stand": km,
                "lat": getal(plek.get("mapMatchedLatitude")),
                "lon": getal(plek.get("mapMatchedLongitude")),
            }
        )
    return uit
