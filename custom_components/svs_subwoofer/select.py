"""Select platform for SVS Subwoofer."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LPF_SLOPES,
    ROOM_GAIN_FREQUENCIES,
    ROOM_GAIN_SLOPES,
    STANDBY_MODES,
    STANDBY_MODE_MAP,
    PRESETS,
    PRESET_MAP,
)
from .coordinator import SVSSubwooferCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SVSSelectEntityDescription(SelectEntityDescription):
    """Describes SVS select entity."""

    svs_param: str
    value_map: dict[str, int]
    is_preset: bool = False


# Build value maps
LPF_SLOPE_OPTIONS = [f"{v} dB" for v in LPF_SLOPES]
LPF_SLOPE_MAP = {f"{v} dB": v for v in LPF_SLOPES}

ROOM_GAIN_FREQ_OPTIONS = [f"{v} Hz" for v in ROOM_GAIN_FREQUENCIES]
ROOM_GAIN_FREQ_MAP = {f"{v} Hz": v for v in ROOM_GAIN_FREQUENCIES}

ROOM_GAIN_SLOPE_OPTIONS = [f"{v} dB" for v in ROOM_GAIN_SLOPES]
ROOM_GAIN_SLOPE_MAP = {f"{v} dB": v for v in ROOM_GAIN_SLOPES}


SELECT_DESCRIPTIONS: tuple[SVSSelectEntityDescription, ...] = (
    SVSSelectEntityDescription(
        key="lpf_slope",
        translation_key="lpf_slope",
        svs_param="LOW_PASS_FILTER_SLOPE",
        options=LPF_SLOPE_OPTIONS,
        value_map=LPF_SLOPE_MAP,
        icon="mdi:tune-vertical",
    ),
    SVSSelectEntityDescription(
        key="room_gain_frequency",
        translation_key="room_gain_frequency",
        svs_param="ROOM_GAIN_FREQ",
        options=ROOM_GAIN_FREQ_OPTIONS,
        value_map=ROOM_GAIN_FREQ_MAP,
        icon="mdi:home-sound-in",
    ),
    SVSSelectEntityDescription(
        key="room_gain_slope",
        translation_key="room_gain_slope",
        svs_param="ROOM_GAIN_SLOPE",
        options=ROOM_GAIN_SLOPE_OPTIONS,
        value_map=ROOM_GAIN_SLOPE_MAP,
        icon="mdi:home-sound-in",
    ),
    SVSSelectEntityDescription(
        key="standby_mode",
        translation_key="standby_mode",
        svs_param="STANDBY",
        options=STANDBY_MODES,
        value_map=STANDBY_MODE_MAP,
        icon="mdi:power-standby",
    ),
    SVSSelectEntityDescription(
        key="preset",
        translation_key="preset",
        svs_param="PRESET",
        options=PRESETS,
        value_map=PRESET_MAP,
        is_preset=True,
        icon="mdi:playlist-music",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS select entities."""
    coordinator: SVSSubwooferCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SVSSelectEntity(coordinator, description)
        for description in SELECT_DESCRIPTIONS
    )


class SVSSelectEntity(CoordinatorEntity[SVSSubwooferCoordinator], SelectEntity):
    """Representation of an SVS select entity."""

    _attr_has_entity_name = True
    entity_description: SVSSelectEntityDescription

    def __init__(
        self,
        coordinator: SVSSubwooferCoordinator,
        description: SVSSelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = coordinator.device_info
        self._base_options = list(description.options)

        # Build reverse map for value -> option lookup
        self._reverse_map = {v: k for k, v in description.value_map.items()}

    @property
    def options(self) -> list[str]:
        """Return list of options, with custom preset names if available."""
        if not self.entity_description.is_preset:
            return self._base_options

        # Build preset options with custom names from coordinator data
        preset_options = []
        for i in range(1, 4):
            name_key = f"PRESET{i}NAME"
            custom_name = self.coordinator.data.get(name_key)
            if custom_name and custom_name.strip():
                # Use custom name, strip null bytes and whitespace
                preset_options.append(custom_name.strip().replace('\x00', ''))
            else:
                preset_options.append(f"Preset {i}")
        preset_options.append("Default")
        return preset_options

    @property
    def _preset_value_map(self) -> dict[str, int]:
        """Return mapping of current preset option names to values."""
        if not self.entity_description.is_preset:
            return self.entity_description.value_map

        # Build dynamic preset map based on current options
        current_options = self.options
        return {
            current_options[0]: 1,  # Preset 1
            current_options[1]: 2,  # Preset 2
            current_options[2]: 3,  # Preset 3
            current_options[3]: 4,  # Default
        }

    @property
    def current_option(self) -> str | None:
        """Return current option."""
        # For presets, we don't track current state from device
        if self.entity_description.is_preset:
            return None

        value = self.coordinator.data.get(self.entity_description.svs_param)
        if value is None:
            return None
        return self._reverse_map.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("Selecting %s for %s", option, self.entity_description.key)

        # Use dynamic preset map for presets
        value_map = self._preset_value_map if self.entity_description.is_preset else self.entity_description.value_map
        value = value_map.get(option)
        if value is None:
            _LOGGER.error("Invalid option: %s", option)
            return

        if self.entity_description.is_preset:
            # Handle preset loading specially
            success = await self.coordinator.async_load_preset(value)
        else:
            success = await self.coordinator.async_send_command(
                self.entity_description.svs_param, value
            )

        if success and not self.entity_description.is_preset:
            self.coordinator.data[self.entity_description.svs_param] = value
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
