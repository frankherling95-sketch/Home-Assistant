"""Tuya: slimme stekkers, lampen, thermostaten en sensoren via de cloud-API van Tuya.

Tuya is het platform achter een groot deel van de slimme apparaten in huis: alles wat je bedient
met de app Smart Life of Tuya Smart, ook als er een ander merk op de doos staat (LSC Smart Connect
van Action, Nedis SmartLife, Calex, Silvercrest van Lidl, …). Die apparaten praten met de cloud
van Tuya. Thuis draait zelf in de cloud en bereikt ze dus daar; lokaal via de wifi bedienen kan
vanuit Cloud Run niet.

Koppelen gaat met een eigen cloudproject op platform.tuya.com: daar koppel je je Smart Life-account
(QR-code scannen in de app) en krijg je een Access ID en Access Secret. Thuis vraagt daarmee een
token (2 uur geldig) en ondertekent elk verzoek met HMAC-SHA256, zoals Tuya beschrijft op
https://developer.tuya.com/en/docs/iot/new-singnature. Je Smart Life-wachtwoord is niet nodig.

Het gratis proefabonnement van Tuya (IoT Core) heeft een maximum aantal verzoeken per maand en
moet om de paar maanden verlengd worden. Daarom zuinig: per ronde één verzoek voor alle apparaten
met hun status, het token bewaard in de kluis, en de specificatie van een apparaat (welke knoppen
het heeft, met welk bereik) maar één keer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from . import KoppelFout, KoppelingVerlopen

# Datacenter → adres van de API. Een Nederlands Smart Life-account zit in Centraal-Europa.
REGIO = {
    "eu": "https://openapi.tuyaeu.com",
    "eu-w": "https://openapi-weaz.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "us-e": "https://openapi-ueaz.tuyaus.com",
    "in": "https://openapi.tuyain.com",
    "cn": "https://openapi.tuyacn.com",
}
TYPEN = ("Boolean", "Integer", "Enum")  # wat Thuis kan tonen en bedienen; Json, Raw en String niet
PAGINA = 50  # apparaten per verzoek
BATCH = 20  # apparaten per statusverzoek

# Foutcodes van Tuya, in gewone taal. Zie https://developer.tuya.com/en/docs/iot/error-code.
TOKEN_VERLOPEN = {1010, 1011}
SLEUTEL_FOUT = {1001, 1004}  # Access Secret klopt niet
ONBEKEND_PROJECT = {1005, 1008, 2009}  # Access ID onbekend (vaak: ander datacenter)
GEEN_RECHT = {1106, 28841101, 28841105}
PROEF_VERLOPEN = {28841002}
UITLEG = {
    **dict.fromkeys(
        SLEUTEL_FOUT, "De Access Secret klopt niet. Kopieer hem opnieuw uit je project op platform.tuya.com."
    ),
    **dict.fromkeys(
        ONBEKEND_PROJECT,
        "Tuya kent deze Access ID niet in dit datacenter. Kies het datacenter van je project (voor Nederland meestal Centraal-Europa).",
    ),
    **dict.fromkeys(
        GEEN_RECHT, "Je Tuya-project mag dit niet. Zet bij je project de dienst IoT Core aan (Service API)."
    ),
    **dict.fromkeys(
        PROEF_VERLOPEN,
        "Het proefabonnement van IoT Core is verlopen. Verleng het op platform.tuya.com (Cloud → je project → Service API).",
    ),
    1013: "De klok van de server en die van Tuya lopen niet gelijk.",
    1111: "De klok van de server en die van Tuya lopen niet gelijk.",
    1110: "Te veel verzoeken tegelijk bij Tuya; probeer het zo nog eens.",
    2001: "Het apparaat is offline.",
    2008: "Het apparaat kent deze opdracht niet.",
}


class TuyaFout(RuntimeError):
    def __init__(self, code: Any, melding: str = "") -> None:
        self.code = code
        self.uitleg = UITLEG.get(code) or f"Tuya gaf een fout: {melding or code}"
        super().__init__(f"{self.uitleg} (code {code})")


def onderteken(
    client_id: str,
    geheim: str,
    methode: str,
    pad: str,
    t: str,
    inhoud: bytes = b"",
    token: str = "",
    nonce: str = "",
    koppen: dict[str, str] | None = None,
) -> str:
    """De handtekening van een verzoek. `pad` met de query erin, gesorteerd op sleutel.

    stringToSign = methode \\n sha256(inhoud) \\n ondertekende koppen \\n pad; ondertekend wordt
    client_id + token + t + nonce + stringToSign (bij het tokenverzoek zonder token).
    """
    kopregels = "".join(f"{k}:{v}\n" for k, v in (koppen or {}).items())
    tekst = f"{methode}\n{hashlib.sha256(inhoud).hexdigest()}\n{kopregels}\n{pad}"
    bericht = client_id + token + t + nonce + tekst
    return hmac.new(geheim.encode(), bericht.encode(), hashlib.sha256).hexdigest().upper()


def met_query(pad: str, params: dict[str, Any] | None) -> str:
    if not params:
        return pad
    return pad + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


def compact(specificatie: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Alleen wat Thuis nodig heeft uit de specificatie van een apparaat: per code het type en bereik.

    `functies`: wat je kunt bedienen; `status`: wat het apparaat meldt. Tuya geeft het bereik als
    JSON in een tekst: {"min": 10, "max": 1000, "scale": 0, "step": 1, "unit": "%"} of {"range": [...]}.
    """
    uit: dict[str, dict[str, Any]] = {"functies": {}, "status": {}}
    for sectie in ("functions", "status"):
        doel = uit["functies" if sectie == "functions" else "status"]
        for f in specificatie.get(sectie) or []:
            if f.get("type") not in TYPEN or not f.get("code"):
                continue
            waarden = f.get("values") or {}
            if isinstance(waarden, str):
                try:
                    waarden = json.loads(waarden or "{}")
                except json.JSONDecodeError:
                    waarden = {}
            spec: dict[str, Any] = {"type": f["type"]}
            if f["type"] == "Integer":
                for k in ("min", "max", "scale", "step"):
                    if isinstance(waarden.get(k), (int, float)):
                        spec[k] = waarden[k]
                if waarden.get("unit"):
                    spec["eenheid"] = str(waarden["unit"])
            elif f["type"] == "Enum":
                spec["keuzes"] = [str(k) for k in waarden.get("range") or []]
            doel[f["code"]] = spec
    return uit


