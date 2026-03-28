"""
Scenario tests for the HeishaMon WDC rules simulator.

Covers:
  A - Cold day: min-freq active, shift should be ≤ 0
  B - Mild day: setpoint is in a reasonable range
  C - Defrost: min-freq control is skipped (shift unchanged)
  D - Compressor off: pump duty → pumpDutyLow
  E - Compressor on:  pump duty → pumpDutyHigh
  F - Boot initialization: all globals set correctly
  G - Weather curve accuracy: spot-check interpolated setpoints
"""

from __future__ import annotations

import math
import pytest
from simulator import HeishaMonSimulator


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def fresh_sim() -> HeishaMonSimulator:
    """Return a booted simulator with default config."""
    sim = HeishaMonSimulator()
    # Provide a basic Outside_Temp so boot's EMA init doesn't store None
    sim.set_sensors(Outside_Temp=10.0)
    sim.boot()
    return sim


# ---------------------------------------------------------------------------
# Scenario A — Cold day
# ---------------------------------------------------------------------------

class TestScenarioA_ColdDay:
    """
    Outdoor=-5°C (cold), inlet=27°C, outlet=37°C (near setpoint), compressor running.

    At -5°C the weather curve gives:
      tempRange = 18 - (-10) = 28
      setpointRange = 40 - 27 = 13
      tempOffset = 18 - (-5) = 23
      setpoint = ceil(27 + 23 * 13 / 28) = ceil(27 + 10.68) = ceil(37.68) = 38

    outletDelta = 37 - 38 = -1  → Case 1 (outlet approaching setpoint)
    targetShift = inlet(27) + margin(3) - setpoint(38) = -8
    dynamicShift = max(-3, -8) = -3 (clamped)

    With outlet=33 instead (delta=-5) we'd hit Case 2 (well below setpoint) →
    shift resets to 0, which is also correct but doesn't test the lowering path.
    We use outlet=37 to specifically test Case 1.
    """

    def setup_method(self):
        self.sim = fresh_sim()
        self.sim.set_sensors(
            Outside_Temp=-5.0,
            Main_Inlet_Temp=27.0,
            Main_Outlet_Temp=37.0,  # near setpoint=38, triggers Case 1
            Compressor_Freq=30,
            Defrosting_State=0,
        )
        # Fire timer=2 to seed the smoothed temp, then timer=1 for curve
        self.sim.fire_timer(2)
        # Override smoothed temp to match outdoor for determinism
        self.sim.set_globals(OutsideTemp=-5.0)
        self.sim.fire_timer(1)
        self.sim.fire_timer(3)

    def test_dynamic_shift_is_negative(self):
        shift = self.sim.get_global("dynamicShift")
        assert shift is not None, "dynamicShift should be set"
        assert shift < 0, f"Expected negative shift on cold day but got {shift}"

    def test_dynamic_shift_clamped_to_minus_three(self):
        shift = self.sim.get_global("dynamicShift")
        assert shift == -3, f"Expected shift=-3 (clamped) but got {shift}"

    def test_calculated_setpoint_is_38(self):
        sp = self.sim.get_global("calculatedSetpoint")
        assert sp == 38, f"Expected calculatedSetpoint=38 for outdoor=-5°C, got {sp}"

    def test_final_setpoint_applied_is_reduced(self):
        # finalSetpoint = calculatedSetpoint + dynamicShift = 38 + (-3) = 35
        last = self.sim.get_global("lastSetpoint")
        assert last is not None
        assert last < self.sim.get_global("calculatedSetpoint"), (
            "Applied setpoint should be below the base calculated setpoint"
        )


# ---------------------------------------------------------------------------
# Scenario B — Mild day
# ---------------------------------------------------------------------------

