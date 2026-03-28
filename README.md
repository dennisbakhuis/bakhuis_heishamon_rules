# bakhuis_heishamon_rules
HeishaMon rules for the Bakhuis Panasonic Aquarea heat pump — Weather Dependent Control (WDC) with minimum-frequency operation and pump speed management.

## What the rules do
The rules run directly on the [HeishaMon](https://github.com/heishamon/HeishaMon) device (ESP8266) and implement four control loops:

| Timer | Interval | Function |
|-------|----------|----------|
| 1 | 30 min | Weather curve — linear interpolation outdoor temp → water setpoint |
| 2 | 30 s | Temperature smoothing — exponential moving average of outdoor temp |
| 3 | 30 s | Minimum frequency control — dynamically shifts setpoint to keep compressor at min speed |
| 4 | 15 s | Pump speed control — adjusts pump duty based on compressor state |

## Repository layout
```
src/
├── heishamon_rules/
│   ├── heishamon_rules_commented.txt   ← source of truth (human-readable, with comments)
│   ├── rules_syntax.md                 ← HeishaMon rules language reference
│   └── examples/                       ← reference implementations from the community
└── simulator/                          ← Python simulator package

tests/                                  ← pytest test suite
Makefile                                ← build commands
pyproject.toml                          ← consolidated uv project
```

## Deploying rules to HeishaMon
The device has a 10 KB limit, so the commented source must be minified before uploading.

**Prerequisites:** Python + [uv](https://github.com/astral-sh/uv)

```bash
# Install dependencies (first time only)
uv sync

# Minify (strips all comments and whitespace)
make rules

# Minify (strip comments only, keep whitespace)
make comments
```

The minified output is written to `src/heishamon_rules/heishamon_rules_minified.txt`. Upload that file via the HeishaMon web interface under **Rules**.

## Simulator & tests
A Python simulator lets you run and test the control logic without real hardware. It interprets the rules file directly so tests always reflect the deployed code.

### Setup

```bash
uv sync
```

### Run all tests

```bash
uv run pytest -v
```

All 37 tests should pass across 7 scenarios (cold day, mild day, defrost skip, pump duty, boot state, weather curve accuracy).

### Run a quick simulation in Python
```python
from simulator import HeishaMonSimulator

sim = HeishaMonSimulator()   # loads heishamon_rules_commented.txt automatically
sim.boot()

sim.set_sensors(
    Outside_Temp=-5.0,
    Main_Inlet_Temp=27.0,
    Main_Outlet_Temp=33.0,
    Compressor_Freq=30,
    Defrosting_State=0,
)

sim.fire_timer(1)   # weather curve  → sets #calculatedSetpoint
sim.fire_timer(2)   # temp smoothing → updates #OutsideTemp
sim.fire_timer(3)   # min-freq       → adjusts #dynamicShift and writes SetZ1HeatRequestTemperature
sim.fire_timer(4)   # pump control   → writes SetMaxPumpDuty

print("Setpoint:", sim.get_sensor("SetZ1HeatRequestTemperature"))
print("Dynamic shift:", sim.get_global("dynamicShift"))
print("Pump duty:", sim.get_sensor("SetMaxPumpDuty"))
```

For more details on the simulator internals and test scenarios, see [`src/simulator/`](src/simulator/).

## Heating Curve (Weather-Dependent Auto-Regulation)

### What is WAR?

WAR (Weather-Dependent Auto-Regulation) automatically adjusts the water supply temperature based on outdoor temperature. Colder outside means higher water temperature, milder outside means lower water temperature — keeping the house comfortable without manual adjustment and maximising heat pump efficiency.

### 3-Point Piecewise Curve

Rather than a single straight line (which forces a compromise between cold and mild accuracy), this implementation uses **two segments** that better match the real heat-loss characteristics of the building. The curve was calibrated to match the Node-RED system exactly.

**Control points:**

| Point | Outdoor temp | Water temp | Description |
|-------|-------------|-----------|-------------|
| Cold  | −7 °C       | 40 °C     | Maximum heating demand |
| Mid   | +5 °C       | 33 °C     | Transition between segments |
| Warm  | +15 °C      | 28 °C     | Minimum heating demand |

**Segments:**

| Segment | Range | Slope | Notes |
|---------|-------|-------|-------|
| 1 (cold)  | −7 °C to +5 °C  | −0.583 °C/°C | Steeper — more sensitive to cold |
| 2 (warm)  | +5 °C to +15 °C | −0.500 °C/°C | Shallower — gentle adjustment in mild weather |

Outside the range, the setpoint is **clamped**: below −7 °C → 40 °C; above +15 °C → 28 °C.

**ASCII curve shape:**

```
Water temp (°C)
  40 | *
     |  \  ← segment 1 (steeper: −0.58 °C/°C)
  33 |    *
     |     \  ← segment 2 (shallower: −0.5 °C/°C)
  28 |       *
     +--------+--------+-- Outdoor temp (°C)
             -7        5       15
```

**Comparison to the old 2-point curve:**
The previous implementation used a single line from −10 °C → 40 °C to 18 °C → 27 °C. The new piecewise curve narrows the outdoor range to the realistic operating window (−7 °C to +15 °C), uses a kink point at +5 °C to follow the actual building heat loss profile, and matches the Node-RED calibration exactly.

### Curve parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `curveOutdoorLow` | −7 °C | Cold curve point: outdoor temp |
| `curveOutdoorMid` | +5 °C | Mid curve point: outdoor temp |
| `curveOutdoorHigh` | +15 °C | Warm curve point: outdoor temp |
| `curveTargetLow` | 40 °C | Water temp at cold point |
| `curveTargetMid` | 33 °C | Water temp at mid point |
| `curveTargetHigh` | 28 °C | Water temp at warm point |
| `minSetpoint` | 20 °C | Hard minimum water temp |
| `maxSetpoint` | 42 °C | Hard maximum water temp |
| `minFreqMargin` | 3 °C | Keep setpoint this many °C above inlet |
| `pumpDutyHigh` | 140 | Pump duty when compressor is running |
| `pumpDutyLow` | 93 | Pump duty when compressor is off |