class Tuya:
    """Eén cloudproject van Tuya. `record` is de koppeling uit de kluis: regio, access_id,
    access_secret, en wat Thuis bijhoudt (token, verloopt, specs per apparaat)."""

    def __init__(
        self,
        record: dict[str, Any],
        client: httpx.Client | None = None,
        klok: Callable[[], float] = time.time,
    ) -> None:
        self.regio = record.get("regio") or "eu"
        if self.regio not in REGIO:
            raise KoppelFout("Kies het datacenter van je Tuya-project.")
        self.access_id = record["access_id"]
        self._geheim = record["access_secret"]
        self.token = record.get("token") or ""
        self.verloopt = float(record.get("verloopt") or 0)
        self.specs: dict[str, dict[str, Any]] = dict(record.get("specs") or {})
        self.client = client or httpx.Client(timeout=20, base_url=REGIO[self.regio])
        self._klok = klok
        self.gewijzigd = False

    @property
    def record(self) -> dict[str, Any]:
        """Wat er na een ronde terug de kluis in gaat (zie koppelingen.nieuwe_stand)."""
        return {"token": self.token, "verloopt": self.verloopt, "specs": self.specs}

    # ── verzoeken ─────────────────────────────────────────────────────────────

    def _zorg_voor_token(self) -> None:
        if self.token and self.verloopt - 60 > self._klok():
            return
        r = self._verzoek("GET", "/v1.0/token", {"grant_type": 1}, met_token=False)
        self.token = r["access_token"]
        self.verloopt = round(self._klok() + int(r.get("expire_time") or 7200))
        self.gewijzigd = True

    def _verzoek(
        self,
        methode: str,
        pad: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
        met_token: bool = True,
        opnieuw: bool = True,
    ) -> Any:
        if met_token:
            self._zorg_voor_token()
        url = met_query(pad, params)
        inhoud = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
        t = str(int(self._klok() * 1000))
        nonce = uuid.uuid4().hex
        token = self.token if met_token else ""
        koppen = {
            "client_id": self.access_id,
            "t": t,
            "nonce": nonce,
            "sign_method": "HMAC-SHA256",
            "sign": onderteken(self.access_id, self._geheim, methode, url, t, inhoud, token, nonce),
        }
        if met_token:
            koppen["access_token"] = token
        if body is not None:
            koppen["Content-Type"] = "application/json"
        r = self.client.request(methode, url, content=inhoud or None, headers=koppen)
        try:
            data = r.json()
        except ValueError as err:
            raise TuyaFout(f"HTTP {r.status_code}") from err
        if data.get("success"):
            return data.get("result")
        code = data.get("code")
        if code in TOKEN_VERLOPEN and met_token and opnieuw:  # token toch verlopen: één keer een nieuw
            self.verloopt = 0
            return self._verzoek(methode, pad, params, body, opnieuw=False)
        if code in SLEUTEL_FOUT | ONBEKEND_PROJECT:  # de sleutels werken niet (meer)
            raise KoppelingVerlopen("Tuya", UITLEG[code])
        raise TuyaFout(code, str(data.get("msg") or ""))

    # ── apparaten ─────────────────────────────────────────────────────────────

    def apparaten(self) -> list[dict[str, Any]]:
        """Alle apparaten van de app-accounts die aan het project gekoppeld zijn, met hun status.

        Elk apparaat zoals Tuya het geeft: id, name, category, online, product_name en status
        ([{code, value}]). Ontbreekt de status in de lijst, dan komt die er per twintig bij.
        """
        lijst: list[dict[str, Any]] = []
        rij = ""
        for _ in range(20):  # hooguit 1000 apparaten
            params: dict[str, Any] = {"size": PAGINA}
            if rij:
                params["last_row_key"] = rij
            r = self._verzoek("GET", "/v1.0/iot-01/associated-users/devices", params) or {}
            lijst += r.get("devices") or r.get("list") or []
            rij = r.get("last_row_key") or ""
            if not r.get("has_more") or not rij:
                break
        zonder = [a["id"] for a in lijst if "status" not in a]
        if zonder:
            status: dict[str, list[dict[str, Any]]] = {}
            for i in range(0, len(zonder), BATCH):
                deel = ",".join(zonder[i : i + BATCH])
                for s in self._verzoek("GET", "/v1.0/iot-03/devices/status", {"device_ids": deel}) or []:
                    status[s.get("id")] = s.get("status") or []
            for a in lijst:
                a.setdefault("status", status.get(a["id"], []))
        return lijst

    def specificatie(self, apparaat_id: str) -> dict[str, dict[str, Any]]:
        return compact(self._verzoek("GET", f"/v1.0/iot-03/devices/{apparaat_id}/specification") or {})

    def zorg_voor_specs(self, apparaten: list[dict[str, Any]]) -> None:
        """Specificaties van nieuwe apparaten erbij, die van verdwenen apparaten weg."""
        ids = {a["id"] for a in apparaten}
        for a in apparaten:
            if a["id"] not in self.specs:
                try:
                    self.specs[a["id"]] = self.specificatie(a["id"])
                except TuyaFout:  # volgende ronde opnieuw; tot dan alleen lezen
                    continue
                self.gewijzigd = True
        for weg in set(self.specs) - ids:
            del self.specs[weg]
            self.gewijzigd = True

    def stuur(self, apparaat_id: str, opdrachten: list[dict[str, Any]]) -> None:
        """Opdrachten ({code, value}) naar een apparaat. Tuya geeft ze door; het apparaat meldt
        zijn nieuwe stand een tel later."""
        self._verzoek("POST", f"/v1.0/iot-03/devices/{apparaat_id}/commands", body={"commands": opdrachten})

    # ── koppelen ──────────────────────────────────────────────────────────────

    @classmethod
    def koppel(
        cls, regio: str, access_id: str, access_secret: str, client: httpx.Client | None = None
    ) -> dict[str, Any]:
        """Controleert de sleutels en zoekt de apparaten; geeft wat in de kluis komt en een bevestiging."""
        t = cls({"regio": regio, "access_id": access_id, "access_secret": access_secret}, client=client)
        try:
            lijst = t.apparaten()
        except KoppelingVerlopen as err:
            raise KoppelFout(err.reden) from err
        except TuyaFout as err:
            raise KoppelFout(err.uitleg) from err
        if not lijst:
            raise KoppelFout(
                "Tuya vond geen apparaten. Koppel je Smart Life-account aan het project "
                "(Devices → Link App Account) en probeer het opnieuw."
            )
        t.zorg_voor_specs(lijst)
        namen = sorted(str(a.get("name") or a["id"]) for a in lijst)
        meer = f" en {len(namen) - 3} meer" if len(namen) > 3 else ""
        return {
            "regio": regio,
            "access_id": access_id,
            "access_secret": access_secret,
            **t.record,
            "account": access_id,
            "bericht": f"{len(lijst)} {'apparaat' if len(lijst) == 1 else 'apparaten'} gevonden: {', '.join(namen[:3])}{meer}",
        }