class TestScenarioB_MildDay:
    """
    Outdoor=12°C, inlet=27°C, outlet=30°C, compressor running.

    At 12°C:
      tempOffset = 18 - 12 = 6
      setpoint = ceil(27 + 6 * 13 / 28) = ceil(27 + 2.79) = ceil(29.79) = 30

    outletDelta = 30 - 30 = 0  → Case 1 (outlet approaching setpoint)
    targetShift = inlet(27) + margin(3) - setpoint(30) = 0
    dynamicShift = max(-3, 0) = 0
    """

    def setup_method(self):
        self.sim = fresh_sim()
        self.sim.set_sensors(
            Outside_Temp=12.0,
            Main_Inlet_Temp=27.0,
            Main_Outlet_Temp=30.0,
            Compressor_Freq=25,
            Defrosting_State=0,
        )
        self.sim.set_globals(OutsideTemp=12.0)
        self.sim.fire_timer(1)
        self.sim.fire_timer(3)

    def test_calculated_setpoint_reasonable(self):
        sp = self.sim.get_global("calculatedSetpoint")
        assert sp is not None
        assert 25 <= sp <= 42, f"Setpoint {sp} is outside safe range [25, 42]"

    def test_calculated_setpoint_is_30(self):
        sp = self.sim.get_global("calculatedSetpoint")
        assert sp == 30, f"Expected calculatedSetpoint=30 for outdoor=12°C, got {sp}"

    def test_shift_is_zero(self):
        shift = self.sim.get_global("dynamicShift")
        assert shift == 0, f"Expected shift=0 for mild day, got {shift}"


# ---------------------------------------------------------------------------
# Scenario C — Defrost
# ---------------------------------------------------------------------------

class TestScenarioC_Defrost:
    """
    When Defrosting_State=1, the min-freq guard condition is False,
    so the entire timer=3 body is skipped and dynamicShift is not modified.
    """

    def setup_method(self):
        self.sim = fresh_sim()
        # Set a non-zero initial shift to detect if it changes
        self.sim.set_globals(dynamicShift=-2)
        self.sim.set_sensors(
            Outside_Temp=5.0,
            Main_Inlet_Temp=27.0,
            Main_Outlet_Temp=33.0,
            Compressor_Freq=30,
            Defrosting_State=1,   # defrosting!
        )
        self.sim.set_globals(OutsideTemp=5.0)
        self.sim.fire_timer(1)
        self.sim.fire_timer(3)

    def test_shift_unchanged_during_defrost(self):
        shift = self.sim.get_global("dynamicShift")
        assert shift == -2, (
            f"dynamicShift should remain -2 during defrost, got {shift}"
        )

    def test_no_setpoint_written_during_defrost(self):
        # lastSetpoint should still be 0 (never written by timer=3)
        last = self.sim.get_global("lastSetpoint")
        assert last == 0, f"lastSetpoint should be 0 (timer=3 skipped), got {last}"


# ---------------------------------------------------------------------------
# Scenario D — Compressor off
# ---------------------------------------------------------------------------

class TestScenarioD_CompressorOff:
    """
    Compressor_Freq=0 → pump duty should be pumpDutyLow (93).
    """

    def setup_method(self):
        self.sim = fresh_sim()
        self.sim.set_sensors(Compressor_Freq=0)
        self.sim.fire_timer(4)

    def test_pump_duty_low(self):
        duty = self.sim.get_sensor("SetMaxPumpDuty")
        low = self.sim.get_global("pumpDutyLow")
        assert duty == low, f"Expected pump duty={low} when compressor off, got {duty}"

    def test_last_pump_duty_updated(self):
        last = self.sim.get_global("lastPumpDuty")
        low = self.sim.get_global("pumpDutyLow")
        assert last == low, f"lastPumpDuty should be {low}, got {last}"


# ---------------------------------------------------------------------------
# Scenario E — Compressor on
# ---------------------------------------------------------------------------

class TestScenarioE_CompressorOn:
    """
    Compressor_Freq=30 → pump duty should be pumpDutyHigh (140).
    """

    def setup_method(self):
        self.sim = fresh_sim()
        self.sim.set_sensors(Compressor_Freq=30)
        self.sim.fire_timer(4)

    def test_pump_duty_high(self):
        duty = self.sim.get_sensor("SetMaxPumpDuty")
        high = self.sim.get_global("pumpDutyHigh")
        assert duty == high, f"Expected pump duty={high} when compressor on, got {duty}"

    def test_last_pump_duty_updated(self):
        last = self.sim.get_global("lastPumpDuty")
        high = self.sim.get_global("pumpDutyHigh")
        assert last == high, f"lastPumpDuty should be {high}, got {last}"


# ---------------------------------------------------------------------------
# Scenario F — Boot initialization
# ---------------------------------------------------------------------------

