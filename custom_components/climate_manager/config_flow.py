"""Config flow for Climate Manager integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_MQTT_BASE, DEFAULT_MQTT_BASE, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MQTT_BASE, default=DEFAULT_MQTT_BASE): str,
    }
)


class HeatingManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore
    """Handle a config flow for Climate Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            data = {
                CONF_MQTT_BASE: user_input[CONF_MQTT_BASE].strip(),
            }
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Climate Manager for HeishaMon",
                data=data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ClimateManagerOptionsFlow(config_entry)


class ClimateManagerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Climate Manager."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_room_sensor = self._config_entry.options.get(
            "room_sensor",
            self._config_entry.data.get("room_sensor", ""),
        )

        schema = vol.Schema({
            vol.Optional("room_sensor", default=current_room_sensor): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "example": "sensor.living_room_temperature"
            },
        )
