"""Select platform for SVS Subwoofer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SVSConfigEntry
from .const import (
    GROUP_FEATURE_PRESET,
    GROUP_FEATURE_STANDBY,
    GROUP_STATE_MIXED,
    LPF_SLOPES,
    PRESET_MANUAL,
    PRESET_MANUAL_OPTION,
    PRESET_MAP,
    PRESETS,
    ROOM_GAIN_FREQUENCIES,
    ROOM_GAIN_SLOPES,
    STANDBY_MODE_MAP,
    STANDBY_MODES,
)
from .coordinator import SVSSubwooferCoordinator
from .helpers import preset_option_names
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
    entry: SVSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS select entities."""
    if isinstance(entry.runtime_data, SVSGroup):
        group = entry.runtime_data
        entities: list[SelectEntity] = []
        if GROUP_FEATURE_PRESET in group.features:
            entities.append(SVSGroupPresetSelect(group))
        if GROUP_FEATURE_STANDBY in group.features:
            entities.append(SVSGroupStandbySelect(group))
        async_add_entities(entities)
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
            active = self.coordinator.data.get("ACTIVE_PRESET")
            if active is None:
                return None
            if active == PRESET_MANUAL:
                return PRESET_MANUAL_OPTION
            # Map preset number to current option name (0-indexed into options list)
            current_options = self.options
            idx = active - 1 if active <= 3 else 3  # preset 4 = Default = index 3
            if 0 <= idx < len(current_options):
                return current_options[idx]
            return None

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
    """A group's preset: the presets every member has, matched by name."""

    _attr_translation_key = "group_preset"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, group: SVSGroup) -> None:
        """Initialize the entity."""
        super().__init__(group, "preset")

    @property
    def options(self) -> list[str]:
        """Return the shared preset names, plus Manual and Mixed."""
        return [
            *self.svs_group.matched_presets(),
            PRESET_MANUAL_OPTION,
            GROUP_STATE_MIXED,
        ]

    @property
    def current_option(self) -> str | None:
        """Return the shared preset, Manual, Mixed, or None if unknown.

        Manual when every member is in Manual, the preset's name when every
        member has a preset of that name active, and Mixed otherwise.
        """
        return self.svs_group.active_preset()

    async def async_select_option(self, option: str) -> None:
        """Load the preset with this name on every member."""
        if option == GROUP_STATE_MIXED:
            # Mixed is a state, not something that can be loaded
            return
        coordinators = self.svs_group.coordinators()
        if option == PRESET_MANUAL_OPTION:
            for coordinator in coordinators.values():
                coordinator.set_manual()
            return
        slots = self.svs_group.matched_presets().get(option)
        if slots is None:
            raise HomeAssistantError(f"Not every subwoofer has a preset named {option}")
        # A preset load already resends a load the subwoofer does not confirm
        await self.svs_group.async_command_members(
            lambda address, coordinator: coordinator.async_load_preset(slots[address]),
            f"load {option} on",
            retry=False,
        )


class SVSGroupStandbySelect(SVSGroupEntity, SelectEntity):
    """A group's standby mode, set on every member."""

    _attr_translation_key = "group_standby_mode"
    _attr_icon = "mdi:power-standby"
    _attr_options = [*STANDBY_MODES, GROUP_STATE_MIXED]

    def __init__(self, group: SVSGroup) -> None:
        """Initialize the entity."""
        super().__init__(group, "standby_mode")
        self._names = {value: name for name, value in STANDBY_MODE_MAP.items()}

    @property
    def current_option(self) -> str | None:
        """Return the shared standby mode, Mixed, or None if unknown."""
        values = [
            coordinator.data.get("STANDBY")
            for coordinator in self.svs_group.coordinators().values()
        ]
        if not values or None in values:
            return None
        if len(set(values)) > 1:
            return GROUP_STATE_MIXED
        return self._names.get(int(values[0]))

    async def async_select_option(self, option: str) -> None:
        """Set the standby mode on every member."""
        if option == GROUP_STATE_MIXED:
            return
        value = STANDBY_MODE_MAP[option]
        await self.svs_group.async_command_members(
            lambda address, coordinator: coordinator.async_send_command(
                "STANDBY", value
            ),
            f"set {option} on",
        )
