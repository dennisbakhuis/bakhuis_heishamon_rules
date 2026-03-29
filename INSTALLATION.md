# Installation Guide

This guide walks you through the complete setup from hardware to running rules.
Follow the phases **in order** — each phase builds on the previous one.

```
Phase 1 → HeishaMon hardware + MQTT
Phase 2 → Configure MQTT in Home Assistant
Phase 3 → Heating Manager dashboard (monitor before you control)
Phase 4 → Deploy the rules script
```

---

## Prerequisites

- **Panasonic Aquarea heat pump** — H, J, K, L, or M series
  ([confirmed models](https://github.com/heishamon/HeishaMon/blob/main/HeatPumpType.md))
- **HeishaMon device** — PCB or DIY Wemos D1 mini
  ([buy from Tindie](https://www.tindie.com/stores/thehognl/) or build from the project)
- **MQTT broker** — Mosquitto on a Raspberry Pi or existing home server is fine
- **Home Assistant** — any recent version with the MQTT integration

---

## Phase 1 — HeishaMon hardware + MQTT

### 1.1 Flash the firmware

Download the latest binary from the
[HeishaMon releases page](https://github.com/heishamon/HeishaMon/releases).
Use the Wemos D1 mini binary for the small board, or the ESP32-S3 binary for the
large HeishaMon PCB.

Flash using the HeishaMon web flasher or `esptool`:
```bash
esptool.py --port /dev/ttyUSB0 write_flash 0x0 HeishaMon.ino.bin
```

### 1.2 First boot — configure WiFi and MQTT

1. After flashing, HeishaMon broadcasts a WiFi hotspot (SSID: `HeishaMon-XXXXXX`)
2. Connect to it and open [http://192.168.4.1](http://192.168.4.1)
3. Set **WiFi SSID** and **password**
4. Set **MQTT server** (IP of your broker), port 1883, and optionally username/password
5. Leave the MQTT topic base as `panasonic_heat_pump` (the rest of this guide assumes that)
6. Save and reboot

### 1.3 Connect to the heat pump

Plug the HeishaMon into the **CN-CNT** or **CN-NMODE** port on the indoor unit.
HeishaMon is powered by the heat pump over the cable.

### 1.4 Verify data is publishing

Open your MQTT broker (e.g. MQTT Explorer) and subscribe to `panasonic_heat_pump/#`.
Within 60 seconds you should see messages arriving on topics like:
- `panasonic_heat_pump/main/Outside_Temp`
- `panasonic_heat_pump/main/Main_Outlet_Temp`
- `panasonic_heat_pump/main/Compressor_Freq`

If nothing arrives after 2 minutes, check the HeishaMon web UI at its IP address —
the **Log** tab shows what it's receiving from the heat pump.

### 1.5 Enable OpenTherm (required for RTC)

In the HeishaMon web UI → **Settings** → enable **OpenTherm**.
No physical OpenTherm thermostat is needed — this just enables the MQTT interface
that lets Home Assistant send room temperature values to the rules.

---

## Phase 2 — Configure MQTT in Home Assistant

### 2.1 Add the MQTT integration

In HA: **Settings → Devices & Services → Add Integration → MQTT** — configure
your broker details (host/IP, port 1883, and optionally username/password).

If you already have the MQTT integration, skip this step.

### 2.2 Verify MQTT connectivity

Go to **Developer Tools → MQTT** in HA and subscribe to `panasonic_heat_pump/#`.
Within 60 seconds you should see messages arriving from HeishaMon.

If nothing arrives, confirm HeishaMon is online and its MQTT broker settings
(host/IP, port, credentials) match your broker.

---

> **Optional: HeishaMon HA integration (HACS)**
>
> The HeishaMon project also provides a ready-made HA integration package
> ([heishamon-homeassistant](https://github.com/kamaradclimber/heishamon-homeassistant))
> that creates additional sensors and controls via HACS.
>
> **This is NOT required for the Heating Manager.** The Heating Manager is
> fully self-contained — all sensors, controls, and automations are defined in
> the files under `src/heating_manager/`. The only dependency is the MQTT
> broker, which you configured in step 2.1.
>
> You may still install the HACS integration if you want its additional
> features (e.g. full device integration, diagnostics), but the Heating
> Manager will work without it.

---

## Phase 3 — Heating Manager dashboard

Install the integration **before** the rules so you can see the heat pump behaving
normally first and confirm everything is working.

### Install via HACS

1. In Home Assistant: HACS → ⋮ → Custom Repositories →
   URL: `https://github.com/dennisbakhuis/bakhuis_heishamon_rules` → Category: Integration → Add

2. Find "Heating Manager for HeishaMon" in HACS → Install → Restart Home Assistant

3. Go to **Settings → Integrations → + Add Integration** → search "Heating Manager"

4. Enter your MQTT base topic (default: `panasonic_heat_pump`) and optionally
   your room temperature sensor entity ID for RTC

5. Submit → all sensors, controls, and analysis entities are created automatically

6. **Import the dashboard:**
   Settings → Dashboards → Add Dashboard → give it a name → Edit (pencil) →
   switch to YAML mode → paste the contents of `src/heating_manager/dashboard.yaml`

That's it — no configuration.yaml editing required.

> ✅ Confirm you can see live temperatures and the WAR setpoint is computing
> correctly before moving to Phase 4.

---

## Phase 4 — Deploy the rules script

The rules run directly on the HeishaMon device and take over setpoint control
from whatever the heat pump's built-in schedule or manual settings were doing.

> ⚠️ Once the rules are loaded, HeishaMon actively writes `Z1HeatRequestTemperature`
> every 30 minutes (weather curve) and every 30 seconds (min-freq + RTC adjustments).
> The heat pump's own schedule and curve settings are overridden.

### 4.1 Review and tune the parameters

Open `src/heishamon_rules/heishamon_rules_commented.txt` and review the
**System#Boot** section. Key parameters to check before first deploy:

```
-- Heating curve (tune to your house — defaults match Node-RED calibration)
#curveOutdoorLow    = -7;    -- outdoor temp at cold endpoint
#curveOutdoorMid    =  5;    -- outdoor temp at middle point
#curveOutdoorHigh   = 15;    -- outdoor temp at warm endpoint
#curveTargetLow     = 40;    -- water temp at cold endpoint
#curveTargetMid     = 33;    -- water temp at middle point
#curveTargetHigh    = 28;    -- water temp at warm endpoint
#minSetpoint        = 20;    -- hard minimum water temp
#maxSetpoint        = 42;    -- hard maximum water temp

-- Feature flags (start with min-freq and soft-start off until you're comfortable)
#enableMinFreq      = 1;     -- set to 0 to disable initially
#enableRTC          = 1;     -- set to 0 if room sensor not yet configured
#enableSoftStart    = 1;     -- set to 0 initially, enable after observing behavior

-- Soft-start tuning (tune after observing a few compressor cycles)
#softStartDuration  = 780;   -- seconds (13 min default — adjust to your HP)
```

### 4.2 Minify the rules

Install dependencies and build the minified file:

```bash
# From the repo root
uv sync
make rules
```

This produces `src/heishamon_rules/heishamon_rules_minified.txt` (stripped of all
comments, must be under 10 KB).

### 4.3 Upload to HeishaMon

1. Open the HeishaMon web UI (http://heishamon.local or its IP address)
2. Go to the **Rules** tab
3. Paste or upload the contents of `heishamon_rules_minified.txt`
4. Click **Save** — HeishaMon validates the ruleset instantly
5. If valid, the rules start running immediately; if invalid, the old ruleset is
   kept and an error appears in the console

### 4.4 Verify the rules are running

In HeishaMon's **Console** tab, you should see print output from the rules
(if `print()` statements are present). More reliably, watch the **Analysis** tab
of your Heating Manager dashboard:

- **WAR Setpoint** should update and the **Z1 Heat Request** should match it
  (within the shift range)
- The **Net Shift** should stay near 0 at first (if min-freq, RTC, soft-start
  are all disabled or inactive)
- Over the next few compressor cycles, you'll see soft-start shifts appear if
  `#enableSoftStart = 1` and the outdoor temp is below 8°C

### 4.5 Progressive feature enablement (recommended)

Suggested order for enabling features after confirming the basics work:

| Step | Enable | What to watch |
|------|--------|---------------|
| 1 | WAR curve only (`enableMinFreq=0`, `enableRTC=0`, `enableSoftStart=0`) | Z1 request matches WAR setpoint in Analysis tab |
| 2 | Min-freq (`enableMinFreq=1`) | Net shift goes slightly negative during long runs; HP stays on longer |
| 3 | RTC (`enableRTC=1`) | Net shift tracks room temperature correction; room sensor visible in Monitor |
| 4 | Soft-start (`enableSoftStart=1`) | Soft-start progress shows in Analysis tab on next compressor startup |

To change a flag, edit `heishamon_rules_commented.txt`, re-run `make rules`, and
re-upload the minified file.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| HeishaMon not publishing MQTT | HeishaMon web UI → Log tab; verify broker IP and credentials |
| HA sensors `unavailable` | MQTT connected? sensors.yaml added to configuration.yaml? HA restarted? |
| Dashboard showing wrong entity IDs | See `src/heating_manager/README.md` → Entity ID verification |
| Rules not taking effect | HeishaMon Console → any parse errors? Rules tab → is ruleset saved? |
| Z1 request not changing | Check `@Outside_Temp` is available; timer=1 fires after 60s from boot |
| RTC not working | OpenTherm enabled in HeishaMon? HA automation running? Check `sensor.heishamon_room_temperature` in HA |
| Soft-start never activates | Outdoor temp must be ≤ 8°C; check `sensor.heishamon_softstart_progress` |

---

## Summary

```
Phase 1  HeishaMon device → connected to HP → publishing to MQTT
   ↓
Phase 2  MQTT integration configured in HA → broker connected
   ↓
Phase 3  Heating Manager → dashboard installed → Analysis tab shows WAR/RTC/soft-start
   ↓
Phase 4  Rules deployed → HeishaMon controls setpoint → dashboard confirms it's working
```

For detailed documentation on the rules logic, see [`README.md`](README.md).
For the dashboard, see [`src/heating_manager/README.md`](src/heating_manager/README.md).
