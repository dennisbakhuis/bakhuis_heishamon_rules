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
  H - RTC corrections: parametrised delta → expected rtcShift
  I - RTC disabled: rtcShift stays 0 regardless of delta
  J - RTC missing sensor: rtcShift stays 0 when ?roomTemp not set
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
    Outdoor=-5°C (cold), inlet=27°C, outlet=38°C (near setpoint), compressor running.

    At -5°C the weather curve gives (new 3-point piecewise, segment 1: -7°C to 5°C):
      tempRange     = 5 - (-7) = 12
      setpointRange = 40 - 33  = 7   (TargetLow - TargetMid)
      tempOffset    = 5 - (-5) = 10  (curveOutdoorMid - outdoorTemp)
      setpoint = ceil(33 + 10 * 7 / 12) = ceil(33 + 5.833) = ceil(38.833) = 39

    outletDelta = 38 - 39 = -1  → Case 1 (outlet approaching setpoint)
    targetShift = inlet(27) + margin(3) - setpoint(39) = -9
    dynamicShift = max(-3, -9) = -3 (clamped)

    With outlet=33 instead (delta=-6) we'd hit Case 2 (well below setpoint) →
    shift resets to 0, which is also correct but doesn't test the lowering path.
    We use outlet=38 to specifically test Case 1.
    """

    def setup_method(self):
        self.sim = fresh_sim()
        self.sim.set_sensors(
            Outside_Temp=-5.0,
            Main_Inlet_Temp=27.0,
            Main_Outlet_Temp=38.0,  # near setpoint=39, triggers Case 1
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

    def test_calculated_setpoint_is_39(self):
        sp = self.sim.get_global("calculatedSetpoint")
        assert sp == 39, f"Expected calculatedSetpoint=39 for outdoor=-5°C, got {sp}"

    def test_final_setpoint_applied_is_reduced(self):
        # finalSetpoint = calculatedSetpoint + dynamicShift = 39 + (-3) = 36
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

    At 12°C the weather curve gives (new 3-point piecewise, segment 2: 5°C to 15°C):
      tempRange     = 15 - 5   = 10
      setpointRange = 33 - 28  = 5   (TargetMid - TargetHigh)
      tempOffset    = 15 - 12  = 3   (curveOutdoorHigh - outdoorTemp)
      setpoint = ceil(28 + 3 * 5 / 10) = ceil(28 + 1.5) = ceil(29.5) = 30

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
        assert self.sim.get_global("curveOutdoorLow") == -7

    def test_curve_outdoor_mid(self):
        assert self.sim.get_global("curveOutdoorMid") == 5

    def test_curve_outdoor_high(self):
        assert self.sim.get_global("curveOutdoorHigh") == 15

    def test_curve_target_low(self):
        assert self.sim.get_global("curveTargetLow") == 40

    def test_curve_target_mid(self):
        assert self.sim.get_global("curveTargetMid") == 33

    def test_curve_target_high(self):
        assert self.sim.get_global("curveTargetHigh") == 28

    def test_min_setpoint(self):
        assert self.sim.get_global("minSetpoint") == 20

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

    def test_rtc_enabled(self):
        assert self.sim.get_global("rtcEnabled") == 1

    def test_rtc_shift_zero(self):
        assert self.sim.get_global("rtcShift") == 0

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
    Verify calculateHeatingCurve produces the expected interpolated setpoints
    for the 3-point piecewise WAR curve.

    Control points:
      Cold: outdoor -7°C  → water 40°C
      Mid:  outdoor  5°C  → water 33°C
      Warm: outdoor 15°C  → water 28°C

    Segment 1 formula (outdoor in [-7, 5]):
      ceil(33 + (5 - outdoor) * 7 / 12)
        outdoor=-7:  ceil(33 + 12*7/12) = ceil(40.0)  = 40
        outdoor=-2:  ceil(33 +  7*7/12) = ceil(37.08) = 38
        outdoor= 0:  ceil(33 +  5*7/12) = ceil(35.92) = 36
        outdoor=2.9: ceil(33 + 2.1*7/12)= ceil(34.23) = 35
        outdoor= 5:  ceil(33 +  0*7/12) = ceil(33.0)  = 33

    Segment 2 formula (outdoor in (5, 15]):
      ceil(28 + (15 - outdoor) * 5 / 10)
        outdoor= 5:  ceil(28 + 10*5/10) = ceil(33.0)  = 33
        outdoor=10:  ceil(28 +  5*5/10) = ceil(30.5)  = 31
        outdoor=15:  ceil(28 +  0*5/10) = ceil(28.0)  = 28

    Clamping:
      outdoor <= -7  → 40  (cold clamp)
      outdoor >= 15  → 28  (warm clamp)
    """

    CASES = [
        (-10,  40, "Below cold clamp: setpoint = 40"),
        ( -7,  40, "Cold endpoint: setpoint = 40"),
        ( -2,  38, "Segment 1 at -2°C: ceil(33 + 7*7/12) = 38"),
        (  0,  36, "Segment 1 at  0°C: ceil(33 + 5*7/12) = 36"),
        (2.9,  35, "Segment 1 at 2.9°C: ceil(33 + 2.1*7/12) = 35"),
        (  5,  33, "Mid endpoint: setpoint = 33"),
        ( 10,  31, "Segment 2 at 10°C: ceil(28 + 5*5/10) = 31"),
        ( 15,  28, "Warm endpoint: setpoint = 28"),
        ( 20,  28, "Above warm clamp: setpoint = 28"),
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


# ---------------------------------------------------------------------------
# Scenario H — RTC corrections (parametrised)
# ---------------------------------------------------------------------------

class TestScenarioH_RTCCorrections:
    """
    Verify calculateRTC() produces the correct #rtcShift for each delta band.

    Correction table (delta = ?roomTemp - ?roomTempSet):
      delta > +1.5°C  → -3
      +1.0 to +1.5°C  → -2
      +0.5 to +1.0°C  → -1
      -0.2 to +0.5°C  →  0  (dead band)
      -0.4 to -0.2°C  → +1
      -0.6 to -0.4°C  → +2
      -2.0 to -0.6°C  → +3
      < -2.0°C        → +4
    """

    CASES = [
        (+2.0, -3, "delta=+2.0: well above +1.5 → -3"),
        (+1.2, -2, "delta=+1.2: in (1.0, 1.5] → -2"),
        (+0.7, -1, "delta=+0.7: in (0.5, 1.0] → -1"),
        (+0.3,  0, "delta=+0.3: in dead band [-0.2, 0.5] → 0"),
        ( 0.0,  0, "delta=0.0: in dead band → 0"),
        (-0.3, +1, "delta=-0.3: in [-0.4, -0.2) → +1"),
        (-0.5, +2, "delta=-0.5: in [-0.6, -0.4) → +2"),
        (-1.0, +3, "delta=-1.0: in [-2.0, -0.6) → +3"),
        (-3.0, +4, "delta=-3.0: below -2.0 → +4"),
    ]

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sim = HeishaMonSimulator()
        self.sim.set_sensors(Outside_Temp=10.0)
        self.sim.boot()
        # Ensure RTC is enabled
        self.sim.set_globals(rtcEnabled=1)

    @pytest.mark.parametrize("delta,expected_shift,desc", CASES)
    def test_rtc_shift(self, delta: float, expected_shift: int, desc: str):
        room_setpoint = 21.0
        room_temp = room_setpoint + delta
        self.sim.set_opentherm(roomTemp=room_temp, roomTempSet=room_setpoint)
        self.sim.call_function("calculateRTC")
        result = self.sim.get_global("rtcShift")
        assert result == expected_shift, f"{desc}: expected {expected_shift}, got {result}"


# ---------------------------------------------------------------------------
# Scenario I — RTC disabled
# ---------------------------------------------------------------------------

class TestScenarioI_RTCDisabled:
    """
    When #rtcEnabled = 0, calculateRTC() should always set #rtcShift = 0
    regardless of the room temperature delta.
    """

    def setup_method(self):
        self.sim = HeishaMonSimulator()
        self.sim.set_sensors(Outside_Temp=10.0)
        self.sim.boot()
        # Disable RTC
        self.sim.set_globals(rtcEnabled=0)
        # Set room temperatures with a large delta that would normally give -3
        self.sim.set_opentherm(roomTemp=24.0, roomTempSet=21.0)  # delta = +3.0

    def test_rtc_shift_zero_when_disabled(self):
        self.sim.call_function("calculateRTC")
        shift = self.sim.get_global("rtcShift")
        assert shift == 0, f"Expected rtcShift=0 when disabled, got {shift}"

    def test_rtc_shift_stays_zero_after_multiple_calls(self):
        """RTC shift remains 0 across multiple calls when disabled."""
        for _ in range(3):
            self.sim.call_function("calculateRTC")
        shift = self.sim.get_global("rtcShift")
        assert shift == 0, f"Expected rtcShift=0 after multiple calls, got {shift}"


# ---------------------------------------------------------------------------
# Scenario J — RTC with missing sensor
# ---------------------------------------------------------------------------

class TestScenarioJ_RTCMissingSensor:
    """
    When ?roomTemp is not set (sensor not available), calculateRTC() should
    set #rtcShift = 0 (safe fallback, no adjustment).
    """

    def setup_method(self):
        self.sim = HeishaMonSimulator()
        self.sim.set_sensors(Outside_Temp=10.0)
        self.sim.boot()
        # RTC enabled, but DO NOT set roomTemp or roomTempSet

    def test_rtc_shift_zero_when_roomtemp_missing(self):
        self.sim.call_function("calculateRTC")
        shift = self.sim.get_global("rtcShift")
        assert shift == 0, f"Expected rtcShift=0 when sensor missing, got {shift}"

    def test_rtc_shift_zero_when_only_roomtempset_missing(self):
        """Only roomTemp set but roomTempSet missing → shift stays 0."""
        self.sim.set_opentherm(roomTemp=22.0)
        self.sim.call_function("calculateRTC")
        shift = self.sim.get_global("rtcShift")
        assert shift == 0, f"Expected rtcShift=0 when roomTempSet missing, got {shift}"
