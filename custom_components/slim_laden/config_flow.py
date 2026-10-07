"""Config flow: sensoren kiezen en auto/lader beschrijven."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_POWER,
    CONF_PRICE_SENSOR,
    CONF_SOC_SENSOR,
    DEFAULT_CAPACITY,
    DEFAULT_EFFICIENCY,
    DEFAULT_NAME,
    DEFAULT_POWER,
    DEFAULT_PRICE_SENSOR,
    DOMAIN,
)


def _schema(defaults: dict[str, Any], with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = str
    soc_key = (
        vol.Optional(CONF_SOC_SENSOR, description={"suggested_value": defaults[CONF_SOC_SENSOR]})
        if defaults.get(CONF_SOC_SENSOR)
        else vol.Optional(CONF_SOC_SENSOR)
    )
    fields.update(
        {
            vol.Required(
                CONF_PRICE_SENSOR, default=defaults.get(CONF_PRICE_SENSOR, DEFAULT_PRICE_SENSOR)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            soc_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="battery")),
            vol.Required(CONF_CAPACITY, default=defaults.get(CONF_CAPACITY, DEFAULT_CAPACITY)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=200,
                    step=0.1,
                    unit_of_measurement="kWh",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_POWER, default=defaults.get(CONF_POWER, DEFAULT_POWER)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=22,
                    step=0.1,
                    unit_of_measurement="kW",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_EFFICIENCY, default=defaults.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=50,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )
    return vol.Schema(fields)


class SlimLadenConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if self.hass.states.get(user_input[CONF_PRICE_SENSOR]) is None:
                errors[CONF_PRICE_SENSOR] = "entity_not_found"
            else:
                await self.async_set_unique_id(
                    user_input[CONF_PRICE_SENSOR] + "|" + user_input.get(CONF_SOC_SENSOR, "")
                )
                self._abort_if_unique_id_configured()
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}, with_name=True), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SlimLadenOptionsFlow()


class SlimLadenOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current, with_name=False))
