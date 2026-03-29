"""Sensor platform for Climate Manager."""

from __future__ import annotations

import logging
import math
import time
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CONF_MQTT_BASE,
    DOMAIN,
    TOPIC_3WAY_VALVE,
    TOPIC_COMPRESSOR_CURRENT,
    TOPIC_COMPRESSOR_FREQ,
    TOPIC_DEFROSTING,
    TOPIC_FAN1_SPEED,
    TOPIC_FAN2_SPEED,
    TOPIC_HEAT_POWER_CONSUMED,
    TOPIC_HEAT_POWER_PRODUCED,
    TOPIC_HEATING_MODE,
    TOPIC_HEATPUMP_STATE,
    TOPIC_INLET_TEMP,
    TOPIC_LAST_ERROR,
    TOPIC_MAX_PUMP_DUTY,
    TOPIC_OPERATING_HOURS,
    TOPIC_OPERATING_MODE,
    TOPIC_OT_ROOM_SETPOINT_ECHO,
    TOPIC_OT_ROOM_TEMP_ECHO,
    TOPIC_OUTLET_TEMP,
    TOPIC_OUTSIDE_PIPE_TEMP,
    TOPIC_OUTSIDE_TEMP,
    TOPIC_PUMP_FLOW,
    TOPIC_PUMP_FLOWRATE_MODE,
    TOPIC_PUMP_SPEED,
    TOPIC_QUIET_MODE,
    TOPIC_START_STOP_COUNTER,
    TOPIC_TARGET_TEMP,
    TOPIC_Z1_HEAT_REQUEST,
    TOPIC_Z1_SENSOR_SETTINGS,
    TOPIC_Z1_WATER_TEMP,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, DOMAIN)},
    name="Climate Manager",
    manufacturer="HeishaMon / Panasonic",
    model="Aquarea Heat Pump",
)