class TestScenarioF_BootInit:
    """
    After System#Boot, all #globals should be set to their configured defaults.
    """

    def setup_method(self):
        self.sim = HeishaMonSimulator()
        self.sim.set_sensors(Outside_Temp=10.0)
        self.sim.boot()

    def test_curve_outdoor_low(self):
        assert self.sim.get_global("curveOutdoorLow") == -10

    def test_curve_outdoor_high(self):
        assert self.sim.get_global("curveOutdoorHigh") == 18

    def test_curve_target_low(self):
        assert self.sim.get_global("curveTargetLow") == 40

    def test_curve_target_high(self):
        assert self.sim.get_global("curveTargetHigh") == 27

    def test_min_setpoint(self):
        assert self.sim.get_global("minSetpoint") == 25

    def test_max_setpoint(self):
        assert self.sim.get_global("maxSetpoint") == 42

    def test_update_interval(self):
        assert self.sim.get_global("updateInterval") == 1800

    def test_hysteresis(self):
        assert self.sim.get_global("hysteresis") == 0.5

    def test_last_setpoint_zero(self):
        assert self.sim.get_global("lastSetpoint") == 0

    def test_calculated_setpoint_fallback(self):
        # Bug 2 fix: should be 35, not 0
        assert self.sim.get_global("calculatedSetpoint") == 35, (
            "calculatedSetpoint should default to 35 at boot (bug-2 fix)"
        )

    def test_enable_min_freq(self):
        assert self.sim.get_global("enableMinFreq") == 1

    def test_dynamic_shift_zero(self):
        assert self.sim.get_global("dynamicShift") == 0

    def test_min_freq_margin(self):
        assert self.sim.get_global("minFreqMargin") == 3

    def test_enable_pump_control(self):
        assert self.sim.get_global("enablePumpControl") == 1

    def test_pump_duty_high(self):
        assert self.sim.get_global("pumpDutyHigh") == 140

    def test_pump_duty_low(self):
        assert self.sim.get_global("pumpDutyLow") == 93

    def test_last_pump_duty_zero(self):
        assert self.sim.get_global("lastPumpDuty") == 0

    def test_timers_scheduled(self):
        # All four timers should have been scheduled
        timers = self.sim._interp.timers_
        assert 1 in timers and timers[1] == 60
        assert 2 in timers and timers[2] == 30
        assert 3 in timers and timers[3] == 90
        assert 4 in timers and timers[4] == 15


# ---------------------------------------------------------------------------
# Scenario G — Weather curve accuracy
# ---------------------------------------------------------------------------

class TestScenarioG_WeatherCurveAccuracy:
    """
    Verify calculateHeatingCurve produces the expected interpolated setpoints.

    With the default curve (outdoor: -10→+18, setpoint: 40→27):
      tempRange = 28, setpointRange = 13

    At -10°C → 40 (clamped to curveTargetLow)
    At  18°C → 27 (clamped to curveTargetHigh)
    At   0°C: tempOffset = 18, setpoint = ceil(27 + 18*13/28) = ceil(27+8.36) = ceil(35.36) = 36
    At  10°C: tempOffset =  8, setpoint = ceil(27 +  8*13/28) = ceil(27+3.71) = ceil(30.71) = 31
    At  20°C → 27 (above high threshold, clamped)
    At -15°C → 40 (below low threshold, clamped)
    """

    CASES = [
        (-10,  40, "At coldest extreme, setpoint clamps to curveTargetLow"),
        ( 18,  27, "At warmest extreme, setpoint clamps to curveTargetHigh"),
        (  0,  36, "At 0°C, linear interpolation gives 36"),
        ( 10,  31, "At 10°C, linear interpolation gives 31"),
        ( 20,  27, "Above high threshold, setpoint clamps to curveTargetHigh"),
        (-15,  40, "Below low threshold, setpoint clamps to curveTargetLow"),
    ]

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sim = HeishaMonSimulator()
        self.sim.set_sensors(Outside_Temp=10.0)
        self.sim.boot()

    @pytest.mark.parametrize("outdoor,expected,desc", CASES)
    def test_curve_value(self, outdoor: float, expected: int, desc: str):
        self.sim.call_function("calculateHeatingCurve", outdoor)
        result = self.sim.get_global("calculatedSetpoint")
        assert result == expected, f"{desc}: expected {expected}, got {result}"
