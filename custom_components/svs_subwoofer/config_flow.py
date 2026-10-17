"""Config flow for SVS Subwoofer integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CONNECTION_MODE,
    CONF_DISCONNECT_AFTER,
    CONF_ENTRY_TYPE,
    CONF_GROUP_FEATURES,
    CONF_MEMBERS,
    CONF_OFFSETS,
    CONF_RECONNECT_INTERVAL,
    CONF_VOLUME_MODE,
    CONNECTION_MODES,
    CONNECTION_PERIODIC,
    DEFAULT_DISCONNECT_AFTER,
    DEFAULT_RECONNECT_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_GROUP,
    GROUP_FEATURE_VOLUME,
    GROUP_FEATURES,
    OFFSET_MAX,
    OFFSET_MIN,
    SVS_SERVICE_UUID,
    VOLUME_MODE_MATCHED,
    VOLUME_MODE_OFFSET,
    VOLUME_MODES,
    get_connection_mode,
)

_LOGGER = logging.getLogger(__name__)

# Known SVS device name patterns (OUI prefix for SVS)
SVS_MAC_PREFIX = "08:EB:ED"


def _subwoofer_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return the config entries for subwoofers (not subwoofer groups)."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_GROUP
    ]


def _same_members_group(
    hass: HomeAssistant, members: list[str], exclude: str | None = None
) -> ConfigEntry | None:
    """Return another group with exactly these members, if there is one."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GROUP
            and entry.entry_id != exclude
            and set(entry.options.get(CONF_MEMBERS, [])) == set(members)
        ):
            return entry
    return None


class GroupStepsMixin:
    """The subwoofer group steps, shared by the config and options flows.

    Collects the group settings in self._group and finishes with
    self._async_finish_group().
    """

    hass: HomeAssistant
    _group: dict[str, Any]

    def _member_labels(self) -> dict[str, str]:
        """Return the subwoofers that can be members, address -> name, by name."""
        labels: dict[str, str] = {}
        for entry in _subwoofer_entries(self.hass):
            address = entry.data[CONF_ADDRESS]
            labels[address] = entry.title
        # Two subwoofers with the same name are told apart by address
        names = list(labels.values())
        labels = {
            address: name if names.count(name) == 1 else f"{name} ({address})"
            for address, name in labels.items()
        }
        return dict(sorted(labels.items(), key=lambda item: item[1].casefold()))

    def _members_schema(self, extra: dict[Any, Any]) -> vol.Schema:
        labels = self._member_labels()
        members = [a for a in self._group.get(CONF_MEMBERS, []) if a in labels]
        return vol.Schema(
            {
                **extra,
                vol.Required(CONF_MEMBERS, default=members): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=address, label=label)
                            for address, label in labels.items()
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_GROUP_FEATURES,
                    default=self._group.get(CONF_GROUP_FEATURES, GROUP_FEATURES),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=GROUP_FEATURES,
                        multiple=True,
                        translation_key=CONF_GROUP_FEATURES,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

    async def _async_members_done(self) -> ConfigFlowResult:
        """Continue after the members and features are chosen."""
        if GROUP_FEATURE_VOLUME in self._group[CONF_GROUP_FEATURES]:
            return await self.async_step_group_volume()
        return await self._async_finish_group()

    async def async_step_group_volume(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how the group volume moves the subwoofers."""
        if user_input is not None:
            self._group[CONF_VOLUME_MODE] = user_input[CONF_VOLUME_MODE]
            if self._group[CONF_VOLUME_MODE] == VOLUME_MODE_OFFSET:
                return await self.async_step_group_offsets()
            return await self._async_finish_group()

        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="group_volume",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_VOLUME_MODE,
                        default=self._group.get(CONF_VOLUME_MODE, VOLUME_MODE_MATCHED),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=VOLUME_MODES,
                            translation_key=CONF_VOLUME_MODE,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_group_offsets(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set each subwoofer's offset from the group volume."""
        labels = self._member_labels()
        members = self._group[CONF_MEMBERS]
        # The fields are named after the subwoofers, so the dialog shows them
        fields = {label: a for a, label in labels.items() if a in members}
        if user_input is not None:
            shown = set(fields.values())
            self._group[CONF_OFFSETS] = {
                # A member without a field here (not set up) keeps its offset
                **{
                    address: offset
                    for address, offset in self._group.get(CONF_OFFSETS, {}).items()
                    if address in members and address not in shown
                },
                **{
                    address: int(user_input.get(field, 0))
                    for field, address in fields.items()
                },
            }
            return await self._async_finish_group()

        offsets = self._group.get(CONF_OFFSETS, {})
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="group_offsets",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        field, default=offsets.get(address, 0)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=OFFSET_MIN,
                            max=OFFSET_MAX,
                            step=1,
                            unit_of_measurement="dB",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                    for field, address in fields.items()
                }
            ),
        )

    def _group_options(self) -> dict[str, Any]:
        """Return the options to store for the group."""
        return {
            CONF_MEMBERS: self._group[CONF_MEMBERS],
            CONF_GROUP_FEATURES: self._group[CONF_GROUP_FEATURES],
            CONF_VOLUME_MODE: self._group.get(CONF_VOLUME_MODE, VOLUME_MODE_MATCHED),
            CONF_OFFSETS: self._group.get(CONF_OFFSETS, {}),
        }

    async def _async_finish_group(self) -> ConfigFlowResult:
        raise NotImplementedError


