from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.slim_laden.const import DOMAIN

PRICE = "sensor.current_electricity_price_all_in"
SOC = "sensor.ev6_ev_battery_level"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _prices(hass: HomeAssistant, now_cheap: bool) -> None:
    start = dt_util.now().replace(minute=0, second=0, microsecond=0)
    prices = [0.01 if (now_cheap and i == 0) else 0.30 for i in range(24)]
    hass.states.async_set(
        PRICE,
        prices[0],
        {
            "prices": [
                {"from": start + timedelta(hours=i), "till": start + timedelta(hours=i + 1), "price": p}
                for i, p in enumerate(prices)
            ]
        },
    )


async def _setup(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Slim laden",
            "price_sensor": PRICE,
            "soc_sensor": SOC,
            "capacity_kwh": 77.4,
            "power_kw": 11,
            "efficiency": 90,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_flow_rejects_missing_sensor(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "x",
            "price_sensor": "sensor.bestaat_niet",
            "capacity_kwh": 60,
            "power_kw": 11,
            "efficiency": 90,
        },
    )
    assert result["errors"] == {"price_sensor": "entity_not_found"}


async def test_setup_and_charge_now(hass: HomeAssistant) -> None:
    _prices(hass, now_cheap=True)
    hass.states.async_set(SOC, "40")
    await _setup(hass)

    assert hass.states.get("binary_sensor.slim_laden_charge_now").state == "on"
    assert float(hass.states.get("sensor.slim_laden_needed_energy").state) > 0
    assert hass.states.get("switch.slim_laden_enabled").state == "on"

    # Doel bereikt en duur uur → niet laden; reageert direct op de SoC-sensor.
    _prices(hass, now_cheap=False)
    hass.states.async_set(SOC, "95")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.slim_laden_charge_now").state == "off"

    # Uitschakelen = gewoon laden.
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.slim_laden_enabled"}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.slim_laden_charge_now")
    assert state.state == "on" and state.attributes["reden"] == "uitgeschakeld"


async def test_settings_entities(hass: HomeAssistant) -> None:
    _prices(hass, now_cheap=False)
    hass.states.async_set(SOC, "40")
    await _setup(hass)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.slim_laden_target_soc", "value": 100}, blocking=True
    )
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.slim_laden_departure", "time": "06:00:00"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("number.slim_laden_target_soc").state == "100.0"
    assert hass.states.get("time.slim_laden_departure").state == "06:00:00"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.data.needed_kwh == round(0.6 * 77.4 / 0.9, 2)


async def test_entity_ids_onafhankelijk_van_taal(hass: HomeAssistant) -> None:
    hass.config.language = "nl"
    _prices(hass, now_cheap=False)
    await _setup(hass)
    # Dashboards in git verwijzen naar deze ID's; ze mogen niet meevertalen.
    for entity_id in (
        "binary_sensor.slim_laden_charge_now",
        "sensor.slim_laden_plan_start",
        "number.slim_laden_target_soc",
        "time.slim_laden_departure",
        "switch.slim_laden_enabled",
    ):
        assert hass.states.get(entity_id) is not None, entity_id
