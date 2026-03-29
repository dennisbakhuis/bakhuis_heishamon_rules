"""Select platform for Heating Manager."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_MQTT_BASE
from .sensor import DEVICE_INFO

_LOGGER = logging.getLogger(__name__)

# (key, name, options, value_map, publish_suffix, icon, default)
SELECT_DESCRIPTIONS = [
    (
        "quiet_mode",
        "Quiet Mode",
        ["Off", "Level 1 (less power)", "Level 2 (even less power)", "Level 3 (least power)"],
        {
            "Off": "0",
            "Level 1 (less power)": "1",
            "Level 2 (even less power)": "2",
            "Level 3 (least power)": "3",
        },
        "commands/SetQuietMode",
        "mdi:volume-off",
        "Off",
    ),
    (
        "operation_mode",
        "Operation Mode",
        ["Heat only", "Cool only", "Auto", "DHW only", "Heat+DHW", "Cool+DHW", "Auto+DHW"],
        {
            "Heat only": "0",
            "Cool only": "1",
            "Auto": "2",
            "DHW only": "3",
            "Heat+DHW": "4",
            "Cool+DHW": "5",
            "Auto+DHW": "6",
        },
        "commands/SetOperationMode",
        "mdi:heat-pump",
        "Heat+DHW",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    mqtt_base = entry.data[CONF_MQTT_BASE]
    entities = []
    for desc in SELECT_DESCRIPTIONS:
        entities.append(HeishaMonSelect(entry, mqtt_base, desc))
    async_add_entities(entities)


class HeishaMonSelect(RestoreEntity, SelectEntity):
    """A select entity for Heating Manager."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        mqtt_base: str,
        desc: tuple,
    ) -> None:
        """Initialize."""
        (key, name, options, value_map, publish_suffix, icon, default) = desc
        self._entry = entry
        self._mqtt_base = mqtt_base
        self._key = key
        self._value_map = value_map
        self._publish_suffix = publish_suffix

        self._attr_name = name
        self._attr_unique_id = f"heating_manager_{key}"
        self._attr_options = options
        self._attr_current_option = default
        self._attr_icon = icon
        self._attr_device_info = DEVICE_INFO

    async def async_added_to_hass(self) -> None:
        """Restore state from previous run."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Select an option and publish to MQTT."""
        self._attr_current_option = option
        self.async_write_ha_state()

        mqtt_value = self._value_map.get(option)
        if mqtt_value is not None:
            await mqtt.async_publish(
                self.hass,
                f"{self._mqtt_base}/{self._publish_suffix}",
                mqtt_value,
            )
