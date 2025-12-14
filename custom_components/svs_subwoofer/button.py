"""Button platform for SVS Subwoofer."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SVSSubwooferCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS button entities."""
    coordinator: SVSSubwooferCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([SVSReconnectButton(coordinator)])


class SVSReconnectButton(CoordinatorEntity[SVSSubwooferCoordinator], ButtonEntity):
    """Button to reconnect to the subwoofer."""

    _attr_has_entity_name = True
    _attr_translation_key = "reconnect"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: SVSSubwooferCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_reconnect"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle button press - reconnect to subwoofer."""
        _LOGGER.debug("Reconnect button pressed for %s", self.coordinator.address)

        # Disconnect first if connected
        if self.coordinator.is_connected:
            await self.coordinator.async_disconnect()

        # Request a refresh which will trigger reconnection
        await self.coordinator.async_request_refresh()
