"""Coordinator: leest prijs- en accusensor, rekent het laadplan door."""

from __future__ import annotations

import logging
from datetime import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_POWER,
    CONF_PRICE_SENSOR,
    CONF_SOC_SENSOR,
    DEFAULT_CHEAP_THRESHOLD,
    DEFAULT_DEPARTURE,
    DEFAULT_EFFICIENCY,
    DEFAULT_TARGET_SOC,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .planner import Plan, PlanInput, make_plan, next_deadline, parse_price_attributes

_LOGGER = logging.getLogger(__name__)


class SlimLadenCoordinator(DataUpdateCoordinator[Plan]):
    """Herberekent elke minuut en direct bij een nieuwe prijs of SoC."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL, config_entry=entry)
        # Instellingen; de entiteiten zetten hier hun herstelde waarde in.
        self.enabled = True
        self.target_soc: float = DEFAULT_TARGET_SOC
        self.departure: time = time.fromisoformat(DEFAULT_DEPARTURE)
        self.cheap_threshold: float = DEFAULT_CHEAP_THRESHOLD
        self.soc: float | None = None

    @property
    def settings(self) -> dict:
        return {**self.config_entry.data, **self.config_entry.options}

    @callback
    def async_start_tracking(self) -> None:
        sources = [self.settings[CONF_PRICE_SENSOR]]
        if soc := self.settings.get(CONF_SOC_SENSOR):
            sources.append(soc)

        @callback
        def _changed(_: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_refresh())

        self.config_entry.async_on_unload(async_track_state_change_event(self.hass, sources, _changed))

    async def async_apply(self) -> None:
        """Instelling gewijzigd via een entiteit: meteen herplannen."""
        await self.async_refresh()

    def _read_soc(self) -> float | None:
        entity_id = self.settings.get(CONF_SOC_SENSOR)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    async def _async_update_data(self) -> Plan:
        cfg = self.settings
        now = dt_util.now()
        tz = dt_util.get_default_time_zone()

        price_state = self.hass.states.get(cfg[CONF_PRICE_SENSOR])
        slots = parse_price_attributes(price_state.attributes, tz) if price_state else []
        if price_state is not None and not slots:
            _LOGGER.debug("Geen prijsblokken gevonden in %s", cfg[CONF_PRICE_SENSOR])

        self.soc = self._read_soc()
        plan = make_plan(
            PlanInput(
                now=now,
                deadline=next_deadline(now, self.departure),
                slots=slots,
                soc=self.soc,
                target_soc=self.target_soc,
                capacity_kwh=float(cfg[CONF_CAPACITY]),
                power_kw=float(cfg[CONF_POWER]),
                efficiency=float(cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100,
                cheap_threshold=self.cheap_threshold,
            )
        )
        if not self.enabled:
            # Uitgeschakeld = gewoon laden zoals de lader dat zonder ons zou doen.
            plan.charge_now, plan.reason = True, "uitgeschakeld"
        return plan
