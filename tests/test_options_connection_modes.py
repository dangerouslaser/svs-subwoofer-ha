"""Tests for the Bluetooth Connection Options dialog and the connection modes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.svs_subwoofer import coordinator as coordinator_module
from custom_components.svs_subwoofer.const import DOMAIN

from .conftest import ADDRESS, FakeSubwoofer, SetupEntry, settle

STRINGS = Path("custom_components/svs_subwoofer")


def _entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS.lower(),
        data={CONF_ADDRESS: ADDRESS},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def test_periodic_opens_the_timing_step(hass: HomeAssistant) -> None:
    """Periodic is the default and leads to the timing step."""
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"connection_mode": "periodic"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "timing"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"reconnect_interval": 300, "disconnect_after": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "connection_mode": "periodic",
        "reconnect_interval": 300,
        "disconnect_after": 120,
    }


async def test_timing_fields_fall_back_to_defaults(hass: HomeAssistant) -> None:
    """The timing fields are optional; empty ones use their defaults."""
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"connection_mode": "periodic"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["reconnect_interval"] == 0
    assert entry.options["disconnect_after"] == 60


async def test_constant_and_quiet_keep_the_timing_values(hass: HomeAssistant) -> None:
    """Constant and Quiet save at once and keep the stored timing values."""
    for mode in ("constant", "quiet"):
        entry = _entry(
            hass,
            {
                "connection_mode": "periodic",
                "reconnect_interval": 300,
                "disconnect_after": 90,
            },
        )
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"connection_mode": mode}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options == {
            "connection_mode": mode,
            "reconnect_interval": 300,
            "disconnect_after": 90,
        }
        await hass.config_entries.async_remove(entry.entry_id)


def test_dialog_text() -> None:
    """Both steps share the title, and each mode carries its description."""
    for name in ("strings.json", "translations/en.json"):
        strings = json.loads((STRINGS / name).read_text(encoding="utf-8"))
        steps = strings["options"]["step"]
        assert steps["init"]["title"] == "Bluetooth Connection Options"
        assert steps["timing"]["title"] == "Bluetooth Connection Options"
        labels = strings["selector"]["connection_mode"]["options"]
        for mode, label in (
            ("periodic", "Periodic"),
            ("constant", "Constant"),
            ("quiet", "Quiet"),
        ):
            assert labels[mode].startswith(f"{label} – ")
        assert "n't" not in json.dumps(strings), "contraction in UI text"


async def test_periodic_disconnects_and_refreshes(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Periodic disconnects after the hang-on time and reconnects to refresh."""
    await setup_entry(
        {
            "connection_mode": "periodic",
            "reconnect_interval": 0.2,
            "disconnect_after": 0.1,
        }
    )
    await settle(1.0)
    # Connected at setup, then disconnected and reconnected at least once
    assert sub.connects >= 2


async def test_constant_checks_with_a_settings_request(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Constant keeps the connection and checks it by asking for settings."""
    with (
        patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.1),
        patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0),
    ):
        await setup_entry({"connection_mode": "constant"})
        reads_at_setup = sub.frame_types().count("f11f")
        await settle(0.6)
    assert sub.frame_types().count("f11f") > reads_at_setup
    assert sub.connects == 1
    assert sub.info_reads == []


async def test_quiet_checks_without_settings_requests(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Quiet keeps the connection with a standard read, not a settings request."""
    with patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.1):
        await setup_entry({"connection_mode": "quiet"})
        reads_at_setup = sub.frame_types().count("f11f")
        await settle(0.6)
    assert sub.frame_types().count("f11f") == reads_at_setup
    assert len(sub.info_reads) >= 3
    assert sub.connects == 1


