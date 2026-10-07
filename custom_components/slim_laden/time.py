"""Vertrektijd: uiterlijk dan moet de auto op doel-SoC zijn."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SlimLadenConfigEntry
from .entity import SlimLadenEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SlimLadenConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VertrekTijd(entry.runtime_data, "departure")])


class VertrekTijd(SlimLadenEntity, TimeEntity, RestoreEntity):
    _domain = "time"

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self.coordinator.departure = time.fromisoformat(last.state)
            except ValueError:
                pass

    @property
    def native_value(self) -> time:
        return self.coordinator.departure

    async def async_set_value(self, value: time) -> None:
        self.coordinator.departure = value
        self.async_write_ha_state()
        await self.coordinator.async_apply()
