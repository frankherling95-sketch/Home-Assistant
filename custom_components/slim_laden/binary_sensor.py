"""Binary sensor `Nu laden`: het enige signaal dat de lader-automatisering nodig heeft."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SlimLadenConfigEntry
from .entity import SlimLadenEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SlimLadenConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([NuLadenSensor(entry.runtime_data, "charge_now")])


class NuLadenSensor(SlimLadenEntity, BinarySensorEntity):
    _domain = "binary_sensor"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.charge_now if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.coordinator.data
        return {"reden": plan.reason} if plan else {}
