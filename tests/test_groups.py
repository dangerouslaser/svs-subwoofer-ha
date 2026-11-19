"""Tests for subwoofer groups."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.svs_subwoofer import device_action, device_trigger
from custom_components.svs_subwoofer.const import (
    CONF_ENTRY_TYPE,
    CONF_MEMBERS,
    DOMAIN,
    ENTRY_TYPE_GROUP,
)

from .conftest import ADDRESS, FakeSubwoofer, SetupEntry, settle

ADDRESS_2 = "54:B7:E5:82:D1:E3"


@pytest.fixture
async def subs(
    hass: HomeAssistant,
    sub: FakeSubwoofer,
    fake_subs: dict[str, FakeSubwoofer],
    setup_entry: SetupEntry,
) -> tuple[FakeSubwoofer, FakeSubwoofer]:
    """Two subwoofers set up: the first as Left, the second as Right."""
    fake_subs[ADDRESS_2] = FakeSubwoofer()
    await setup_entry(name="Left")
    await setup_entry(address=ADDRESS_2, name="Right")
    return sub, fake_subs[ADDRESS_2]


async def _add_group(
    hass: HomeAssistant, members: list[str] | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Subwoofers",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_GROUP},
        options={CONF_MEMBERS: members or [ADDRESS, ADDRESS_2]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle()
    return entry


def _group_entity(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str):
    found = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"group_{entry.entry_id}_{key}"
    )
    assert found, f"No group {platform} {key}"
    return found


def _state(hass: HomeAssistant, entity_id: str) -> str:
    return hass.states.get(entity_id).state


async def _call(hass: HomeAssistant, domain: str, service: str, data: dict) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)
    await settle(1.0)


async def test_group_preset_matches_by_name(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """A group preset loads the slot with that name on each subwoofer."""
    left, right = subs
    # Right has the same presets in a different order, and one Left lacks
    right.preset_names = ["LOW", "MOVIE", "HIGH"]
    await hass.config_entries.async_reload(
        hass.config_entries.async_entries(DOMAIN)[1].entry_id
    )
    await settle()
    entry = await _add_group(hass)
    preset = _group_entity(hass, entry, "select", "preset")

    options = hass.states.get(preset).attributes["options"]
    assert options == ["HIGH", "LOW", "Default", "Manual"]

    await _call(hass, "select", "select_option", {"entity_id": preset, "option": "LOW"})
    # LOW is Left's slot 3 and Right's slot 1
    assert left.settings["VOLUME"] == -20
    assert right.settings["VOLUME"] == -10
    assert _state(hass, preset) == "LOW"


async def test_group_state_is_unknown_while_members_differ(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """Group settings show only what every subwoofer agrees on."""
    left, right = subs
    entry = await _add_group(hass)
    volume = _group_entity(hass, entry, "number", "volume")
    standby = _group_entity(hass, entry, "select", "standby_mode")

    # Both start with the same settings
    assert _state(hass, volume) == "-15.0"
    assert _state(hass, standby) == "ON"

    # Changing one subwoofer on its own makes the group unknown
    left_volume = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{ADDRESS}_volume"
    )
    await _call(hass, "number", "set_value", {"entity_id": left_volume, "value": -30})
    assert _state(hass, volume) == STATE_UNKNOWN
    assert right.settings["VOLUME"] == -15


async def test_group_volume_and_standby_set_every_member(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """Group volume and standby are sent to every subwoofer."""
    left, right = subs
    entry = await _add_group(hass)
    volume = _group_entity(hass, entry, "number", "volume")
    standby = _group_entity(hass, entry, "select", "standby_mode")

    await _call(hass, "number", "set_value", {"entity_id": volume, "value": -25})
    assert left.settings["VOLUME"] == right.settings["VOLUME"] == -25
    assert _state(hass, volume) == "-25.0"

    await _call(
        hass, "select", "select_option", {"entity_id": standby, "option": "Trigger"}
    )
    assert left.settings["STANDBY"] == right.settings["STANDBY"] == 1
    assert _state(hass, standby) == "Trigger"


async def test_failed_member_is_named_and_the_others_still_change(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """A member that fails is named in the error; the others are still set."""
    left, right = subs
    entry = await _add_group(hass)
    volume = _group_entity(hass, entry, "number", "volume")
    left.fail_writes = 10
    left.refuse_connects = 10

    with pytest.raises(HomeAssistantError, match="Left"):
        await _call(hass, "number", "set_value", {"entity_id": volume, "value": -5})
    assert right.settings["VOLUME"] == -5


async def test_group_follows_members_being_unloaded_and_removed(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """A group is unavailable without all its subwoofers, and drops removed ones."""
    entry = await _add_group(hass)
    volume = _group_entity(hass, entry, "number", "volume")
    right_entry = hass.config_entries.async_entries(DOMAIN)[1]
    assert right_entry.title == "Right"

    await hass.config_entries.async_unload(right_entry.entry_id)
    await settle()
    assert _state(hass, volume) == STATE_UNAVAILABLE

    await hass.config_entries.async_setup(right_entry.entry_id)
    await settle()
    assert _state(hass, volume) == "-15.0"

    await hass.config_entries.async_remove(right_entry.entry_id)
    await settle()
    assert entry.options[CONF_MEMBERS] == [ADDRESS]


async def test_group_device_has_no_device_automations(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """Device triggers and actions are for subwoofers, not groups."""
    entry = await _add_group(hass)
    volume = _group_entity(hass, entry, "number", "volume")
    device_id = er.async_get(hass).async_get(volume).device_id
    assert device_id
    assert await device_trigger.async_get_triggers(hass, device_id) == []
    assert await device_action.async_get_actions(hass, device_id) == []


async def test_create_group_from_the_menu(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """With two subwoofers, Add entry offers a group, which needs two members."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "group"}
    )
    assert result["step_id"] == "group"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Both", CONF_MEMBERS: [ADDRESS]}
    )
    assert result["errors"] == {CONF_MEMBERS: "too_few_members"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Both", CONF_MEMBERS: [ADDRESS, ADDRESS_2]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Both"
    assert result["options"] == {CONF_MEMBERS: [ADDRESS, ADDRESS_2]}
    await settle()


async def test_change_members_in_the_options(
    hass: HomeAssistant, subs: tuple[FakeSubwoofer, FakeSubwoofer]
) -> None:
    """Configure changes the members, and still needs two."""
    entry = await _add_group(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "group"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: [ADDRESS_2]}
    )
    assert result["errors"] == {CONF_MEMBERS: "too_few_members"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: [ADDRESS_2, ADDRESS]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await settle()
    assert entry.options[CONF_MEMBERS] == [ADDRESS_2, ADDRESS]
