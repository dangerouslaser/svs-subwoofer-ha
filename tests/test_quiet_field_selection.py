"""Tests for the Quiet connection choosing which field to read (dev)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.svs_subwoofer import coordinator as coordinator_module

from .conftest import MANUFACTURER_UUID, SERIAL_UUID, FakeSubwoofer, SetupEntry, settle


async def _run_quiet(setup_entry: SetupEntry, sub: FakeSubwoofer) -> int:
    """Run the Quiet connection briefly; return the settings reads at setup."""
    with (
        patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.1),
        patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0),
    ):
        await setup_entry({"connection_mode": "quiet"})
        reads_at_setup = sub.frame_types().count("f11f")
        await settle(0.6)
    return reads_at_setup


async def test_reads_the_serial_number_when_offered(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """The serial number is the first choice."""
    await _run_quiet(setup_entry, sub)
    assert sub.info_reads
    assert set(sub.info_reads) == {SERIAL_UUID}


async def test_falls_back_to_another_field(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Without a serial number, another standard field is read instead."""
    del sub.device_info[SERIAL_UUID]
    await _run_quiet(setup_entry, sub)
    assert sub.info_reads
    assert set(sub.info_reads) == {MANUFACTURER_UUID}
    assert sub.connects == 1


async def test_no_standard_field_uses_the_settings_check(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A sub with no standard field is checked like Constant, without reconnecting."""
    sub.device_info.clear()
    reads_at_setup = await _run_quiet(setup_entry, sub)
    assert sub.info_reads == []
    assert sub.frame_types().count("f11f") > reads_at_setup
    assert sub.connects == 1
