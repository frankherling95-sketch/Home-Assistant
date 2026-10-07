"""Sensoren die het laadplan zichtbaar maken."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SlimLadenConfigEntry
from .entity import SlimLadenEntity
from .planner import Plan


@dataclass(frozen=True, kw_only=True)
class PlanSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Plan], Any]
    attr_fn: Callable[[Plan], dict[str, Any]] = lambda _: {}


def _schedule(plan: Plan) -> dict[str, Any]:
    return {
        "blokken": [{"van": s.start.isoformat(), "tot": s.end.isoformat(), "prijs": s.price} for s in plan.slots],
        "volledig": plan.complete,
        "reden": plan.reason,
    }


SENSORS: tuple[PlanSensorDescription, ...] = (
    PlanSensorDescription(
        key="plan_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda p: p.start,
        attr_fn=_schedule,
    ),
    PlanSensorDescription(
        key="plan_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda p: p.end,
    ),
    PlanSensorDescription(
        key="needed_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda p: p.needed_kwh,
    ),
    PlanSensorDescription(
        key="estimated_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        value_fn=lambda p: p.estimated_cost,
    ),
    PlanSensorDescription(
        key="average_price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        suggested_display_precision=3,
        value_fn=lambda p: round(p.estimated_cost / p.needed_kwh, 4) if p.needed_kwh and p.complete else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SlimLadenConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(PlanSensor(entry.runtime_data, d) for d in SENSORS)


class PlanSensor(SlimLadenEntity, SensorEntity):
    entity_description: PlanSensorDescription

    def __init__(self, coordinator, description: PlanSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        plan = self.coordinator.data
        return self.entity_description.value_fn(plan) if plan else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        plan = self.coordinator.data
        return self.entity_description.attr_fn(plan) if plan else None
