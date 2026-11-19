"""Tests for setting up a subwoofer and sending commands. Every branch has these."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.svs_subwoofer import coordinator as coordinator_module
from custom_components.svs_subwoofer.const import DOMAIN

from .conftest import ADDRESS, NAME, FakeSubwoofer, SetupEntry, entity_id, settle


async def test_setup_reads_settings(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Setup connects, reads the settings, and shows them."""
    sub.settings["VOLUME"] = -21
    entry = await setup_entry()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id(hass, "number", "volume")).state == "-21.0"
    options = hass.states.get(entity_id(hass, "select", "preset")).attributes["options"]
    assert options[:3] == ["HIGH", "MEDIUM", "LOW"]


async def test_set_volume_writes_to_subwoofer(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Setting the volume sends it to the subwoofer and shows it."""
    await setup_entry()
    volume = entity_id(hass, "number", "volume")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": volume, "value": -12}, blocking=True
    )
    await settle()
    assert sub.settings["VOLUME"] == -12
    assert hass.states.get(volume).state == "-12.0"


async def test_switch_writes_to_subwoofer(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Turning on a switch sends the setting to the subwoofer."""
    await setup_entry()
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": entity_id(hass, "switch", "peq1_enable")},
        blocking=True,
    )
    await settle()
    assert sub.settings["PEQ1_ENABLE"] == 1


async def test_unload_disconnects(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Unloading the entry closes the Bluetooth connection."""
    entry = await setup_entry()
    assert sub.client.is_connected
    assert await hass.config_entries.async_unload(entry.entry_id)
    await settle()
    assert not sub.client.is_connected


async def test_subwoofer_not_found_retries_without_an_error(
    hass: HomeAssistant,
    sub: FakeSubwoofer,
    setup_entry: SetupEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A sub the proxy has not seen yet is retried, not logged as an error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS.lower(),
        title=NAME,
        data={CONF_ADDRESS: ADDRESS, CONF_NAME: NAME},
    )
    entry.add_to_hass(hass)
    with patch.object(
        coordinator_module, "async_ble_device_from_address", return_value=None
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await settle()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not [
        record
        for record in caplog.records
        if record.name.startswith("custom_components.svs_subwoofer")
        and record.levelno >= logging.ERROR
    ]
    # Stop the retry
    await hass.config_entries.async_unload(entry.entry_id)
