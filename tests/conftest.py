"""Shared fixtures: a fake SVS subwoofer speaking the real BLE protocol."""

from __future__ import annotations

import asyncio
from binascii import crc_hqx
from collections.abc import AsyncGenerator, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.svs_subwoofer import coordinator as coordinator_module
from custom_components.svs_subwoofer.const import DOMAIN

ADDRESS = "54:B7:E5:82:D1:E2"
NAME = "Test Sub"

SERIAL_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
MODEL_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
MANUFACTURER_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

# Memory ID 4, in offset order: 26 two-byte values (52 bytes)
LAYOUT = [
    "DISPLAY",
    "DISPLAY_TIMEOUT",
    "STANDBY",
    "BRIGHTNESS",
    "LOW_PASS_FILTER_ENABLE",
    "LOW_PASS_FILTER_FREQ",
    "LOW_PASS_FILTER_SLOPE",
    "PEQ1_ENABLE",
    "PEQ1_FREQ",
    "PEQ1_BOOST",
    "PEQ1_QFACTOR",
    "PEQ2_ENABLE",
    "PEQ2_FREQ",
    "PEQ2_BOOST",
    "PEQ2_QFACTOR",
    "PEQ3_ENABLE",
    "PEQ3_FREQ",
    "PEQ3_BOOST",
    "PEQ3_QFACTOR",
    "ROOM_GAIN_ENABLE",
    "ROOM_GAIN_FREQ",
    "ROOM_GAIN_SLOPE",
    "VOLUME",
    "PHASE",
    "POLARITY",
    "PORTTUNING",
]

# Values reported by a real SB3000
DEFAULT_SETTINGS: dict[str, float] = {
    "DISPLAY": 0,
    "DISPLAY_TIMEOUT": 10,
    "STANDBY": 2,
    "BRIGHTNESS": 2,
    "LOW_PASS_FILTER_ENABLE": 0,
    "LOW_PASS_FILTER_FREQ": 80,
    "LOW_PASS_FILTER_SLOPE": 12,
    "PEQ1_ENABLE": 0,
    "PEQ1_FREQ": 50,
    "PEQ1_BOOST": 0,
    "PEQ1_QFACTOR": 1.0,
    "PEQ2_ENABLE": 0,
    "PEQ2_FREQ": 50,
    "PEQ2_BOOST": 0,
    "PEQ2_QFACTOR": 1.0,
    "PEQ3_ENABLE": 0,
    "PEQ3_FREQ": 50,
    "PEQ3_BOOST": 0,
    "PEQ3_QFACTOR": 1.0,
    "ROOM_GAIN_ENABLE": 0,
    "ROOM_GAIN_FREQ": 25,
    "ROOM_GAIN_SLOPE": 12,
    "VOLUME": -15,
    "PHASE": 0,
    "POLARITY": 0,
    "PORTTUNING": 20,
}

PRESET_NAMES = ["HIGH", "MEDIUM", "LOW"]
# Preset number -> volume; presets differ only in volume, as on the test subs
PRESET_VOLUMES = {1: -10, 2: -15, 3: -20, 4: -25}


def encode_value(value: float) -> bytes:
    """Encode one numeric value the way the subwoofer does."""
    mask = 0 if value >= 0 else 0xFFFF
    return ((round(10 * abs(value)) ^ mask) + (mask % 2)).to_bytes(2, "little")


def decode_value(raw: bytes) -> float:
    """Decode one numeric value written to the subwoofer."""
    number = int.from_bytes(raw, "little")
    mask = 0 if number < 0xF000 else 0xFFFF
    value = ((-1) ** (mask % 2)) * ((number - (mask % 2)) ^ mask) / 10
    return int(value) if value == int(value) else value


def build_frame(frame_type: bytes, payload: bytes) -> bytes:
    """Wrap a payload in preamble, type, length, and CRC."""
    head = b"\xaa" + frame_type + (len(payload) + 7).to_bytes(2, "little") + payload
    return head + crc_hqx(head, 0).to_bytes(2, "little")


