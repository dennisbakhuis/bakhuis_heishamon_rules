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
heishamon_rules/
├── heishamon_rules_commented.txt   ← source of truth (human-readable, with comments)
├── rules_syntax.md                 ← HeishaMon rules language reference
└── examples/                       ← reference implementations from the community

simulator/                          ← Python test suite (see below)
Makefile                            ← build commands
pyproject.toml                      ← top-level uv project
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

The minified output is written to `heishamon_rules/heishamon_rules_minified.txt`. Upload that file via the HeishaMon web interface under **Rules**.

## Simulator & tests

A Python simulator lets you run and test the control logic without real hardware. It interprets the rules file directly so tests always reflect the deployed code.

### Setup

```bash
cd simulator
uv sync
```

### Run all tests

```bash
cd simulator
uv run pytest -v
```

All 37 tests should pass across 7 scenarios (cold day, mild day, defrost skip, pump duty, boot state, weather curve accuracy).

### Run a quick simulation in Python

```python
from heishamon_sim import HeishaMonSimulator

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

For more details on the simulator internals and test scenarios, see [`simulator/README.md`](simulator/README.md).

## Heating curve parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `curveOutdoorLow` | −10 °C | Coldest expected outdoor temp |
| `curveOutdoorHigh` | 18 °C | Outdoor temp where heating stops |
| `curveTargetLow` | 40 °C | Water temp at coldest outdoor temp |
| `curveTargetHigh` | 27 °C | Water temp at warmest outdoor temp |
| `minSetpoint` | 25 °C | Hard minimum water temp |
| `maxSetpoint` | 42 °C | Hard maximum water temp |
| `minFreqMargin` | 3 °C | Keep setpoint this many °C above inlet |
| `pumpDutyHigh` | 140 | Pump duty when compressor is running |
| `pumpDutyLow` | 93 | Pump duty when compressor is off |
