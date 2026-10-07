"""Slim laden: EV laden op de goedkoopste uren.

Combineert drie bestaande integraties:
  * Frank Energie   — dagprijzen (sensor met `prices`-attribuut)
  * Kia/Hyundai     — laadtoestand van de auto (SoC-sensor)
  * Easee           — de lader, aangestuurd via de meegeleverde blueprint
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import SlimLadenCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH, Platform.TIME]

type SlimLadenConfigEntry = ConfigEntry[SlimLadenCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SlimLadenConfigEntry) -> bool:
    coordinator = SlimLadenCoordinator(hass, entry)
    entry.runtime_data = coordinator
    # Eerst de platforms: die herstellen doel-SoC, vertrektijd enz. vóór de eerste berekening.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()
    coordinator.async_start_tracking()
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SlimLadenConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload_on_options(hass: HomeAssistant, entry: SlimLadenConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