def read_response(memory_id: int, offset: int, data: bytes) -> bytes:
    """Build a READ_RESP frame."""
    payload = (
        b"\xc4\x00\x00\x20"
        + memory_id.to_bytes(4, "little")
        + offset.to_bytes(2, "little")
        + len(data).to_bytes(2, "little")
        + data
    )
    return build_frame(b"\xf2\x00", payload)


class FakeSubwoofer:
    """Behaves like an SVS SB3000 over BLE, as observed on real hardware.

    - A full settings read is answered with the settings frame followed by a
      separate standby frame, packed back to back into 20-byte notifications
      (packing="real"), or each frame in its own notifications ("separate")
    - Loading a preset applies it and pushes offsets 0x08 to 0x33 unasked
    - Writes are applied but not echoed
    - silent=True accepts the connection and answers nothing
    - ignore_loads=N ignores the next N preset loads, as if they were lost
    - lose_names={slot: N} loses the next N name replies for a preset slot
    - refuse_connects=N refuses the next N connections, as if out of range
    - connect_delay=S keeps a connection being set up for S seconds after the
      link is open (as discovering its services does)
    - fail_loads=N fails the next N preset load writes, as a lost link would
    - fail_writes=N fails the next N setting writes, as a lost link would
    - drop_after_writes=N drops the link on the Nth write from now, failing
      that write, as a sub that goes away part-way through a read does
    - late_replies=S delivers a read's reply after its first fragment S seconds
      late, as a slow link does (the probe before a command can then still be
      answering when the command goes out)
    """

    def __init__(self) -> None:
        self.settings = dict(DEFAULT_SETTINGS)
        self.preset_names = list(PRESET_NAMES)
        self.presets = {
            number: dict(DEFAULT_SETTINGS) | {"VOLUME": volume}
            for number, volume in PRESET_VOLUMES.items()
        }
        self.sw_version = "5.0.9"
        self.hw_version = "SVS SB3000"
        self.device_info: dict[str, bytes] = {
            SERIAL_UUID: b"SB3KD1E2",
            MANUFACTURER_UUID: b"SVS",
        }
        self.packing = "separate"
        self.silent = False
        self.ignore_loads = 0
        self.lose_names: dict[int, int] = {}
        self.refuse_connects = 0
        self.connect_delay = 0.0
        self.fail_loads = 0
        self.fail_writes = 0
        self.drop_after_writes = 0
        self.late_replies = 0.0
        self.client: FakeBleakClient | None = None
        self.connects = 0
        self.received: list[bytes] = []
        self.info_reads: list[str] = []

    def settings_bytes(self, start: int = 0, end: int = 52) -> bytes:
        """Return memory ID 4 between two offsets."""
        data = b"".join(encode_value(self.settings[name]) for name in LAYOUT)
        return data[start:end]

    def frame_types(self) -> list[str]:
        """Return the type bytes (hex) of every frame received."""
        return [frame[1:3].hex() for frame in self.received]

    def handle(self, frame: bytes) -> list[bytes]:
        """Process one frame from Home Assistant; return the reply frames."""
        self.received.append(frame)
        if self.silent:
            return []
        frame_type, body = frame[1:3], frame[5:-2]
        if frame_type == b"\xf1\x1f":  # MEMREAD
            memory_id = int.from_bytes(body[0:4], "little")
            offset = int.from_bytes(body[4:6], "little")
            size = int.from_bytes(body[6:8], "little")
            if memory_id == 4:
                replies = [
                    read_response(4, offset, self.settings_bytes(offset, offset + size))
                ]
                if offset == 0 and size == 52:
                    # The real sub follows a full read with a standby frame
                    replies.append(
                        read_response(4, 4, encode_value(self.settings["STANDBY"]))
                    )
                return replies
            if 8 <= memory_id <= 10:
                slot = memory_id - 7
                if self.lose_names.get(slot):
                    self.lose_names[slot] -= 1
                    return []
                name = self.preset_names[memory_id - 8].encode().ljust(8, b"\x00")
                return [read_response(memory_id, 0, name)]
            return []
        if frame_type == b"\xf0\x1f":  # MEMWRITE
            memory_id = int.from_bytes(body[0:4], "little")
            offset = int.from_bytes(body[4:6], "little")
            if memory_id == 4:
                self.settings[LAYOUT[offset // 2]] = decode_value(body[8:10])
            elif 8 <= memory_id <= 10:
                self.preset_names[memory_id - 8] = body[8:16].rstrip(b"\x00").decode()
            return []
        if frame_type == b"\x07\x04":  # PRESETLOADSAVE
            memory_id = int.from_bytes(body[0:4], "little")
            if 0x18 <= memory_id <= 0x1B:
                if self.ignore_loads:
                    self.ignore_loads -= 1
                    return []
                self.settings |= {
                    name: value
                    for name, value in self.presets[memory_id - 0x17].items()
                    if LAYOUT.index(name) >= 4
                }
                return [read_response(4, 8, self.settings_bytes(8, 52))]
            if 0x1C <= memory_id <= 0x1E:
                self.presets[memory_id - 0x1B] = dict(self.settings)
            return []
        if frame_type == b"\xfc\x1f":  # SUB_INFO2: software version
            text = self.sw_version.encode()
            return [
                build_frame(
                    b"\xfd\x00", b"\xc4\x00\x00\x20" + bytes([len(text)]) + text
                )
            ]
        if frame_type == b"\xfe\x1f":  # SUB_INFO3: model name
            text = self.hw_version.encode()
            return [
                build_frame(
                    b"\xff\x00", b"\xc4\x00\x00\x20" + bytes([len(text)]) + text
                )
            ]
        return []

    def notifications(self, frames: list[bytes]) -> list[bytes]:
        """Split reply frames into 20-byte BLE notifications."""
        if self.packing == "real":
            stream = b"".join(frames)
            return [stream[i : i + 20] for i in range(0, len(stream), 20)]
        return [frame[i : i + 20] for frame in frames for i in range(0, len(frame), 20)]


class FakeBleakClient:
    """Minimal BleakClient stand-in backed by a FakeSubwoofer."""

    def __init__(
        self, sub: FakeSubwoofer, disconnected_callback: Callable | None
    ) -> None:
        self.sub = sub
        self.is_connected = True
        self.disconnected_callback = disconnected_callback
        self.callback: Callable | None = None
        self.services = SimpleNamespace(get_characteristic=self._get_characteristic)

    def _get_characteristic(self, uuid: str) -> Any:
        if uuid in self.sub.device_info:
            return SimpleNamespace(uuid=uuid, properties=["read"])
        return None

    async def start_notify(self, uuid: str, callback: Callable) -> None:
        self.callback = callback

    async def write_gatt_char(
        self, uuid: str, data: bytes, response: bool = False
    ) -> None:
        if not self.is_connected:
            raise BleakError("Not connected")
        frame = bytes(data)
        if self.sub.drop_after_writes:
            self.sub.drop_after_writes -= 1
            if not self.sub.drop_after_writes:
                await self.disconnect()
                raise BleakError("GATT Protocol Error: Unlikely Error")
        if (
            self.sub.fail_loads
            and frame[1:3] == b"\x07\x04"
            and 0x18 <= int.from_bytes(frame[5:9], "little") <= 0x1B
        ):
            self.sub.fail_loads -= 1
            raise BleakError("The fake subwoofer's link failed")
        if self.sub.fail_writes and frame[1:3] == b"\xf0\x1f":
            self.sub.fail_writes -= 1
            raise BleakError("The fake subwoofer's link failed")
        loop = asyncio.get_running_loop()
        chunks = self.sub.notifications(self.sub.handle(frame))
        late = self.sub.late_replies and frame[1:3] == b"\xf1\x1f"
        for number, chunk in enumerate(chunks):
            if late and number:
                loop.call_later(self.sub.late_replies, self._notify, chunk)
            else:
                loop.call_soon(self._notify, chunk)

    def _notify(self, chunk: bytes) -> None:
        if self.is_connected and self.callback:
            self.callback(None, bytearray(chunk))

    async def read_gatt_char(self, uuid: str) -> bytearray:
        if not self.is_connected:
            raise BleakError("Not connected")
        self.sub.info_reads.append(uuid)
        if uuid not in self.sub.device_info:
            raise BleakError(f"Characteristic {uuid} not found")
        return bytearray(self.sub.device_info[uuid])

    async def disconnect(self) -> bool:
        if self.is_connected:
            self.is_connected = False
            if self.disconnected_callback:
                self.disconnected_callback(self)
        return True


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Load integrations from custom_components in every test."""


@pytest.fixture
def fake_subs() -> dict[str, FakeSubwoofer]:
    """The fake subwoofers in range, by address."""
    return {}


@pytest.fixture
def sub(fake_subs: dict[str, FakeSubwoofer]) -> FakeSubwoofer:
    """A fresh fake subwoofer at ADDRESS."""
    fake_subs[ADDRESS] = FakeSubwoofer()
    return fake_subs[ADDRESS]


SetupEntry = Callable[..., Any]


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant,
    sub: FakeSubwoofer,
    fake_subs: dict[str, FakeSubwoofer],
) -> AsyncGenerator[SetupEntry]:
    """Set up config entries wired to the fake subwoofer; unload them afterwards."""
    # The Bluetooth integration itself is not needed: the connection is faked
    hass.config.components.add("bluetooth")
    entries: list[MockConfigEntry] = []

    async def fake_establish_connection(
        client_class: Any,
        device: Any,
        name: str,
        disconnected_callback=None,
        **kwargs: Any,
    ) -> FakeBleakClient:
        fake = fake_subs[device.address]
        if fake.refuse_connects:
            fake.refuse_connects -= 1
            raise BleakError("The fake subwoofer refused the connection")
        fake.connects += 1
        fake.client = FakeBleakClient(fake, disconnected_callback)
        if fake.connect_delay:
            await asyncio.sleep(fake.connect_delay)
        return fake.client

    with (
        # The real 0.2 s pause between commands only slows the tests down
        patch.object(coordinator_module, "COMMAND_DELAY", 0.01),
        patch.object(
            coordinator_module, "establish_connection", fake_establish_connection
        ),
        patch.object(
            coordinator_module,
            "async_ble_device_from_address",
            side_effect=lambda hass, address, connectable=True: SimpleNamespace(
                address=address, name=NAME
            ),
        ),
    ):

        async def _setup(
            options: dict[str, Any] | None = None,
            address: str = ADDRESS,
            name: str = NAME,
        ) -> MockConfigEntry:
            entry = MockConfigEntry(
                domain=DOMAIN,
                unique_id=address.lower(),
                title=name,
                data={CONF_ADDRESS: address, CONF_NAME: name},
                options=options or {},
            )
            entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(entry.entry_id)
            await settle()
            entries.append(entry)
            return entry

        yield _setup

        for entry in entries:
            # A test may have removed the entry already
            if (
                hass.config_entries.async_get_entry(entry.entry_id)
                and entry.state.recoverable
            ):
                await hass.config_entries.async_unload(entry.entry_id)
        await settle()


async def settle(seconds: float = 0.3) -> None:
    """Let queued notifications and short delays run.

    Real time instead of hass.async_block_till_done(), which would also wait
    for the integration's idle-disconnect timer.
    """
    await asyncio.sleep(seconds)


def entity_id(
    hass: HomeAssistant, platform: str, key: str, address: str = ADDRESS
) -> str:
    """Return the entity ID of one of a subwoofer's entities."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{address}_{key}")
    assert found, f"No {platform} entity with key {key}"
    return found
