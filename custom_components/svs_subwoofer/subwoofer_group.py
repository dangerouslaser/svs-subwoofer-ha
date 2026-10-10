"""Subwoofer groups: control several subwoofers together.

A group is its own config entry and device. It holds no connection of its
own: it reads its members' state from their coordinators and sends commands
through them. Changing a member directly never changes the group or the other
members.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_GROUP_FEATURES,
    CONF_MEMBERS,
    CONF_OFFSETS,
    CONF_VOLUME_MODE,
    DOMAIN,
    GROUP_FEATURES,
    GROUP_ID_PREFIX,
    GROUP_STATE_MIXED,
    PRESET_MANUAL,
    PRESET_MANUAL_OPTION,
    SIGNAL_MEMBERS_CHANGED,
    VOLUME_MODE_MATCHED,
    VOLUME_MODE_OFFSET,
)
from .helpers import preset_option_names

if TYPE_CHECKING:
    from .coordinator import SVSSubwooferCoordinator

_LOGGER = logging.getLogger(__name__)

# A command a group sends one member: True when it was done
type MemberCommand = Callable[[str, SVSSubwooferCoordinator], Awaitable[bool]]


def preset_names(coordinator: SVSSubwooferCoordinator) -> dict[int, str]:
    """Return a subwoofer's preset names by slot, as its Preset select shows them."""
    return dict(enumerate(preset_option_names(coordinator.data), start=1))


def unnamed_slots(coordinator: SVSSubwooferCoordinator) -> set[int]:
    """Return the slots the subwoofer has no name for (shown as "Preset N")."""
    return {
        slot
        for slot in range(1, 4)
        if not (coordinator.data.get(f"PRESET{slot}NAME") or "")
        .replace("\x00", "")
        .strip()
    }


