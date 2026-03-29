"""Integration setup tests for Climate Manager.

These tests use lightweight mocking (no real HA install required) to verify:
- The LovelaceYAML constructor is called with args in the correct order
- async_setup_entry stores data and returns True
- async_unload_entry cleans up the entry from hass.data
- The source code uses the correct (hass, url_path, config) argument order
"""
from __future__ import annotations

import ast
import re
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers: build minimal homeassistant stub modules so we can import the
# custom component without a real HA installation.
# ---------------------------------------------------------------------------

INIT_PATH = Path(__file__).parent.parent / "custom_components" / "climate_manager" / "__init__.py"
SOURCE = INIT_PATH.read_text()


def _build_ha_stubs() -> dict[str, types.ModuleType]:
    """Return a dict of minimal stub modules for homeassistant."""
    stubs: dict[str, types.ModuleType] = {}

    def _mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        stubs[name] = m
        return m

    _mod("homeassistant")
    ha_core = _mod("homeassistant.core")
    ha_core.HomeAssistant = MagicMock  # type: ignore[attr-defined]
    ha_core.callback = lambda f: f  # type: ignore[attr-defined]

    ha_cfg = _mod("homeassistant.config_entries")
    ha_cfg.ConfigEntry = MagicMock  # type: ignore[attr-defined]

    _mod("homeassistant.components")
    ha_mqtt = _mod("homeassistant.components.mqtt")
    ha_mqtt.async_subscribe = AsyncMock()  # type: ignore[attr-defined]
    ha_mqtt.async_publish = AsyncMock()  # type: ignore[attr-defined]

    ha_frontend = _mod("homeassistant.components.frontend")
    ha_frontend.async_register_built_in_panel = MagicMock()  # type: ignore[attr-defined]
    ha_frontend.async_remove_panel = MagicMock()  # type: ignore[attr-defined]

    _mod("homeassistant.components.lovelace")
    ha_lovelace_dash = _mod("homeassistant.components.lovelace.dashboard")
    ha_lovelace_dash.LovelaceYAML = MagicMock()  # type: ignore[attr-defined]

    _mod("homeassistant.helpers")
    ha_event = _mod("homeassistant.helpers.event")
    ha_event.async_track_state_change_event = MagicMock()  # type: ignore[attr-defined]
    ha_event.async_track_time_interval = MagicMock()  # type: ignore[attr-defined]

    return stubs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ha_stubs():
    """Inject HA stub modules into sys.modules for the duration of a test."""
    stubs = _build_ha_stubs()
    old = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    yield stubs
    # Restore original state
    for k, v in old.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v
    # Remove custom_component modules so they're re-imported fresh next test
    for key in list(sys.modules):
        if "climate_manager" in key:
            del sys.modules[key]


@pytest.fixture()
def mock_hass():
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.bus = MagicMock()
    return hass


