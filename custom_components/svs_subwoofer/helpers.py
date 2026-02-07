"""Shared helpers for SVS Subwoofer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import SVSSubwooferCoordinator

_LOGGER = logging.getLogger(__name__)


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
