"""Number platform for Heating Manager."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MQTT_BASE
from .sensor import DEVICE_INFO

_LOGGER = logging.getLogger(__name__)

# (key, name, min, max, step, unit, icon, default, publish_suffix_or_None)
NUMBER_DESCRIPTIONS = [
    (
        "room_setpoint_target",
        "Room Setpoint (RTC)",
        15,
        25,
        0.5,
        "°C",
        "mdi:home-thermometer-outline",
        21.0,
        None,
    ),
    (
        "dhw_temp",
        "DHW Target Temperature",
        40,
        75,
        1,
        "°C",
        "mdi:water-thermometer",
        52.0,
        "commands/SetDHWTemp",
    ),
    ("war_outdoor_low", "WAR Outdoor Low", -15, 0, 0.5, "°C", "mdi:thermometer-low", -7.0, None),
    ("war_outdoor_mid", "WAR Outdoor Mid", 0, 10, 0.5, "°C", "mdi:thermometer", 5.0, None),
    ("war_outdoor_high", "WAR Outdoor High", 10, 25, 0.5, "°C", "mdi:thermometer-high", 15.0, None),
    ("war_target_low", "WAR Target Low", 30, 45, 0.5, "°C", "mdi:thermometer-water", 40.0, None),
    ("war_target_mid", "WAR Target Mid", 25, 42, 0.5, "°C", "mdi:thermometer-water", 33.0, None),
    ("war_target_high", "WAR Target High", 20, 38, 0.5, "°C", "mdi:thermometer-water", 28.0, None),
    ("war_min_setpoint", "WAR Min Setpoint", 15, 30, 0.5, "°C", "mdi:arrow-down-bold", 20.0, None),
    ("war_max_setpoint", "WAR Max Setpoint", 35, 55, 0.5, "°C", "mdi:arrow-up-bold", 42.0, None),
    (
        "softstart_duration",
        "Soft-Start Duration",
        120,
        1800,
        60,
        "s",
        "mdi:timer-outline",
        780.0,
        None,
    ),
    (
        "softstart_max_shift",
        "Soft-Start Max Shift",
        1,
        10,
        0.5,
        "°C",
        "mdi:thermometer-plus-outline",
        5.0,
        None,
    ),
    (
        "softstart_outdoor_max",
        "Soft-Start Outdoor Max",
        0,
        15,
        0.5,
        "°C",
        "mdi:thermometer-chevron-up",
        8.0,
        None,
    ),
    (
        "compressor_start_epoch",
        "Compressor Start Epoch",
        0,
        9999999999,
        1,
        None,
        "mdi:timer",
        0.0,
        None,
    ),
]

# Keys that use SLIDER mode
_SLIDER_KEYS = {
    "war_outdoor_low",
    "war_outdoor_mid",
    "war_outdoor_high",
    "war_target_low",
    "war_target_mid",
    "war_target_high",
    "war_min_setpoint",
    "war_max_setpoint",
    "softstart_duration",
    "softstart_max_shift",
    "softstart_outdoor_max",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    mqtt_base = entry.data[CONF_MQTT_BASE]
    entities = []
    for desc in NUMBER_DESCRIPTIONS:
        entities.append(HeishaMonNumber(entry, mqtt_base, desc))
    async_add_entities(entities)


class HeishaMonNumber(RestoreNumber, NumberEntity):
    """A number entity for Heating Manager configuration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        mqtt_base: str,
        desc: tuple,
    ) -> None:
        """Initialize."""
        (key, name, min_val, max_val, step, unit, icon, default, publish_suffix) = desc
        self._entry = entry
        self._mqtt_base = mqtt_base
        self._key = key
        self._publish_suffix = publish_suffix
        self._default = default

        self._attr_name = name
        self._attr_unique_id = f"heating_manager_{key}"
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_native_value = default
        self._attr_device_info = DEVICE_INFO

        if key in _SLIDER_KEYS:
            self._attr_mode = NumberMode.SLIDER
        else:
            self._attr_mode = NumberMode.BOX

        if key == "compressor_start_epoch":
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Restore state from previous run."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data and last_data.native_value is not None:
            try:
                val = float(last_data.native_value)
                if self._attr_native_min_value <= val <= self._attr_native_max_value:
                    self._attr_native_value = val
            except (ValueError, TypeError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value and optionally publish to MQTT."""
        self._attr_native_value = value
        self.async_write_ha_state()

        if self._publish_suffix:
            await mqtt.async_publish(
                self.hass,
                f"{self._mqtt_base}/{self._publish_suffix}",
                str(value),
            )
