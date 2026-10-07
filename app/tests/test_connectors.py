from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from thuis.connectors import easee as easee_mod
from thuis.connectors.easee import Easee
from thuis.connectors.frank import URL, Frank, FrankFout
from thuis.connectors.kia import naar_rij

PRIJS = {
    "from": "2026-10-07T00:00:00.000Z",
    "till": "2026-10-07T00:15:00.000Z",
    "marketPrice": 0.08,
    "marketPriceTax": 0.0168,
    "sourcingMarkupPrice": 0.02,
    "energyTaxPrice": 0.1108,
}


@respx.mock
def test_frank_prijzen_allin_en_kwartieren():
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "marketPricesElectricity": [PRIJS],
                    "marketPricesGas": [{**PRIJS, "till": "2026-10-07T01:00:00.000Z"}],
                }
            },
        )
    )
    rijen = Frank().prijzen(date(2026, 10, 7), date(2026, 10, 9))
    stroom = rijen[0]
    assert stroom["soort"] == "stroom"
    assert stroom["allin"] == pytest.approx(0.2276)
    assert stroom["van"] == datetime(2026, 10, 7, tzinfo=UTC)
    assert (stroom["tot"] - stroom["van"]).seconds == 900
    assert rijen[1]["soort"] == "gas"


@respx.mock
def test_frank_verbruik_logt_in_en_kiest_site():
    route = respx.post(URL)
    route.side_effect = [
        httpx.Response(200, json={"data": {"login": {"authToken": "T", "refreshToken": "R"}}}),
        httpx.Response(200, json={"data": {"userSites": [{"reference": "S1", "status": "IN_DELIVERY"}]}}),
        httpx.Response(
            200,
            json={
                "data": {
                    "periodUsageAndCosts": {
                        "electricity": {
                            "unit": "kWh",
                            "items": [
                                {
                                    "from": "2026-10-06T22:00:00+00:00",
                                    "till": "2026-10-06T23:00:00+00:00",
                                    "usage": 0.5,
                                    "costs": 0.12,
                                    "unit": "kWh",
                                }
                            ],
                        },
                        "feedIn": {"unit": "kWh", "items": []},
                        "gas": {
                            "unit": "m3",
                            "items": [
                                {
                                    "from": "2026-10-06T22:00:00+00:00",
                                    "till": "2026-10-06T23:00:00+00:00",
                                    "usage": 0.1,
                                    "costs": 0.14,
                                    "unit": None,
                                }
                            ],
                        },
                    }
                }
            },
        ),
    ]
    rijen = Frank("a@b.nl", "geheim").verbruik(date(2026, 10, 7))
    assert [r["soort"] for r in rijen] == ["stroom", "gas"]
    assert rijen[1]["eenheid"] == "m3"
    assert route.calls[2].request.headers["authorization"] == "Bearer T"


@respx.mock
def test_frank_graphql_fout_wordt_exceptie():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"errors": [{"message": "kapot"}]}))
    with pytest.raises(FrankFout, match="kapot"):
        Frank().prijzen(date(2026, 10, 7), date(2026, 10, 8))


@respx.mock
def test_easee_meting_en_herlogin_bij_401():
    respx.post(f"{easee_mod.URL}/api/accounts/login").mock(
        return_value=httpx.Response(200, json={"accessToken": "A"})
    )
    state = respx.get(f"{easee_mod.URL}/api/chargers/EH1/state")
    state.side_effect = [
        httpx.Response(401),
        httpx.Response(
            200, json={"chargerOpMode": 3, "totalPower": 10.8, "sessionEnergy": 4.2, "lifetimeEnergy": 1234.5}
        ),
    ]
    m = Easee("u", "p").meting("EH1", "Oprit")
    assert m["status"] == "laden" and m["vermogen_kw"] == 10.8 and m["totaal_kwh"] == 1234.5
    pause = respx.post(f"{easee_mod.URL}/api/chargers/EH1/commands/pause_charging").mock(
        return_value=httpx.Response(202)
    )
    Easee("u", "p").pauzeer("EH1")
    assert pause.called


def test_kia_rij_uit_voertuig():
    class V:
        id, name = "car-1", "EV6"
        ev_battery_percentage, ev_driving_range = 64, 310
        ev_battery_is_plugged_in, ev_battery_is_charging = True, False
        last_updated_at = datetime(2026, 10, 7, 18, 0)

    rij = naar_rij(V(), datetime(2026, 10, 7, 18, 5, tzinfo=UTC))
    assert rij["accu_pct"] == 64.0 and rij["bereik_km"] == 310.0 and rij["ingeplugd"] is True
    assert rij["bijgewerkt"].tzinfo is not None
