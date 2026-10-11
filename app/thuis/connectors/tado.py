"""tado°: slimme thermostaten en radiatorknoppen, via de REST-API van tado.

tado heeft geen officiële API voor derden, maar laat de REST-API van de eigen app open voor
"fair use" (https://support.tado.com/en/articles/8565472). Inloggen gaat met de device code flow
(OAuth 2.0): Thuis vraagt een code, jij bevestigt die met je tado-account op de site van tado, en
Thuis krijgt een token. Je wachtwoord komt niet langs Thuis.

Drie dingen maken tado bijzonder:

- Elk refresh-token is één keer bruikbaar (rotatie). De app (Cloud Run-service) en de verzamelaar
  (job) gebruiken dezelfde tokens. Wie ververst, schrijft de nieuwe meteen in de kluis; wie het
  verversen geweigerd ziet worden (de ander was net eerder), pakt de nieuwe tokens uit de kluis.
- Zonder Auto-Assist-abonnement staat tado 100 verzoeken per dag toe, met 20.000
  (https://support.tado.com/en/articles/12165739). Thuis leest het restant uit de header
  `ratelimit` van elk antwoord en is daar zuinig mee: de verzamelaar vraagt de stand dan eens per
  uur, de app hooguit eens per vijf minuten. Het verversen van een token telt niet mee.
- Er zijn twee generaties: tado° X (sinds 2024) via hops.tado.com, de oudere (V3, V3+) via
  my.tado.com. Welke het is, staat in het huis ("generation": "LINE_X").
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import KoppelFout, KoppelingVerlopen

CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"  # vaste client-ID van tado voor de device code flow
LOGIN = "https://login.tado.com/oauth2"
MY = "https://my.tado.com/api/v2"
HOPS = "https://hops.tado.com"
MIN_TEMP, MAX_TEMP, STAP = 5.0, 25.0, 0.5
STANDAARD_TEMP = 20.0  # als je een zone die uit staat hoger zet
AUTO_ASSIST = 1000  # vanaf zoveel verzoeken per dag: een abonnement, dan niet zuinig hoeven zijn
UUR = timedelta(minutes=55)  # zonder Auto-Assist vraagt de verzamelaar hooguit zo vaak
RESERVE = 25  # zoveel verzoeken laat de verzamelaar per dag over voor jou in de app
TOKEN_VELDEN = ("access_token", "refresh_token", "verloopt")


class TadoFout(RuntimeError):
    def __init__(self, uitleg: str) -> None:
        super().__init__(uitleg)
        self.uitleg = uitleg


class Opslag:
    """Waar de tokens en het restant van de dag bewaard worden: de kluis (of niets, in tests)."""

    def __init__(self, kluis: Any = None) -> None:
        self.kluis = kluis

    def lees(self) -> dict[str, Any] | None:
        return ((self.kluis.lees().get("koppelingen") or {}).get("tado")) if self.kluis else None

    def schrijf(self, velden: dict[str, Any]) -> None:
        if self.kluis is not None:
            from ..kluis import werk_velden_bij

            werk_velden_bij(self.kluis, "tado", velden)


def _quotum(r: httpx.Response, oud: dict[str, Any] | None) -> dict[str, Any] | None:
    """Uit `ratelimit: "perday";r=93;t=4567` en `ratelimit-policy: "perday";q=100;w=86400`."""
    rest = re.search(r"\br=(\d+)", r.headers.get("ratelimit", ""))
    if not rest:
        return oud
    per_dag = re.search(r"\bq=(\d+)", r.headers.get("ratelimit-policy", ""))
    vol = re.search(r"\bt=(\d+)", r.headers.get("ratelimit", ""))
    return {
        "over": int(rest.group(1)),
        "per_dag": int(per_dag.group(1)) if per_dag else (oud or {}).get("per_dag"),
        "vol_om": (datetime.now(UTC) + timedelta(seconds=int(vol.group(1)))).isoformat() if vol else None,
        "tijd": datetime.now(UTC).isoformat(),
    }


class Tado:
    """Eén tado-huis. `record` is de koppeling uit de kluis: home_id, generatie, zones en de tokens."""

    def __init__(
        self,
        record: dict[str, Any],
        kluis: Any = None,
        client: httpx.Client | None = None,
        klok: Callable[[], float] = time.time,
        slaap: Callable[[float], None] = time.sleep,
    ) -> None:
        self.record = dict(record)
        self.opslag = Opslag(kluis)
        self.client = client or httpx.Client(timeout=20)
        self._klok = klok
        self._slaap = slaap

    # ── tokens ────────────────────────────────────────────────────────────────

    def _geldig(self) -> bool:
        return (
            bool(self.record.get("access_token"))
            and float(self.record.get("verloopt") or 0) - 60 > self._klok()
        )

    def _herlaad(self) -> None:
        """De tokens zoals ze nu in de kluis staan (misschien heeft de verzamelaar net ververst)."""
        r = self.opslag.lees()
        if r:
            self.record.update({k: r.get(k) for k in TOKEN_VELDEN})

    def _zorg_voor_token(self) -> str:
        if self._geldig():
            return self.record["access_token"]
        self._herlaad()
        if self._geldig():
            return self.record["access_token"]
        gebruikt = self.record.get("refresh_token")
        if self._ververs():
            return self.record["access_token"]
        # Geweigerd: misschien ververste de ander net met hetzelfde token. Even wachten en de kluis lezen.
        for _ in range(2):
            self._slaap(1.5)
            self._herlaad()
            if self.record.get("refresh_token") != gebruikt and (self._geldig() or self._ververs()):
                return self.record["access_token"]
        self.opslag.schrijf({"status": "opnieuw"})
        raise KoppelingVerlopen("tado", "tado nam het token niet meer aan")

    def _ververs(self) -> bool:
        if not self.record.get("refresh_token"):
            return False
        r = self.client.post(
            f"{LOGIN}/token",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self.record["refresh_token"],
            },
        )
        if r.status_code >= 500:
            raise TadoFout("tado is even niet bereikbaar; probeer het zo nog eens.")
        if r.status_code >= 400:
            return False
        self._bewaar_tokens(r.json())
        return True

    def _bewaar_tokens(self, d: dict[str, Any]) -> None:
        velden = {
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token") or self.record.get("refresh_token"),
            "verloopt": round(self._klok() + int(d.get("expires_in") or 600)),
        }
        self.record.update(velden)
        self.opslag.schrijf({**velden, "status": "ok"})  # meteen: het oude refresh-token werkt niet meer

    # ── verzoeken ─────────────────────────────────────────────────────────────

    @property
    def quotum(self) -> dict[str, Any] | None:
        return self.record.get("quotum")

    @property
    def zuinig(self) -> bool:
        """Zonder Auto-Assist (of zolang we het niet weten): zuinig met verzoeken."""
        return (self.quotum or {}).get("per_dag") is None or self.quotum["per_dag"] < AUTO_ASSIST

    def _verzoek(self, methode: str, url: str, body: Any = None, opnieuw: bool = True) -> Any:
        r = self.client.request(
            methode, url, json=body, headers={"Authorization": f"Bearer {self._zorg_voor_token()}"}
        )
        self.record["quotum"] = _quotum(r, self.quotum)
        if r.status_code == 401 and opnieuw:  # token toch verlopen
            self.record["verloopt"] = 0
            return self._verzoek(methode, url, body, opnieuw=False)
        if r.status_code == 429:
            raise TadoFout(
                "Het dagmaximum van tado is bereikt (100 verzoeken zonder Auto-Assist). Morgen weer."
            )
        if r.status_code == 404:
            raise TadoFout(
                "tado kent deze zone niet (meer). Koppel tado opnieuw als je zones hebt veranderd."
            )
        if r.status_code >= 400:
            raise TadoFout(f"tado gaf een fout (HTTP {r.status_code}).")
        return r.json() if r.content else None

    @property
    def x(self) -> bool:
        return self.record.get("generatie") == "LINE_X"

    def _thuis(self) -> str:
        return f"{HOPS if self.x else MY}/homes/{self.record['home_id']}"

    # ── lezen ─────────────────────────────────────────────────────────────────

    def apparaten(self) -> list[dict[str, Any]]:
        """Alle zones (kamers) met hun stand, in de vorm van apparaten.maak. Eén verzoek."""
        zones = self.record.get("zones") or {}
        if self.x:
            kamers = self._verzoek("GET", f"{self._thuis()}/rooms") or []
            return [apparaat_x(k) for k in kamers]
        standen = (self._verzoek("GET", f"{self._thuis()}/zoneStates") or {}).get("zoneStates") or {}
        return [
            apparaat_v3(zone_id, info, standen[zone_id])
            for zone_id, info in zones.items()
            if zone_id in standen and info.get("type") in ("HEATING", "HOT_WATER")
        ]

    def aan_de_beurt(self, moment: datetime, gevraagd: datetime | None = None) -> bool:
        """Mag de verzamelaar nu de stand vragen? Met Auto-Assist elke ronde, anders eens per uur,
        en nooit als er minder dan RESERVE verzoeken over zijn (die zijn voor jou in de app)."""
        if not self.zuinig:
            return True
        over = (self.quotum or {}).get("over")
        if over is not None and over < (10 if gevraagd else RESERVE):
            return False
        laatst = self.record.get("gelezen")
        return gevraagd is not None or not laatst or moment - datetime.fromisoformat(laatst) >= UUR

    def metingen(self, moment: datetime, gevraagd: datetime | None = None) -> list[dict[str, Any]]:
        """Rijen voor apparaat_meting, als het de beurt is van tado; anders niets."""
        if not self.aan_de_beurt(moment, gevraagd):
            return []
        lijst = self.apparaten()
        self.record["gelezen"] = moment.isoformat()
        self.opslag.schrijf({"gelezen": self.record["gelezen"], "quotum": self.quotum})
        return [meting(a, moment) for a in lijst]

    # ── bedienen ──────────────────────────────────────────────────────────────

    def zet(self, zone_id: str, stand: str, temperatuur: float | None = None) -> None:
        """stand: "schema" (terug naar het schema), "handmatig" (tot je het terugzet), "blok" (tot het
        volgende blok in je schema) of "uit". Eén verzoek."""
        if self.x:
            pad = f"{self._thuis()}/rooms/{zone_id}/manualControl"
            if stand == "schema":
                self._verzoek("DELETE", pad)
                return
            setting: dict[str, Any] = (
                {"power": "OFF"} if stand == "uit" else {"power": "ON", "temperature": {"value": temperatuur}}
            )
            eind = {"type": "NEXT_TIME_BLOCK" if stand == "blok" else "MANUAL"}
            self._verzoek("POST", pad, {"setting": setting, "termination": eind})
            return
        pad = f"{self._thuis()}/zones/{zone_id}/overlay"
        if stand == "schema":
            self._verzoek("DELETE", pad)
            return
        soort = ((self.record.get("zones") or {}).get(zone_id) or {}).get("type", "HEATING")
        setting = {"type": soort, "power": "OFF"}
        if stand != "uit":
            setting["power"] = "ON"
            if soort == "HEATING":
                setting["temperature"] = {"celsius": temperatuur}
        eind = {"typeSkillBasedApp": "NEXT_TIME_BLOCK" if stand == "blok" else "MANUAL"}
        self._verzoek("PUT", pad, {"setting": setting, "termination": eind})

    # ── koppelen ──────────────────────────────────────────────────────────────

    @staticmethod
    def start_koppeling(client: httpx.Client | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Vraagt een code aan. Geeft (wat de app bewaart tot de bevestiging, wat de gebruiker ziet)."""
        client = client or httpx.Client(timeout=20)
        r = client.post(f"{LOGIN}/device_authorize", data={"client_id": CLIENT_ID, "scope": "offline_access"})
        if r.status_code >= 400:
            raise TadoFout(f"tado gaf geen code (HTTP {r.status_code}); probeer het zo nog eens.")
        d = r.json()
        interval = int(d.get("interval") or 5)
        verloopt = round(time.time() + int(d.get("expires_in") or 300))
        link = str(d.get("verification_uri_complete") or d.get("verification_uri") or "")
        wacht = {"device_code": d["device_code"], "interval": interval, "verloopt": verloopt}
        toon = {
            "code": d.get("user_code", ""),
            "link": link if link.startswith("https://") else "https://login.tado.com/oauth2/device",
            "interval": interval,
            "verloopt": datetime.fromtimestamp(verloopt, UTC).isoformat(),
        }
        return wacht, toon

    @classmethod
    def controleer_koppeling(
        cls, wacht: dict[str, Any], client: httpx.Client | None = None
    ) -> dict[str, Any] | None:
        """None zolang de code niet bevestigd is; daarna de koppeling (huis, generatie, zones, tokens)."""
        if time.time() > wacht["verloopt"]:
            raise KoppelFout("De code is verlopen. Begin opnieuw met koppelen.")
        client = client or httpx.Client(timeout=20)
        r = client.post(
            f"{LOGIN}/token",
            data={
                "client_id": CLIENT_ID,
                "device_code": wacht["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.status_code != 200:
            fout = d.get("error")
            if fout == "authorization_pending" or r.status_code >= 500:
                return None
            if fout == "slow_down":
                wacht["interval"] = int(wacht.get("interval", 5)) + 5
                return None
            if fout == "expired_token":
                raise KoppelFout("De code is verlopen. Begin opnieuw met koppelen.")
            if fout == "access_denied":
                raise KoppelFout(
                    "Het koppelen is bij tado geweigerd of afgebroken. Begin opnieuw met koppelen."
                )
            raise KoppelFout(
                f"tado weigerde het koppelen ({fout or r.status_code}). Begin opnieuw met koppelen."
            )
        t = cls({}, client=client)
        t._bewaar_tokens(d)
        try:
            return t._zoek_huis()
        except TadoFout as err:
            raise KoppelFout(err.uitleg) from err

    def _zoek_huis(self) -> dict[str, Any]:
        """Het huis (het eerste, als je er meer hebt), de generatie en de zones. Drie verzoeken."""
        huizen = (self._verzoek("GET", f"{MY}/me") or {}).get("homes") or []
        if not huizen:
            raise TadoFout("Er hangt geen huis aan dit tado-account.")
        huis = self._verzoek("GET", f"{MY}/homes/{huizen[0]['id']}") or {}
        self.record.update(
            {
                "home_id": huizen[0]["id"],
                "home_naam": huis.get("name") or huizen[0].get("name") or "tado",
                "generatie": huis.get("generation") or "PRE_LINE_X",
            }
        )
        if self.x:
            kamers = self._verzoek("GET", f"{self._thuis()}/rooms") or []
            zones = {
                str(k["id"]): {"naam": k.get("name") or f"Kamer {k['id']}", "type": "HEATING"} for k in kamers
            }
        else:
            lijst = self._verzoek("GET", f"{self._thuis()}/zones") or []
            zones = {
                str(z["id"]): {"naam": z.get("name") or f"Zone {z['id']}", "type": z.get("type")}
                for z in lijst
            }
        self.record["zones"] = zones
        namen = [z["naam"] for z in zones.values() if z.get("type") in ("HEATING", "HOT_WATER")]
        meer = f" en {len(namen) - 3} meer" if len(namen) > 3 else ""
        return {
            **{
                k: self.record.get(k)
                for k in (*TOKEN_VELDEN, "home_id", "home_naam", "generatie", "zones", "quotum")
            },
            "account": self.record["home_naam"],
            "bericht": f"{'tado° X' if self.x else 'tado°'}, zones: {', '.join(namen[:3]) or 'geen'}{meer}",
        }


# ── van tado naar de vorm van een apparaat (zie apparaten.maak) ────────────────


def _tijd(iso: Any) -> str | None:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(UTC).isoformat()
    except ValueError:
        return None


def _apparaat(
    zone_id: str,
    naam: str,
    soort_tado: str,
    online: bool,
    aan_power: bool,
    gewenst: float | None,
    binnen: float | None,
    vocht: float | None,
    verwarming: float | None,
    handmatig: dict[str, Any] | None,
    volgende: dict[str, Any] | None,
    raam: bool,
    product: str,
) -> dict[str, Any]:
    stand = "schema" if not handmatig else "uit" if not aan_power else "handmatig"
    warm_water = soort_tado == "HOT_WATER"
    bediening = [
        {"code": "tado_stand", "type": "Enum", "waarde": stand, "keuzes": ["schema", "handmatig", "uit"]},
    ]
    if not warm_water:
        bediening.append(
            {
                "code": "temp_set",
                "type": "Integer",
                "waarde": gewenst if aan_power else None,
                "min": MIN_TEMP,
                "max": MAX_TEMP,
                "stap": STAP,
                "eenheid": "°C",
                "standaard": STANDAARD_TEMP,
            }
        )
    status: list[dict[str, Any]] = []
    if verwarming is not None:
        status.append({"code": "verwarming", "waarde": round(verwarming), "eenheid": "%"})
    if handmatig and handmatig.get("tot"):
        status.append({"code": "handmatig_tot", "waarde": handmatig["tot"], "eenheid": None})
    elif handmatig:  # zonder eindtijd: tot het volgende blok, of tot je het zelf terugzet
        blok = handmatig.get("soort") in ("NEXT_TIME_BLOCK", "TIMER")
        tekst = "tot het volgende blok" if blok else "tot je het terugzet"
        status.append({"code": "handmatig_tot", "waarde": tekst, "eenheid": None})
    if volgende and volgende.get("start"):
        status.append({"code": "schema_volgende", "waarde": volgende["start"], "eenheid": None})
        if volgende.get("temperatuur") is not None:
            status.append({"code": "schema_temp", "waarde": volgende["temperatuur"], "eenheid": "°C"})
    metingen = {k: v for k, v in (("temperatuur", binnen), ("vochtigheid", vocht)) if v is not None}
    return {
        "id": f"tado-{zone_id}",
        "naam": naam,
        "product": product,
        "categorie": "tado",
        "soort": "klimaat",
        "online": online,
        # Aan = verwarmt nu (of warm water staat aan): dan gloeit het icoon.
        "aan": (aan_power if warm_water else bool(verwarming and verwarming > 0)) if online else False,
        "schakelaars": [],
        "metingen": metingen,
        "toestand": "raam_open" if raam else ("uit" if not aan_power else None),
        "bediening": bediening,
        "status": status,
        "bron": "tado",
    }


def apparaat_v3(zone_id: str, info: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    setting = s.get("setting") or {}
    sensor = s.get("sensorDataPoints") or {}
    overlay = s.get("overlay")
    eind = (overlay or {}).get("termination") or {}
    volgend = s.get("nextScheduleChange") or {}
    return _apparaat(
        zone_id,
        info.get("naam") or f"Zone {zone_id}",
        info.get("type") or "HEATING",
        ((s.get("link") or {}).get("state") or "ONLINE") == "ONLINE",
        setting.get("power") == "ON",
        ((setting.get("temperature") or {}).get("celsius")),
        ((sensor.get("insideTemperature") or {}).get("celsius")),
        ((sensor.get("humidity") or {}).get("percentage")),
        (((s.get("activityDataPoints") or {}).get("heatingPower") or {}).get("percentage")),
        {
            "tot": _tijd(eind.get("projectedExpiry")) if eind.get("projectedExpiry") else None,
            "soort": eind.get("typeSkillBasedApp") or eind.get("type"),
        }
        if overlay
        else None,
        {
            "start": _tijd(volgend.get("start")) if volgend.get("start") else None,
            "temperatuur": (((volgend.get("setting") or {}).get("temperature") or {}).get("celsius")),
        },
        bool(s.get("openWindow")),
        "tado° warm water" if info.get("type") == "HOT_WATER" else "tado°",
    )


def apparaat_x(k: dict[str, Any]) -> dict[str, Any]:
    setting = k.get("setting") or {}
    sensor = k.get("sensorDataPoints") or {}
    eind = k.get("manualControlTermination")
    volgend = k.get("nextScheduleChange") or {}
    return _apparaat(
        str(k["id"]),
        k.get("name") or f"Kamer {k['id']}",
        "HEATING",
        ((k.get("connection") or {}).get("state") or "CONNECTED") == "CONNECTED",
        setting.get("power") == "ON",
        ((setting.get("temperature") or {}).get("value")),
        ((sensor.get("insideTemperature") or {}).get("value")),
        ((sensor.get("humidity") or {}).get("percentage")),
        ((k.get("heatingPower") or {}).get("percentage")),
        {
            "tot": _tijd(eind.get("projectedExpiry")) if eind.get("projectedExpiry") else None,
            "soort": eind.get("type"),
        }
        if eind
        else None,
        {
            "start": _tijd(volgend.get("start")) if volgend.get("start") else None,
            "temperatuur": (((volgend.get("setting") or {}).get("temperature") or {}).get("value")),
        },
        bool((k.get("openWindow") or {}).get("activated")),
        "tado° X",
    )


def meting(a: dict[str, Any], tijd: datetime) -> dict[str, Any]:
    """Rij voor de tabel apparaat_meting (zoals bij Tuya)."""
    stand = next((b["waarde"] for b in a["bediening"] if b["code"] == "tado_stand"), None)
    gewenst = next((b["waarde"] for b in a["bediening"] if b["code"] == "temp_set"), None)
    verwarming = next((s["waarde"] for s in a["status"] if s["code"] == "verwarming"), None)
    return {
        "tijd": tijd,
        "apparaat_id": a["id"],
        "naam": a["naam"],
        "soort": a["soort"],
        "online": a["online"],
        "aan": a["aan"],
        "vermogen_w": None,
        "temperatuur": a["metingen"].get("temperatuur"),
        "vochtigheid": a["metingen"].get("vochtigheid"),
        "status": json.dumps(
            {"stand": stand, "gewenst": gewenst, "verwarming": verwarming}, separators=(",", ":")
        ),
    }
