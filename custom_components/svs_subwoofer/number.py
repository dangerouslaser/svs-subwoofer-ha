"""Number platform for SVS Subwoofer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SVSConfigEntry
from .const import (
    GROUP_FEATURE_VOLUME,
    GROUP_STATE_MIXED,
    LPF_FREQ_MAX,
    LPF_FREQ_MIN,
    LPF_FREQ_STEP,
    PEQ_BOOST_MAX,
    PEQ_BOOST_MIN,
    PEQ_BOOST_STEP,
    PEQ_FREQ_MAX,
    PEQ_FREQ_MIN,
    PEQ_FREQ_STEP,
    PEQ_Q_MAX,
    PEQ_Q_MIN,
    PEQ_Q_STEP,
    PHASE_MAX,
    PHASE_MIN,
    PHASE_STEP,
    PRESET_MANUAL_OPTION,
    VOLUME_MAX,
    VOLUME_MIN,
    VOLUME_STEP,
)
from .coordinator import SVSSubwooferCoordinator
from .subwoofer_group import SVSGroup, SVSGroupEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SVSNumberEntityDescription(NumberEntityDescription):
    """Describes SVS number entity."""

    svs_param: str


NUMBER_DESCRIPTIONS: tuple[SVSNumberEntityDescription, ...] = (
    SVSNumberEntityDescription(
        key="volume",
        translation_key="volume",
        svs_param="VOLUME",
        native_min_value=VOLUME_MIN,
        native_max_value=VOLUME_MAX,
        native_step=VOLUME_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
        icon="mdi:volume-high",
    ),
    SVSNumberEntityDescription(
        key="phase",
        translation_key="phase",
        svs_param="PHASE",
        native_min_value=PHASE_MIN,
        native_max_value=PHASE_MAX,
        native_step=PHASE_STEP,
        native_unit_of_measurement="°",
        mode=NumberMode.SLIDER,
        icon="mdi:sine-wave",
    ),
    SVSNumberEntityDescription(
        key="lpf_frequency",
        translation_key="lpf_frequency",
        svs_param="LOW_PASS_FILTER_FREQ",
        entity_category=EntityCategory.CONFIG,
        native_min_value=LPF_FREQ_MIN,
        native_max_value=LPF_FREQ_MAX,
        native_step=LPF_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
        icon="mdi:tune-vertical",
    ),
    # PEQ1
    SVSNumberEntityDescription(
        key="peq1_frequency",
        translation_key="peq1_frequency",
        svs_param="PEQ1_FREQ",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq1_boost",
        translation_key="peq1_boost",
        svs_param="PEQ1_BOOST",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq1_q_factor",
        translation_key="peq1_q_factor",
        svs_param="PEQ1_QFACTOR",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
        icon="mdi:equalizer",
    ),
    # PEQ2
    SVSNumberEntityDescription(
        key="peq2_frequency",
        translation_key="peq2_frequency",
        svs_param="PEQ2_FREQ",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq2_boost",
        translation_key="peq2_boost",
        svs_param="PEQ2_BOOST",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq2_q_factor",
        translation_key="peq2_q_factor",
        svs_param="PEQ2_QFACTOR",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
        icon="mdi:equalizer",
    ),
    # PEQ3
    SVSNumberEntityDescription(
        key="peq3_frequency",
        translation_key="peq3_frequency",
        svs_param="PEQ3_FREQ",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq3_boost",
        translation_key="peq3_boost",
        svs_param="PEQ3_BOOST",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
        icon="mdi:equalizer",
    ),
    SVSNumberEntityDescription(
        key="peq3_q_factor",
        translation_key="peq3_q_factor",
        svs_param="PEQ3_QFACTOR",
        entity_category=EntityCategory.CONFIG,
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
        icon="mdi:equalizer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SVSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS number entities."""
    if isinstance(entry.runtime_data, SVSGroup):
        group = entry.runtime_data
        if GROUP_FEATURE_VOLUME in group.features:
            async_add_entities([SVSGroupVolumeNumber(group)])
        return

    coordinator = entry.runtime_data

    async_add_entities(
        SVSNumberEntity(coordinator, description) for description in NUMBER_DESCRIPTIONS
    )


