"""Easee (officiële REST-API, https://api.easee.com)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

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
    def __init__(self, gebruiker: str, wachtwoord: str, client: httpx.Client | None = None) -> None:
        self.gebruiker, self.wachtwoord = gebruiker, wachtwoord
        self.client = client or httpx.Client(timeout=30, base_url=URL)
        self._token: str | None = None

    def _verzoek(self, methode: str, pad: str, **kwargs: Any) -> Any:
        if self._token is None:
            self.login()
        r = self.client.request(methode, pad, headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
        if r.status_code == 401:  # token verlopen: één keer opnieuw inloggen
            self.login()
            r = self.client.request(
                methode, pad, headers={"Authorization": f"Bearer {self._token}"}, **kwargs
            )
        if r.status_code >= 400:
            raise EaseeFout(f"{methode} {pad}: HTTP {r.status_code}")
        return r.json() if r.content else None

    def login(self) -> None:
        r = self.client.post(
            "/api/accounts/login", json={"userName": self.gebruiker, "password": self.wachtwoord}
        )
        if r.status_code >= 400:
            raise EaseeFout(f"Inloggen bij Easee mislukt: HTTP {r.status_code}")
        self._token = r.json()["accessToken"]

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
