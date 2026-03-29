# Heating Manager Dashboard

A complete Home Assistant Lovelace dashboard for monitoring and controlling a **Panasonic Aquarea heat pump** via [HeishaMon](https://github.com/Egyras/HeishaMon).

Built-in cards only — **no HACS, no custom components required**.

---

## Overview

The dashboard has three tabs:

### 🌡️ Monitor
Live operational overview of the heat pump:
- **Status bar** — HP power state, operating mode, defrost indicator, quiet mode, compressor frequency. A red banner appears automatically during defrost cycles.
- **Temperature glance** — outdoor, outside pipe, inlet, outlet, Z1 target, Z1 water, room temp, room setpoint (8 sensors at a glance).
- **Temperature history graph** — 24-hour trend of outlet, inlet, outdoor, and Z1 heat request.
- **Power & efficiency** — heat produced, electricity consumed, COP (heat-only), 24-hour power history.
- **Operational stats** — compressor hours, start/stop count, pump flow and speed, fan speeds, current, last error code.

### 📊 Analysis
Breaks down the setpoint calculation into components:
- **WAR Curve Analysis** — shows what the weather compensation curve would produce at the current outdoor temperature, compared to the actual setpoint the rules sent. The difference is the net shift from RTC + soft-start + min-freq combined.
- **RTC Analysis** — room temperature vs setpoint, computed delta, and which RTC correction step is active.
- **Soft-Start Analysis** — how long the compressor has been running, ramp progress (0–100%), and the current soft-start boost.
- **Combined setpoint history** — 24-hour overlay of WAR setpoint, Z1 heat request, and HP-confirmed main target.

### ⚙️ Settings
Controls and diagnostics:
- **Room setpoint slider** — sets the RTC target temperature (15–25°C). Automatically published to HeishaMon via MQTT.
- **HP direct controls** — quiet mode, heat mode, Z1 heat shift, DHW target temperature.
- **Feature status** — read-only table of HeishaMon rule features and where to configure them.
- **MQTT diagnostics** — last-updated timestamps for key sensors, and instructions for verifying MQTT connectivity.

---

## Configuration

### MQTT Base Topic

All MQTT topics use the prefix `panasonic_heat_pump` by default — the standard HeishaMon topic base.

If your HeishaMon device uses a different base topic (e.g. `my_heat_pump`), you only need to edit **one file**: `sensors.yaml`. Replace every occurrence of `panasonic_heat_pump` in the `state_topic` and `command_topic` fields.

`topics.yaml` documents every topic used by the Heating Manager and is the canonical reference. It is **not loaded by Home Assistant** — it is documentation only.

### Entity Naming

All sensor and switch entities follow the `heishamon_*` naming convention:

- `sensor.heishamon_outside_temp`, `sensor.heishamon_outlet_temp`, etc.
- `switch.heishamon_heatpump` — master on/off switch
- `sensor.heishamon_room_temp` — room temperature (OpenTherm echo)
- `sensor.heishamon_room_setpoint_received` — room setpoint echo

The `input_select` and `input_number` controls from the HeishaMon HA integration (`heishamon.yaml`) are also used for quiet mode, heat mode, DHW temperature, and heat shift. These retain their `heishamon_*` names from that integration.

---

## Installation

### Prerequisites
- Home Assistant with MQTT integration configured and connected to your HeishaMon broker.
- HeishaMon device publishing to `panasonic_heat_pump/#` topics.
- The [HeishaMon HA integration package](https://github.com/Egyras/HeishaMon) (`heishamon.yaml`) already imported — this provides the `input_select` / `input_number` controls for quiet mode, heat mode, heat shift, and DHW temperature.

---

### Step 1 — Add MQTT Switch and Sensors

Open `sensors.yaml`. It contains the full MQTT configuration for:
- The HP master on/off **switch** (`switch.heishamon_heatpump`)
- All **sensor** topics published by HeishaMon
- The **OpenTherm echo sensors** for room temperature RTC

Uncomment the `mqtt:` block and paste it into your `configuration.yaml` under the `mqtt:` key:

```yaml
mqtt:
  switch:
    - name: "Heishamon Heat Pump"
      unique_id: heishamon_heatpump
      state_topic: "panasonic_heat_pump/main/Heatpump_State"
      command_topic: "panasonic_heat_pump/commands/SetHeatpump"
      payload_on: "1"
      payload_off: "0"
      state_on: "1"
      state_off: "0"
      icon: mdi:heat-pump

  sensor:
    - name: "Heishamon Outside Temp"
      unique_id: heishamon_outside_temp
      state_topic: "panasonic_heat_pump/main/Outside_Temp"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement
    # ... (continue with all sensors from sensors.yaml)
```

If you already have an `mqtt:` key, merge the `switch:` and `sensor:` lists into your existing block.

**To use a different MQTT base topic:** replace `panasonic_heat_pump` in every `state_topic` / `command_topic` in `sensors.yaml`. See `topics.yaml` for the full topic reference.

---

### Step 2 — Add Input Helpers

Open `helpers.yaml` and paste the contents into your `configuration.yaml`:

```yaml
# In configuration.yaml:

input_number:
  heishamon_room_setpoint_target:
    name: "Room Setpoint (RTC)"
    min: 15
    max: 25
    step: 0.5
    unit_of_measurement: "°C"
    icon: mdi:home-thermometer-outline
    initial: 21

input_datetime:
  heishamon_compressor_start_time:
    name: "Heishamon Compressor Start Time"
    has_date: true
    has_time: true
```

If you use separate include files (`input_number.yaml`, `input_datetime.yaml`), paste the relevant sections there instead.

---

### Step 3 — Add Template Sensors

Open `sensors.yaml`. The `template:` block contains all the computed sensors for the Analysis tab (WAR setpoint, RTC delta, soft-start, heat COP, etc.).

Paste the `template:` block into your `configuration.yaml`. If you already have a `template:` key, merge the `- sensor:` list into your existing one:

```yaml
# In configuration.yaml:

template:
  - sensor:
      # ... paste all sensors from the template: block in sensors.yaml here ...
```

> **Important:** YAML is whitespace-sensitive. Each sensor definition starts with `- name:` at 6 spaces of indentation inside `template: → - sensor:`.

---

### Step 4 — Add Automations

Open `automations.yaml`. It contains two automations.

**Before adding:** replace `sensor.your_room_temperature_sensor` in Automation A with the entity_id of your actual room temperature sensor. Find it via HA → Developer Tools → States, search for a temperature sensor in your living area.

**To add via the HA UI:**
1. Go to Settings → Automations & Scenes → Automations
2. Click the ⋮ menu → "Import automation"
3. Paste each automation block and save

**To add via file-based config:**
Paste both automations into your `automations.yaml` (the file HA manages, usually at `config/automations.yaml`), then reload automations via Developer Tools → YAML → Automations.

---

### Step 5 — Restart Home Assistant

After adding helpers, template sensors, MQTT sensors, and automations:

1. Go to Settings → System → Restart → **Restart Home Assistant** (full restart to pick up all config changes)
2. Wait for HA to come back up
3. Verify there are no errors in Settings → System → Logs

---

### Step 6 — Import the Dashboard

1. Go to **Settings → Dashboards**
2. Click **+ Add dashboard**
3. Give it a name (e.g., "Heating Manager") and click Create
4. Open the new dashboard → click the ✏️ Edit button (top right)
5. Click ⋮ → **Edit in raw YAML editor**
6. Replace all content with the contents of `dashboard.yaml`
7. Click **Save**

**Enable in sidebar:** In Settings → Dashboards, find your new dashboard and enable "Show in sidebar".

---

### Step 7 — Verify Entity IDs

Open the Monitor tab. If any entity cards show "Entity not available", check the entity ID.

All entities follow the `heishamon_*` convention. Key ones to verify:

| Expected entity_id | Where to verify |
|---|---|
| `sensor.heishamon_outside_temp` | Developer Tools → States, search `heishamon` |
| `sensor.heishamon_compressor_freq` | Developer Tools → States |
| `sensor.heishamon_heat_cop` | Developer Tools → States |
| `sensor.heishamon_room_temp` | Should appear after Step 1 above |
| `switch.heishamon_heatpump` | Should appear after Step 1 above |
| `input_number.heishamon_room_setpoint_target` | Should appear after Step 2 above |

If any entities are missing, confirm the MQTT sensors block from `sensors.yaml` was added to `configuration.yaml` and HA was restarted.

---

## RTC Setup

Room Temperature Control requires HA to publish your room temperature to HeishaMon via MQTT.

1. Find your room temperature sensor entity_id (e.g., `sensor.living_room_temperature`)
2. In `automations.yaml`, replace both occurrences of `sensor.your_room_temperature_sensor` with your actual entity_id
3. Add the automation to HA (Step 4 above)
4. Use the **Room Setpoint** slider on the Settings tab to set your target temperature (default: 21°C)

To verify it's working: after the automation runs, check that `sensor.heishamon_room_temp` in HA matches your room sensor's value. It may take up to 5 minutes (the keepalive interval) after initial setup.

---

## Analysis Tab Explained

### WAR Curve
The **Weather Adaptive Regulation** curve maps outdoor temperature to a target water temperature:

| Outdoor | Water Setpoint |
|---------|---------------|
| ≤ −7°C  | 40°C (max)    |
| 5°C     | 33°C          |
| 15°C    | 28°C          |
| ≥ 15°C  | 28°C (min)    |

Between breakpoints the curve is piecewise linear (ceiling-rounded).

**`sensor.heishamon_war_setpoint`** computes this value in real time from the current outdoor temperature.

**Net Shift** = Actual Z1 Request − WAR Setpoint. A positive shift means min-freq boost or cold compensation is adding heat; a negative shift means RTC is reducing heat (room is warm) or soft-start is ramping down.

### RTC (Room Temperature Control)
The RTC correction lookup table adjusts the water setpoint based on how far the room temperature is from the setpoint:

| Room − Setpoint delta | Correction |
|-----------------------|-----------|
| > +1.5°C              | −3°C      |
| > +1.0°C              | −2°C      |
| > +0.5°C              | −1°C      |
| −0.2 to +0.5°C        | 0°C (dead band) |
| −0.4 to −0.2°C        | +1°C      |
| −0.6 to −0.4°C        | +2°C      |
| −2.0 to −0.6°C        | +3°C      |
| < −2.0°C              | +4°C      |

**`sensor.heishamon_rtc_delta`** = room − setpoint  
**`sensor.heishamon_rtc_correction`** = the correction step from the table above

### Soft-Start
When the compressor starts cold (outdoor ≤ 8°C), the setpoint is temporarily boosted and ramped back to the WAR value over 780 seconds (~13 minutes). The formula is:

```
shift = floor(5 × (sqrt(elapsed / 780) − 1))   clamped to [−5, 0]
```

At startup (t=0): shift = −5°C (maximum boost above WAR setpoint)  
At t=780s: shift = 0°C (ramp complete, back to WAR)

**`sensor.heishamon_compressor_run_seconds`** — elapsed seconds since last compressor start  
**`sensor.heishamon_softstart_shift`** — current shift value  
**`sensor.heishamon_softstart_progress`** — percentage through the 780-second ramp

> Soft-start only activates when outdoor temperature ≤ 8°C. Above that, shift is always 0.

### Heat COP
**`sensor.heishamon_heat_cop`** = heat power produced ÷ electrical power consumed.  
Only computed when electrical consumption > 50 W. COP > 3 is good for floor heating; COP > 4 is excellent.

---

## Troubleshooting

### Sensors show "Unknown" or "Unavailable"

**Template sensors (WAR setpoint, RTC, soft-start, COP):**
- Confirm the `template:` block from `sensors.yaml` was added to `configuration.yaml` and HA was restarted.
- Check HA Logs (Settings → System → Logs) for template rendering errors.
- In Developer Tools → Template, paste a sensor's `state:` block to test it manually.

**MQTT sensors (heishamon_outside_temp, heishamon_room_temp, etc.):**
- Confirm the `mqtt:` block from `sensors.yaml` was added and HA restarted.
- Check that HeishaMon is publishing — subscribe to `panasonic_heat_pump/#` in Developer Tools → MQTT.
- For room temp sensors: check that the RTC sync automation has run at least once.

### MQTT not receiving data from HeishaMon

1. Verify HeishaMon is online (check its web UI or ping it).
2. In HA → Developer Tools → MQTT, subscribe to `panasonic_heat_pump/#` — you should see messages every ~10 seconds.
3. Check your MQTT broker (Mosquitto) is running: Settings → Add-ons → Mosquitto broker → check state.
4. If HeishaMon recently rebooted, wait ~60 seconds for it to reconnect and resume publishing.

### Wrong MQTT prefix

If your HeishaMon uses a topic base other than `panasonic_heat_pump`:

1. Open `sensors.yaml`
2. Replace every occurrence of `panasonic_heat_pump` with your actual base topic
3. Restart Home Assistant

`topics.yaml` documents all topics for reference. Entity IDs (`sensor.heishamon_*`) do not change — only the MQTT topics in `sensors.yaml` need updating.

### Compressor start time not updating

If `sensor.heishamon_softstart_progress` stays at 100% or the soft-start shift never changes:
1. Verify the **HeishaMon: Track compressor start time** automation is enabled.
2. Check its trace (Settings → Automations → click it → Traces) to confirm it fired when the compressor started.
3. Verify `input_datetime.heishamon_compressor_start_time` exists (check Developer Tools → States).

### Room temperature not being sent to HeishaMon

1. Confirm `sensor.your_room_temperature_sensor` in `automations.yaml` was replaced with your actual entity ID.
2. Check the automation trace to see if it ran and what payload was published.
3. In Developer Tools → MQTT, subscribe to `panasonic_heat_pump/opentherm/read/roomTemp` and trigger the automation manually to test.
4. After a successful publish, `sensor.heishamon_room_temp` should update within seconds.
