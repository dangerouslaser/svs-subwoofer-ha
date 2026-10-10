"""SVS Subwoofer integration for Home Assistant.

Control SVS subwoofers via Bluetooth using the same protocol as the official SVS app.
Based on pySVS by Logon84: https://github.com/logon84/pySVS
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_ENTRY_TYPE,
    CONF_KEEP_ALIVE,
    CONF_MEMBERS,
    CONF_OFFSETS,
    DEFAULT_KEEP_ALIVE,
    DOMAIN,
    ENTRY_TYPE_GROUP,
    SIGNAL_MEMBERS_CHANGED,
)
from .coordinator import SVSSubwooferCoordinator, preset_store
from .services import async_setup_services, async_unload_services
from .subwoofer_group import SVSGroup

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

# A subwoofer group has no connection of its own, so it only has these
GROUP_PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SELECT]

type SVSConfigEntry = ConfigEntry[SVSSubwooferCoordinator | SVSGroup]


def _is_group(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GROUP


async def async_setup_entry(hass: HomeAssistant, entry: SVSConfigEntry) -> bool:
    """Set up SVS Subwoofer from a config entry."""
    if _is_group(entry):
        entry.runtime_data = SVSGroup(hass, entry)
        _async_check_group_size(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, GROUP_PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        return True

    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, "SVS Subwoofer")

    _LOGGER.debug("Setting up SVS Subwoofer: %s (%s)", name, address)

    coordinator = SVSSubwooferCoordinator(
        hass,
        entry.entry_id,
        address,
        name,
        keep_alive=entry.options.get(CONF_KEEP_ALIVE, DEFAULT_KEEP_ALIVE),
    )

    # Register the device before connecting, so the firmware version and
    # model reported during the first connection have a device to go to
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.device_info
    )

    await coordinator.async_load_preset_records()

    # Not ready (for example, the Bluetooth proxy has not seen the sub yet
    # after a restart) is not an error: Home Assistant logs the reason, shows
    # it on the integration, and retries, at once when Bluetooth sees the sub
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await coordinator.async_shutdown()
        raise
    except Exception as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(f"Could not connect to {address}: {err}") from err

    # Store coordinator
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register services (once, when first device is added)
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Let groups pick up this subwoofer
    async_dispatcher_send(hass, SIGNAL_MEMBERS_CHANGED)

    # Reload when options change so the connection mode takes effect
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Home Assistant does not unload config entries when it stops, so
    # disconnect explicitly instead of abandoning the BLE connection
    async def _async_stop(event: Event) -> None:
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    _LOGGER.info("SVS Subwoofer %s (%s) set up successfully", name, address)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SVSConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading SVS Subwoofer: %s", entry.title)

    if _is_group(entry):
        return await hass.config_entries.async_unload_platforms(entry, GROUP_PLATFORMS)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Disconnect from device
        coordinator: SVSSubwooferCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        # Let groups drop this subwoofer
        async_dispatcher_send(hass, SIGNAL_MEMBERS_CHANGED)

        # Unregister services when last device is removed
        if not hass.data[DOMAIN]:
            async_unload_services(hass)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up after a removed subwoofer or group.

    A removed subwoofer's recorded preset settings are deleted, and it leaves
    every group it was in, offset included.
    """
    if _is_group(entry):
        ir.async_delete_issue(hass, DOMAIN, _group_size_issue(entry))
        return
    address = entry.data[CONF_ADDRESS]
    await preset_store(hass, address).async_remove()
    for group in hass.config_entries.async_entries(DOMAIN):
        if not _is_group(group) or address not in group.options.get(CONF_MEMBERS, []):
            continue
        options = dict(group.options)
        options[CONF_MEMBERS] = [a for a in options[CONF_MEMBERS] if a != address]
        options[CONF_OFFSETS] = {
            a: offset
            for a, offset in options.get(CONF_OFFSETS, {}).items()
            if a != address
        }
        hass.config_entries.async_update_entry(group, options=options)
        _async_check_group_size(hass, group)


def _group_size_issue(group: ConfigEntry) -> str:
    return f"group_too_few_members_{group.entry_id}"


def _async_check_group_size(hass: HomeAssistant, group: ConfigEntry) -> None:
    """Raise a repair issue while a group has fewer than two subwoofers.

    That happens when its subwoofers are removed; the group then no longer
    does what it was made for, so it is not left to carry on quietly.
    """
    members = group.options.get(CONF_MEMBERS, [])
    if len(members) >= 2:
        ir.async_delete_issue(hass, DOMAIN, _group_size_issue(group))
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        _group_size_issue(group),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="group_too_few_members",
        translation_placeholders={"group": group.title, "count": str(len(members))},
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    try:
        await async_unload_entry(hass, entry)
    except Exception as err:
        _LOGGER.error("Failed to unload SVS Subwoofer entry: %s", err)
        # Continue to try setup anyway to recover
    await async_setup_entry(hass, entry)
