"""DataUpdateCoordinator for SVS Subwoofer."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SVS_CHAR_UUID, COMMAND_DELAY
from .svs_protocol import svs_encode, FrameAssembler

_LOGGER = logging.getLogger(__name__)

# Connection timeout in seconds
CONNECTION_TIMEOUT = 60.0

# Number of connection retry attempts
MAX_CONNECT_RETRIES = 3
RETRY_DELAY = 2.0

# Auto-disconnect after idle (seconds)
IDLE_DISCONNECT_TIMEOUT = 60.0


class SVSSubwooferCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for SVS Subwoofer BLE communication."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance.
            address: BLE MAC address of the subwoofer.
            name: User-friendly name for the device.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"SVS Subwoofer {name}",
            # No update_interval - push-based via BLE notifications
        )
        self.address = address
        self.device_name = name
        self._client: BleakClient | None = None
        self._frame_assembler = FrameAssembler()
        self._connected = False
        self._command_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._idle_disconnect_task: asyncio.Task | None = None

        # Initialize data with defaults
        self.data: dict[str, Any] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the subwoofer."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=self.device_name,
            manufacturer="SVS",
            model="SB-1000 Pro",
        )

    def _schedule_idle_disconnect(self) -> None:
        """Schedule disconnection after idle timeout."""
        self._cancel_idle_disconnect()
        self._idle_disconnect_task = self.hass.async_create_task(
            self._idle_disconnect_timer()
        )

    def _cancel_idle_disconnect(self) -> None:
        """Cancel any pending idle disconnect."""
        if self._idle_disconnect_task:
            self._idle_disconnect_task.cancel()
            self._idle_disconnect_task = None

    async def _idle_disconnect_timer(self) -> None:
        """Wait for idle timeout then disconnect."""
        try:
            await asyncio.sleep(IDLE_DISCONNECT_TIMEOUT)
            if self._connected:
                _LOGGER.debug(
                    "Idle timeout reached, disconnecting from %s", self.address
                )
                await self.async_disconnect()
        except asyncio.CancelledError:
            pass  # Timer was cancelled, no action needed

    async def _async_setup(self) -> None:
        """Set up the coordinator - called during first refresh."""
        await self._connect()
        # Request initial state
        await self._request_full_settings()
        # Start idle disconnect timer
        self._schedule_idle_disconnect()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device.

        This is called by the coordinator framework but we use push-based
        updates via BLE notifications, so we just return current data.
        """
        if not self._connected:
            await self._connect()
            await self._request_full_settings()
            self._schedule_idle_disconnect()
        return self.data

    async def _connect(self) -> None:
        """Establish BLE connection with notifications."""
        if self._connected and self._client and self._client.is_connected:
            return

        last_error: Exception | None = None

        for attempt in range(MAX_CONNECT_RETRIES):
            # Get fresh BLE device reference each attempt
            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if not ble_device:
                _LOGGER.warning(
                    "Device %s not found (attempt %d/%d). "
                    "Ensure subwoofer is powered on and not connected to another device.",
                    self.address, attempt + 1, MAX_CONNECT_RETRIES
                )
                if attempt < MAX_CONNECT_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise UpdateFailed(
                    f"Device {self.address} not found. "
                    "Check that the subwoofer is powered on and the SVS app is disconnected."
                )

            _LOGGER.debug(
                "Connecting to SVS Subwoofer at %s (attempt %d/%d)",
                self.address, attempt + 1, MAX_CONNECT_RETRIES
            )

            try:
                # Create fresh client for each attempt
                self._client = BleakClient(
                    ble_device,
                    disconnected_callback=self._on_disconnect,
                )
                await asyncio.wait_for(
                    self._client.connect(),
                    timeout=CONNECTION_TIMEOUT
                )
                await self._client.start_notify(SVS_CHAR_UUID, self._notification_handler)
                self._connected = True
                _LOGGER.info("Connected to SVS Subwoofer at %s", self.address)
                return
            except asyncio.TimeoutError as err:
                last_error = err
                _LOGGER.warning(
                    "Timeout connecting to %s (attempt %d/%d)",
                    self.address, attempt + 1, MAX_CONNECT_RETRIES
                )
            except BleakError as err:
                last_error = err
                _LOGGER.warning(
                    "BLE error connecting to %s: %s (attempt %d/%d)",
                    self.address, err, attempt + 1, MAX_CONNECT_RETRIES
                )

            # Clean up failed client
            if self._client:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
                self._client = None

            if attempt < MAX_CONNECT_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        # All retries failed
        raise UpdateFailed(
            f"Failed to connect to {self.address} after {MAX_CONNECT_RETRIES} attempts: {last_error}"
        )

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from device."""
        _LOGGER.warning("Disconnected from SVS Subwoofer at %s", self.address)
        self._connected = False
        self._frame_assembler.reset()

    @callback
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle incoming BLE notifications.

        Args:
            sender: Characteristic handle.
            data: Notification data.
        """
        decoded = self._frame_assembler.add_data(bytes(data))

        if decoded and decoded.get("FRAME_RECOGNIZED"):
            validated = decoded.get("VALIDATED_VALUES", {})
            if validated:
                # Update our data store
                self.data.update(validated)
                _LOGGER.debug("Updated data: %s", validated)
                # Notify listeners of new data
                self.async_set_updated_data(self.data)

    async def async_send_command(
        self, param: str, value: Any
    ) -> bool:
        """Send a command to the subwoofer.

        Args:
            param: Parameter name (e.g., "VOLUME", "PHASE").
            value: Value to set.

        Returns:
            True if command was sent successfully.
        """
        async with self._command_lock:
            if not self._connected:
                try:
                    await self._connect()
                except UpdateFailed:
                    _LOGGER.error("Failed to reconnect for command")
                    return False

            if not self._client:
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
                # Reset idle disconnect timer
                self._schedule_idle_disconnect()
                return True
            except BleakError as err:
                _LOGGER.error("Failed to send command: %s", err)
                self._connected = False
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
            if not self._connected:
                try:
                    await self._connect()
                except UpdateFailed:
                    return False

            if not self._client:
                return False

            frame, meta = svs_encode("PRESETLOADSAVE", f"PRESET{preset_number}LOAD")
            if not frame:
                return False

            try:
                _LOGGER.debug("Loading preset: %s", meta)
                await self._client.write_gatt_char(SVS_CHAR_UUID, frame)
                await asyncio.sleep(COMMAND_DELAY)

                # After loading preset, request current settings
                await self._request_full_settings()
                # Reset idle disconnect timer
                self._schedule_idle_disconnect()
                return True
            except BleakError as err:
                _LOGGER.error("Failed to load preset: %s", err)
                self._connected = False
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

    async def async_disconnect(self) -> None:
        """Disconnect from the device."""
        self._cancel_idle_disconnect()
        async with self._disconnect_lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.disconnect()
                except BleakError:
                    pass
            self._connected = False
            self._client = None
            _LOGGER.debug("Disconnected from SVS Subwoofer at %s", self.address)

    async def async_request_refresh_data(self) -> None:
        """Request a refresh of all data from the subwoofer."""
        if self._connected:
            await self._request_full_settings()
