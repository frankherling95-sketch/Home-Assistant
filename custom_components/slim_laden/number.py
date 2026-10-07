"""Instelbare getallen: doel-SoC en goedkoop-drempel."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import CURRENCY_EURO, PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SlimLadenConfigEntry
from .const import DEFAULT_CHEAP_THRESHOLD, DEFAULT_TARGET_SOC
from .entity import SlimLadenEntity


@dataclass(frozen=True, kw_only=True)
class SettingDescription(NumberEntityDescription):
    attr: str  # attribuutnaam op de coordinator
    default: float


NUMBERS = (
    SettingDescription(
        key="target_soc",
        attr="target_soc",
        default=DEFAULT_TARGET_SOC,
        native_min_value=10,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
    SettingDescription(
        key="cheap_threshold",
        attr="cheap_threshold",
        default=DEFAULT_CHEAP_THRESHOLD,
        native_min_value=-0.5,
        native_max_value=1.0,
        native_step=0.01,
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SlimLadenConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(SettingNumber(entry.runtime_data, d) for d in NUMBERS)


class SettingNumber(SlimLadenEntity, RestoreNumber):
    _domain = "number"

    entity_description: SettingDescription

    def __init__(self, coordinator, description: SettingDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return True  # instelling, los van de prijsdata

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        value = last.native_value if last and last.native_value is not None else self.entity_description.default
        setattr(self.coordinator, self.entity_description.attr, value)

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator, self.entity_description.attr)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.coordinator, self.entity_description.attr, value)
        self.async_write_ha_state()
        await self.coordinator.async_apply()
