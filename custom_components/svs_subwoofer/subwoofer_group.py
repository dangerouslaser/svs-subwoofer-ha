"""Subwoofer groups: control several subwoofers as one.

A group is a config entry of its own, listing its member subwoofers by
Bluetooth address. Its entities show a setting when every member agrees on
it, and set it on every member, one subwoofer at a time.

(Not named group.py: Home Assistant takes a group.py in an integration as
support for its own Group integration.)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_MEMBERS, DOMAIN, SIGNAL_SUBWOOFERS_CHANGED

if TYPE_CHECKING:
    from .coordinator import SVSSubwooferCoordinator

GROUP_ID_PREFIX = "group_"


class SVSGroup:
    """The subwoofers of one group."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the group from its config entry."""
        self.hass = hass
        self.entry_id = entry.entry_id
        self.addresses: list[str] = [
            address.upper() for address in entry.options.get(CONF_MEMBERS, [])
        ]
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{GROUP_ID_PREFIX}{entry.entry_id}")},
            name=entry.title,
            manufacturer="SVS",
            model="Subwoofer group",
        )

    @property
    def members(self) -> list[SVSSubwooferCoordinator]:
        """Return the coordinators of the members that are set up, in order."""
        by_address = {
            coordinator.address.upper(): coordinator
            for coordinator in self.hass.data.get(DOMAIN, {}).values()
        }
        return [by_address[a] for a in self.addresses if a in by_address]

    @property
    def available(self) -> bool:
        """Return True when every member is set up and reachable."""
        members = self.members
        return len(members) == len(self.addresses) and all(
            member.last_update_success for member in members
        )

    def agreed(self, value: Callable[[SVSSubwooferCoordinator], Any]) -> Any | None:
        """Return the value every member has, or None if they differ."""
        values = [value(member) for member in self.members]
        if not values or values[0] is None:
            return None
        return values[0] if all(v == values[0] for v in values) else None

    async def async_apply(
        self,
        description: str,
        command: Callable[[SVSSubwooferCoordinator], Awaitable[bool]],
    ) -> None:
        """Run a command on every member, one at a time.

        One at a time, so a Bluetooth adapter or proxy is not asked for
        several connections at once. Every member is tried even if one
        fails; the error names the members that failed.
        """
        failed = []
        for member in self.members:
            try:
                ok = await command(member)
            except HomeAssistantError:
                ok = False
            if not ok:
                failed.append(member.device_name)
        if failed:
            raise HomeAssistantError(f"Failed to {description} on {', '.join(failed)}")


class SVSGroupEntity(Entity):
    """An entity of a subwoofer group, updated whenever a member changes."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, group: SVSGroup, key: str) -> None:
        """Initialize the entity."""
        self._group = group
        self._attr_unique_id = f"{GROUP_ID_PREFIX}{group.entry_id}_{key}"
        self._attr_device_info = group.device_info
        self._unsub_members: list[CALLBACK_TYPE] = []

    @property
    def available(self) -> bool:
        """Return True when every member is set up and reachable."""
        return self._group.available

    async def async_added_to_hass(self) -> None:
        """Follow the members, and members being set up or unloaded."""
        self._follow_members()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SUBWOOFERS_CHANGED, self._members_changed
            )
        )
        self.async_on_remove(self._unfollow_members)

    @callback
    def _follow_members(self) -> None:
        self._unfollow_members()
        self._unsub_members = [
            member.async_add_listener(self.async_write_ha_state)
            for member in self._group.members
        ]

    @callback
    def _unfollow_members(self) -> None:
        for unsub in self._unsub_members:
            unsub()
        self._unsub_members = []

    @callback
    def _members_changed(self) -> None:
        self._follow_members()
        self.async_write_ha_state()
