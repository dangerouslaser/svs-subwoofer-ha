"""Select platform for SVS Subwoofer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SVSConfigEntry, SVSGroupConfigEntry
from .const import (
    LPF_SLOPES,
    PRESET_MANUAL_OPTION,
    PRESET_MAP,
    PRESETS,
    ROOM_GAIN_FREQUENCIES,
    ROOM_GAIN_SLOPES,
    STANDBY_MODE_MAP,
    STANDBY_MODES,
)
from .coordinator import SVSSubwooferCoordinator
from .helpers import current_preset_option, is_group_entry, preset_option_names
from .subwoofer_group import SVSGroup, SVSGroupEntity

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
        entity_category=EntityCategory.CONFIG,
        options=LPF_SLOPE_OPTIONS,
        value_map=LPF_SLOPE_MAP,
        icon="mdi:tune-vertical",
    ),
    SVSSelectEntityDescription(
        key="room_gain_frequency",
        translation_key="room_gain_frequency",
        svs_param="ROOM_GAIN_FREQ",
        entity_category=EntityCategory.CONFIG,
        options=ROOM_GAIN_FREQ_OPTIONS,
        value_map=ROOM_GAIN_FREQ_MAP,
        icon="mdi:home-sound-in",
    ),
    SVSSelectEntityDescription(
        key="room_gain_slope",
        translation_key="room_gain_slope",
        svs_param="ROOM_GAIN_SLOPE",
        entity_category=EntityCategory.CONFIG,
        options=ROOM_GAIN_SLOPE_OPTIONS,
        value_map=ROOM_GAIN_SLOPE_MAP,
        icon="mdi:home-sound-in",
    ),
    SVSSelectEntityDescription(
        key="standby_mode",
        translation_key="standby_mode",
        svs_param="STANDBY",
        entity_category=EntityCategory.CONFIG,
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
    entry: SVSConfigEntry | SVSGroupConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS select entities."""
    if is_group_entry(entry):
        group: SVSGroup = entry.runtime_data
        async_add_entities([SVSGroupPresetSelect(group), SVSGroupStandbySelect(group)])
        return

    coordinator = entry.runtime_data

    async_add_entities(
        SVSSelectEntity(coordinator, description) for description in SELECT_DESCRIPTIONS
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

        # The presets' names from coordinator data, then Manual, which is
        # shown when the settings no longer match any preset
        return [*preset_option_names(self.coordinator.data), PRESET_MANUAL_OPTION]

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
        if self.entity_description.is_preset:
            return current_preset_option(self.coordinator.data)

        value = self.coordinator.data.get(self.entity_description.svs_param)
        if value is None:
            return None
        return self._reverse_map.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("Selecting %s for %s", option, self.entity_description.key)

        # Manual is not loaded onto the sub; it only marks the current settings
        if self.entity_description.is_preset and option == PRESET_MANUAL_OPTION:
            self.coordinator.set_manual()
            return

        # Use dynamic preset map for presets
        value_map = (
            self._preset_value_map
            if self.entity_description.is_preset
            else self.entity_description.value_map
        )
        value = value_map.get(option)
        if value is None:
            _LOGGER.error("Invalid option: %s", option)
            return

        if self.entity_description.is_preset:
            success = await self.coordinator.async_load_preset(value)
        else:
            success = await self.coordinator.async_send_command(
                self.entity_description.svs_param, value
            )

        if not success:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key} to {option}"
            )


class SVSGroupPresetSelect(SVSGroupEntity, SelectEntity):
    """Load a preset on every subwoofer of a group, matched by name.

    A preset loads the slot with that name on each subwoofer, so LOW in one
    subwoofer's slot 1 loads LOW from another's slot 3. Only the presets that
    every subwoofer has are offered. The state is unknown while the
    subwoofers are not all on the same preset.
    """

    _attr_translation_key = "preset"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, group: SVSGroup) -> None:
        """Initialize the select."""
        super().__init__(group, "preset")

    @property
    def options(self) -> list[str]:
        """Return the presets that every subwoofer has, then Manual."""
        members = self._group.members
        if not members:
            return [PRESET_MANUAL_OPTION]
        common = preset_option_names(members[0].data)
        for member in members[1:]:
            names = {name.casefold() for name in preset_option_names(member.data)}
            common = [name for name in common if name.casefold() in names]
        return [*common, PRESET_MANUAL_OPTION]

    @property
    def current_option(self) -> str | None:
        """Return the preset every subwoofer is on, if they agree."""
        agreed = self._group.agreed(
            lambda member: (current_preset_option(member.data) or "").casefold()
        )
        if not agreed:
            return None
        return next((o for o in self.options if o.casefold() == agreed), None)

    async def async_select_option(self, option: str) -> None:
        """Load the preset with this name on every subwoofer."""
        if option == PRESET_MANUAL_OPTION:
            for member in self._group.members:
                member.set_manual()
            return
        if option not in self.options:
            raise ServiceValidationError(
                f"Not every subwoofer in the group has a preset named {option}"
            )

        async def load(member: SVSSubwooferCoordinator) -> bool:
            names = [n.casefold() for n in preset_option_names(member.data)]
            return await member.async_load_preset(names.index(option.casefold()) + 1)

        await self._group.async_apply(f"load preset {option}", load)


class SVSGroupStandbySelect(SVSGroupEntity, SelectEntity):
    """Set the standby mode on every subwoofer of a group.

    The state is unknown while the subwoofers are in different modes.
    """

    _attr_translation_key = "standby_mode"
    _attr_icon = "mdi:power-standby"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = STANDBY_MODES

    def __init__(self, group: SVSGroup) -> None:
        """Initialize the select."""
        super().__init__(group, "standby_mode")
        self._reverse_map = {v: k for k, v in STANDBY_MODE_MAP.items()}

    @property
    def current_option(self) -> str | None:
        """Return the standby mode every subwoofer is in, if they agree."""
        value = self._group.agreed(lambda member: member.data.get("STANDBY"))
        return None if value is None else self._reverse_map.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Set the standby mode on every subwoofer."""
        value = STANDBY_MODE_MAP[option]
        await self._group.async_apply(
            f"set standby mode {option}",
            lambda member: member.async_send_command("STANDBY", value),
        )
