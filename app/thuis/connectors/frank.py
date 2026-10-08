"""Frank Energie (GraphQL).

- Marktprijzen stroom en gas: openbaar, geen login nodig. Per dag, in kwartieren.
- Verbruik en kosten per uur (slimme meter): met je Frank-account.

Frank heeft geen openbare documentatie; de queries volgen de bibliotheek die de Home
Assistant-integratie gebruikt (python-frank-energie, gecontroleerd op versie 2026.9.20).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx

URL = "https://frank-graphql-prod.graphcdn.app/"

_PRIJS_VELDEN = "from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice allInPrice"
_PRIJZEN = f"""
query MarketPrices($date: String!, $resolution: PriceResolution!) {{
  marketPrices(date: $date, resolution: $resolution) {{
    electricityPrices {{ {_PRIJS_VELDEN} }}
    gasPrices {{ {_PRIJS_VELDEN} }}
  }}
}}"""
# Zo meldt Frank een dag waarvan de prijzen nog niet bekend zijn (morgen vóór ±13:00).
_NOG_GEEN_PRIJZEN = "no marketprices found"

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
        """All-in prijzen (incl. btw, inkoopvergoeding en energiebelasting) per kwartier, dagen [start, eind).

        Een dag waarvan de prijzen nog niet gepubliceerd zijn, wordt overgeslagen.
        """
        rijen: list[dict[str, Any]] = []
        dag = start
        while dag < eind:
            try:
                data = self._post(_PRIJZEN, {"date": str(dag), "resolution": "PT15M"})
            except FrankFout as err:
                if _NOG_GEEN_PRIJZEN not in str(err).lower():
                    raise
                data = {}
            markt = data.get("marketPrices") or {}
            rijen += [_prijsrij("stroom", p) for p in markt.get("electricityPrices") or []]
            # Gas heeft één prijs per dag, maar komt ook per kwartier: samenvoegen houdt de tabel klein.
            rijen += _samenvoegen([_prijsrij("gas", p) for p in markt.get("gasPrices") or []])
            dag += timedelta(days=1)
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


def _prijsrij(soort: str, p: dict[str, Any]) -> dict[str, Any]:
    delen = ("marketPrice", "marketPriceTax", "sourcingMarkupPrice", "energyTaxPrice")
    allin = p.get("allInPrice")
    return {
        "soort": soort,
        "van": _tijd(p["from"]),
        "tot": _tijd(p["till"]),
        "marktprijs": float(p["marketPrice"]),
        "allin": round(float(allin) if allin is not None else sum(float(p[k] or 0) for k in delen), 5),
    }


def _samenvoegen(rijen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aansluitende blokken met dezelfde prijs tot één blok samenvoegen."""
    uit: list[dict[str, Any]] = []
    for r in sorted(rijen, key=lambda r: r["van"]):
        if uit and uit[-1]["tot"] == r["van"] and uit[-1]["allin"] == r["allin"]:
            uit[-1] = {**uit[-1], "tot": r["tot"]}
        else:
            uit.append(dict(r))
    return uit


def dagen(rond: date, terug: int, vooruit: int) -> list[date]:
    return [rond + timedelta(days=d) for d in range(-terug, vooruit + 1)]
