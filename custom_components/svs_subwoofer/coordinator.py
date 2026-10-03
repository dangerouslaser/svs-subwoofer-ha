"""DataUpdateCoordinator for SVS Subwoofer."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakNotFoundError, establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.const import CONF_DEVICE_ID, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COMMAND_DELAY,
    DOMAIN,
    EVENT_SVS_SUBWOOFER,
    SVS_CHAR_UUID,
    SYNCABLE_PARAMS,
    TRIGGER_SUBTYPE_DEFAULT,
    TRIGGER_TYPE_CONNECTED,
    TRIGGER_TYPE_DISCONNECTED,
    TRIGGER_TYPE_PRESET_LOADED,
)
from .svs_protocol import FrameAssembler, svs_encode

_LOGGER = logging.getLogger(__name__)

# Connection timeout in seconds
CONNECTION_TIMEOUT = 60.0

# Number of connection retry attempts
MAX_CONNECT_RETRIES = 3
RETRY_DELAY = 2.0

# Auto-disconnect after idle (seconds)
IDLE_DISCONNECT_TIMEOUT = 60.0

# How often to check the link when "stay connected" is enabled (seconds)
KEEP_ALIVE_INTERVAL = 30.0

# Probe the link before a command if nothing was received for this long (seconds)
LIVENESS_STALE_AFTER = 20.0

# How long to wait for the subwoofer to answer a probe (seconds)
PROBE_TIMEOUT = 3.0


class SVSSubwooferCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for SVS Subwoofer BLE communication."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        address: str,
        name: str,
        keep_alive: bool = False,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance.
            entry_id: ID of the config entry that owns this device.
            address: BLE MAC address of the subwoofer.
            name: User-friendly name for the device.
            keep_alive: Stay connected and probe the link instead of
                disconnecting when idle.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"SVS Subwoofer {name}",
            # No update_interval - push-based via BLE notifications
        )
        self.address = address
        self.device_name = name
        self._entry_id = entry_id
        self._keep_alive = keep_alive
        self._client: BleakClient | None = None
        self._frame_assembler = FrameAssembler()
        self._connected = False
        # Serializes all BLE traffic and connection state changes
        self._command_lock = asyncio.Lock()
        self._idle_disconnect_task: asyncio.Task | None = None
        self._keep_alive_task: asyncio.Task | None = None
        # Set when the user explicitly disconnects; suppresses keep-alive reconnects
        self._manual_disconnect = False
        # Monotonic time of the last notification, and a signal for probes
        self._last_rx = 0.0
        self._rx_event = asyncio.Event()

        # Initialize data with sensible defaults
        # This ensures entities have values even before first device response
        self.data: dict[str, Any] = {
            # Volume and phase
            "VOLUME": -20,
            "PHASE": 0,
            # Low pass filter
            "LOW_PASS_FILTER_ENABLE": 0,
            "LOW_PASS_FILTER_FREQ": 80,
            "LOW_PASS_FILTER_SLOPE": 12,
            # PEQ1
            "PEQ1_ENABLE": 0,
            "PEQ1_FREQ": 50,
            "PEQ1_BOOST": 0,
            "PEQ1_QFACTOR": 1.0,
            # PEQ2
            "PEQ2_ENABLE": 0,
            "PEQ2_FREQ": 50,
            "PEQ2_BOOST": 0,
            "PEQ2_QFACTOR": 1.0,
            # PEQ3
            "PEQ3_ENABLE": 0,
            "PEQ3_FREQ": 50,
            "PEQ3_BOOST": 0,
            "PEQ3_QFACTOR": 1.0,
            # Room gain
            "ROOM_GAIN_ENABLE": 0,
            "ROOM_GAIN_FREQ": 31,
            "ROOM_GAIN_SLOPE": 6,
            # Other
            "STANDBY": 0,
            "POLARITY": 0,
            # Preset names (empty until loaded from device)
            "PRESET1NAME": "",
            "PRESET2NAME": "",
            "PRESET3NAME": "",
            # Active preset (None until a preset is loaded)
            "ACTIVE_PRESET": None,
        }
        self._device_id: str | None = None

    def _get_device_id(self) -> str | None:
        """Get the device ID from the device registry."""
        if self._device_id:
            return self._device_id
        device_registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, self._entry_id
        ):
            if (DOMAIN, self.address) in device.identifiers:
                self._device_id = device.id
                break
        return self._device_id

    def _fire_event(self, trigger_type: str, subtype: str | None = None) -> None:
        """Fire a device automation event."""
        device_id = self._get_device_id()
        if not device_id:
            return
        event_data = {
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        if subtype:
            event_data["subtype"] = subtype
        self.hass.bus.async_fire(EVENT_SVS_SUBWOOFER, event_data)
        _LOGGER.debug("Fired event %s: %s", EVENT_SVS_SUBWOOFER, event_data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the subwoofer."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=self.device_name,
            manufacturer="SVS",
            model="Subwoofer",
        )

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the subwoofer."""
        return self._connected

    def _schedule_idle_disconnect(self) -> None:
        """Schedule disconnection after idle timeout.

        Caller must hold _command_lock, so the timer can never be cancelled
        part-way through its own disconnect.
        """
        self._cancel_idle_disconnect()
        if self._keep_alive:
            return
        self._idle_disconnect_task = self.hass.async_create_task(
            self._idle_disconnect_timer()
        )

    def _cancel_idle_disconnect(self) -> None:
        """Cancel any pending idle disconnect."""
        task, self._idle_disconnect_task = self._idle_disconnect_task, None
        # Never cancel ourselves: the timer calls async_disconnect, which lands here
        if task and task is not asyncio.current_task():
            task.cancel()

    async def _idle_disconnect_timer(self) -> None:
        """Wait for idle timeout then disconnect."""
        await asyncio.sleep(IDLE_DISCONNECT_TIMEOUT)
        _LOGGER.debug("Idle timeout reached, disconnecting from %s", self.address)
        await self.async_disconnect()

    def _start_keep_alive(self) -> None:
        """Start the keep-alive loop if enabled and not already running."""
        if not self._keep_alive or self._keep_alive_task:
            return
        self._keep_alive_task = self.hass.async_create_background_task(
            self._keep_alive_loop(), f"svs_subwoofer keep-alive {self.address}"
        )

    async def _keep_alive_loop(self) -> None:
        """Keep the link busy and reconnect if it has silently died."""
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            if self._manual_disconnect:
                continue
            async with self._command_lock:
                try:
                    await self._ensure_live()
                except UpdateFailed as err:
                    _LOGGER.debug(
                        "Keep-alive reconnect to %s failed: %s", self.address, err
                    )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device.

        This is called by the coordinator framework but we use push-based
        updates via BLE notifications, so we just connect if needed (which
        also re-reads all settings) and return current data.
        """
        async with self._command_lock:
            if not self._connected:
                await self._connect()
                self._schedule_idle_disconnect()
        self._start_keep_alive()
        return self.data

    async def _connect(self) -> None:
        """Establish BLE connection with notifications and read all settings.

        Caller must hold _command_lock.
        """
        if self._connected and self._client and self._client.is_connected:
            return

        # The sub only accepts one connection; release any half-dead client first
        self._connected = False
        await self._async_release_client()

        # Get BLE device reference
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if not ble_device:
            raise UpdateFailed(
                f"Device {self.address} not found. "
                "Check that the subwoofer is powered on and the SVS app is disconnected."
            )

        _LOGGER.debug("Connecting to SVS Subwoofer at %s", self.address)

        try:
            # Use bleak_retry_connector for reliable HA Bluetooth integration
            self._client = await establish_connection(
                BleakClient,
                ble_device,
                self.address,
                disconnected_callback=self._on_disconnect,
                max_attempts=MAX_CONNECT_RETRIES,
            )
            await self._client.start_notify(SVS_CHAR_UUID, self._notification_handler)
        except BleakNotFoundError as err:
            await self._async_release_client()
            raise UpdateFailed(f"Device {self.address} not found: {err}") from err
        except TimeoutError as err:
            await self._async_release_client()
            raise UpdateFailed(f"Timeout connecting to {self.address}: {err}") from err
        except BleakError as err:
            await self._async_release_client()
            raise UpdateFailed(f"Failed to connect to {self.address}: {err}") from err

        self._connected = True
        self._manual_disconnect = False
        _LOGGER.info("Connected to SVS Subwoofer at %s", self.address)
        # Notify listeners of connection state change
        self.async_set_updated_data(self.data)
        # Fire connected event for device automations
        self._fire_event(TRIGGER_TYPE_CONNECTED)
        # Settings may have changed while we were away (e.g. via the SVS app)
        await self._request_full_settings()

    async def _async_release_client(self) -> None:
        """Disconnect and forget the BLE client without publishing state.

        The client is detached before disconnecting so its disconnect callback
        is ignored as stale.
        """
        client, self._client = self._client, None
        self._frame_assembler.reset()
        if client and client.is_connected:
            try:
                await client.disconnect()
            except BleakError as err:
                _LOGGER.debug("Error disconnecting from %s: %s", self.address, err)

    async def _async_drop_connection(self) -> None:
        """Tear down the connection and publish the disconnected state.

        Caller must hold _command_lock.
        """
        was_connected = self._connected
        self._connected = False
        await self._async_release_client()
        if was_connected:
            _LOGGER.debug("Disconnected from SVS Subwoofer at %s", self.address)
            self.async_set_updated_data(self.data)
            self._fire_event(TRIGGER_TYPE_DISCONNECTED)

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from device."""
        if client is not self._client:
            # Callback from a client we already released
            return
        _LOGGER.warning("Disconnected from SVS Subwoofer at %s", self.address)
        self._connected = False
        self._client = None
        self._frame_assembler.reset()
        # Notify listeners of connection state change
        self.async_set_updated_data(self.data)
        # Fire disconnected event for device automations
        self._fire_event(TRIGGER_TYPE_DISCONNECTED)

    @callback
    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle incoming BLE notifications."""
        self._last_rx = time.monotonic()
        self._rx_event.set()
        for decoded in self._frame_assembler.add_data(bytes(data)):
            validated = decoded.get("VALIDATED_VALUES", {})
            if validated:
                # Update our data store
                self.data.update(validated)
                _LOGGER.debug("Updated data from %s: %s", self.address, validated)
                # Notify listeners of new data
                self.async_set_updated_data(self.data)

    async def _async_probe(self) -> bool:
        """Check the subwoofer still answers on the current connection.

        Caller must hold _command_lock. A link can report connected while the
        sub has stopped responding, in which case writes are silently dropped.
        """
        frame, _ = svs_encode("MEMREAD", "FULL_SETTINGS")
        self._rx_event.clear()
        try:
            await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
            await asyncio.wait_for(self._rx_event.wait(), PROBE_TIMEOUT)
        except (BleakError, TimeoutError):
            return False
        await asyncio.sleep(COMMAND_DELAY)
        return True

    async def _ensure_live(self) -> None:
        """Make sure there is a responsive connection, reconnecting if needed.

        Caller must hold _command_lock. Raises UpdateFailed if connecting fails.
        """
        if self._connected and self._client and self._client.is_connected:
            if time.monotonic() - self._last_rx < LIVENESS_STALE_AFTER:
                return
            if await self._async_probe():
                return
            _LOGGER.warning(
                "SVS Subwoofer at %s stopped responding, reconnecting", self.address
            )
            await self._async_drop_connection()
        await self._connect()

    async def _ensure_writable(self) -> bool:
        """Ensure BLE client is connected and ready for a write.

        Caller must hold _command_lock.
        """
        try:
            await self._ensure_live()
        except UpdateFailed as err:
            _LOGGER.error("Failed to connect for command: %s", err)
            return False
        return True

    async def async_send_command(self, param: str, value: Any) -> bool:
        """Send a command to the subwoofer.

        Args:
            param: Parameter name (e.g., "VOLUME", "PHASE").
            value: Value to set.

        Returns:
            True if command was sent successfully.
        """
        async with self._command_lock:
            if not await self._ensure_writable():
                return False

            frame, meta = svs_encode("MEMWRITE", param, value)
            if not frame:
                _LOGGER.error("Failed to encode command for %s=%s", param, value)
                return False

            try:
                _LOGGER.debug("Sending command: %s", meta)
                await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
                # Rate limiting per pySVS protocol
                await asyncio.sleep(COMMAND_DELAY)
                # Optimistic update — the SVS device does not reliably push a
                # notification after a write, so reflect the new value locally
                # so all paths (entities, services, sync_from) stay consistent.
                self.data[param] = value
                # User modified a param — any active preset is no longer truly active
                if (
                    param in SYNCABLE_PARAMS
                    and self.data.get("ACTIVE_PRESET") is not None
                ):
                    self.data["ACTIVE_PRESET"] = None
                self.async_set_updated_data(self.data)
                # Reset idle disconnect timer
                self._schedule_idle_disconnect()
                return True
            except BleakError as err:
                _LOGGER.error("Failed to send command: %s", err)
                await self._async_drop_connection()
                return False
            except Exception as err:
                _LOGGER.error("Unexpected error sending command: %s", err)
                await self._async_drop_connection()
                return False

    async def async_load_preset(self, preset_number: int) -> bool:
        """Load a preset on the subwoofer.

        Args:
            preset_number: Preset number (1-4).

        Returns:
            True if command was sent successfully.
        """
        if not 1 <= preset_number <= 4:
            _LOGGER.error("Invalid preset number: %s", preset_number)
            return False

        async with self._command_lock:
            if not await self._ensure_writable():
                return False

            frame, meta = svs_encode("PRESETLOADSAVE", f"PRESET{preset_number}LOAD")
            if not frame:
                return False

            try:
                _LOGGER.debug("Loading preset: %s", meta)
                await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
                await asyncio.sleep(COMMAND_DELAY)

                # Track which preset is active and publish immediately;
                # _request_full_settings will follow with the actual values.
                self.data["ACTIVE_PRESET"] = preset_number
                self.async_set_updated_data(self.data)
                # After loading preset, request current settings
                await self._request_full_settings()
                # Reset idle disconnect timer
                self._schedule_idle_disconnect()
                # Fire preset loaded event for device automations
                subtype = (
                    TRIGGER_SUBTYPE_DEFAULT
                    if preset_number == 4
                    else f"preset_{preset_number}"
                )
                self._fire_event(TRIGGER_TYPE_PRESET_LOADED, subtype)
                return True
            except BleakError as err:
                _LOGGER.error("Failed to load preset: %s", err)
                await self._async_drop_connection()
                return False

    async def async_save_preset(self, preset_number: int) -> bool:
        """Save current settings to a preset slot on the subwoofer.

        Args:
            preset_number: Preset number (1-3). Note: Preset 4 is factory default and cannot be saved.

        Returns:
            True if command was sent successfully.
        """
        if not 1 <= preset_number <= 3:
            _LOGGER.error(
                "Invalid preset number for save: %s (must be 1-3)", preset_number
            )
            return False

        async with self._command_lock:
            if not await self._ensure_writable():
                return False

            frame, meta = svs_encode("PRESETLOADSAVE", f"PRESET{preset_number}SAVE")
            if not frame:
                return False

            try:
                _LOGGER.debug("Saving preset: %s", meta)
                await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
                await asyncio.sleep(COMMAND_DELAY)
                # Reset idle disconnect timer
                self._schedule_idle_disconnect()
                return True
            except BleakError as err:
                _LOGGER.error("Failed to save preset: %s", err)
                await self._async_drop_connection()
                return False

    async def _request_full_settings(self) -> None:
        """Request all settings from subwoofer."""
        if not self._client or not self._connected:
            return

        requests = [
            ("MEMREAD", "FULL_SETTINGS"),
            ("MEMREAD", "PRESET1NAME"),
            ("MEMREAD", "PRESET2NAME"),
            ("MEMREAD", "PRESET3NAME"),
        ]

        for ftype, param in requests:
            frame, meta = svs_encode(ftype, param)
            if frame:
                try:
                    _LOGGER.debug("Requesting: %s", meta)
                    await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
                    await asyncio.sleep(COMMAND_DELAY)
                except BleakError as err:
                    _LOGGER.warning("Failed to request %s: %s", param, err)

    async def async_disconnect(self, manual: bool = False) -> None:
        """Disconnect from the device.

        Args:
            manual: The user asked to disconnect (e.g. to use the SVS app), so
                keep-alive must not reconnect until the next command.
        """
        async with self._command_lock:
            self._cancel_idle_disconnect()
            if manual:
                self._manual_disconnect = True
            await self._async_drop_connection()

    async def async_reconnect(self) -> None:
        """Drop the current connection, reconnect and re-read all settings.

        Raises UpdateFailed if the device cannot be reached.
        """
        async with self._command_lock:
            await self._async_drop_connection()
            await self._connect()
            self._schedule_idle_disconnect()
        self._start_keep_alive()

    async def async_shutdown(self) -> None:
        """Stop background tasks and disconnect when the entry unloads."""
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None
        await self.async_disconnect()
        await super().async_shutdown()

    async def async_request_refresh_data(self) -> None:
        """Request a refresh of all data from the subwoofer."""
        if self._connected:
            await self._request_full_settings()
