"""Hoofdschakelaar. Uit = `Nu laden` staat altijd aan (gewoon laden)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SlimLadenConfigEntry
from .entity import SlimLadenEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SlimLadenConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SlimLadenSwitch(entry.runtime_data, "enabled")])


class SlimLadenSwitch(SlimLadenEntity, SwitchEntity, RestoreEntity):
    _domain = "switch"

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.coordinator.enabled = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        self.coordinator.enabled = value
        self.async_write_ha_state()
        await self.coordinator.async_apply()
