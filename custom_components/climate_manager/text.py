"""Text platform for Climate Manager — editable config values."""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensor import DEVICE_INFO

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities."""
    async_add_entities([RoomSensorConfigText(entry)])


class RoomSensorConfigText(TextEntity):
    """Editable text entity storing the room sensor entity ID."""

    _attr_has_entity_name = True
    _attr_name = "Room Sensor Entity"
    _attr_unique_id = "climate_manager_room_sensor_entity"
    _attr_icon = "mdi:thermometer-auto"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise from config entry options/data."""
        self._entry = entry
        self._attr_device_info = DEVICE_INFO
        # Read initial value: options take priority over data
        self._attr_native_value = (
            entry.options.get("room_sensor")
            or entry.data.get("room_sensor", "")
        ) or ""

    async def async_set_value(self, value: str) -> None:
        """Persist new entity ID to config entry options and update state."""
        self._attr_native_value = value.strip()
        new_options = dict(self._entry.options)
        new_options["room_sensor"] = self._attr_native_value
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()
