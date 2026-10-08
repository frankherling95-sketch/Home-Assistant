"""Easee (officiële REST-API, https://api.easee.com)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from . import KoppelFout, KoppelingVerlopen

URL = "https://api.easee.com"

# chargerOpMode → leesbare status
STATUS = {
    0: "offline",
    1: "niet_verbonden",
    2: "wacht_op_start",
    3: "laden",
    4: "klaar",
    5: "fout",
    6: "klaar_om_te_laden",
    7: "wacht_op_autorisatie",
    8: "deautoriseren",
    100: "start_laden",
    101: "stop_laden",
    102: "offline",
    103: "wacht_op_loadbalancing",
    104: "wacht_op_autorisatie",
    105: "wacht_op_smart_start",
    106: "wacht_op_schema",
    107: "authenticeren",
    108: "gepauzeerd_equalizer",
    109: "zoekt_master",
    157: "auto_reageert_niet",
}

# Statussen waarin een auto aan de lader hangt en pauzeren/hervatten zin heeft.
VERBONDEN = {"wacht_op_start", "laden", "klaar_om_te_laden", "wacht_op_smart_start", "wacht_op_schema"}


class EaseeFout(RuntimeError):
    pass


class Easee:
    """Met wachtwoord, of met bewaarde tokens (`access_token`, `refresh_token`, `verloopt` als epoch).

    Een refresh-token is bij Easee maar één keer bruikbaar: na elke verversing de nieuwe bewaren.
    """

    def __init__(
        self,
        gebruiker: str = "",
        wachtwoord: str = "",
        client: httpx.Client | None = None,
        tokens: dict[str, Any] | None = None,
    ) -> None:
        self.gebruiker, self.wachtwoord = gebruiker, wachtwoord
        self.client = client or httpx.Client(timeout=30, base_url=URL)
        self.tokens: dict[str, Any] = dict(tokens or {})
        self.gewijzigd = False

    def _geldig(self) -> bool:
        return (
            bool(self.tokens.get("access_token"))
            and float(self.tokens.get("verloopt") or 0) - 60 > time.time()
        )

    def _zorg_voor_token(self) -> None:
        if self._geldig():
            return
        if self.tokens.get("refresh_token"):
            self._ververs()
        else:
            self.login()

    def _ververs(self) -> None:
        r = self.client.post(
            "/api/accounts/refresh_token",
            json={
                "accessToken": self.tokens.get("access_token"),
                "refreshToken": self.tokens["refresh_token"],
            },
        )
        if r.status_code < 400:
            self._bewaar(r.json())
        elif self.wachtwoord:
            self.login()
        else:  # sessie bij Easee verlopen of ingetrokken
            raise KoppelingVerlopen("Easee", f"HTTP {r.status_code}")

    def _bewaar(self, antwoord: dict[str, Any]) -> None:
        self.tokens = {
            "access_token": antwoord["accessToken"],
            "refresh_token": antwoord.get("refreshToken"),
            "verloopt": round(time.time() + int(antwoord.get("expiresIn") or 3600)),
        }
        self.gewijzigd = True

    def _verzoek(self, methode: str, pad: str, **kwargs: Any) -> Any:
        self._zorg_voor_token()
        r = self.client.request(methode, pad, headers=self._kop(), **kwargs)
        if r.status_code == 401:  # token toch verlopen: één keer verversen of opnieuw inloggen
            self.tokens["verloopt"] = 0
            self._zorg_voor_token()
            r = self.client.request(methode, pad, headers=self._kop(), **kwargs)
        if r.status_code >= 400:
            raise EaseeFout(f"{methode} {pad}: HTTP {r.status_code}")
        return r.json() if r.content else None

    def _kop(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def login(self) -> None:
        r = self.client.post(
            "/api/accounts/login", json={"userName": self.gebruiker, "password": self.wachtwoord}
        )
        if r.status_code >= 400:
            raise EaseeFout(f"Inloggen bij Easee mislukt: HTTP {r.status_code}")
        self._bewaar(r.json())

    @classmethod
    def koppel(cls, gebruiker: str, wachtwoord: str) -> dict[str, Any]:
        """Eenmalig inloggen; geeft wat bewaard wordt (tokens, geen wachtwoord) en een bevestiging."""
        e = cls(gebruiker, wachtwoord)
        try:
            e.login()
        except EaseeFout as err:
            raise KoppelFout(
                "Inloggen bij Easee mislukt: controleer je e-mailadres (of telefoonnummer) en wachtwoord."
            ) from err
        laders = e.laders()
        namen = ", ".join(lad["naam"] for lad in laders) or "geen"
        return {"tokens": e.tokens, "account": gebruiker, "bericht": f"Laders gevonden: {namen}"}

    def laders(self) -> list[dict[str, str]]:
        return [
            {"id": c["id"], "naam": c.get("name") or c["id"]} for c in self._verzoek("GET", "/api/chargers")
        ]

    def meting(self, lader_id: str, naam: str = "") -> dict[str, Any]:
        s = self._verzoek("GET", f"/api/chargers/{lader_id}/state")
        return {
            "tijd": datetime.now(UTC),
            "lader_id": lader_id,
            "naam": naam or lader_id,
            "status": STATUS.get(s.get("chargerOpMode"), f"onbekend_{s.get('chargerOpMode')}"),
            "vermogen_kw": float(s.get("totalPower") or 0),
            "sessie_kwh": float(s.get("sessionEnergy") or 0),
            "totaal_kwh": float(s.get("lifetimeEnergy") or 0),
        }

    def pauzeer(self, lader_id: str) -> None:
        self._verzoek("POST", f"/api/chargers/{lader_id}/commands/pause_charging")

    def hervat(self, lader_id: str) -> None:
        self._verzoek("POST", f"/api/chargers/{lader_id}/commands/resume_charging")
