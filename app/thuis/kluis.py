"""De kluis: logins en tokens van de koppelingen, als één JSON-object.

In Google Cloud is dat het geheim `thuis-geheimen` in Secret Manager (lezen en schrijven via de
REST-API); lokaal een JSON-bestand. De app schrijft erin bij het koppelen, de verzamelaar als
een token is ververst. Beide voegen alleen hun eigen wijzigingen samen met de nieuwste versie,
zodat ze elkaars werk niet overschrijven.

Vorm: {"FRANK_EMAIL": … (oude logins uit het setup-script), "koppelingen": {"frank": {…}, …},
"wachtend": {"bmw": {…}}} (een BMW-koppeling die nog op bevestiging wacht)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import Config

_LOG = logging.getLogger(__name__)
SECRET_API = "https://secretmanager.googleapis.com/v1"
BEWAAR_VERSIES = 2  # de nieuwste en één terug; oudere worden vernietigd (6 actieve versies zijn gratis)


class Kluis(Protocol):
    def lees(self) -> dict[str, Any]: ...
    def schrijf(self, data: dict[str, Any]) -> None: ...


def werk_bij(
    kluis: Kluis,
    koppelingen: dict[str, dict[str, Any] | None] | None = None,
    wachtend: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Wijzigingen per koppeling samenvoegen met de nieuwste stand en opslaan. None = verwijderen.

    `wachtend`: koppelingen die op een bevestiging wachten (BMW), apart van de echte.
    """
    data = kluis.lees()
    for sectie, wijzig in (("koppelingen", koppelingen), ("wachtend", wachtend)):
        if wijzig is None:
            continue
        alle = dict(data.get(sectie) or {})
        for naam, waarde in wijzig.items():
            if waarde is None:
                alle.pop(naam, None)
            else:
                alle[naam] = waarde
        data[sectie] = alle
    kluis.schrijf(data)
    return data


def maak_kluis(cfg: Config) -> Kluis:
    soort = cfg.kluis or ("secretmanager" if cfg.opslag == "bigquery" else "bestand")
    if soort == "secretmanager":
        return SecretKluis(cfg.gcp_project, cfg.geheim)
    return BestandKluis(cfg.kluis_pad)


class GeheugenKluis:
    """Voor tests."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = json.loads(json.dumps(data or {}))
        self.schrijfacties = 0

    def lees(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.data))

    def schrijf(self, data: dict[str, Any]) -> None:
        self.data = json.loads(json.dumps(data))
        self.schrijfacties += 1


class BestandKluis:
    """Lokaal: een JSON-bestand naast de DuckDB (staat in .gitignore)."""

    def __init__(self, pad: str) -> None:
        self.pad = Path(pad)

    def lees(self) -> dict[str, Any]:
        try:
            return json.loads(self.pad.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def schrijf(self, data: dict[str, Any]) -> None:
        # Eerst naar een tijdelijk bestand, dan vervangen: nooit een half geschreven kluis.
        fd, tijdelijk = tempfile.mkstemp(dir=self.pad.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tijdelijk, self.pad)


def _google_token() -> str:
    import google.auth
    import google.auth.transport.requests

    cred, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    cred.refresh(google.auth.transport.requests.Request())
    return cred.token


class SecretKluis:
    """Secret Manager via REST: elke schrijfactie is een nieuwe versie."""

    def __init__(
        self,
        project: str,
        geheim: str,
        token: Callable[[], str] = _google_token,
        client: httpx.Client | None = None,
    ) -> None:
        self.naam = f"projects/{project}/secrets/{geheim}"
        self._token = token
        self.client = client or httpx.Client(timeout=30)

    def _verzoek(self, methode: str, pad: str, **kwargs: Any) -> dict[str, Any]:
        r = self.client.request(
            methode, f"{SECRET_API}/{pad}", headers={"Authorization": f"Bearer {self._token()}"}, **kwargs
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def lees(self) -> dict[str, Any]:
        try:
            antwoord = self._verzoek("GET", f"{self.naam}/versions/latest:access")
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:  # nog geen versie
                return {}
            raise
        return json.loads(base64.b64decode(antwoord["payload"]["data"]) or b"{}")

    def schrijf(self, data: dict[str, Any]) -> None:
        inhoud = base64.b64encode(json.dumps(data).encode()).decode()
        nieuw = self._verzoek("POST", f"{self.naam}:addVersion", json={"payload": {"data": inhoud}})
        self._ruim_op(nieuw.get("name", ""))

    def _ruim_op(self, nieuwste: str) -> None:
        """Oude versies vernietigen. Mislukt dat, dan is dat geen reden om de ronde te laten falen."""
        try:
            versies = self._verzoek(
                "GET", f"{self.naam}/versions", params={"filter": "state:(ENABLED OR DISABLED)"}
            )
            namen = sorted(
                (v["name"] for v in versies.get("versions", [])),
                key=lambda n: int(n.rsplit("/", 1)[1]),
                reverse=True,
            )
            for naam in namen[BEWAAR_VERSIES:]:
                if naam != nieuwste:
                    self._verzoek("POST", f"{naam}:destroy", json={})
        except Exception:  # noqa: BLE001
            _LOG.warning("Oude versies van %s niet opgeruimd", self.naam, exc_info=True)
