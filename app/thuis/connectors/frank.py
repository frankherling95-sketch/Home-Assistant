"""Frank Energie (GraphQL).

- Marktprijzen stroom en gas: openbaar, geen login nodig.
- Verbruik en kosten per uur (slimme meter): met je Frank-account.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx

URL = "https://frank-graphql-prod.graphcdn.app/"

_PRIJZEN = """
query MarketPrices($startDate: Date!, $endDate: Date!) {
  marketPricesElectricity(startDate: $startDate, endDate: $endDate) {
    from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice
  }
  marketPricesGas(startDate: $startDate, endDate: $endDate) {
    from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice
  }
}"""

_LOGIN = """
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) { authToken refreshToken }
}"""

_SITES = "query UserSites { userSites { reference status } }"

_VERBRUIK = """
query PeriodUsageAndCosts($date: String!, $siteReference: String!) {
  periodUsageAndCosts(date: $date, siteReference: $siteReference) {
    gas { unit items { from till usage costs unit } }
    electricity { unit items { from till usage costs unit } }
    feedIn { unit items { from till usage costs unit } }
  }
}"""


class FrankFout(RuntimeError):
    pass


def _tijd(waarde: str) -> datetime:
    dt = datetime.fromisoformat(waarde.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise FrankFout(f"Tijd zonder tijdzone: {waarde}")
    return dt


class Frank:
    def __init__(
        self,
        email: str = "",
        wachtwoord: str = "",
        site: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self.email, self.wachtwoord, self.site = email, wachtwoord, site
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _post(self, query: str, variabelen: dict[str, Any], auth: bool = False) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"} if auth and self._token else {}
        r = self.client.post(URL, json={"query": query, "variables": variabelen}, headers=headers)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise FrankFout("; ".join(e.get("message", "?") for e in body["errors"]))
        return body["data"]

    # ── openbaar ──────────────────────────────────────────────────────────────

    def prijzen(self, start: date, eind: date) -> list[dict[str, Any]]:
        """All-in prijzen (incl. btw, inkoopvergoeding en energiebelasting) per blok, [start, eind)."""
        data = self._post(_PRIJZEN, {"startDate": str(start), "endDate": str(eind)})
        rijen = []
        for soort, sleutel in (("stroom", "marketPricesElectricity"), ("gas", "marketPricesGas")):
            for p in data.get(sleutel) or []:
                rijen.append(
                    {
                        "soort": soort,
                        "van": _tijd(p["from"]),
                        "tot": _tijd(p["till"]),
                        "marktprijs": float(p["marketPrice"]),
                        "allin": round(
                            sum(
                                float(p[k] or 0)
                                for k in (
                                    "marketPrice",
                                    "marketPriceTax",
                                    "sourcingMarkupPrice",
                                    "energyTaxPrice",
                                )
                            ),
                            5,
                        ),
                    }
                )
        return rijen

    # ── met account ───────────────────────────────────────────────────────────

    def login(self) -> None:
        if not (self.email and self.wachtwoord):
            raise FrankFout("Geen Frank Energie-login ingesteld")
        data = self._post(_LOGIN, {"email": self.email, "password": self.wachtwoord})
        self._token = data["login"]["authToken"]
        if not self.site:
            sites = self._post(_SITES, {}, auth=True)["userSites"]
            actief = [s for s in sites if s.get("status") in (None, "IN_DELIVERY")] or sites
            if not actief:
                raise FrankFout("Geen leveringsadres gevonden bij Frank Energie")
            self.site = actief[0]["reference"]

    def verbruik(self, dag: date) -> list[dict[str, Any]]:
        """Verbruik en kosten per blok voor één dag: stroom, teruglevering en gas."""
        if self._token is None:
            self.login()
        data = self._post(_VERBRUIK, {"date": str(dag), "siteReference": self.site}, auth=True)
        periode = data.get("periodUsageAndCosts") or {}
        rijen = []
        for soort, sleutel in (("stroom", "electricity"), ("teruglevering", "feedIn"), ("gas", "gas")):
            blok = periode.get(sleutel) or {}
            for i in blok.get("items") or []:
                rijen.append(
                    {
                        "soort": soort,
                        "van": _tijd(i["from"]),
                        "tot": _tijd(i["till"]),
                        "hoeveelheid": float(i["usage"] or 0),
                        "kosten": float(i["costs"] or 0),
                        "eenheid": i.get("unit") or blok.get("unit") or ("m3" if soort == "gas" else "kWh"),
                    }
                )
        return rijen


def dagen(rond: date, terug: int, vooruit: int) -> list[date]:
    return [rond + timedelta(days=d) for d in range(-terug, vooruit + 1)]
