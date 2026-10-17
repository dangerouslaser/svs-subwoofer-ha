"""Shared helpers for SVS Subwoofer integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, GROUP_ID_PREFIX, PRESET_MANUAL_OPTION

if TYPE_CHECKING:
    from .coordinator import SVSSubwooferCoordinator
    from .subwoofer_group import SVSGroup

_LOGGER = logging.getLogger(__name__)


# Names that a preset's own name may not take, as the select shows them
RESERVED_PRESET_NAMES = ("Default", PRESET_MANUAL_OPTION)


def preset_option_names(data: Mapping[str, Any]) -> list[str]:
    """Return the Preset select's option for each preset slot, 1 to 4.

    A slot's option is its name on the subwoofer, or "Preset N" without one.
    A name that another option already has, or that is Default or Manual,
    would give the select two identical options (and Manual would be taken for
    the Manual option), so it gets the slot added: "Manual (Preset 2)".
    """
    names: list[str] = []
    taken = {name.casefold() for name in RESERVED_PRESET_NAMES}
    for slot in range(1, 4):
        name = (data.get(f"PRESET{slot}NAME") or "").replace("\x00", "").strip()
        name = name or f"Preset {slot}"
        if name.casefold() in taken:
            name = f"{name} (Preset {slot})"
        taken.add(name.casefold())
        names.append(name)
    names.append("Default")
    return names


def get_coordinator_for_device(
    hass: HomeAssistant, device_id: str
) -> SVSSubwooferCoordinator | None:
    """Get the coordinator for a device by its device ID.

    Uses device registry to find the MAC address identifier,
    then matches against coordinators stored in hass.data[DOMAIN].
    """
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if not device:
        _LOGGER.warning("Device not found: %s", device_id)
        return None

    # Find the MAC address from device identifiers
    device_address = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            device_address = identifier[1]
            break

    if not device_address:
        _LOGGER.warning("No SVS identifier found for device: %s", device_id)
        return None

    # Find coordinator by MAC address match
    for coord in hass.data.get(DOMAIN, {}).values():
        if hasattr(coord, "address") and coord.address == device_address:
            return coord

    _LOGGER.warning("No coordinator found for device: %s", device_id)
    return None


def get_group_for_device(hass: HomeAssistant, device_id: str) -> SVSGroup | None:
    """Return the subwoofer group a device stands for, or None if it is not one.

    Also None for a group that is not set up.
    """
    device = dr.async_get(hass).async_get(device_id)
    if not device:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN and identifier.startswith(GROUP_ID_PREFIX):
            entry = hass.config_entries.async_get_entry(
                identifier.removeprefix(GROUP_ID_PREFIX)
            )
            return getattr(entry, "runtime_data", None) if entry else None
    return None


def get_coordinators_for_device(
    hass: HomeAssistant, device_id: str
) -> list[SVSSubwooferCoordinator]:
    """Return the subwoofers a device stands for: itself, or a group's members.

    A group's members that are not set up are left out, with a warning.
    """
    if (group := get_group_for_device(hass, device_id)) is not None:
        coordinators = group.coordinators()
        for address in group.members:
            if address not in coordinators:
                _LOGGER.warning(
                    "%s is not set up, skipping it", group.member_name(address)
                )
        return list(coordinators.values())
    coordinator = get_coordinator_for_device(hass, device_id)
    return [coordinator] if coordinator else []
