"""BMW CarData: de officiële API van BMW (https://bmw-cardata.bmwgroup.com).

Koppelen gaat met de device code flow (OAuth 2.0 met PKCE): Thuis vraagt een code aan, jij logt
in op de site van BMW en bevestigt die code, en daarna krijgt Thuis tokens. Je wachtwoord gaat
niet door Thuis heen. Nodig is alleen een client-ID uit het CarData-portaal (My BMW → BMW
CarData), met "CarData API" aan.

BMW staat 50 verzoeken per dag toe. De verzamelaar draait elke 15 minuten, dus de auto wordt
niet elke ronde gevraagd: elk kwartier als hij laadt, elk half uur als de stekker erin zit en
anders elk uur. Over elke 24 uur samen nooit meer dan 45 verzoeken; de rest blijft over voor
koppelen en herstel.

Tokens: het access-token is een uur geldig, het refresh-token twee weken. Bij elke verversing
geeft BMW een nieuw refresh-token, dus steeds het nieuwste bewaren.

Alles wat bewaard moet blijven (tokens, auto, container, telling van verzoeken) staat in één
dict, `record`: dat is de koppeling zoals die in de kluis staat.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import KoppelFout, KoppelingVerlopen

AUTH = "https://customer.bmwgroup.com/gcdm/oauth"
API = "https://api-cardata.bmwgroup.com"
# Alleen de REST-API: de datastroom (cardata:streaming:read) gebruikt Thuis niet.
SCOPE = "authenticate_user openid cardata:api:read"
DIENST = "BMW"

MAX_PER_DAG = 45  # BMW: 50 per dag
ZUINIG_VANAF = 35  # daarboven hooguit één keer per uur
SPELING = timedelta(minutes=3)  # Cloud Scheduler start niet op de seconde

# Welke gegevens Thuis vraagt (een "container" bij BMW). Verandert deze lijst, verhoog dan de
# versie in CONTAINER_DOEL: bij de volgende ronde komt er een nieuwe container voor de oude.
CONTAINER_NAAM = "Thuis"
CONTAINER_DOEL = "Thuis energieplatform v1"
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
DESCRIPTORS = (*ACCU, *BEREIK, STEKKER, LAADPOORT, LAADSTATUS, HV_STATUS)

ONGELDIG = {"", "INVALID", "-NA-", "UNKNOWN"}
VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
CONTAINER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BmwFout(RuntimeError):
    def __init__(self, status: int, code: str = "", tekst: str = "") -> None:
        super().__init__(tekst or f"BMW CarData: {code or f'HTTP {status}'}")
        self.status, self.code = status, code


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _json(r: httpx.Response) -> dict[str, Any]:
    try:
        d = r.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {"items": d}


def _tokens(antwoord: dict[str, Any], oud: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "access_token": antwoord["access_token"],
        "refresh_token": antwoord.get("refresh_token") or (oud or {}).get("refresh_token"),
        "verloopt": round(time.time() + int(antwoord.get("expires_in") or 3600)),
    }


# ── koppelen (device code flow) ───────────────────────────────────────────────


def start_koppeling(client_id: str, client: httpx.Client | None = None) -> tuple[dict, dict]:
    """Vraagt een code aan. Geeft (wat de app bewaart tot de bevestiging, wat de gebruiker ziet)."""
    client = client or httpx.Client(timeout=30)
    verifier, challenge = _pkce()
    r = client.post(
        f"{AUTH}/device/code",
        data={
            "client_id": client_id,
            "response_type": "device_code",
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers={"Accept": "application/json"},
    )
    if r.status_code >= 500:
        raise BmwFout(r.status_code)
    d = _json(r)
    if r.status_code >= 400 or not d.get("device_code"):
        raise KoppelFout(
            "BMW kent deze client-ID niet, of CarData API staat er niet aan. Kopieer de client-ID "
            "opnieuw uit het CarData-portaal en kijk of 'CarData API' aan staat."
        )
    interval = int(d.get("interval") or 5)
    verloopt = round(time.time() + int(d.get("expires_in") or 300))
    wacht = {
        "client_id": client_id,
        "device_code": d["device_code"],
        "code_verifier": verifier,
        "interval": interval,
        "verloopt": verloopt,
    }
    link = str(d.get("verification_uri_complete") or d.get("verification_uri") or "")
    toon = {
        "code": d.get("user_code", ""),
        "link": link if link.startswith("https://") else "https://bmw-cardata.bmwgroup.com",
        "interval": interval,
        "verloopt": datetime.fromtimestamp(verloopt, UTC).isoformat(),
    }
    return wacht, toon


def controleer_koppeling(wacht: dict[str, Any], client: httpx.Client | None = None) -> dict[str, Any] | None:
    """Vraagt BMW of de code al is bevestigd. None = nog niet; anders de nieuwe koppeling.

    Bij `slow_down` gaat `wacht["interval"]` omhoog: de app wacht dan langer tussen het vragen.
    """
    if time.time() > wacht["verloopt"]:
        raise KoppelFout("De code is verlopen. Begin opnieuw met koppelen.")
    client = client or httpx.Client(timeout=30)
    r = client.post(
        f"{AUTH}/token",
        data={
            "client_id": wacht["client_id"],
            "device_code": wacht["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "code_verifier": wacht["code_verifier"],
        },
    )
    d = _json(r)
    if r.status_code != 200:
        fout = d.get("error")
        if fout == "authorization_pending":
            return None
        if fout == "slow_down":
            wacht["interval"] = int(wacht.get("interval", 5)) + 5
            return None
        if fout == "expired_token":
            raise KoppelFout("De code is verlopen. Begin opnieuw met koppelen.")
        if fout == "access_denied":
            raise KoppelFout("Het koppelen is bij BMW geweigerd of afgebroken. Begin opnieuw met koppelen.")
        if r.status_code >= 500:
            # Na deze storing werkt de code bij BMW niet meer; anders gewoon nog eens vragen.
            if "invalid_access_token" in r.text:
                raise KoppelFout("BMW brak het koppelen af. Begin opnieuw met koppelen.")
            return None
        raise KoppelFout(f"BMW weigerde het koppelen ({fout or r.status_code}). Begin opnieuw met koppelen.")

    b = BMW({"client_id": wacht["client_id"], "tokens": _tokens(d)}, client)
    b.zoek_auto()
    b.zorg_voor_container()
    return {**b.record, "account": b.record["naam"], "bericht": f"Auto gevonden: {b.record['naam']}"}


# ── de auto uitlezen ──────────────────────────────────────────────────────────


class BMW:
    def __init__(self, record: dict[str, Any], client: httpx.Client | None = None) -> None:
        self.record: dict[str, Any] = {**record, "tokens": dict(record.get("tokens") or {})}
        self.client = client or httpx.Client(timeout=30)
        self.gewijzigd = False

    # tokens

    def _zorg_voor_token(self) -> None:
        t = self.record["tokens"]
        if not t.get("access_token") or float(t.get("verloopt") or 0) - 120 < time.time():
            self._ververs()

    def _ververs(self) -> None:
        t = self.record["tokens"]
        if not t.get("refresh_token"):
            raise KoppelingVerlopen(DIENST, "geen refresh-token")
        r = self.client.post(
            f"{AUTH}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": t["refresh_token"],
                "client_id": self.record["client_id"],
            },
        )
        if r.status_code in (400, 401, 403):  # na twee weken zonder verversing, of ingetrokken
            raise KoppelingVerlopen(DIENST, f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise BmwFout(r.status_code, tekst=f"BMW: tokens verversen mislukt (HTTP {r.status_code})")
        self.record["tokens"] = _tokens(r.json(), t)
        self.gewijzigd = True

    # verzoeken aan de API (tellen mee voor het dagmaximum)

    def _vragen(self, moment: float | None = None) -> list[float]:
        grens = (moment or time.time()) - 86400
        self.record["vragen"] = [v for v in self.record.get("vragen") or [] if v > grens]
        return self.record["vragen"]

    def _api(self, methode: str, pad: str, opnieuw: bool = True, **kwargs: Any) -> Any:
        self._zorg_voor_token()
        self._vragen().append(round(time.time()))
        self.gewijzigd = True
        r = self.client.request(
            methode,
            f"{API}{pad}",
            headers={
                "Authorization": f"Bearer {self.record['tokens']['access_token']}",
                "x-version": "v1",
                "Accept": "application/json",
            },
            **kwargs,
        )
        if r.status_code < 400:
            return r.json() if r.content else None
        code = str(_json(r).get("exveErrorId") or "")
        if opnieuw and (r.status_code == 401 or code in ("CU-101", "CU-102")):
            self.record["tokens"]["verloopt"] = 0  # toch verlopen: één keer verversen
            return self._api(methode, pad, opnieuw=False, **kwargs)
        if r.status_code == 429 or code == "CU-429":
            # Het dagmaximum van BMW is op: een paar uur niets meer vragen.
            self.record["pauze_tot"] = round(time.time() + 3 * 3600)
            raise BmwFout(r.status_code, code, "BMW: het maximum van 50 verzoeken per dag is bereikt")
        raise BmwFout(r.status_code, code)

    # bij het koppelen

    def zoek_auto(self) -> None:
        """De auto waarvan je hoofdgebruiker bent (alleen daarvan geeft BMW gegevens)."""
        auto = [
            m
            for m in _lijst(self._api("GET", "/customers/vehicles/mappings"), "mappings", "vehicles")
            if str(m.get("mappingType") or "PRIMARY").upper() == "PRIMARY" and VIN.match(str(m.get("vin")))
        ]
        if not auto:
            raise KoppelFout(
                "Er staat geen auto op je BMW-account waarvan jij de hoofdgebruiker bent. "
                "Voeg de auto eerst toe in de My BMW-app."
            )
        vin = auto[0]["vin"]
        try:
            basis = self._api("GET", f"/customers/vehicles/{vin}/basicData") or {}
        except BmwFout:
            basis = {}
        merk = "MINI" if basis.get("brand") == "MINI" else "BMW"
        model = str(basis.get("modelName") or "").strip()
        self.record["vin"] = vin
        self.record["naam"] = model if model.upper().startswith(merk) else f"{merk} {model}".strip()

    def zorg_voor_container(self) -> None:
        """Hergebruik de container van Thuis; een oude versie gaat weg (maximaal 10 per account)."""
        bestaand = _lijst(self._api("GET", "/customers/containers"), "containers", "items")
        van_thuis = [
            c
            for c in bestaand
            if c.get("name") == CONTAINER_NAAM
            and c.get("state", "ACTIVE") == "ACTIVE"
            and CONTAINER_ID.match(str(c.get("containerId")))
        ]
        for c in van_thuis:
            if c.get("purpose") == CONTAINER_DOEL:
                self.record["container_id"] = c["containerId"]
                return
        for c in van_thuis:
            self._api("DELETE", f"/customers/containers/{c['containerId']}")
        try:
            nieuw = self._api(
                "POST",
                "/customers/containers",
                json={
                    "name": CONTAINER_NAAM,
                    "purpose": CONTAINER_DOEL,
                    "technicalDescriptors": list(DESCRIPTORS),
                },
            )
        except BmwFout as err:
            if err.code == "CU-124":
                raise KoppelFout(
                    "Je account heeft al 10 containers bij BMW CarData. Verwijder er een in het "
                    "CarData-portaal en koppel opnieuw."
                ) from err
            raise
        self.record["container_id"] = nieuw["containerId"]

    # elke ronde

    def wachttijd(self, moment: datetime) -> timedelta | None:
        """Hoe lang na het vorige verzoek het volgende mag. None: nu even niet (maximum bereikt)."""
        if float(self.record.get("pauze_tot") or 0) > moment.timestamp():
            return None
        gedaan = len(self._vragen(moment.timestamp()))
        if gedaan >= MAX_PER_DAG:
            return None
        toestand = self.record.get("toestand") or {}
        minuten = 15 if toestand.get("laadt") else 30 if toestand.get("ingeplugd") else 60
        if gedaan >= ZUINIG_VANAF:
            minuten = 60
        return timedelta(minutes=minuten)

    def aan_de_beurt(self, moment: datetime) -> bool:
        wacht = self.wachttijd(moment)
        if wacht is None:
            return False
        laatst = self.record.get("laatst")
        return not laatst or moment - datetime.fromisoformat(laatst) >= wacht - SPELING

    def metingen(self, moment: datetime | None = None) -> list[dict[str, Any]]:
        """Eén rij voor auto_meting, of niets als de auto deze ronde niet aan de beurt is."""
        moment = moment or datetime.now(UTC)
        if not self.aan_de_beurt(moment):
            return []
        self.record["laatst"] = moment.isoformat()  # ook bij een fout: niet elke ronde opnieuw
        self.gewijzigd = True
        if not self.record.get("container_id"):
            self.zorg_voor_container()
        try:
            data = self._telematisch()
        except BmwFout as err:
            if err.code != "CU-105":  # CU-105: container bestaat niet meer
                raise
            self.record.pop("container_id", None)
            self.zorg_voor_container()
            data = self._telematisch()
        rij = naar_rij(self.record["vin"], self.record.get("naam") or DIENST, data, moment)
        self.record["toestand"] = {"laadt": bool(rij["laadt"]), "ingeplugd": bool(rij["ingeplugd"])}
        return [rij]

    def _telematisch(self) -> dict[str, Any]:
        d = self._api(
            "GET",
            f"/customers/vehicles/{self.record['vin']}/telematicData",
            params={"containerId": self.record["container_id"]},
        )
        return (d or {}).get("telematicData") or {}


def _lijst(d: Any, *sleutels: str) -> list[dict[str, Any]]:
    """BMW geeft lijsten soms kaal en soms in een object terug."""
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    if isinstance(d, dict):
        for s in (*sleutels, "items"):
            if isinstance(d.get(s), list):
                return [x for x in d[s] if isinstance(x, dict)]
        if "vin" in d or "containerId" in d:
            return [d]
    return []


def _waarde(data: dict[str, Any], *sleutels: str) -> tuple[str, dict[str, Any]] | None:
    for s in sleutels:
        e = data.get(s)
        if isinstance(e, dict) and e.get("value") is not None and str(e["value"]).strip() not in ONGELDIG:
            return str(e["value"]).strip(), e
    return None


def _getal(x: str) -> float | None:
    try:
        return float(x)
    except ValueError:
        return None


def naar_rij(vin: str, naam: str, data: dict[str, Any], moment: datetime) -> dict[str, Any]:
    gebruikt: list[dict[str, Any]] = []

    def lees(*sleutels: str) -> str | None:
        w = _waarde(data, *sleutels)
        if w is None:
            return None
        gebruikt.append(w[1])
        return w[0]

    accu = lees(*ACCU)
    bereik = None
    w = _waarde(data, *BEREIK)
    if w is not None and (km := _getal(w[0])) is not None:
        gebruikt.append(w[1])
        bereik = km * 1.609344 if str(w[1].get("unit", "")).lower() in ("mi", "miles") else km
    stekker = lees(STEKKER)
    if stekker is not None:
        ingeplugd = stekker.lower() == "true"
    else:
        poort = lees(LAADPOORT)
        ingeplugd = None if poort is None else poort.upper() == "CONNECTED"
    status = lees(LAADSTATUS)
    if status is not None:
        laadt = status.upper() == "CHARGINGACTIVE"
    else:
        hv = lees(HV_STATUS)
        laadt = None if hv is None else hv.upper() == "CHARGING"
    if laadt:
        ingeplugd = True
    tijden = [t for e in gebruikt if (t := _tijd(e.get("timestamp")))]
    return {
        "tijd": moment,
        "auto_id": vin,
        "naam": naam,
        "accu_pct": _getal(accu) if accu is not None else None,
        "bereik_km": round(bereik, 1) if bereik is not None else None,
        "ingeplugd": ingeplugd,
        "laadt": laadt,
        "bijgewerkt": max(tijden) if tijden else None,
    }


def _tijd(x: Any) -> datetime | None:
    if not x:
        return None
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)