@pytest.fixture()
def mock_entry():
    """Return a minimal mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "mqtt_base": "panasonic_heat_pump",
        "room_sensor": "",
    }
    return entry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_lovelace_yaml_arg_order_in_source() -> None:
    """Verify source uses LovelaceYAML(hass, url_path, config) — not (hass, config, url_path).

    This is a static guard: parse the source AST to find every LovelaceYAML(...)
    call and check positional argument order.  A regression here caused
    ``TypeError: 'str' object is not a mapping`` at runtime.
    """
    tree = ast.parse(SOURCE)

    lovelace_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Match: lovelace_dashboard.LovelaceYAML(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "LovelaceYAML"
            ):
                lovelace_calls.append(node)

    assert lovelace_calls, "No LovelaceYAML call found in __init__.py"

    for call in lovelace_calls:
        args = call.args
        assert len(args) >= 3, (
            f"LovelaceYAML called with {len(args)} positional args, expected >= 3"
        )
        # args[1] should be a Name or something that resolves to url_path (a str-like)
        # args[2] should be a Name or something that resolves to config (a dict-like)
        # We check that args[1] (url_path) is NOT a dict-like ast node and
        # args[2] (config) is NOT a simple string constant.
        url_path_arg = args[1]
        config_arg = args[2]

        # url_path should be a Name (variable) or Constant string — never a dict literal
        assert not isinstance(url_path_arg, ast.Dict), (
            "args[1] to LovelaceYAML looks like a dict — expected url_path (str), "
            "got config dict instead (arg-order bug)"
        )
        # config should not be a plain string constant
        if isinstance(config_arg, ast.Constant):
            assert not isinstance(config_arg.value, str), (
                "args[2] to LovelaceYAML is a string literal — expected config dict, "
                "not url_path string (arg-order bug)"
            )


def test_lovelace_yaml_call_matches_expected_pattern() -> None:
    """Regex check that the call site reads LovelaceYAML(hass, DASHBOARD_URL_PATH, ...).

    Complements the AST test with a readable grep-style assertion.
    """
    # The fixed call should have hass as first arg, url_path second, config third
    pattern = re.compile(
        r"LovelaceYAML\s*\(\s*hass\s*,\s*DASHBOARD_URL_PATH\s*,",
        re.MULTILINE,
    )
    assert pattern.search(SOURCE), (
        "Expected 'LovelaceYAML(hass, DASHBOARD_URL_PATH, ...)' in __init__.py "
        "but the pattern was not found — check argument order."
    )


@pytest.mark.asyncio
async def test_setup_entry_success(ha_stubs, mock_hass, mock_entry) -> None:
    """async_setup_entry should store entry data and return True."""
    # Provide a lovelace-like object in hass.data
    lovelace_mock = MagicMock()
    lovelace_mock.dashboards = {}
    mock_hass.data["lovelace"] = lovelace_mock

    # Import the module under stubs
    from custom_components.climate_manager import async_setup_entry  # noqa: PLC0415

    result = await async_setup_entry(mock_hass, mock_entry)

    assert result is True
    assert "climate_manager" in mock_hass.data
    assert mock_entry.entry_id in mock_hass.data["climate_manager"]


@pytest.mark.asyncio
async def test_setup_entry_without_lovelace(ha_stubs, mock_hass, mock_entry) -> None:
    """async_setup_entry should succeed even when lovelace is not in hass.data."""
    # No lovelace key — should just log a warning and continue
    from custom_components.climate_manager import async_setup_entry  # noqa: PLC0415

    result = await async_setup_entry(mock_hass, mock_entry)

    assert result is True


@pytest.mark.asyncio
async def test_unload_entry_cleanup(ha_stubs, mock_hass, mock_entry) -> None:
    """async_unload_entry should remove the entry from hass.data."""
    from custom_components.climate_manager import (  # noqa: PLC0415
        async_setup_entry,
        async_unload_entry,
    )

    lovelace_mock = MagicMock()
    lovelace_mock.dashboards = {}
    mock_hass.data["lovelace"] = lovelace_mock

    # Set up first
    await async_setup_entry(mock_hass, mock_entry)
    assert mock_entry.entry_id in mock_hass.data["climate_manager"]

    # Unload
    result = await async_unload_entry(mock_hass, mock_entry)

    assert result is True
    assert mock_entry.entry_id not in mock_hass.data.get("climate_manager", {})


@pytest.mark.asyncio
async def test_setup_entry_lovelace_yaml_called_with_correct_args(
    ha_stubs, mock_hass, mock_entry
) -> None:
    """LovelaceYAML stub should be called with (hass, url_path, config) in that order."""
    lovelace_mock = MagicMock()
    lovelace_mock.dashboards = {}
    mock_hass.data["lovelace"] = lovelace_mock

    from custom_components.climate_manager import (  # noqa: PLC0415
        DASHBOARD_URL_PATH,
    )

    # Capture the LovelaceYAML constructor calls
    yaml_cls_mock = MagicMock()
    ha_stubs["homeassistant.components.lovelace.dashboard"].LovelaceYAML = yaml_cls_mock

    # Re-import so it picks up the patched mock
    del sys.modules["custom_components.climate_manager"]
    from custom_components.climate_manager import async_setup_entry as setup_fn  # noqa: PLC0415

    await setup_fn(mock_hass, mock_entry)

    assert yaml_cls_mock.called, "LovelaceYAML was never instantiated"
    call_args = yaml_cls_mock.call_args
    pos_args = call_args.args

    # Positional: (hass, url_path, config)
    assert len(pos_args) == 3, f"Expected 3 positional args, got {len(pos_args)}: {pos_args}"
    assert pos_args[0] is mock_hass, "First arg to LovelaceYAML should be hass"
    assert pos_args[1] == DASHBOARD_URL_PATH, (
        f"Second arg should be url_path={DASHBOARD_URL_PATH!r}, got {pos_args[1]!r}"
    )
    assert isinstance(pos_args[2], dict), (
        f"Third arg should be a dict (config), got {type(pos_args[2])!r}: {pos_args[2]!r}"
    )
