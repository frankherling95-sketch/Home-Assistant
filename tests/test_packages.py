"""Packages en dashboards uit de repo laden en de templates doorrekenen."""

from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml

ROOT = Path(__file__).parent.parent
FRANK = "sensor.current_electricity_price_all_in"


def _templates() -> list:
    items: list = []
    for path in sorted((ROOT / "packages").glob("*.yaml")):
        items += load_yaml(path).get("template", [])
    return items


async def _setup(hass: HomeAssistant, prices: list[float]) -> None:
    start = dt_util.start_of_local_day()
    # Frank Energie levert echte datetime-objecten in het attribuut.
    hass.states.async_set(
        FRANK,
        prices[dt_util.now().hour],
        {
            "prices": [
                {"from": start + timedelta(hours=i), "till": start + timedelta(hours=i + 1), "price": p}
                for i, p in enumerate(prices)
            ]
        },
    )
    assert await async_setup_component(hass, "template", {"template": _templates()})
    await hass.async_block_till_done()


async def test_prijsproxy_en_inzichten(hass: HomeAssistant) -> None:
    prices = [0.30] * 48
    prices[dt_util.now().hour] = 0.25
    prices[30] = -0.05  # morgen 06:00 het goedkoopst
    await _setup(hass, prices)

    nu = hass.states.get("sensor.stroomprijs_nu")
    assert float(nu.state) == 0.25
    assert len(nu.attributes["prices"]) == 48
    assert isinstance(nu.attributes["prices"][0]["from"], str)

    assert float(hass.states.get("sensor.stroomprijs_vandaag_laagste").state) == 0.25
    assert float(hass.states.get("sensor.stroomprijs_vandaag_hoogste").state) == 0.30
    goedkoopst = hass.states.get("sensor.stroom_goedkoopste_moment")
    assert dt_util.parse_datetime(goedkoopst.state) == dt_util.start_of_local_day() + timedelta(hours=30)
    assert goedkoopst.attributes["prijs"] == -0.05
    assert hass.states.get("sensor.stroomprijs_niveau").state == "laag"


async def test_ontbrekende_bronnen_zijn_unavailable(hass: HomeAssistant) -> None:
    await _setup(hass, [0.2] * 24)
    for entity_id in ("sensor.auto_accuniveau", "sensor.lader_status", "binary_sensor.auto_ingeplugd"):
        assert hass.states.get(entity_id).state == "unavailable"


@pytest.mark.parametrize("name", ["energie.yaml", "laden.yaml"])
def test_dashboards_zijn_geldige_yaml(name: str) -> None:
    dashboard = load_yaml(ROOT / "dashboards" / name)
    assert dashboard["views"]
