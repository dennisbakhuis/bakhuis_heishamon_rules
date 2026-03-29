"""
Tests for heating_manager YAML configuration files and HA template logic.

Covers:
  A - YAML validity: all 5 heating_manager YAML files parse without errors.
  B - Entity consistency: every entity referenced in dashboard.yaml is defined
      in sensors.yaml, helpers.yaml, or the known HeishaMon integration allowlist.
  C - Template logic: Python reimplementations of the three HA template sensors:
      C1 - WAR curve setpoint (weather-to-water compensation)
      C2 - RTC correction step (8-band lookup)
      C3 - Soft-start shift (ramp formula)
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
import yaml

HM_DIR = Path(__file__).parent.parent / "src" / "heating_manager"


# =============================================================================
# Group A — YAML validity
# =============================================================================


class TestYAMLValidity:
    """All heating manager YAML files must parse without errors."""

    @pytest.mark.parametrize(
        "filename",
        [
            "dashboard.yaml",
            "sensors.yaml",
            "helpers.yaml",
            "automations.yaml",
            "topics.yaml",
            "heating_manager_package.yaml",
        ],
    )
    def test_yaml_parses(self, filename: str) -> None:
        """
        Each YAML file in src/heating_manager/ must parse cleanly.

        Parameters
        ----------
        filename : str
            Filename to parse (relative to HM_DIR).
        """
        content = (HM_DIR / filename).read_text()
        result = yaml.safe_load(content)
        assert result is not None


# =============================================================================
# Group B — Entity consistency
# =============================================================================


class TestEntityConsistency:
    """Every entity referenced in dashboard.yaml must be defined or allowlisted."""

    def test_all_dashboard_entities_are_defined(self) -> None:
        """
        Every entity referenced in dashboard.yaml must be defined in
        sensors.yaml or helpers.yaml.

        The check filters to heishamon_* entities only, ignoring aquarea_* or
        other non-heishamon references that may appear in the dashboard.
        """
        dashboard_text = (HM_DIR / "dashboard.yaml").read_text()
        sensors_text = (HM_DIR / "sensors.yaml").read_text()
        helpers_text = (HM_DIR / "helpers.yaml").read_text()

        # --- All entity: xyz references in dashboard ---
        referenced = set(re.findall(r"entity:\s+([\w.]+)", dashboard_text))

        # --- sensor.heishamon_* and switch.heishamon_* from unique_id in sensors.yaml ---
        sensor_ids = set(re.findall(r"unique_id:\s+(heishamon_\w+)", sensors_text))
        defined_sensors = {f"sensor.{uid}" for uid in sensor_ids} | {
            f"switch.{uid}" for uid in sensor_ids
        }

        # --- input_number.*, input_datetime.*, and input_select.* from helpers.yaml ---
        # Keys at exactly 2-space indent are the helper entity names.
        input_keys = set(re.findall(r"^  (\w+):", helpers_text, re.MULTILINE))
        defined_helpers = (
            {f"input_number.{k}" for k in input_keys}
            | {f"input_datetime.{k}" for k in input_keys}
            | {f"input_select.{k}" for k in input_keys}
        )

        all_defined = defined_sensors | defined_helpers

        # Only check heishamon_* references (skip aquarea_*, generic sensor names etc.)
        heishamon_refs = {e for e in referenced if "heishamon" in e}

        undefined = heishamon_refs - all_defined
        assert undefined == set(), f"Entities referenced in dashboard but not defined: {undefined}"


# =============================================================================
# Group C — Template logic
# =============================================================================

# ---------------------------------------------------------------------------
# Helpers (Python reimplementations of HA template sensors)
# ---------------------------------------------------------------------------


def compute_war_setpoint(
    outdoor_temp: float,
    ol: float = -7.0,
    om: float = 5.0,
    oh: float = 15.0,
    tl: float = 40.0,
    tm: float = 33.0,
    th: float = 28.0,
    min_sp: float = 20.0,
    max_sp: float = 42.0,
) -> int:
    """
    Compute WAR setpoint matching the HA template sensor formula.

    Piecewise weather-to-water compensation curve driven by configurable
    control points (read from input_number helpers in HA).

    Default values match the Node-RED calibration:
      cold (-7→40), mid (5→33), warm (15→28), clamp [20, 42].

    Parameters
    ----------
    outdoor_temp : float
        Outdoor air temperature in °C.
    ol : float
        Outdoor temperature at cold control point.
    om : float
        Outdoor temperature at mid control point.
    oh : float
        Outdoor temperature at warm control point.
    tl : float
        Water target at cold control point.
    tm : float
        Water target at mid control point.
    th : float
        Water target at warm control point.
    min_sp : float
        Minimum water setpoint (hard floor).
    max_sp : float
        Maximum water setpoint (hard ceiling).

    Returns
    -------
    int
        Target water setpoint in °C.
    """
    t = outdoor_temp
    if t <= ol:
        raw: float = max(tl, min_sp)
    elif t >= oh:
        raw = max(th, min_sp)
    elif t <= om:
        slope = (tl - tm) / (om - ol)
        raw = max(min(math.ceil(tm + (om - t) * slope), int(max_sp)), int(min_sp))
    else:
        slope = (tm - th) / (oh - om)
        raw = max(min(math.ceil(th + (oh - t) * slope), int(max_sp)), int(min_sp))
    return int(raw)


def compute_rtc_correction(delta: float) -> int:
    """
    Compute RTC correction step matching the HA template sensor formula.

    8-band lookup table: delta = room_temp - room_setpoint.
    Positive delta means room is warmer than target (reduce setpoint).
    Negative delta means room is cooler than target (boost setpoint).

    Parameters
    ----------
    delta : float
        Difference between actual room temperature and setpoint (°C).

    Returns
    -------
    int
        Correction to apply to the water setpoint (°C), range [-3, +4].
    """
    if delta > 1.5:
        return -3
    if delta > 1.0:
        return -2
    if delta > 0.5:
        return -1
    if delta >= -0.2:
        return 0
    if delta >= -0.4:
        return 1
    if delta >= -0.6:
        return 2
    if delta >= -2.0:
        return 3
    return 4


def compute_softstart_shift(
    comp_run_seconds: float,
    duration: float = 780.0,
    max_shift: float = 5.0,
    outdoor_temp: float = 0.0,
    outdoor_max: float = 8.0,
) -> int:
    """
    Compute soft-start shift matching the HA template sensor formula.

    Ramps the water setpoint down by up to max_shift degrees at compressor
    start, then returns to 0 as the ramp completes.

    Note on truncation vs floor
    ---------------------------
    The HA Jinja2 template uses ``| int`` which is *truncation toward zero*,
    not ``floor()``.  For negative numbers these differ:

    - ``floor(-3.21) = -4`` — HeishaMon rules behavior
    - ``int(-3.21)  = -3`` — HA template behavior (truncation, implemented here)

    This function matches the HA template behavior (``int()`` truncation).

    Parameters
    ----------
    comp_run_seconds : float
        Seconds elapsed since compressor started (0 = not running).
    duration : float, optional
        Ramp duration in seconds, by default 780.0.
    max_shift : float, optional
        Maximum downward shift in °C, by default 5.0.
    outdoor_temp : float, optional
        Current outdoor temperature in °C, by default 0.0.
    outdoor_max : float, optional
        Maximum outdoor temperature at which soft-start is active, by default 8.0.

    Returns
    -------
    int
        Soft-start shift in °C, range [-max_shift, 0]. Returns 0 when inactive.
    """
    if outdoor_temp > outdoor_max or comp_run_seconds <= 0 or comp_run_seconds >= duration:
        return 0
    raw = max_shift * (math.sqrt(comp_run_seconds / duration) - 1)
    # | int in Jinja2 truncates toward zero (same as Python int())
    return max(-int(max_shift), min(0, int(raw)))


# ---------------------------------------------------------------------------
# C1: WAR curve
# ---------------------------------------------------------------------------


class TestWARCurve:
    """Spot-check WAR setpoint formula against known values."""

    @pytest.mark.parametrize(
        ("outdoor", "expected"),
        [
            (-10.0, 40),
            (-7.0, 40),
            (-2.0, 38),
            (0.0, 36),
            (2.9, 35),
            (5.0, 33),
            (10.0, 31),
            (15.0, 28),
            (20.0, 28),
        ],
    )
    def test_war_setpoint(self, outdoor: float, expected: int) -> None:
        """
        WAR setpoint must match expected value for given outdoor temperature.

        Parameters
        ----------
        outdoor : float
            Outdoor temperature in °C.
        expected : int
            Expected water setpoint in °C.
        """
        assert compute_war_setpoint(outdoor) == expected


# ---------------------------------------------------------------------------
# C2: RTC correction
# ---------------------------------------------------------------------------


class TestRTCCorrection:
    """Spot-check RTC correction lookup table against known values."""

    @pytest.mark.parametrize(
        ("delta", "expected"),
        [
            (2.0, -3),
            (1.2, -2),
            (0.7, -1),
            (0.3, 0),
            (0.0, 0),
            (-0.3, 1),
            (-0.5, 2),
            (-1.0, 3),
            (-3.0, 4),
        ],
    )
    def test_rtc_correction(self, delta: float, expected: int) -> None:
        """
        RTC correction must match expected value for given delta.

        Parameters
        ----------
        delta : float
            Room temperature minus setpoint (°C).
        expected : int
            Expected RTC correction step (°C).
        """
        assert compute_rtc_correction(delta) == expected


# ---------------------------------------------------------------------------
# C3: Soft-start shift
# ---------------------------------------------------------------------------


class TestSoftStartShift:
    """
    Spot-check soft-start shift formula against known values.

    Note: The HA template uses ``| int`` (truncation toward zero), so values
    differ from the HeishaMon rules (which use floor).  These tests match the
    HA template behavior.

    Examples of the difference:
      t=100s → raw=-3.21 → HA template: int(-3.21)=-3, rules: floor(-3.21)=-4
      t=400s → raw=-1.42 → HA template: int(-1.42)=-1, rules: floor(-1.42)=-2
    """

    @pytest.mark.parametrize(
        ("comp_run_sec", "outdoor", "expected"),
        [
            (0, 0.0, 0),  # compressor not started
            (100, 0.0, -3),  # HA int() truncation: int(-3.21)=-3
            (400, 0.0, -1),  # HA int() truncation: int(-1.42)=-1
            (780, 0.0, 0),  # ramp complete
            (900, 0.0, 0),  # past ramp duration
            (400, 10.0, 0),  # outdoor too warm (>8°C)
        ],
    )
    def test_softstart_shift(self, comp_run_sec: float, outdoor: float, expected: int) -> None:
        """
        Soft-start shift must match expected value for given conditions.

        Parameters
        ----------
        comp_run_sec : float
            Seconds since compressor started.
        outdoor : float
            Outdoor temperature in °C.
        expected : int
            Expected soft-start shift in °C.
        """
        result = compute_softstart_shift(comp_run_sec, outdoor_temp=outdoor)
        assert result == expected, (
            f"comp_run_sec={comp_run_sec}, outdoor={outdoor}: expected {expected}, got {result}"
        )