class SVSSubwooferConfigFlow(GroupStepsMixin, ConfigFlow, domain=DOMAIN):
    """Handle config flow for SVS Subwoofer."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._group: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GROUP:
            return SVSGroupOptionsFlow(config_entry)
        return SVSSubwooferOptionsFlow()

    async def async_step_create_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the group and choose its members and what it controls."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if len(user_input[CONF_MEMBERS]) < 2:
                errors[CONF_MEMBERS] = "too_few_members"
            elif _same_members_group(self.hass, user_input[CONF_MEMBERS]):
                errors[CONF_MEMBERS] = "duplicate_group"
            else:
                self._group = {
                    CONF_NAME: user_input[CONF_NAME].strip(),
                    CONF_MEMBERS: user_input[CONF_MEMBERS],
                    CONF_GROUP_FEATURES: user_input.get(
                        CONF_GROUP_FEATURES, GROUP_FEATURES
                    ),
                }
                return await self._async_members_done()
            self._group = {**self._group, **user_input}

        return self.async_show_form(
            step_id="create_group",
            data_schema=self._members_schema(
                {vol.Required(CONF_NAME, default=self._group.get(CONF_NAME, "")): str}
            ),
            errors=errors,
        )

    async def _async_finish_group(self) -> ConfigFlowResult:
        """Create the group entry."""
        return self.async_create_entry(
            title=self._group[CONF_NAME] or "Subwoofer group",
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_GROUP},
            options=self._group_options(),
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery.

        This is called when HA discovers a device matching our manifest.json
        bluetooth matchers.
        """
        _LOGGER.debug("Bluetooth discovery: %s", discovery_info)

        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or "SVS Subwoofer"
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth device setup."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_device")

        if user_input is not None:
            name = user_input.get(
                CONF_NAME, self._discovery_info.name or "SVS Subwoofer"
            )
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: name,
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=self._discovery_info.name or "SVS Subwoofer"
                    ): str,
                }
            ),
            description_placeholders={
                "name": self._discovery_info.name or "SVS Subwoofer",
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer a subwoofer group once at least two subwoofers are set up."""
        if len(_subwoofer_entries(self.hass)) >= 2:
            return self.async_show_menu(
                step_id="user", menu_options=["add_subwoofer", "create_group"]
            )
        return await self.async_step_add_subwoofer(user_input)

    async def async_step_add_subwoofer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated configuration.

        Shows discovered devices or allows manual MAC entry.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS, "")

            # Check if user selected a discovered device or entered manual address
            if address in self._discovered_devices:
                # User selected a discovered device
                device = self._discovered_devices[address]
                formatted_mac = format_mac(address)
                await self.async_set_unique_id(formatted_mac)
                self._abort_if_unique_id_configured()

                # Use device name if user didn't provide a custom name
                user_name = user_input.get(CONF_NAME, "")
                final_name = (
                    user_name if user_name else (device.name or "SVS Subwoofer")
                )

                return self.async_create_entry(
                    title=final_name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: final_name,
                    },
                )
            elif address == "manual":
                # User wants manual entry
                return await self.async_step_manual()
            else:
                # Validate manual MAC address format
                address = address.upper().replace("-", ":")
                mac_clean = address.replace(":", "")
                if len(mac_clean) != 12 or not all(
                    c in "0123456789ABCDEF" for c in mac_clean
                ):
                    errors[CONF_ADDRESS] = "invalid_mac"
                else:
                    formatted_mac = format_mac(address)
                    await self.async_set_unique_id(formatted_mac)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, "SVS Subwoofer"),
                        data={
                            CONF_ADDRESS: address,
                            CONF_NAME: user_input.get(CONF_NAME, "SVS Subwoofer"),
                        },
                    )

        # Discover Bluetooth devices - show all devices with names
        # Prioritize SVS devices (by MAC prefix or service UUID)
        current_addresses = self._async_current_ids()
        svs_devices: dict[str, BluetoothServiceInfoBleak] = {}
        other_devices: dict[str, BluetoothServiceInfoBleak] = {}

        for info in async_discovered_service_info(self.hass):
            if info.address in current_addresses:
                continue
            # Skip devices without names (harder to identify)
            if not info.name or info.name == info.address:
                continue

            # Check if this is an SVS device by service UUID or MAC prefix
            service_uuids_lower = [s.lower() for s in info.service_uuids]
            is_svs = (
                SVS_SERVICE_UUID.lower() in service_uuids_lower
                or info.address.upper().startswith(SVS_MAC_PREFIX)
            )

            if is_svs:
                svs_devices[info.address] = info
                _LOGGER.debug("Found SVS device: %s (%s)", info.name, info.address)
            else:
                other_devices[info.address] = info
                _LOGGER.debug("Found other device: %s (%s)", info.name, info.address)

        # Combine: SVS devices first, then others
        self._discovered_devices = {**svs_devices, **other_devices}

        if self._discovered_devices:
            # Show picker with discovered devices
            # Mark SVS devices with a prefix for clarity
            addresses = {}
            for addr, info in self._discovered_devices.items():
                is_svs = addr.upper().startswith(SVS_MAC_PREFIX)
                prefix = "[SVS] " if is_svs else ""
                addresses[addr] = f"{prefix}{info.name or 'Unknown'} ({addr})"

            addresses["manual"] = "Enter MAC address manually..."

            return self.async_show_form(
                step_id="add_subwoofer",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ADDRESS): vol.In(addresses),
                        vol.Optional(CONF_NAME, default=""): str,
                    }
                ),
                errors=errors,
                description_placeholders={
                    "hint": "Leave name blank to use the device's advertised name"
                },
            )

        # No devices found - go straight to manual entry
        return await self.async_step_manual()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual MAC address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS, "").upper().replace("-", ":")

            # Validate MAC address format
            mac_clean = address.replace(":", "")
            if len(mac_clean) != 12 or not all(
                c in "0123456789ABCDEF" for c in mac_clean
            ):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                formatted_mac = format_mac(address)
                await self.async_set_unique_id(formatted_mac)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "SVS Subwoofer"),
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: user_input.get(CONF_NAME, "SVS Subwoofer"),
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="SVS Subwoofer"): str,
                }
            ),
            errors=errors,
            description_placeholders={"mac_format": "AA:BB:CC:DD:EE:FF"},
        )


def _duration_selector(minimum: int, maximum: int, step: int) -> NumberSelector:
    """Return a number box for a duration in seconds."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


class SVSSubwooferOptionsFlow(OptionsFlow):
    """Handle the Bluetooth connection options for SVS Subwoofer.

    The timing options only apply to the Periodic connection, so they are
    shown on a second step only in that case.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the connection mode."""
        options = self.config_entry.options
        if user_input is not None:
            if user_input[CONF_CONNECTION_MODE] == CONNECTION_PERIODIC:
                return await self.async_step_timing()
            # Keep the timing values for when Periodic is chosen again
            return self.async_create_entry(
                data={
                    CONF_CONNECTION_MODE: user_input[CONF_CONNECTION_MODE],
                    CONF_RECONNECT_INTERVAL: options.get(
                        CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL
                    ),
                    CONF_DISCONNECT_AFTER: options.get(
                        CONF_DISCONNECT_AFTER, DEFAULT_DISCONNECT_AFTER
                    ),
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONNECTION_MODE,
                        default=get_connection_mode(self.config_entry.options),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=mode, label=mode.capitalize())
                                for mode in CONNECTION_MODES
                            ],
                            translation_key=CONF_CONNECTION_MODE,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the Periodic connection timing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # An emptied field uses its default, not the value stored before
            interval = user_input.get(
                CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL
            )
            hang_on = user_input.get(CONF_DISCONNECT_AFTER, DEFAULT_DISCONNECT_AFTER)
            # A refresh that is not longer than the hang-on time keeps the
            # link up nearly all the time and lights the panel LEDs at every
            # reconnect
            if 0 < interval <= hang_on:
                errors[CONF_RECONNECT_INTERVAL] = "refresh_within_hang_on"
            else:
                return self.async_create_entry(
                    data={
                        CONF_CONNECTION_MODE: CONNECTION_PERIODIC,
                        CONF_RECONNECT_INTERVAL: interval,
                        CONF_DISCONNECT_AFTER: hang_on,
                    }
                )

        # The fields start with the stored values (or what was just entered)
        # as suggestions, so that a field emptied on submit is left out
        shown = self.config_entry.options if user_input is None else user_input
        return self.async_show_form(
            step_id="timing",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_RECONNECT_INTERVAL,
                        description={
                            "suggested_value": shown.get(
                                CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL
                            )
                        },
                    ): _duration_selector(0, 3600, 10),
                    vol.Optional(
                        CONF_DISCONNECT_AFTER,
                        description={
                            "suggested_value": shown.get(
                                CONF_DISCONNECT_AFTER, DEFAULT_DISCONNECT_AFTER
                            )
                        },
                    ): _duration_selector(10, 600, 10),
                }
            ),
            errors=errors,
        )


class SVSGroupOptionsFlow(GroupStepsMixin, OptionsFlow):
    """Change a subwoofer group's members and settings.

    The group is renamed with Home Assistant's own rename, like any device.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        # Not self.config_entry: assigning that is deprecated on newer HA
        self._entry = config_entry
        self._group: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start with the members and features."""
        return await self.async_step_group_members()

    async def async_step_group_members(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the members and what the group controls."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if len(user_input[CONF_MEMBERS]) < 2:
                errors[CONF_MEMBERS] = "too_few_members"
            elif _same_members_group(
                self.hass, user_input[CONF_MEMBERS], exclude=self._entry.entry_id
            ):
                errors[CONF_MEMBERS] = "duplicate_group"
            else:
                self._group[CONF_MEMBERS] = user_input[CONF_MEMBERS]
                self._group[CONF_GROUP_FEATURES] = user_input.get(
                    CONF_GROUP_FEATURES, GROUP_FEATURES
                )
                return await self._async_members_done()

        return self.async_show_form(
            step_id="group_members",
            data_schema=self._members_schema({}),
            errors=errors,
        )

    async def _async_finish_group(self) -> ConfigFlowResult:
        """Save the group options."""
        return self.async_create_entry(data=self._group_options())
