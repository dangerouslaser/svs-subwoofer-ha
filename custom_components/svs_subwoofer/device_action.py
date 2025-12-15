"""Device actions for SVS Subwoofer."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    DOMAIN,
    ACTION_TYPE_LOAD_PRESET,
    ACTION_TYPE_SAVE_PRESET,
    ACTION_TYPE_SET_VOLUME,
    ACTION_TYPE_RECONNECT,
    ACTION_TYPES,
    CONF_PRESET,
    CONF_VOLUME,
    VOLUME_MIN,
    VOLUME_MAX,
)

_LOGGER = logging.getLogger(__name__)

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
        vol.Optional(CONF_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
        vol.Optional(CONF_VOLUME): vol.All(
            vol.Coerce(int), vol.Range(min=VOLUME_MIN, max=VOLUME_MAX)
        ),
    }
)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return a list of actions for SVS Subwoofer devices."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if not device:
        return []

    # Check if this device belongs to our domain
    if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
        return []

    actions = []
    base_action = {
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: device_id,
    }

    # Add all action types
    actions.append({**base_action, CONF_TYPE: ACTION_TYPE_LOAD_PRESET})
    actions.append({**base_action, CONF_TYPE: ACTION_TYPE_SAVE_PRESET})
    actions.append({**base_action, CONF_TYPE: ACTION_TYPE_SET_VOLUME})
    actions.append({**base_action, CONF_TYPE: ACTION_TYPE_RECONNECT})

    return actions


def _get_coordinator_for_device(hass: HomeAssistant, device_id: str):
    """Get the coordinator for a device by its device ID.

    Uses device registry to find the MAC address identifier,
    then matches against coordinators.
    """
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if not device:
        return None

    # Find the MAC address from device identifiers
    device_address = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            device_address = identifier[1]
            break

    if not device_address:
        return None

    # Find coordinator by MAC address match
    for coord in hass.data.get(DOMAIN, {}).values():
        if hasattr(coord, "address") and coord.address == device_address:
            return coord

    return None


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: dict[str, Any],
    variables: dict[str, Any],
    context: Context | None,
) -> None:
    """Execute a device action."""
    device_id = config[CONF_DEVICE_ID]
    action_type = config[CONF_TYPE]

    # Get the coordinator for this device
    coordinator = _get_coordinator_for_device(hass, device_id)

    if not coordinator:
        _LOGGER.error("Coordinator not found for device %s", device_id)
        return

    if action_type == ACTION_TYPE_LOAD_PRESET:
        preset = config.get(CONF_PRESET, 1)
        await coordinator.async_load_preset(preset)

    elif action_type == ACTION_TYPE_SAVE_PRESET:
        preset = config.get(CONF_PRESET, 1)
        if preset > 3:
            _LOGGER.error(
                "Cannot save to preset %d (only presets 1-3 can be saved)", preset
            )
            return
        await coordinator.async_save_preset(preset)

    elif action_type == ACTION_TYPE_SET_VOLUME:
        volume = config.get(CONF_VOLUME, -20)
        await coordinator.async_send_command("VOLUME", volume)

    elif action_type == ACTION_TYPE_RECONNECT:
        if coordinator.is_connected:
            await coordinator.async_disconnect()
        await coordinator.async_request_refresh()


async def async_get_action_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, vol.Schema]:
    """Return action capabilities."""
    action_type = config[CONF_TYPE]

    if action_type == ACTION_TYPE_LOAD_PRESET:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required(CONF_PRESET, default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=4)
                    ),
                }
            )
        }

    if action_type == ACTION_TYPE_SAVE_PRESET:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required(CONF_PRESET, default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=3)
                    ),
                }
            )
        }

    if action_type == ACTION_TYPE_SET_VOLUME:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required(CONF_VOLUME, default=-20): vol.All(
                        vol.Coerce(int), vol.Range(min=VOLUME_MIN, max=VOLUME_MAX)
                    ),
                }
            )
        }

    # No extra fields for reconnect
    return {}
