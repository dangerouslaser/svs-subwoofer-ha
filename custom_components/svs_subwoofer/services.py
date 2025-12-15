"""Services for SVS Subwoofer integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    DOMAIN,
    SERVICE_SYNC_FROM,
    SERVICE_SET_VOLUME,
    SERVICE_LOAD_PRESET,
    SYNCABLE_PARAMS,
    VOLUME_MIN,
    VOLUME_MAX,
)

if TYPE_CHECKING:
    from .coordinator import SVSSubwooferCoordinator

_LOGGER = logging.getLogger(__name__)

# Service field names
ATTR_SOURCE_DEVICE_ID = "source_device_id"
ATTR_TARGET_DEVICE_IDS = "target_device_ids"
ATTR_DEVICE_IDS = "device_ids"
ATTR_VOLUME = "volume"
ATTR_OFFSETS = "offsets"
ATTR_PRESET = "preset"

# Service schemas
SERVICE_SYNC_FROM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SOURCE_DEVICE_ID): cv.string,
        vol.Required(ATTR_TARGET_DEVICE_IDS): vol.All(cv.ensure_list, [cv.string]),
    }
)

SERVICE_SET_VOLUME_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_VOLUME): vol.All(
            vol.Coerce(int), vol.Range(min=VOLUME_MIN, max=VOLUME_MAX)
        ),
        vol.Optional(ATTR_OFFSETS, default={}): dict,
    }
)

SERVICE_LOAD_PRESET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_PRESET): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
            vol.In(["1", "2", "3", "4", "Default", "default"]),
        ),
    }
)


def _get_coordinator_for_device(
    hass: HomeAssistant, device_id: str
) -> SVSSubwooferCoordinator | None:
    """Get the coordinator for a device by its device ID.

    Uses device registry to find the MAC address identifier,
    then matches against coordinators.
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


async def async_sync_from(hass: HomeAssistant, call: ServiceCall) -> None:
    """Copy all settings from source subwoofer to target subwoofer(s)."""
    source_device_id = call.data[ATTR_SOURCE_DEVICE_ID]
    target_device_ids = call.data[ATTR_TARGET_DEVICE_IDS]

    source_coord = _get_coordinator_for_device(hass, source_device_id)
    if not source_coord:
        _LOGGER.error("Source device not found: %s", source_device_id)
        return

    _LOGGER.info(
        "Syncing settings from %s to %d device(s)",
        source_coord.device_name,
        len(target_device_ids),
    )

    for target_id in target_device_ids:
        target_coord = _get_coordinator_for_device(hass, target_id)
        if not target_coord:
            _LOGGER.warning("Target device not found, skipping: %s", target_id)
            continue

        _LOGGER.debug(
            "Syncing %s -> %s", source_coord.device_name, target_coord.device_name
        )

        # Copy each syncable parameter
        for param in SYNCABLE_PARAMS:
            value = source_coord.data.get(param)
            if value is not None:
                try:
                    await target_coord.async_send_command(param, value)
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to sync %s to %s: %s",
                        param,
                        target_coord.device_name,
                        err,
                    )

    _LOGGER.info("Sync complete")


async def async_set_volume(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set volume on multiple subwoofers with optional per-device offsets."""
    device_ids = call.data[ATTR_DEVICE_IDS]
    base_volume = call.data[ATTR_VOLUME]
    offsets = call.data.get(ATTR_OFFSETS, {})

    _LOGGER.info("Setting volume to %d dB on %d device(s)", base_volume, len(device_ids))

    for device_id in device_ids:
        coord = _get_coordinator_for_device(hass, device_id)
        if not coord:
            _LOGGER.warning("Device not found, skipping: %s", device_id)
            continue

        # Apply offset if specified for this device
        offset = offsets.get(device_id, 0)
        volume = max(VOLUME_MIN, min(VOLUME_MAX, base_volume + offset))

        try:
            await coord.async_send_command("VOLUME", volume)
            _LOGGER.debug(
                "Set volume on %s to %d dB (base: %d, offset: %d)",
                coord.device_name,
                volume,
                base_volume,
                offset,
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to set volume on %s: %s", coord.device_name, err
            )


async def async_load_preset(hass: HomeAssistant, call: ServiceCall) -> None:
    """Load preset on multiple subwoofers."""
    device_ids = call.data[ATTR_DEVICE_IDS]
    preset = call.data[ATTR_PRESET]

    # Map preset name/string to number
    preset_map = {
        "Default": 4,
        "default": 4,
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
    }
    preset_num = preset_map.get(str(preset), preset) if isinstance(preset, str) else preset

    _LOGGER.info("Loading preset %s on %d device(s)", preset_num, len(device_ids))

    for device_id in device_ids:
        coord = _get_coordinator_for_device(hass, device_id)
        if not coord:
            _LOGGER.warning("Device not found, skipping: %s", device_id)
            continue

        try:
            await coord.async_load_preset(preset_num)
            _LOGGER.debug("Loaded preset %s on %s", preset_num, coord.device_name)
        except Exception as err:
            _LOGGER.warning(
                "Failed to load preset on %s: %s", coord.device_name, err
            )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up SVS Subwoofer services."""

    async def handle_sync_from(call: ServiceCall) -> None:
        await async_sync_from(hass, call)

    async def handle_set_volume(call: ServiceCall) -> None:
        await async_set_volume(hass, call)

    async def handle_load_preset(call: ServiceCall) -> None:
        await async_load_preset(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_FROM,
        handle_sync_from,
        schema=SERVICE_SYNC_FROM_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_VOLUME,
        handle_set_volume,
        schema=SERVICE_SET_VOLUME_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOAD_PRESET,
        handle_load_preset,
        schema=SERVICE_LOAD_PRESET_SCHEMA,
    )

    _LOGGER.debug("SVS Subwoofer services registered")


def async_unload_services(hass: HomeAssistant) -> None:
    """Unload SVS Subwoofer services."""
    hass.services.async_remove(DOMAIN, SERVICE_SYNC_FROM)
    hass.services.async_remove(DOMAIN, SERVICE_SET_VOLUME)
    hass.services.async_remove(DOMAIN, SERVICE_LOAD_PRESET)

    _LOGGER.debug("SVS Subwoofer services unregistered")
