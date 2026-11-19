"""Tests for disconnecting on stop (PR 11) and the reconnect backoff (PR 12)."""

from __future__ import annotations

import time
from unittest.mock import patch

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from custom_components.svs_subwoofer import coordinator as coordinator_module

from .conftest import FakeSubwoofer, SetupEntry, entity_id, settle


async def test_disconnects_when_home_assistant_stops(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Stopping Home Assistant closes the connection instead of abandoning it."""
    await setup_entry()
    assert sub.client.is_connected
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await settle()
    assert not sub.client.is_connected


async def test_connected_only_after_the_sub_answers(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A connection the sub never answers is not shown as connected."""
    sub.silent = True
    await setup_entry()
    assert hass.states.get(entity_id(hass, "binary_sensor", "connected")).state == "off"


async def test_silent_sub_backs_off(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A silent sub is retried once at once, then with growing delays."""
    with (
        patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.05),
        patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0),
        patch.object(coordinator_module, "PROBE_TIMEOUT", 0.05),
    ):
        await setup_entry({"connection_mode": "constant"})
        sub.silent = True
        await settle(2.0)
    # Without backoff this would reconnect every few tenths of a second
    assert sub.connects <= 3
    coordinator = hass.config_entries.async_entries("svs_subwoofer")[0].runtime_data
    assert coordinator._retry_at > time.monotonic()


async def test_command_bypasses_the_backoff(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A command tries at once even while automatic reconnects back off."""
    with (
        patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.05),
        patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0),
        patch.object(coordinator_module, "PROBE_TIMEOUT", 0.05),
    ):
        await setup_entry({"connection_mode": "constant"})
        sub.silent = True
        await settle(1.0)
        sub.silent = False
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, "number", "volume"), "value": -30},
            blocking=True,
        )
        await settle()
    assert sub.settings["VOLUME"] == -30
    assert hass.states.get(entity_id(hass, "binary_sensor", "connected")).state == "on"
