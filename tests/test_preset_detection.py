"""Tests for preset detection and the Manual state (PR 10)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.svs_subwoofer import (
    coordinator as coordinator_module,
    device_action,
)
from custom_components.svs_subwoofer.const import DOMAIN

from .conftest import ADDRESS, NAME, FakeSubwoofer, SetupEntry, entity_id, settle


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id(hass, "select", "preset"), "option": option},
        blocking=True,
    )
    await settle(1.0)


def _preset(hass: HomeAssistant) -> str:
    return hass.states.get(entity_id(hass, "select", "preset")).state


def _options(hass: HomeAssistant) -> list[str]:
    return hass.states.get(entity_id(hass, "select", "preset")).attributes["options"]


async def test_loaded_preset_is_shown(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Loading a preset applies it on the sub and shows it."""
    await setup_entry()
    await _select(hass, "HIGH")
    assert sub.settings["VOLUME"] == -10
    assert _preset(hass) == "HIGH"


async def test_volume_change_shows_manual_and_it_sticks(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A change made in HA shows Manual, even when it matches a preset again."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    volume = entity_id(hass, "number", "volume")
    for value in (-14, -15):  # -15 is MEDIUM's volume again
        await hass.services.async_call(
            "number", "set_value", {"entity_id": volume, "value": value}, blocking=True
        )
        await settle()
        assert _preset(hass) == "Manual", value


async def test_selecting_manual_sends_nothing(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Choosing Manual marks the settings as manual without writing to the sub."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    frames_before = len(sub.received)
    await _select(hass, "Manual")
    assert _preset(hass) == "Manual"
    assert [t for t in sub.frame_types()[frames_before:] if t != "f11f"] == []


async def test_loading_a_preset_clears_manual(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Manual lasts until a preset is loaded."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    await _select(hass, "Manual")
    await _select(hass, "LOW")
    assert _preset(hass) == "LOW"


async def test_preset_loaded_outside_ha_is_recognized(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """After HA has recorded a preset, it is recognized when loaded elsewhere."""
    entry = await setup_entry()
    await _select(hass, "LOW")
    await _select(hass, "MEDIUM")
    # Load LOW behind HA's back (for example from the SVS app), then reconnect
    sub.settings["VOLUME"] = -20
    assert await hass.config_entries.async_reload(entry.entry_id)
    await settle(1.0)
    assert _preset(hass) == "LOW"


async def test_preset_load_sends_only_the_load_command(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A load relies on the sub's own reply instead of extra requests."""
    await setup_entry()
    frames_before = len(sub.received)
    await _select(hass, "HIGH")
    assert sub.frame_types()[frames_before:] == ["0704"]


async def test_lost_preset_load_is_resent(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A load the sub does not confirm is sent again."""
    await setup_entry()
    sub.ignore_loads = 1
    frames_before = len(sub.received)
    await _select(hass, "HIGH")
    assert sub.frame_types()[frames_before:] == ["0704", "0704"]
    assert sub.settings["VOLUME"] == -10
    assert _preset(hass) == "HIGH"


async def test_unconfirmed_preset_load_fails_and_records_nothing(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A load that never arrives fails, and the old settings stay as they were."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    sub.ignore_loads = 2
    with pytest.raises(HomeAssistantError):
        await _select(hass, "HIGH")
    assert sub.settings["VOLUME"] == -15
    # MEDIUM's settings were not recorded as HIGH's
    assert _preset(hass) == "MEDIUM"


async def _select_failing(hass: HomeAssistant, option: str) -> None:
    """Select an option that is expected to fail, and let things settle."""
    with pytest.raises(HomeAssistantError):
        await _select(hass, option)
    await settle(1.0)


async def test_end_of_a_probe_reply_is_not_taken_for_a_load(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """The probe before a load can still be answering when the load goes out.

    The sub loses the first load, and the rest of the probe's reply arrives
    meanwhile. It must not count as the load's answer: the load is sent again,
    and the preset that is recorded and shown is the one the sub has.
    """
    await setup_entry()
    sub.ignore_loads = 1
    sub.late_replies = 0.1
    # Probe before every command, as after a long silence
    with patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0.0):
        frames_before = len(sub.received)
        await _select(hass, "HIGH")
    loads = [t for t in sub.frame_types()[frames_before:] if t == "0704"]
    assert loads == ["0704", "0704"]
    assert sub.settings["VOLUME"] == -10
    assert _preset(hass) == "HIGH"


async def test_failed_write_shows_what_was_shown_before(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A load whose write fails does not leave the new preset on show."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    sub.fail_loads = 1
    await _select_failing(hass, "HIGH")
    assert _preset(hass) == "MEDIUM"


async def test_failed_write_keeps_manual(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Manual is not lost when the load that would end it fails."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    volume = entity_id(hass, "number", "volume")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": volume, "value": -14}, blocking=True
    )
    await settle()
    assert _preset(hass) == "Manual"
    sub.fail_loads = 1
    await _select_failing(hass, "HIGH")
    assert _preset(hass) == "Manual"


async def test_unconfirmed_load_keeps_manual(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A load the sub never confirms leaves Manual as it was."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    volume = entity_id(hass, "number", "volume")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": volume, "value": -14}, blocking=True
    )
    await settle()
    sub.ignore_loads = 2
    await _select_failing(hass, "HIGH")
    assert _preset(hass) == "Manual"


async def test_manual_ends_when_a_load_is_confirmed(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """The rollback does not keep Manual after a load that worked."""
    await setup_entry()
    await _select(hass, "MEDIUM")
    await _select(hass, "Manual")
    await _select(hass, "HIGH")
    assert _preset(hass) == "HIGH"


async def test_manual_chosen_before_settings_are_known_stays(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Manual chosen while a setting is unknown holds once the settings arrive."""
    entry = await setup_entry()
    coordinator = entry.runtime_data
    coordinator.data["VOLUME"] = None
    await _select(hass, "Manual")
    assert _preset(hass) == "Manual"
    await coordinator.async_request_refresh_data()
    await settle(1.0)
    assert coordinator.data["VOLUME"] is not None
    assert _preset(hass) == "Manual"


async def test_preset_named_manual_is_told_apart_from_manual(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A preset named Manual gets its own option, which loads it."""
    sub.preset_names = ["HIGH", "Manual", "LOW"]
    await setup_entry()
    assert _options(hass) == ["HIGH", "Manual (Preset 2)", "LOW", "Default", "Manual"]
    await _select(hass, "Manual (Preset 2)")
    assert sub.settings["VOLUME"] == -15
    assert _preset(hass) == "Manual (Preset 2)"
    # The Manual option is still Manual
    await _select(hass, "Manual")
    assert _preset(hass) == "Manual"


async def test_duplicate_and_reserved_preset_names_get_their_slot(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Two options are never the same, ignoring case."""
    sub.preset_names = ["HIGH", "high", "Default"]
    await setup_entry()
    assert _options(hass) == [
        "HIGH",
        "high (Preset 2)",
        "Default (Preset 3)",
        "Default",
        "Manual",
    ]


def _device_id(hass: HomeAssistant) -> str:
    devices = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, ADDRESS)})
    assert len(devices) == 1
    return devices[0].id


async def test_load_preset_service_loads_and_reports_a_failed_load(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """The service loads the preset, and fails naming a device that did not."""
    await setup_entry()
    data = {"device_ids": [_device_id(hass)], "preset": 1}
    await hass.services.async_call(DOMAIN, "load_preset", data, blocking=True)
    assert sub.settings["VOLUME"] == -10

    sub.ignore_loads = 2
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            DOMAIN, "load_preset", {**data, "preset": 2}, blocking=True
        )
    assert NAME in str(raised.value)


async def test_load_preset_device_action_reports_a_failed_load(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """The device action fails when the preset did not load."""
    await setup_entry()
    config = {
        "device_id": _device_id(hass),
        "domain": DOMAIN,
        "type": "load_preset",
        "preset": 2,
    }
    await device_action.async_call_action_from_config(hass, config, {}, None)
    assert sub.settings["VOLUME"] == -15

    sub.ignore_loads = 2
    with pytest.raises(HomeAssistantError):
        await device_action.async_call_action_from_config(
            hass, {**config, "preset": 1}, {}, None
        )
