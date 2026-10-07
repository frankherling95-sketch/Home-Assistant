"""Constanten voor Slim laden."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "slim_laden"

CONF_PRICE_SENSOR = "price_sensor"
CONF_SOC_SENSOR = "soc_sensor"
CONF_CAPACITY = "capacity_kwh"
CONF_POWER = "power_kw"
CONF_EFFICIENCY = "efficiency"

DEFAULT_NAME = "Slim laden"
DEFAULT_PRICE_SENSOR = "sensor.current_electricity_price_all_in"
DEFAULT_CAPACITY = 77.4
DEFAULT_POWER = 11.0
DEFAULT_EFFICIENCY = 90  # %

# Instellingen die als entiteit in het dashboard staan.
DEFAULT_TARGET_SOC = 80
DEFAULT_DEPARTURE = "07:30"
DEFAULT_CHEAP_THRESHOLD = 0.0

UPDATE_INTERVAL = timedelta(minutes=1)
