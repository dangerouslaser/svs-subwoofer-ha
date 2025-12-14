"""Device triggers for SVS Subwoofer."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    EVENT_SVS_SUBWOOFER,
    TRIGGER_TYPE_CONNECTED,
    TRIGGER_TYPE_DISCONNECTED,
    TRIGGER_TYPE_PRESET_LOADED,
    TRIGGER_TYPES,
    TRIGGER_SUBTYPES_PRESET,
)

CONF_SUBTYPE = "subtype"

# Triggers that have subtypes
TRIGGERS_WITH_SUBTYPE = {TRIGGER_TYPE_PRESET_LOADED}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(CONF_SUBTYPE): vol.In(TRIGGER_SUBTYPES_PRESET),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return a list of triggers for SVS Subwoofer devices."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if not device:
        return []

    # Check if this device belongs to our domain
    if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
        return []

    triggers = []
    base_trigger = {
        CONF_PLATFORM: "device",
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: device_id,
    }

    # Add connected/disconnected triggers (no subtypes)
    triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_CONNECTED})
    triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_DISCONNECTED})

    # Add preset loaded triggers (with subtypes)
    for subtype in TRIGGER_SUBTYPES_PRESET:
        triggers.append({
            **base_trigger,
            CONF_TYPE: TRIGGER_TYPE_PRESET_LOADED,
            CONF_SUBTYPE: subtype,
        })

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger to an automation."""
    event_data = {
        CONF_DEVICE_ID: config[CONF_DEVICE_ID],
        CONF_TYPE: config[CONF_TYPE],
    }

    # Include subtype if present
    if CONF_SUBTYPE in config:
        event_data[CONF_SUBTYPE] = config[CONF_SUBTYPE]

    event_config = {
        event_trigger.CONF_PLATFORM: "event",
        event_trigger.CONF_EVENT_TYPE: EVENT_SVS_SUBWOOFER,
        event_trigger.CONF_EVENT_DATA: event_data,
    }

    return await event_trigger.async_attach_trigger(
        hass,
        event_config,
        action,
        trigger_info,
        platform_type="device",
    )
