# HeishaMon WDC Simulator

A Python simulator and test suite for the HeishaMon Weather Dependent Control (WDC) rules.

## What it is

HeishaMon uses a custom scripting language to implement 4 control loops:

1. **Weather curve** (timer=1, every 30 min) — linear interpolation of outdoor temp → water setpoint
2. **Temperature smoothing** (timer=2, every 30s) — EMA of outdoor temperature
3. **Minimum frequency control** (timer=3, every 30s) — dynamically shifts setpoint to keep the compressor running at minimum frequency
4. **Pump speed control** (timer=4, every 15s) — sets pump duty based on compressor state

This package interprets that language in Python so scenarios can be simulated and tested without real hardware.

## Project layout

```
simulator/
├── pyproject.toml
├── README.md                 ← you are here
├── src/
│   └── heishamon_sim/
│       ├── __init__.py
│       ├── interpreter.py    ← HeishaMon rules language interpreter
│       └── simulator.py      ← high-level scenario helper
└── tests/
    └── test_scenarios.py     ← 37 scenario tests (A–G)
```

## Quick start

```bash
cd simulator
uv sync
uv run pytest -v
```

All 37 tests should pass.

## Interpreter approach

The interpreter is deliberately pragmatic:
- Block extraction via regex (`on … then … end`)
- Multi-line conditions / expressions joined by paren-balance checking
- Variable namespaces: `#globals`, `$locals`, `@heatpump_params`
- Expression evaluation via `_translate_expr` + Python `eval`
- Builtins: `isset`, `max`, `min`, `ceil`, `floor`, `round`, `setTimer`, `print`

It's not a complete parser — it's correct enough for testing the WDC control logic.

## Test scenarios

| ID | Name | What it tests |
|----|------|---------------|
| A | Cold day | Min-freq Case 1: outlet near setpoint, shift clamps to −3 |
| B | Mild day | Curve gives correct setpoint, shift stays 0 when margin is met |
| C | Defrost | Min-freq control skipped when `Defrosting_State=1` |
| D | Compressor off | Pump duty set to `pumpDutyLow` (93) |
| E | Compressor on | Pump duty set to `pumpDutyHigh` (140) |
| F | Boot init | All #globals set correctly at boot, including bug-2 fix (`calculatedSetpoint=35`) |
| G | Curve accuracy | Interpolated setpoints correct at −15, −10, 0, 10, 18, 20°C |

## Usage in your own scripts

```python
from heishamon_sim import HeishaMonSimulator

sim = HeishaMonSimulator()           # loads the rules file automatically
sim.boot()

sim.set_sensors(
    Outside_Temp=5.0,
    Main_Inlet_Temp=27.0,
    Main_Outlet_Temp=33.0,
    Compressor_Freq=30,
    Defrosting_State=0,
)

sim.fire_timer(1)   # weather curve → sets calculatedSetpoint
sim.fire_timer(3)   # min-freq control → adjusts dynamicShift

print(sim.get_global("calculatedSetpoint"))
print(sim.get_global("dynamicShift"))
print(sim.get_sensor("SetZ1HeatRequestTemperature"))
```
