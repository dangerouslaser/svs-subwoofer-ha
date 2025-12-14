"""Number platform for SVS Subwoofer."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    VOLUME_MIN,
    VOLUME_MAX,
    VOLUME_STEP,
    PHASE_MIN,
    PHASE_MAX,
    PHASE_STEP,
    LPF_FREQ_MIN,
    LPF_FREQ_MAX,
    LPF_FREQ_STEP,
    PEQ_FREQ_MIN,
    PEQ_FREQ_MAX,
    PEQ_FREQ_STEP,
    PEQ_BOOST_MIN,
    PEQ_BOOST_MAX,
    PEQ_BOOST_STEP,
    PEQ_Q_MIN,
    PEQ_Q_MAX,
    PEQ_Q_STEP,
)
from .coordinator import SVSSubwooferCoordinator

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
    ),
    SVSNumberEntityDescription(
        key="lpf_frequency",
        translation_key="lpf_frequency",
        svs_param="LOW_PASS_FILTER_FREQ",
        native_min_value=LPF_FREQ_MIN,
        native_max_value=LPF_FREQ_MAX,
        native_step=LPF_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
    ),
    # PEQ1
    SVSNumberEntityDescription(
        key="peq1_frequency",
        translation_key="peq1_frequency",
        svs_param="PEQ1_FREQ",
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq1_boost",
        translation_key="peq1_boost",
        svs_param="PEQ1_BOOST",
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq1_q_factor",
        translation_key="peq1_q_factor",
        svs_param="PEQ1_QFACTOR",
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
    ),
    # PEQ2
    SVSNumberEntityDescription(
        key="peq2_frequency",
        translation_key="peq2_frequency",
        svs_param="PEQ2_FREQ",
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq2_boost",
        translation_key="peq2_boost",
        svs_param="PEQ2_BOOST",
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq2_q_factor",
        translation_key="peq2_q_factor",
        svs_param="PEQ2_QFACTOR",
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
    ),
    # PEQ3
    SVSNumberEntityDescription(
        key="peq3_frequency",
        translation_key="peq3_frequency",
        svs_param="PEQ3_FREQ",
        native_min_value=PEQ_FREQ_MIN,
        native_max_value=PEQ_FREQ_MAX,
        native_step=PEQ_FREQ_STEP,
        native_unit_of_measurement="Hz",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq3_boost",
        translation_key="peq3_boost",
        svs_param="PEQ3_BOOST",
        native_min_value=PEQ_BOOST_MIN,
        native_max_value=PEQ_BOOST_MAX,
        native_step=PEQ_BOOST_STEP,
        native_unit_of_measurement="dB",
        mode=NumberMode.SLIDER,
    ),
    SVSNumberEntityDescription(
        key="peq3_q_factor",
        translation_key="peq3_q_factor",
        svs_param="PEQ3_QFACTOR",
        native_min_value=PEQ_Q_MIN,
        native_max_value=PEQ_Q_MAX,
        native_step=PEQ_Q_STEP,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SVS number entities."""
    coordinator: SVSSubwooferCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SVSNumberEntity(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
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
        if success:
            self.coordinator.data[self.entity_description.svs_param] = value
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