class SVSNumberEntity(CoordinatorEntity[SVSSubwooferCoordinator], NumberEntity):
    """Representation of an SVS number entity."""

    _attr_has_entity_name = True
    entity_description: SVSNumberEntityDescription

    def __init__(
        self,
        coordinator: SVSSubwooferCoordinator,
        description: SVSNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return current value."""
        value = self.coordinator.data.get(self.entity_description.svs_param)
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        _LOGGER.debug("Setting %s to %s", self.entity_description.key, value)

        # Convert to int for integer parameters
        if self.entity_description.native_step == 1:
            value = int(value)

        success = await self.coordinator.async_send_command(
            self.entity_description.svs_param, value
        )
        if not success:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key} to {value}"
            )


class SVSGroupVolumeNumber(SVSGroupEntity, RestoreNumber):
    """A group's volume, applied to every member.

    The group volume G is remembered and shown. In Matched mode every member
    is set to G. In Offset mode each member is set to G plus its own offset.
    Offsets apply to changes made with the group volume; when a preset puts
    every member at the same volume, that volume is G.
    Every change sends each member its absolute target, which restores the
    offsets after a member was changed on its own.
    """

    _attr_translation_key = "group_volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_step = VOLUME_STEP
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, group: SVSGroup) -> None:
        """Initialize the entity."""
        super().__init__(group, "volume")
        self._group_volume: float | None = None
        # The volume each member has at the group volume
        self._expected: dict[str, float] = {}

    async def async_added_to_hass(self) -> None:
        """Restore the group volume from before a restart."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self._group_volume = last.native_value
            self._expected = {
                address: last.native_value + offset
                for address, offset in self.svs_group.offsets.items()
            }
        self._adopt_agreed_volume()

    @property
    def native_min_value(self) -> float:
        """Return the lowest group volume that keeps every member in range."""
        return VOLUME_MIN - min(self.svs_group.offsets.values(), default=0)

    @property
    def native_max_value(self) -> float:
        """Return the highest group volume that keeps every member in range.

        With offsets, the group's range is narrower than a subwoofer's, so no
        member is ever asked to go past -60 or 0 dB and the offsets are kept.
        """
        return VOLUME_MAX - max(self.svs_group.offsets.values(), default=0)

    def _member_volumes(self) -> dict[str, float]:
        """Return the volume of each member that has reported it."""
        coordinators = self.svs_group.coordinators()
        return {
            address: float(coordinator.data["VOLUME"])
            for address, coordinator in coordinators.items()
            if coordinator.data.get("VOLUME") is not None
        }

    def _same_preset_active(self) -> bool:
        """Return True if every member has the same preset active."""
        return self.svs_group.active_preset() not in (
            None,
            PRESET_MANUAL_OPTION,
            GROUP_STATE_MIXED,
        )

    def _agreed_volume(self) -> tuple[float, dict[str, float]] | None:
        """Return the group volume the members agree on, and their volumes.

        The members agree when each is at its offset from one group volume,
        or when the same preset put them all at the same volume.
        """
        volumes = self._member_volumes()
        if not volumes:
            return None
        implied = {
            volume - self.svs_group.offsets[address]
            for address, volume in volumes.items()
        }
        if len(implied) == 1:
            return implied.pop(), volumes
        if len(set(volumes.values())) == 1 and self._same_preset_active():
            return next(iter(volumes.values())), volumes
        return None

    @callback
    def _adopt_agreed_volume(self) -> None:
        agreed = self._agreed_volume()
        if agreed is not None:
            self._group_volume, self._expected = agreed

    @callback
    def _handle_member_update(self) -> None:
        # When the members agree, for example after a preset load, that is
        # the group volume from now on
        self._adopt_agreed_volume()
        super()._handle_member_update()

    @property
    def native_value(self) -> float | None:
        """Return the group volume.

        When the members agree, that is the group volume. Otherwise the
        remembered group volume is shown while at least one member is still
        at its volume for it, so changing one member on its own does not
        change the group. Unknown when none is.
        """
        agreed = self._agreed_volume()
        if agreed is not None:
            return agreed[0]
        volumes = self._member_volumes()
        if any(
            self._expected.get(address) == volume for address, volume in volumes.items()
        ):
            return self._group_volume
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set every member to its target for this group volume."""
        # A volume outside the group's range is brought to its nearest end,
        # so every member stays in range and the offsets are kept
        group_volume = int(
            min(max(value, self.native_min_value), self.native_max_value)
        )
        targets = {
            address: group_volume + offset
            for address, offset in self.svs_group.offsets.items()
        }
        try:
            await self.svs_group.async_command_members(
                lambda address, coordinator: coordinator.async_send_command(
                    "VOLUME", targets[address]
                ),
                "set the volume on",
            )
        except HomeAssistantError:
            # Not every member changed: the group keeps the volume it had,
            # and shows what the members report
            self.async_write_ha_state()
            raise
        self._group_volume = group_volume
        self._expected = {address: float(t) for address, t in targets.items()}
        self.async_write_ha_state()
