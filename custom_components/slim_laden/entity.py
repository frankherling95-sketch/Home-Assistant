"""Gedeelde basis voor alle Slim laden-entiteiten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import SlimLadenCoordinator


class SlimLadenEntity(CoordinatorEntity[SlimLadenCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SlimLadenCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_NAME,
            manufacturer="Herling Analytics",
            model="Slim laden",
            entry_type=DeviceEntryType.SERVICE,
        )
