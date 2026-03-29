"""Climate Manager for HeishaMon — Panasonic Aquarea weather-adaptive control.

This integration provides a Climate Manager for controlling a Panasonic Aquarea
heat pump via HeishaMon over MQTT. It includes weather-adaptive setpoint control
(WAR curve), Room Temperature Control (RTC), soft-start, and a full Lovelace
monitoring dashboard.

After installing via HACS, go to Settings → Integrations → Add Integration →
"Climate Manager for HeishaMon" to configure.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components import mqtt as mqtt_integration
from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.lovelace import dashboard as lovelace_dashboard
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CMD_OT_ROOM_SETPOINT,
    CMD_OT_ROOM_TEMP,
    CONF_MQTT_BASE,
    CONF_ROOM_SENSOR,
    DOMAIN,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

DASHBOARD_YAML = str(Path(__file__).parent / "dashboard.yaml")
DASHBOARD_URL_PATH = "climate-manager"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Climate Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"listeners": []}

    mqtt_base = entry.data[CONF_MQTT_BASE]

    # Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Automation 1: Room temp sync ---
    async def _publish_room_temps(_event_or_time: object = None) -> None:
        """Publish room temperature and setpoint to MQTT opentherm topics."""
        # Prefer live text entity value; fall back to config entry
        text_state = hass.states.get("text.climate_manager_room_sensor_entity")
        if text_state and text_state.state not in ("unknown", "unavailable", ""):
            room_sensor = text_state.state.strip()
        else:
            room_sensor = (
                entry.options.get(CONF_ROOM_SENSOR) or entry.data.get(CONF_ROOM_SENSOR, "")
            ) or ""

        # Get room temperature from configured sensor or from the echo sensor
        if room_sensor:
            state = hass.states.get(room_sensor)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    room_temp = float(state.state)
                    await mqtt_integration.async_publish(
                        hass,
                        f"{mqtt_base}/{CMD_OT_ROOM_TEMP}",
                        str(room_temp),
                    )
                except (ValueError, TypeError):
                    pass

        # Get setpoint from number entity
        setpoint_state = hass.states.get("number.climate_manager_room_setpoint_target")
        if setpoint_state and setpoint_state.state not in ("unknown", "unavailable"):
            try:
                setpoint = float(setpoint_state.state)
                await mqtt_integration.async_publish(
                    hass,
                    f"{mqtt_base}/{CMD_OT_ROOM_SETPOINT}",
                    str(setpoint),
                )
            except (ValueError, TypeError):
                pass

    # Track the text entity so we re-publish whenever the configured room sensor entity ID changes
    cancel_room_text = async_track_state_change_event(
        hass,
        ["text.climate_manager_room_sensor_entity"],
        lambda e: hass.async_create_task(_publish_room_temps(e)),
    )
    hass.data[DOMAIN][entry.entry_id]["listeners"].append(cancel_room_text)

    # Track setpoint state changes
    cancel_setpoint = async_track_state_change_event(
        hass,
        ["number.climate_manager_room_setpoint_target"],
        lambda e: hass.async_create_task(_publish_room_temps(e)),
    )
    hass.data[DOMAIN][entry.entry_id]["listeners"].append(cancel_setpoint)

    # Keepalive: publish every 5 minutes
    cancel_keepalive = async_track_time_interval(hass, _publish_room_temps, timedelta(minutes=5))
    hass.data[DOMAIN][entry.entry_id]["listeners"].append(cancel_keepalive)

    # --- Automation 2: Compressor tracker ---
    import time as _time

    # Seed initial state — if compressor is already running on HA startup,
    # initialise start_epoch to now() so run-seconds counts up immediately.
    # (We don't know the actual start time, so 'now' is an approximation.)
    async def _maybe_init_compressor_epoch() -> None:
        state = hass.states.get("sensor.climate_manager_compressor_freq")
        if state and state.state not in ("unknown", "unavailable"):
            try:
                if float(state.state) > 10:
                    epoch_state = hass.states.get("number.climate_manager_compressor_start_epoch")
                    current_epoch = float(epoch_state.state) if epoch_state and epoch_state.state not in ("unknown", "unavailable") else 0
                    if current_epoch <= 0:
                        await hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": "number.climate_manager_compressor_start_epoch",
                             "value": int(_time.time())},
                        )
            except (ValueError, TypeError):
                pass

    hass.async_create_task(_maybe_init_compressor_epoch())

    _prev_freq_above_threshold: dict[str, bool] = {"value": False}

    @callback
    def _on_compressor_freq_change(event: object) -> None:
        """Track compressor start: when freq goes from ≤10 to >10, record epoch."""
        state = hass.states.get("sensor.climate_manager_compressor_freq")
        if state is None or state.state in ("unknown", "unavailable"):
            return

        try:
            freq = float(state.state)
        except (ValueError, TypeError):
            return

        was_above = _prev_freq_above_threshold["value"]
        is_above = freq > 10
        _prev_freq_above_threshold["value"] = is_above

        if not was_above and is_above:
            # Compressor just started
            epoch = int(_time.time())
            hass.async_create_task(
                hass.services.async_call(
                    "number",
                    "set_value",
                    {
                        "entity_id": "number.climate_manager_compressor_start_epoch",
                        "value": epoch,
                    },
                )
            )

    cancel_compressor = async_track_state_change_event(
        hass,
        ["sensor.climate_manager_compressor_freq"],
        _on_compressor_freq_change,
    )
    hass.data[DOMAIN][entry.entry_id]["listeners"].append(cancel_compressor)

    # Register dashboard with HA Lovelace system
    # hass.data["lovelace"] is a LovelaceData dataclass — access via attributes, not dict keys
    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is not None and hasattr(lovelace_data, "dashboards"):
        dashboard_config = {
            "id": DASHBOARD_URL_PATH,
            "title": "Climate Manager",
            "icon": "mdi:heat-pump",
            "show_in_sidebar": True,
            "require_admin": False,
            "filename": DASHBOARD_YAML,
        }
        # LovelaceYAML.__init__ signature: (hass, url_path, config)
        lovelace_data.dashboards[DASHBOARD_URL_PATH] = lovelace_dashboard.LovelaceYAML(
            hass, DASHBOARD_URL_PATH, dashboard_config
        )
    else:
        _LOGGER.warning("Lovelace not available; dashboard panel not registered")

    # Register sidebar entry
    async_register_built_in_panel(
        hass,
        component_name="lovelace",
        sidebar_title="Climate Manager",
        sidebar_icon="mdi:heat-pump",
        frontend_url_path=DASHBOARD_URL_PATH,
        config={"mode": "yaml"},
        require_admin=False,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cancel all listeners
    for cancel in hass.data[DOMAIN][entry.entry_id].get("listeners", []):
        cancel()

    # Remove dashboard from Lovelace and sidebar
    lovelace_data = hass.data.get("lovelace")
    if lovelace_data is not None and hasattr(lovelace_data, "dashboards"):
        lovelace_data.dashboards.pop(DASHBOARD_URL_PATH, None)
    async_remove_panel(hass, DASHBOARD_URL_PATH)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
