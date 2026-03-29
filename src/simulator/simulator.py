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
_DEFAULT_RULES = Path(__file__).parent.parent / "heishamon_rules" / "heishamon_rules_commented.txt"


class HeishaMonSimulator:
    """
    High-level wrapper around HeishaMonInterpreter for scenario testing.

    Attributes
    ----------
    interpreter : HeishaMonInterpreter
        The underlying rules interpreter instance (accessible as ``_interp``).

    Examples
    --------
    >>> sim = HeishaMonSimulator()
    >>> sim.boot()
    >>> sim.set_sensors(Outside_Temp=12.0, Main_Inlet_Temp=27.0,
    ...                 Main_Outlet_Temp=30.0, Compressor_Freq=25,
    ...                 Defrosting_State=0)
    >>> sim.fire_timer(1)
    >>> shift = sim.get_global("dynamicShift")
    """

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self._interp = HeishaMonInterpreter()
        path = Path(rules_path) if rules_path else _DEFAULT_RULES
        self._interp.load_file(path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self) -> None:
        """Execute the ``System#Boot`` event to initialise all globals."""
        self._interp.boot()

    def fire_timer(self, n: int) -> None:
        """
        Fire a ``timer=N`` event.

        Parameters
        ----------
        n : int
            Timer number to fire.
        """
        self._interp.fire_timer(n)

    def fire_event(self, event: str) -> None:
        """
        Fire an arbitrary named event.

        Parameters
        ----------
        event : str
            Event name as it appears after ``on`` in the rules file,
            e.g. ``'?roomTemp'`` or ``'timer=2'``.
        """
        self._interp._fire(event)

    def set_opentherm(self, **kwargs: Any) -> None:
        """
        Set ``?opentherm`` variable values by name (without ``?`` prefix).

        Parameters
        ----------
        **kwargs : Any
            Keyword arguments where each key is an OpenTherm variable name
            and the value is the new reading.

        Examples
        --------
        >>> sim.set_opentherm(roomTemp=21.5, roomTempSet=21.0)
        """
        for name, value in kwargs.items():
            self._interp.set_sensor(f"?{name}", value)

    def call_function(self, name: str, *args: Any) -> None:
        """
        Call a named user-defined function with arguments.

        Parameters
        ----------
        name : str
            Function name (without sigils).
        *args : Any
            Positional arguments forwarded to the function.
        """
        self._interp.call_function(name, list(args))

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def set_sensors(self, **kwargs: Any) -> None:
        """
        Set ``@heatpump`` sensor/actuator values by name (without ``@`` prefix).

        Parameters
        ----------
        **kwargs : Any
            Keyword arguments where each key is a sensor name and the value
            is the new reading.

        Examples
        --------
        >>> sim.set_sensors(Outside_Temp=12.0, Compressor_Freq=30)
        """
        for name, value in kwargs.items():
            self._interp.set_sensor(name, value)

    def set_globals(self, **kwargs: Any) -> None:
        """
        Override ``#global`` variables by name (without ``#`` prefix).

        Parameters
        ----------
        **kwargs : Any
            Keyword arguments where each key is a global variable name and
            the value is the new setting.

        Examples
        --------
        >>> sim.set_globals(enableMinFreq=1, minFreqMargin=3)
        """
        for name, value in kwargs.items():
            self._interp.set_global(name, value)

    def get_sensor(self, name: str) -> Any:
        """
        Get a ``@heatpump`` parameter value.

        Parameters
        ----------
        name : str
            Sensor name, with or without ``@`` prefix.

        Returns
        -------
        Any
            Current sensor value, or ``None`` if not set.
        """
        return self._interp.get_sensor(name)

    def get_global(self, name: str) -> Any:
        """
        Get a ``#global`` variable value.

        Parameters
        ----------
        name : str
            Variable name, with or without ``#`` prefix.

        Returns
        -------
        Any
            Current global value, or ``None`` if not set.
        """
        return self._interp.get_global(name)

    def get_all_globals(self) -> dict[str, Any]:
        """
        Return a copy of all ``#global`` variables.

        Returns
        -------
        dict[str, Any]
            Snapshot of the current global state.
        """
        return dict(self._interp.globals_)

    def get_all_sensors(self) -> dict[str, Any]:
        """
        Return a copy of all ``@heatpump`` parameters.

        Returns
        -------
        dict[str, Any]
            Snapshot of the current sensor/actuator state.
        """
        return dict(self._interp.hpparams_)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    @property
    def print_log(self) -> list[str]:
        """
        Messages emitted by ``print()`` calls in the rules.

        Returns
        -------
        list[str]
            All messages printed during rule execution, in order.
        """
        return self._interp._print_log

    @property
    def timer_log(self) -> list[str]:
        """
        ``setTimer()`` calls made during execution.

        Returns
        -------
        list[str]
            Each entry is a string like ``'setTimer(1, 30)'``.
        """
        return self._interp._timer_log