# (topic_suffix, name, unique_suffix, unit, device_class, state_class, icon, enabled_by_default)
MQTT_SENSOR_DESCRIPTIONS = [
    (TOPIC_HEATPUMP_STATE, "Heatpump State", "heatpump_state", None, None, None, "mdi:power", True),
    (
        TOPIC_OPERATING_MODE,
        "Operating Mode",
        "operating_mode",
        None,
        None,
        None,
        "mdi:cog-outline",
        True,
    ),
    (
        TOPIC_DEFROSTING,
        "Defrosting State",
        "defrosting_state",
        None,
        None,
        None,
        "mdi:snowflake-melt",
        False,
    ),
    (TOPIC_QUIET_MODE, "Quiet Mode", "quiet_mode", None, None, None, "mdi:volume-off", False),
    (
        TOPIC_OUTSIDE_TEMP,
        "Outside Temp",
        "outside_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:thermometer",
        True,
    ),
    (
        TOPIC_OUTSIDE_PIPE_TEMP,
        "Outside Pipe Temp",
        "outside_pipe_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:pipe",
        False,
    ),
    (
        TOPIC_INLET_TEMP,
        "Inlet Temp",
        "inlet_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:thermometer-water",
        True,
    ),
    (
        TOPIC_OUTLET_TEMP,
        "Outlet Temp",
        "outlet_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:thermometer-high",
        True,
    ),
    (
        TOPIC_TARGET_TEMP,
        "Target Temp",
        "target_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:target",
        True,
    ),
    (
        TOPIC_Z1_HEAT_REQUEST,
        "Z1 Heat Request",
        "z1_heat_request",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:target",
        True,
    ),
    (
        TOPIC_Z1_WATER_TEMP,
        "Z1 Water Temp",
        "z1_water_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:water-thermometer",
        False,
    ),
    (
        TOPIC_COMPRESSOR_FREQ,
        "Compressor Freq",
        "compressor_freq",
        "Hz",
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:sine-wave",
        True,
    ),
    (
        TOPIC_PUMP_FLOW,
        "Pump Flow",
        "pump_flow",
        "l/min",
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:water-pump",
        False,
    ),
    (
        TOPIC_PUMP_SPEED,
        "Pump Speed",
        "pump_speed",
        "RPM",
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:speedometer",
        False,
    ),
    (
        TOPIC_MAX_PUMP_DUTY,
        "Max Pump Duty",
        "max_pump_duty",
        None,
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:pump",
        False,
    ),
    (TOPIC_3WAY_VALVE, "3way Valve", "3way_valve", None, None, None, "mdi:valve", False),
    (
        TOPIC_HEAT_POWER_PRODUCED,
        "Heat Power Produced",
        "heat_power_produced",
        "W",
        SensorDeviceClass.POWER,
        SensorStateClass.MEASUREMENT,
        "mdi:radiator",
        True,
    ),
    (
        TOPIC_HEAT_POWER_CONSUMED,
        "Heat Power Consumed",
        "heat_power_consumed",
        "W",
        SensorDeviceClass.POWER,
        SensorStateClass.MEASUREMENT,
        "mdi:lightning-bolt",
        True,
    ),
    (
        TOPIC_OPERATING_HOURS,
        "Operating Hours",
        "operating_hours",
        "h",
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:clock-outline",
        False,
    ),
    (
        TOPIC_START_STOP_COUNTER,
        "Start Stop Counter",
        "start_stop_counter",
        None,
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:counter",
        False,
    ),
    (
        TOPIC_LAST_ERROR,
        "Last Error",
        "last_error",
        None,
        None,
        None,
        "mdi:alert-circle-outline",
        False,
    ),
    (
        TOPIC_FAN1_SPEED,
        "Fan 1 Speed",
        "fan1_speed",
        "RPM",
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:fan",
        False,
    ),
    (
        TOPIC_FAN2_SPEED,
        "Fan 2 Speed",
        "fan2_speed",
        "RPM",
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:fan",
        False,
    ),
    (
        TOPIC_COMPRESSOR_CURRENT,
        "Compressor Current",
        "compressor_current",
        "A",
        SensorDeviceClass.CURRENT,
        SensorStateClass.MEASUREMENT,
        "mdi:current-ac",
        False,
    ),
    (
        TOPIC_HEATING_MODE,
        "Heating Mode",
        "heating_mode",
        None,
        None,
        None,
        "mdi:thermometer-check",
        True,
    ),
    (
        TOPIC_Z1_SENSOR_SETTINGS,
        "Z1 Sensor Settings",
        "z1_sensor_settings",
        None,
        None,
        None,
        "mdi:water-thermometer",
        True,
    ),
    (
        TOPIC_PUMP_FLOWRATE_MODE,
        "Pump Flowrate Mode",
        "pump_flowrate_mode",
        None,
        None,
        None,
        "mdi:pump",
        False,
    ),
    (
        TOPIC_OT_ROOM_TEMP_ECHO,
        "Room Temp",
        "room_temp",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:home-thermometer",
        True,
    ),
    (
        TOPIC_OT_ROOM_SETPOINT_ECHO,
        "Room Setpoint Received",
        "room_setpoint_received",
        "°C",
        SensorDeviceClass.TEMPERATURE,
        SensorStateClass.MEASUREMENT,
        "mdi:home-thermometer-outline",
        True,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    mqtt_base = entry.data[CONF_MQTT_BASE]

    entities: list[SensorEntity] = []

    # MQTT sensors
    for (
        topic_suffix,
        name,
        unique_suffix,
        unit,
        device_class,
        state_class,
        icon,
        enabled_by_default,
    ) in MQTT_SENSOR_DESCRIPTIONS:
        entities.append(
            HeishaMonMQTTSensor(
                entry=entry,
                mqtt_base=mqtt_base,
                topic_suffix=topic_suffix,
                name=name,
                unique_suffix=unique_suffix,
                unit=unit,
                device_class=device_class,
                state_class=state_class,
                icon=icon,
                enabled_by_default=enabled_by_default,
            )
        )

    # Template sensors
    entities.extend(
        [
            WARSetpointSensor(entry),
            NetShiftSensor(entry),
            RTCDeltaSensor(entry),
            RTCCorrectionSensor(entry),
            CompressorRunSecondsSensor(entry),
            SoftStartShiftSensor(entry),
            SoftStartProgressSensor(entry),
            HeatCOPSensor(entry),
        ]
    )

    async_add_entities(entities)


class HeishaMonMQTTSensor(RestoreSensor, SensorEntity):
    """Sensor that subscribes to one MQTT topic."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        mqtt_base: str,
        topic_suffix: str,
        name: str,
        unique_suffix: str,
        unit: str | None,
        device_class: str | None,
        state_class: str | None,
        icon: str,
        enabled_by_default: bool = True,
    ) -> None:
        """Initialize the sensor."""
        self._entry = entry
        self._mqtt_base = mqtt_base
        self._topic_suffix = topic_suffix
        self._attr_name = name
        self._attr_unique_id = f"climate_manager_{unique_suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = DEVICE_INFO
        self._attr_entity_registry_enabled_default = enabled_by_default
        self._unsubscribe: Any = None

    @property
    def full_topic(self) -> str:
        """Full MQTT topic."""
        return f"{self._mqtt_base}/{self._topic_suffix}"

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to MQTT."""
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value not in (None, "unknown", "unavailable"):
            self._attr_native_value = last_state.native_value

        @callback
        def message_received(message: Any) -> None:
            """Handle new MQTT message."""
            self._attr_native_value = message.payload
            self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(self.hass, self.full_topic, message_received)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None


class HeishaMonTemplateSensor(SensorEntity):
    """Base class for template sensors that derive from other HA entities."""

    _attr_has_entity_name = True
    _dependencies: list[str] = []
    _cancel_listeners: list[Any]
    _cancel_timer: Any = None

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._cancel_listeners = []
        self._cancel_timer = None
        self._attr_device_info = DEVICE_INFO

    def _get_float(self, entity_id: str, default: float = 0.0) -> float:
        """Get float value from HA state."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _update(self) -> None:
        """Update the sensor value — override in subclasses."""

    async def async_added_to_hass(self) -> None:
        """Subscribe to dependency state changes and run initial update."""
        await super().async_added_to_hass()

        @callback
        def _on_dependency_change(event: Any) -> None:
            self._update()
            self.async_write_ha_state()

        if self._dependencies:
            cancel = async_track_state_change_event(
                self.hass, self._dependencies, _on_dependency_change
            )
            self._cancel_listeners.append(cancel)

        self._update()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel listeners."""
        for cancel in self._cancel_listeners:
            cancel()
        self._cancel_listeners.clear()
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None


class WARSetpointSensor(HeishaMonTemplateSensor):
    """WAR Setpoint template sensor."""

    _attr_name = "WAR Setpoint"
    _attr_unique_id = "climate_manager_war_setpoint"
    _attr_native_unit_of_measurement = "°C"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bell-curve"

    _dependencies = [
        "sensor.climate_manager_outside_temp",
        "number.climate_manager_war_outdoor_low",
        "number.climate_manager_war_outdoor_mid",
        "number.climate_manager_war_outdoor_high",
        "number.climate_manager_war_target_low",
        "number.climate_manager_war_target_mid",
        "number.climate_manager_war_target_high",
        "number.climate_manager_war_min_setpoint",
        "number.climate_manager_war_max_setpoint",
    ]

    def _update(self) -> None:
        outdoor_state = self.hass.states.get("sensor.climate_manager_outside_temp")
        if outdoor_state is None or outdoor_state.state in ("unknown", "unavailable"):
            self._attr_native_value = None
            return

        try:
            outdoor = float(outdoor_state.state)
        except (ValueError, TypeError):
            self._attr_native_value = None
            return

        ol = self._get_float("number.climate_manager_war_outdoor_low", -7.0)
        om = self._get_float("number.climate_manager_war_outdoor_mid", 5.0)
        oh = self._get_float("number.climate_manager_war_outdoor_high", 15.0)
        tl = self._get_float("number.climate_manager_war_target_low", 40.0)
        tm = self._get_float("number.climate_manager_war_target_mid", 33.0)
        th = self._get_float("number.climate_manager_war_target_high", 28.0)
        min_sp = self._get_float("number.climate_manager_war_min_setpoint", 20.0)
        max_sp = self._get_float("number.climate_manager_war_max_setpoint", 42.0)

        self._attr_native_value = _compute_war(outdoor, ol, om, oh, tl, tm, th, min_sp, max_sp)


def _compute_war(
    outdoor: float,
    ol: float,
    om: float,
    oh: float,
    tl: float,
    tm: float,
    th: float,
    min_sp: float,
    max_sp: float,
) -> int:
    """Compute WAR setpoint using piecewise linear formula."""
    if outdoor <= ol:
        raw: float = tl
    elif outdoor >= oh:
        raw = th
    elif outdoor <= om:
        slope = (tl - tm) / (om - ol)
        raw = math.ceil(tm + (om - outdoor) * slope)
    else:
        slope = (tm - th) / (oh - om)
        raw = math.ceil(th + (oh - outdoor) * slope)
    return max(int(min_sp), min(int(max_sp), int(raw)))


class NetShiftSensor(HeishaMonTemplateSensor):
    """Net Shift = Z1 heat request - WAR setpoint."""

    _attr_name = "Net Shift"
    _attr_unique_id = "climate_manager_net_shift"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:delta"

    _dependencies = [
        "sensor.climate_manager_z1_heat_request",
        "sensor.climate_manager_war_setpoint",
    ]

    def _update(self) -> None:
        z1 = self._get_float("sensor.climate_manager_z1_heat_request")
        war = self._get_float("sensor.climate_manager_war_setpoint")
        z1_state = self.hass.states.get("sensor.climate_manager_z1_heat_request")
        war_state = self.hass.states.get("sensor.climate_manager_war_setpoint")
        if (
            z1_state is None
            or z1_state.state in ("unknown", "unavailable")
            or war_state is None
            or war_state.state in ("unknown", "unavailable")
        ):
            self._attr_native_value = None
            return
        self._attr_native_value = round(z1 - war, 1)


class RTCDeltaSensor(HeishaMonTemplateSensor):
    """RTC Delta = room_temp - room_setpoint_received."""

    _attr_name = "RTC Delta"
    _attr_unique_id = "climate_manager_rtc_delta"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:delta"

    _dependencies = [
        "sensor.climate_manager_room_temp",
        "sensor.climate_manager_room_setpoint_received",
    ]

    def _update(self) -> None:
        room_state = self.hass.states.get("sensor.climate_manager_room_temp")
        setpoint_state = self.hass.states.get("sensor.climate_manager_room_setpoint_received")
        if (
            room_state is None
            or room_state.state in ("unknown", "unavailable")
            or setpoint_state is None
            or setpoint_state.state in ("unknown", "unavailable")
        ):
            self._attr_native_value = None
            return
        try:
            room = float(room_state.state)
            setpoint = float(setpoint_state.state)
            self._attr_native_value = round(room - setpoint, 2)
        except (ValueError, TypeError):
            self._attr_native_value = None


class RTCCorrectionSensor(HeishaMonTemplateSensor):
    """RTC Correction — 8-band lookup on RTC delta."""

    _attr_name = "RTC Correction"
    _attr_unique_id = "climate_manager_rtc_correction"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-plus-outline"

    _dependencies = ["sensor.climate_manager_rtc_delta"]

    def _update(self) -> None:
        state = self.hass.states.get("sensor.climate_manager_rtc_delta")
        if state is None or state.state in ("unknown", "unavailable"):
            self._attr_native_value = None
            return
        try:
            delta = float(state.state)
        except (ValueError, TypeError):
            self._attr_native_value = None
            return

        if delta > 1.5:
            self._attr_native_value = -3
        elif delta > 1.0:
            self._attr_native_value = -2
        elif delta > 0.5:
            self._attr_native_value = -1
        elif delta >= -0.2:
            self._attr_native_value = 0
        elif delta >= -0.4:
            self._attr_native_value = 1
        elif delta >= -0.6:
            self._attr_native_value = 2
        elif delta >= -2.0:
            self._attr_native_value = 3
        else:
            self._attr_native_value = 4


class CompressorRunSecondsSensor(HeishaMonTemplateSensor):
    """Compressor Run Seconds — time since compressor started."""

    _attr_name = "Compressor Run Seconds"
    _attr_unique_id = "climate_manager_compressor_run_seconds"
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    _dependencies = [
        "sensor.climate_manager_compressor_freq",
        "number.climate_manager_compressor_start_epoch",
    ]

    def _update(self, _now: Any = None) -> None:
        freq = self._get_float("sensor.climate_manager_compressor_freq", 0)
        start = self._get_float("number.climate_manager_compressor_start_epoch", 0)
        if freq <= 10 or start <= 0:
            self._attr_native_value = 0
        else:
            self._attr_native_value = max(0, int(time.time()) - int(start))

    async def async_added_to_hass(self) -> None:
        """Subscribe + schedule 10s periodic update when compressor running."""
        await super().async_added_to_hass()

        @callback
        def _tick(_now: Any) -> None:
            freq = self._get_float("sensor.climate_manager_compressor_freq", 0)
            if freq > 10:
                self._update()
                self.async_write_ha_state()

        self._cancel_timer = async_track_time_interval(self.hass, _tick, timedelta(seconds=10))

    async def async_will_remove_from_hass(self) -> None:
        """Cancel listeners."""
        await super().async_will_remove_from_hass()


class SoftStartShiftSensor(HeishaMonTemplateSensor):
    """Soft-Start Shift sensor."""

    _attr_name = "Soft-Start Shift"
    _attr_unique_id = "climate_manager_softstart_shift"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-chevron-down"

    _dependencies = [
        "sensor.climate_manager_compressor_run_seconds",
        "sensor.climate_manager_outside_temp",
        "number.climate_manager_softstart_duration",
        "number.climate_manager_softstart_max_shift",
        "number.climate_manager_softstart_outdoor_max",
    ]

    def _update(self) -> None:
        run = self._get_float("sensor.climate_manager_compressor_run_seconds", 0)
        dur = self._get_float("number.climate_manager_softstart_duration", 780.0)
        max_s = self._get_float("number.climate_manager_softstart_max_shift", 5.0)
        outdoor = self._get_float("sensor.climate_manager_outside_temp", 99.0)
        omax = self._get_float("number.climate_manager_softstart_outdoor_max", 8.0)

        if outdoor > omax or run <= 0 or run >= dur:
            self._attr_native_value = 0
            return

        raw = max_s * ((run / dur) ** 0.5 - 1)
        self._attr_native_value = max(-int(max_s), min(0, int(raw)))


class SoftStartProgressSensor(HeishaMonTemplateSensor):
    """Soft-Start Progress sensor."""

    _attr_name = "Soft-Start Progress"
    _attr_unique_id = "climate_manager_softstart_progress"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:progress-clock"

    _dependencies = [
        "sensor.climate_manager_compressor_run_seconds",
        "sensor.climate_manager_outside_temp",
        "number.climate_manager_softstart_duration",
        "number.climate_manager_softstart_max_shift",
        "number.climate_manager_softstart_outdoor_max",
    ]

    def _update(self) -> None:
        run = self._get_float("sensor.climate_manager_compressor_run_seconds", 0)
        dur = self._get_float("number.climate_manager_softstart_duration", 780.0)
        outdoor = self._get_float("sensor.climate_manager_outside_temp", 99.0)
        omax = self._get_float("number.climate_manager_softstart_outdoor_max", 8.0)

        if outdoor > omax:
            self._attr_native_value = 100
            return
        if dur <= 0:
            self._attr_native_value = 100
            return
        self._attr_native_value = min(100, int(run / dur * 100))


class HeatCOPSensor(HeishaMonTemplateSensor):
    """Heat COP sensor."""

    _attr_name = "Heat COP"
    _attr_unique_id = "climate_manager_heat_cop"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fire"

    _dependencies = [
        "sensor.climate_manager_heat_power_produced",
        "sensor.climate_manager_heat_power_consumed",
    ]

    def _update(self) -> None:
        produced = self._get_float("sensor.climate_manager_heat_power_produced", 0)
        consumed = self._get_float("sensor.climate_manager_heat_power_consumed", 0)
        if consumed > 50:
            self._attr_native_value = round(produced / consumed, 2)
        else:
            self._attr_native_value = None
