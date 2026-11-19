"""Tests for adding a subwoofer (the setup flow). Every branch has these."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.svs_subwoofer.const import DOMAIN, SVS_SERVICE_UUID

from .conftest import ADDRESS

DISCOVERY = SimpleNamespace(
    address=ADDRESS, name="LEFT", service_uuids=[SVS_SERVICE_UUID]
)
SETUP = "custom_components.svs_subwoofer.async_setup_entry"
DISCOVERED = "custom_components.svs_subwoofer.config_flow.async_discovered_service_info"


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    """A discovered subwoofer is confirmed and added under the chosen name."""
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=DISCOVERY
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Subwoofer Left"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Subwoofer Left"
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_NAME: "Subwoofer Left"}


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    """A subwoofer that is already set up is not offered again."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS.lower(), data={CONF_ADDRESS: ADDRESS}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_picks_discovered_subwoofer(hass: HomeAssistant) -> None:
    """The user flow lists discovered subwoofers and adds the chosen one."""
    with patch(DISCOVERED, return_value=[DISCOVERY]), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        # With fewer than two subwoofers there is nothing to group, so the
        # user step goes straight to the subwoofer form
        assert result["step_id"] == "subwoofer"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS, CONF_NAME: ""}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # A blank name falls back to the advertised name
    assert result["title"] == "LEFT"


async def test_manual_entry_validates_mac(hass: HomeAssistant) -> None:
    """With nothing discovered, a MAC address is entered and validated."""
    with patch(DISCOVERED, return_value=[]), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "manual"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "not-a-mac", CONF_NAME: "Sub"}
        )
        assert result["errors"] == {CONF_ADDRESS: "invalid_mac"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "54-b7-e5-82-d1-e2", CONF_NAME: "Sub"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDRESS] == ADDRESS
