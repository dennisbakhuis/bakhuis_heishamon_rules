"""Switch platform for Climate Manager."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CMD_SET_HEATPUMP, CONF_MQTT_BASE, TOPIC_HEATPUMP_STATE
from .sensor import DEVICE_INFO

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    mqtt_base = entry.data[CONF_MQTT_BASE]
    async_add_entities([HeishaMonHeatPumpSwitch(entry, mqtt_base)])


class HeishaMonHeatPumpSwitch(RestoreEntity, SwitchEntity):
    """Switch to control the heat pump on/off state."""

    _attr_has_entity_name = True
    _attr_name = "Heat Pump"
    _attr_unique_id = "climate_manager_heat_pump"
    _attr_icon = "mdi:heat-pump"

    def __init__(self, entry: ConfigEntry, mqtt_base: str) -> None:
        """Initialize."""
        self._entry = entry
        self._mqtt_base = mqtt_base
        self._attr_is_on = False
        self._attr_device_info = DEVICE_INFO
        self._unsubscribe: Any = None

    @property
    def state_topic(self) -> str:
        """MQTT state topic."""
        return f"{self._mqtt_base}/{TOPIC_HEATPUMP_STATE}"

    @property
    def command_topic(self) -> str:
        """MQTT command topic."""
        return f"{self._mqtt_base}/{CMD_SET_HEATPUMP}"

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to MQTT."""
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            self._attr_is_on = last_state.state == "on"

        @callback
        def message_received(message: Any) -> None:
            """Handle MQTT state message."""
            if message.payload == "1":
                self._attr_is_on = True
            elif message.payload == "0":
                self._attr_is_on = False
            self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(
            self.hass, self.state_topic, message_received
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the heat pump."""
        await mqtt.async_publish(self.hass, self.command_topic, "1")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the heat pump."""
        await mqtt.async_publish(self.hass, self.command_topic, "0")
        self._attr_is_on = False
        self.async_write_ha_state()