class SVSGroup:
    """A subwoofer group's configuration and access to its members."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Read the group's settings from its config entry options."""
        self.hass = hass
        self.entry = entry
        options = entry.options
        self.members: list[str] = list(options.get(CONF_MEMBERS, []))
        self.features: set[str] = set(options.get(CONF_GROUP_FEATURES, GROUP_FEATURES))
        self.volume_mode: str = options.get(CONF_VOLUME_MODE, VOLUME_MODE_MATCHED)
        offsets = options.get(CONF_OFFSETS, {})
        self.offsets: dict[str, int] = {
            address: (
                int(offsets.get(address, 0))
                if self.volume_mode == VOLUME_MODE_OFFSET
                else 0
            )
            for address in self.members
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the group's own device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{GROUP_ID_PREFIX}{self.entry.entry_id}")},
            name=self.entry.title,
            manufacturer="SVS",
            model="Subwoofer group",
        )

    def coordinators(
        self, addresses: list[str] | None = None
    ) -> dict[str, SVSSubwooferCoordinator]:
        """Return the members that are set up, by address, in member order."""
        loaded = {
            coordinator.address: coordinator
            for coordinator in self.hass.data.get(DOMAIN, {}).values()
        }
        return {
            address: loaded[address]
            for address in (self.members if addresses is None else addresses)
            if address in loaded
        }

    def member_name(self, address: str) -> str:
        """Return a member's name, also when it is not set up."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_ADDRESS) == address:
                return entry.title
        return address

    async def async_command_members(
        self, command: MemberCommand, what: str, retry: bool = True
    ) -> None:
        """Run a command on every member, one at a time.

        One at a time, so a Bluetooth setup with few connection slots is not
        asked for several connections at once. A member whose command fails is
        sent it once more (unless retry is False, for commands that already
        retry). When Bluetooth has no free connection slot for a member, the
        connections this command opened for earlier members are released and
        it is tried again. Raises HomeAssistantError naming the members it
        could not reach, such as "set the volume on Left".
        """
        coordinators = self.coordinators()
        failed = [
            self.member_name(address)
            for address in self.members
            if address not in coordinators
        ]
        # Members that were not connected before this command, and are now
        opened: list[SVSSubwooferCoordinator] = []
        for address, coordinator in coordinators.items():
            was_connected = coordinator.is_connected
            done = await self._async_try(command, address, coordinator, opened)
            if not done and retry:
                done = await self._async_try(command, address, coordinator, opened)
            if not done:
                failed.append(coordinator.device_name)
            elif not was_connected:
                opened.append(coordinator)
        if failed:
            raise HomeAssistantError(f"Could not {what} {', '.join(failed)}")

    @staticmethod
    async def _async_try(
        command: MemberCommand,
        address: str,
        coordinator: SVSSubwooferCoordinator,
        opened: list[SVSSubwooferCoordinator],
    ) -> bool:
        """Run the command on one member, freeing a connection slot if needed."""
        if await command(address, coordinator):
            return True
        if not (coordinator.out_of_slots and opened):
            return False
        _LOGGER.debug(
            "No free Bluetooth connection slot for %s; releasing the connections "
            "this group command opened",
            coordinator.address,
        )
        while opened:
            await opened.pop().async_disconnect()
        return await command(address, coordinator)

    def matched_presets(self) -> dict[str, dict[str, int]]:
        """Return the preset names every member has, with each member's slot.

        Presets are matched by name, not by slot, ignoring case: LOW in one
        sub's slot 1 matches LOW in another's slot 3. An unnamed slot (shown
        as "Preset N") matches only the same unnamed slot on the others, never
        another preset by chance. Names that are missing from any member are
        left out. Names keep the first member's spelling and order, as each
        subwoofer's own Preset select shows them; a name the group itself uses
        (Mixed) gets its slot added, as Default and Manual do there.
        """
        coordinators = list(self.coordinators().items())
        if not coordinators:
            return {}
        matched: dict[str, dict[str, int]] = {}
        first_address, first = coordinators[0]
        first_unnamed = unnamed_slots(first)
        for slot, name in preset_names(first).items():
            key = name.casefold()
            unnamed = slot in first_unnamed
            slots = {first_address: slot}
            for address, coordinator in coordinators[1:]:
                other_unnamed = unnamed_slots(coordinator)
                found = next(
                    (
                        other_slot
                        for other_slot, other in preset_names(coordinator).items()
                        if other.casefold() == key
                        and (other_slot in other_unnamed) == unnamed
                        and (not unnamed or other_slot == slot)
                    ),
                    None,
                )
                if found is None:
                    break
                slots[address] = found
            else:
                if key == GROUP_STATE_MIXED.casefold():
                    name = f"{name} (Preset {slot})"
                matched.setdefault(name, slots)
        return matched

    def active_preset(self) -> str | None:
        """Return the group's preset: a matched preset, Manual, Mixed, or None.

        None while a member's preset is unknown. Manual when every member is
        in Manual, the matched preset when every member has its slot of it
        active, and Mixed otherwise.
        """
        coordinators = self.coordinators()
        active = {
            address: coordinator.data.get("ACTIVE_PRESET")
            for address, coordinator in coordinators.items()
        }
        if not active or None in active.values():
            return None
        if all(value == PRESET_MANUAL for value in active.values()):
            return PRESET_MANUAL_OPTION
        for option, slots in self.matched_presets().items():
            if all(slots.get(address) == value for address, value in active.items()):
                return option
        return GROUP_STATE_MIXED


class SVSGroupEntity(Entity):
    """Base for a group's entities: follows every member's updates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, group: SVSGroup, key: str) -> None:
        """Initialize the entity."""
        self.svs_group = group
        self._attr_unique_id = f"{GROUP_ID_PREFIX}{group.entry.entry_id}_{key}"
        self._attr_device_info = group.device_info
        self._member_listeners: list[CALLBACK_TYPE] = []

    async def async_added_to_hass(self) -> None:
        """Follow the members, and re-read them when subwoofers come and go."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_MEMBERS_CHANGED, self._async_members_changed
            )
        )
        self.async_on_remove(self._unsubscribe_members)
        self._subscribe_members()

    @callback
    def _subscribe_members(self) -> None:
        self._unsubscribe_members()
        for coordinator in self.svs_group.coordinators().values():
            self._member_listeners.append(
                coordinator.async_add_listener(self._handle_member_update)
            )

    @callback
    def _unsubscribe_members(self) -> None:
        while self._member_listeners:
            self._member_listeners.pop()()

    @callback
    def _async_members_changed(self) -> None:
        self._subscribe_members()
        self.async_write_ha_state()

    @callback
    def _handle_member_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Available while at least one member is set up."""
        return any(
            coordinator.last_update_success
            for coordinator in self.svs_group.coordinators().values()
        )
