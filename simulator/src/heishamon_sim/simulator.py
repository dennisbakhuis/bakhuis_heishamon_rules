"""
HeishaMon scenario simulator helpers.

Provides high-level helpers for setting up simulation scenarios,
firing events, and inspecting results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .interpreter import HeishaMonInterpreter

# Default path to the rules file relative to this package
_DEFAULT_RULES = (
    Path(__file__).parent.parent.parent.parent
    / "heishamon_rules"
    / "heishamon_rules_commented.txt"
)


class HeishaMonSimulator:
    """
    High-level wrapper around HeishaMonInterpreter for scenario testing.

    Usage::

        sim = HeishaMonSimulator()
        sim.boot()

        sim.set_sensors(Outside_Temp=12.0, Main_Inlet_Temp=27.0,
                        Main_Outlet_Temp=30.0, Compressor_Freq=25,
                        Defrosting_State=0)
        sim.fire_timer(1)   # weather curve
        sim.fire_timer(3)   # min-freq control

        shift = sim.get_global("dynamicShift")
    """

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self._interp = HeishaMonInterpreter()
        path = Path(rules_path) if rules_path else _DEFAULT_RULES
        self._interp.load_file(path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self) -> None:
        """Execute System#Boot."""
        self._interp.boot()

    def fire_timer(self, n: int) -> None:
        """Fire timer=N."""
        self._interp.fire_timer(n)

    def call_function(self, name: str, *args: Any) -> None:
        """Call a named function with arguments."""
        self._interp.call_function(name, list(args))

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def set_sensors(self, **kwargs: Any) -> None:
        """
        Set @heatpump sensor/actuator values by name (without @ prefix).

        Example::
            sim.set_sensors(Outside_Temp=12.0, Compressor_Freq=30)
        """
        for name, value in kwargs.items():
            self._interp.set_sensor(name, value)

    def set_globals(self, **kwargs: Any) -> None:
        """
        Override #global variables by name (without # prefix).

        Example::
            sim.set_globals(enableMinFreq=1, minFreqMargin=3)
        """
        for name, value in kwargs.items():
            self._interp.set_global(name, value)

    def get_sensor(self, name: str) -> Any:
        """Get @heatpump parameter by name (with or without @)."""
        return self._interp.get_sensor(name)

    def get_global(self, name: str) -> Any:
        """Get #global variable by name (with or without #)."""
        return self._interp.get_global(name)

    def get_all_globals(self) -> dict[str, Any]:
        """Return a copy of all #global variables."""
        return dict(self._interp.globals_)

    def get_all_sensors(self) -> dict[str, Any]:
        """Return a copy of all @heatpump parameters."""
        return dict(self._interp.hpparams_)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    @property
    def print_log(self) -> list[str]:
        """Messages emitted by print() calls."""
        return self._interp._print_log

    @property
    def timer_log(self) -> list[str]:
        """setTimer() calls made during execution."""
        return self._interp._timer_log
