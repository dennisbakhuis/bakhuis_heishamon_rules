"""Config flow for Heating Manager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import CONF_MQTT_BASE, CONF_ROOM_SENSOR, DEFAULT_MQTT_BASE, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MQTT_BASE, default=DEFAULT_MQTT_BASE): str,
        vol.Optional(CONF_ROOM_SENSOR, default=""): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
    }
)


class HeatingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Heating Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            # Clean up empty room sensor
            room_sensor = user_input.get(CONF_ROOM_SENSOR, "").strip()
            data = {
                CONF_MQTT_BASE: user_input[CONF_MQTT_BASE].strip(),
                CONF_ROOM_SENSOR: room_sensor,
            }
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Heating Manager for HeishaMon",
                data=data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )
