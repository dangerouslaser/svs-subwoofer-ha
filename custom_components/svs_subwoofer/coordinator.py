"""DataUpdateCoordinator for SVS Subwoofer."""

from __future__ import annotations

import asyncio
import logging
import re
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
    QUIET_KEEP_ALIVE_CHAR_UUIDS,
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

# At shutdown, how long to wait for a connection in progress to finish before
# the background loops are stopped anyway (seconds)
SHUTDOWN_WAIT = 10.0

# Waits between automatic reconnects while a subwoofer keeps not answering
# (seconds). The first reconnect is immediate; the last delay repeats.
RECONNECT_BACKOFF = (30.0, 60.0, 120.0, 300.0)

# Two letters directly followed by four digits, such as "SB3000"
_SERIES_MODEL = re.compile(r"^([A-Za-z]{2})(\d{4})(?!\d)")


class SVSSubwooferCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for SVS Subwoofer BLE communication."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        address: str,
        name: str,
        keep_alive: bool = False,
        quiet_keep_alive: bool = False,
        idle_timeout: float = IDLE_DISCONNECT_TIMEOUT,
        refresh_interval: float = 0,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance.
            entry_id: ID of the config entry that owns this device.
            address: BLE MAC address of the subwoofer.
            name: User-friendly name for the device.
            keep_alive: Stay connected and probe the link instead of
                disconnecting when idle.
            quiet_keep_alive: Stay connected (Quiet connection): keep the link
                busy with a standard Bluetooth read that does not reach the SVS
                control software. The connection option sets at most one of
                keep_alive and quiet_keep_alive.
            idle_timeout: Periodic connection: seconds without commands
                before disconnecting.
            refresh_interval: Periodic connection: seconds between brief
                connections that refresh the settings while disconnected;
                0 only connects when a command is sent.
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
        self._quiet_keep_alive = quiet_keep_alive
        self._quiet_keep_alive_task: asyncio.Task | None = None
        # Field read by the Quiet connection, chosen once per connection
        # (None: the sub offers none, so the settings check is used)
        self._quiet_char: str | None = None
        self._quiet_char_client: BleakClient | None = None
        # The sub offering no such field is a warning once, not at every connection
        self._quiet_char_warned = False
        self._idle_timeout = idle_timeout
        self._refresh_interval = refresh_interval
        self._refresh_task: asyncio.Task | None = None
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
        # The sub has answered on the current connection. A sub can accept a
        # connection and then never answer, so this, not the link, is what
        # counts as connected.
        self._responsive = False
        # Consecutive connections on which the sub did not answer, and when
        # the keep-alive loop may next reconnect automatically
        self._silent_attempts = 0
        self._retry_at = 0.0

        # Settings are only present once the subwoofer has reported them, so
        # entities show unknown instead of made-up values until the first read
        self.data: dict[str, Any] = {
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
        # No model here: the sub reports its own model name, and leaving it out
        # keeps the last reported model instead of resetting it on every start
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            connections={(dr.CONNECTION_BLUETOOTH, self.address)},
            name=self.device_name,
            manufacturer="SVS",
        )

    @property
    def is_connected(self) -> bool:
        """Return True if connected and the subwoofer is answering."""
        return self._connected and self._responsive

    def _note_silence(self) -> None:
        """Record that the sub did not answer, and schedule the next attempt."""
        self._silent_attempts += 1
        if self._silent_attempts == 1:
            self._retry_at = 0.0
            _LOGGER.warning(
                "SVS Subwoofer at %s stopped responding, reconnecting", self.address
            )
            return
        delay = RECONNECT_BACKOFF[
            min(self._silent_attempts - 2, len(RECONNECT_BACKOFF) - 1)
        ]
        self._retry_at = time.monotonic() + delay
        _LOGGER.warning(
            "SVS Subwoofer at %s is still not responding, next automatic attempt "
            "in %d seconds",
            self.address,
            delay,
        )

    def _schedule_idle_disconnect(self) -> None:
        """Schedule disconnection after idle timeout.

        Caller must hold _command_lock, so the timer can never be cancelled
        part-way through its own disconnect.
        """
        self._cancel_idle_disconnect()
        if self._keep_alive or self._quiet_keep_alive:
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
        await asyncio.sleep(self._idle_timeout)
        _LOGGER.debug("Idle timeout reached, disconnecting from %s", self.address)
        await self.async_disconnect()

    def _start_keep_alive(self) -> None:
        """Start each enabled keep-alive loop that is not already running."""
        if self._keep_alive and not self._keep_alive_task:
            self._keep_alive_task = self.hass.async_create_background_task(
                self._keep_alive_loop(), f"svs_subwoofer keep-alive {self.address}"
            )
        if self._quiet_keep_alive and not self._quiet_keep_alive_task:
            self._quiet_keep_alive_task = self.hass.async_create_background_task(
                self._quiet_keep_alive_loop(),
                f"svs_subwoofer quiet connection {self.address}",
            )
        if (
            self._refresh_interval > 0
            and not (self._keep_alive or self._quiet_keep_alive)
            and not self._refresh_task
        ):
            self._refresh_task = self.hass.async_create_background_task(
                self._refresh_loop(),
                f"svs_subwoofer periodic connection {self.address}",
            )

    async def _refresh_loop(self) -> None:
        """Periodic connection: briefly reconnect to refresh the settings.

        Connecting reads all settings; the idle timer then disconnects again.
        Nothing is done while a connection is already open.
        """
        while True:
            await asyncio.sleep(self._refresh_interval)
            if self._manual_disconnect or time.monotonic() < self._retry_at:
                continue
            async with self._command_lock:
                if self._connected:
                    continue
                try:
                    await self._ensure_live(user_initiated=False)
                except UpdateFailed as err:
                    _LOGGER.debug(
                        "Periodic connection to %s failed: %s", self.address, err
                    )
                    continue
                # A sub can accept the connection and then not answer: that is
                # silence, so these reconnects back off as Constant's do
                if not await self._async_wait_responsive():
                    await self._async_drop_connection()
                    self._note_silence()
                    continue
                _LOGGER.debug("Periodic connection refreshed %s", self.address)
                self._schedule_idle_disconnect()

    async def _async_wait_responsive(self) -> bool:
        """Wait for the sub to answer on this connection, up to PROBE_TIMEOUT."""
        deadline = time.monotonic() + PROBE_TIMEOUT
        while not self._responsive and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        return self._responsive

    async def _quiet_keep_alive_loop(self) -> None:
        """Keep the link busy with a read that does not wake the panel LEDs.

        Only the Bluetooth link is checked here; whether the SVS control
        software still answers is checked before each command instead.
        """
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            if self._manual_disconnect or time.monotonic() < self._retry_at:
                continue
            async with self._command_lock:
                if not (self._connected and self._client and self._client.is_connected):
                    try:
                        await self._ensure_live(user_initiated=False)
                    except UpdateFailed as err:
                        _LOGGER.debug(
                            "Quiet connection: reconnect to %s failed: %s",
                            self.address,
                            err,
                        )
                    continue
                if self._quiet_char_client is not self._client:
                    self._quiet_char_client = self._client
                    self._quiet_char = self._select_quiet_characteristic()
                if self._quiet_char is None:
                    # Nothing quiet to read: check the way Constant does
                    try:
                        await self._ensure_live(user_initiated=False)
                    except UpdateFailed as err:
                        _LOGGER.debug(
                            "Quiet connection: check of %s failed: %s",
                            self.address,
                            err,
                        )
                    continue
                try:
                    await asyncio.wait_for(
                        self._client.read_gatt_char(self._quiet_char),
                        PROBE_TIMEOUT,
                    )
                except (BleakError, KeyError, TimeoutError) as err:
                    _LOGGER.warning(
                        "Quiet connection: read from %s failed (%s), reconnecting",
                        self.address,
                        err or type(err).__name__,
                    )
                    await self._async_drop_connection()
                    self._note_silence()
                    continue
                _LOGGER.debug("Quiet connection: read from %s succeeded", self.address)

    def _select_quiet_characteristic(self) -> str | None:
        """Return the first standard field this sub offers as readable."""
        try:
            services = self._client.services
        except BleakError:
            services = None
        for uuid in QUIET_KEEP_ALIVE_CHAR_UUIDS:
            try:
                char = services.get_characteristic(uuid) if services else None
            except BleakError:
                char = None
            if char is not None and "read" in char.properties:
                _LOGGER.debug(
                    "Quiet connection: reading %s from %s", uuid, self.address
                )
                return uuid
        log = _LOGGER.debug if self._quiet_char_warned else _LOGGER.warning
        self._quiet_char_warned = True
        log(
            "Quiet connection: %s offers no standard readable field, so it is "
            "checked with a settings request instead (as with Constant), which "
            "lights the panel LEDs",
            self.address,
        )
        return None

    async def _keep_alive_loop(self) -> None:
        """Keep the link busy and reconnect if it has silently died."""
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            # Back off while the sub keeps not answering, so endless
            # reconnects do not load the sub or a shared Bluetooth proxy
            if self._manual_disconnect or time.monotonic() < self._retry_at:
                continue
            async with self._command_lock:
                try:
                    await self._ensure_live(user_initiated=False)
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
        self._responsive = False
        self._manual_disconnect = False
        _LOGGER.info("Connected to SVS Subwoofer at %s", self.address)
        # Settings may have changed while we were away (e.g. via the SVS app).
        # The first answer marks the sub as connected; see
        # _notification_handler.
        await self._request_full_settings(versions=True)

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
        was_responsive = self._responsive
        self._connected = False
        self._responsive = False
        await self._async_release_client()
        if was_connected:
            _LOGGER.debug("Disconnected from SVS Subwoofer at %s", self.address)
            self.async_set_updated_data(self.data)
        if was_responsive:
            self._fire_event(TRIGGER_TYPE_DISCONNECTED)

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from device."""
        if client is not self._client:
            # Callback from a client we already released
            return
        _LOGGER.warning("Disconnected from SVS Subwoofer at %s", self.address)
        was_responsive = self._responsive
        self._connected = False
        self._responsive = False
        self._client = None
        self._frame_assembler.reset()
        # Notify listeners of connection state change
        self.async_set_updated_data(self.data)
        # Fire disconnected event for device automations, if connected was fired
        if was_responsive:
            self._fire_event(TRIGGER_TYPE_DISCONNECTED)

    @callback
    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle incoming BLE notifications."""
        self._last_rx = time.monotonic()
        self._rx_event.set()
        if not self._responsive:
            # First answer on this connection: the sub is really connected
            self._responsive = True
            self._silent_attempts = 0
            self._retry_at = 0.0
            _LOGGER.info("SVS Subwoofer at %s is responding", self.address)
            self.async_set_updated_data(self.data)
            # Fire connected event for device automations
            self._fire_event(TRIGGER_TYPE_CONNECTED)
        for decoded in self._frame_assembler.add_data(bytes(data)):
            validated = decoded.get("VALIDATED_VALUES", {})
            if validated:
                # Update our data store
                self.data.update(validated)
                _LOGGER.debug("Updated data from %s: %s", self.address, validated)
                self._update_device_versions(validated)
                # Notify listeners of new data
                self.async_set_updated_data(self.data)

    def _update_device_versions(self, values: dict[str, Any]) -> None:
        """Show the reported firmware version and model on the device."""
        changes: dict[str, str | None] = {}
        if "SW_VERSION" in values:
            changes["sw_version"] = values["SW_VERSION"]
        if "HW_VERSION" in values:
            # The sub's "hardware version" is its model name, such as
            # "SVS SB3000". The manufacturer is shown separately, so drop the
            # brand. It is not a hardware revision, so the hardware version
            # field stays empty.
            model = values["HW_VERSION"].strip()
            brand, _, rest = model.partition(" ")
            if brand.upper() == "SVS":
                model = rest.strip()
            # SVS writes its series models as "SB-3000" or "PB-4000 Pro", but the
            # sub reports "SB3000"; restore the hyphen for that pattern only
            model = _SERIES_MODEL.sub(r"\1-\2", model)
            changes["model"] = model or None
            changes["hw_version"] = None
        self._update_device(changes)

    def _update_device(self, changes: dict[str, str | None]) -> None:
        """Write changed fields to this subwoofer's device registry entry."""
        if not changes:
            return
        device_id = self._get_device_id()
        if device_id:
            dr.async_get(self.hass).async_update_device(device_id, **changes)

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

    async def _ensure_live(self, user_initiated: bool = True) -> None:
        """Make sure there is a responsive connection, reconnecting if needed.

        Caller must hold _command_lock. Raises UpdateFailed if connecting fails,
        or if an automatic reconnect is not due yet because the sub keeps not
        answering. A user action (a command or the Reconnect button) always
        tries immediately.
        """
        if self._connected and self._client and self._client.is_connected:
            if time.monotonic() - self._last_rx < LIVENESS_STALE_AFTER:
                return
            if await self._async_probe():
                return
            await self._async_drop_connection()
            self._note_silence()
            if not user_initiated and time.monotonic() < self._retry_at:
                raise UpdateFailed(f"{self.address} is not responding, backing off")
        try:
            await self._connect()
        except UpdateFailed:
            self._note_silence()
            raise

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

    async def _request_full_settings(self, versions: bool = False) -> None:
        """Request all settings from subwoofer.

        Args:
            versions: Also request the firmware and hardware versions.
        """
        if not self._client or not self._connected:
            return

        requests = [
            ("MEMREAD", "FULL_SETTINGS"),
            ("MEMREAD", "PRESET1NAME"),
            ("MEMREAD", "PRESET2NAME"),
            ("MEMREAD", "PRESET3NAME"),
        ]
        if versions:
            requests += [("SUB_INFO2", ""), ("SUB_INFO3", "")]

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
        # The loops connect only while holding the command lock. Stopping them
        # while it is held here means none is part-way through connecting: a
        # cancelled connect could leave a connection open that nothing closes,
        # which would lock the SVS app out.
        try:
            async with asyncio.timeout(SHUTDOWN_WAIT):
                await self._command_lock.acquire()
            locked = True
        except TimeoutError:
            locked = False
        tasks = [
            task
            for task in (
                self._keep_alive_task,
                self._quiet_keep_alive_task,
                self._refresh_task,
            )
            if task
        ]
        self._keep_alive_task = self._quiet_keep_alive_task = self._refresh_task = None
        for task in tasks:
            task.cancel()
        if locked:
            self._command_lock.release()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.async_disconnect()
        await super().async_shutdown()

    async def async_request_refresh_data(self) -> None:
        """Request a refresh of all data from the subwoofer."""
        if self._connected:
            await self._request_full_settings()
