"""Tests for showing settings as unknown until the subwoofer reports them (PR 9)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .conftest import FakeSubwoofer, SetupEntry, entity_id


async def test_silent_subwoofer_shows_unknown(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A subwoofer that never answers leaves its settings unknown, not made up."""
    sub.silent = True
    await setup_entry()
    for platform, key in (
        ("number", "volume"),
        ("number", "phase"),
        ("select", "standby_mode"),
    ):
        assert hass.states.get(entity_id(hass, platform, key)).state == "unknown", key