async def test_old_keep_alive_becomes_constant(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """An entry with only the old keep_alive flag stays connected, as Constant."""
    entry = _entry(hass, {"keep_alive": True})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    default = next(key for key in schema if key == "connection_mode").default()
    assert default == "constant"
    hass.config_entries.options.async_abort(result["flow_id"])
    await hass.config_entries.async_remove(entry.entry_id)

    # And it runs as Constant: connected, checked with settings requests
    with (
        patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.1),
        patch.object(coordinator_module, "LIVENESS_STALE_AFTER", 0),
    ):
        await setup_entry({"keep_alive": True})
        reads_at_setup = sub.frame_types().count("f11f")
        await settle(0.6)
    assert sub.frame_types().count("f11f") > reads_at_setup
    assert sub.connects == 1


async def test_emptied_timing_fields_use_the_defaults(hass: HomeAssistant) -> None:
    """A field emptied on submit takes its default, not the value stored before."""
    entry = _entry(
        hass,
        {
            "connection_mode": "periodic",
            "reconnect_interval": 300,
            "disconnect_after": 120,
        },
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"connection_mode": "periodic"}
    )
    # The stored values are shown as suggestions
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert suggested == {"reconnect_interval": 300, "disconnect_after": 120}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "connection_mode": "periodic",
        "reconnect_interval": 0,
        "disconnect_after": 60,
    }


async def test_refresh_must_be_longer_than_the_hang_on_time(
    hass: HomeAssistant,
) -> None:
    """A refresh no longer than the hang-on time is refused; 0 is allowed."""
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"connection_mode": "periodic"}
    )
    for interval in (30, 120):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"reconnect_interval": interval, "disconnect_after": 120}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"reconnect_interval": "refresh_within_hang_on"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"reconnect_interval": 0, "disconnect_after": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    for name in ("strings.json", "translations/en.json"):
        strings = json.loads((STRINGS / name).read_text(encoding="utf-8"))
        assert strings["options"]["error"]["refresh_within_hang_on"]


async def test_periodic_refresh_backs_off_a_sub_that_does_not_answer(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A refresh whose connection the sub never answers counts as silence.

    Without that, the refresh reconnected every interval indefinitely.
    """
    with (
        patch.object(coordinator_module, "PROBE_TIMEOUT", 0.1),
        patch.object(coordinator_module, "RECONNECT_BACKOFF", (30.0,)),
    ):
        await setup_entry(
            {
                "connection_mode": "periodic",
                "reconnect_interval": 0.2,
                "disconnect_after": 0.1,
            }
        )
        sub.silent = True
        await settle(0.3)
        connects = sub.connects
        await settle(2.0)
    # At most the immediate retry after the first silence, then the backoff
    assert sub.connects - connects <= 2


async def test_unloading_mid_connection_leaves_no_connection_open(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """A loop stopped while it connects does not leave the link open."""
    entry = await setup_entry(
        {
            "connection_mode": "periodic",
            "reconnect_interval": 0.3,
            "disconnect_after": 0.1,
        }
    )
    await settle(0.2)
    assert not sub.client.is_connected
    # The next refresh opens the link and is still setting it up when the
    # entry unloads
    sub.connect_delay = 1.0
    connects = sub.connects
    await settle(0.5)
    assert sub.connects == connects + 1
    await hass.config_entries.async_unload(entry.entry_id)
    await settle(1.5)
    assert not sub.client.is_connected


async def test_missing_quiet_field_is_warned_about_once(
    hass: HomeAssistant,
    sub: FakeSubwoofer,
    setup_entry: SetupEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The warning is logged once, not at every connection."""
    sub.device_info = {}
    with patch.object(coordinator_module, "KEEP_ALIVE_INTERVAL", 0.1):
        entry = await setup_entry({"connection_mode": "quiet"})
        await settle(0.4)
        await entry.runtime_data.async_reconnect()
        await settle(0.4)
    warnings = [
        record
        for record in caplog.records
        if "offers no standard readable field" in record.getMessage()
    ]
    assert len(warnings) >= 2
    assert [record.levelname for record in warnings].count("WARNING") == 1
