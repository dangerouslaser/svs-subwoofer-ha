"""Tests for splitting notifications into frames and decoder alignment (PR 8)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.svs_subwoofer.svs_protocol import FrameAssembler, svs_decode

from .conftest import (
    DEFAULT_SETTINGS,
    LAYOUT,
    FakeSubwoofer,
    SetupEntry,
    build_frame,
    encode_value,
    entity_id,
    read_response,
)


async def test_settings_read_with_real_packing(
    hass: HomeAssistant, sub: FakeSubwoofer, setup_entry: SetupEntry
) -> None:
    """Frames packed back to back, as a real SB3000 sends them, are all read."""
    sub.packing = "real"
    sub.settings["VOLUME"] = -18
    await setup_entry()
    assert hass.states.get(entity_id(hass, "number", "volume")).state == "-18.0"
    options = hass.states.get(entity_id(hass, "select", "preset")).attributes["options"]
    assert options[:3] == ["HIGH", "MEDIUM", "LOW"]


def test_every_split_of_two_packed_frames() -> None:
    """Two frames sharing notifications decode at every split point."""
    settings = b"".join(encode_value(DEFAULT_SETTINGS[name]) for name in LAYOUT)
    stream = read_response(4, 0, settings) + read_response(4, 4, encode_value(2))
    for cut in range(1, len(stream)):
        frames = []
        assembler = FrameAssembler()
        for chunk in (stream[:cut], stream[cut:]):
            frames += assembler.add_data(chunk)
        assert [len(frame["VALIDATED_VALUES"]) for frame in frames] == [26, 1], cut


def test_garbage_before_a_frame_is_skipped() -> None:
    """Bytes that do not start a frame are discarded."""
    frame = read_response(4, 44, encode_value(-15))
    assert FrameAssembler().add_data(b"\x01\x02" + frame)[0]["VALIDATED_VALUES"] == {
        "VOLUME": -15
    }


def test_out_of_range_value_does_not_shift_the_others() -> None:
    """One rejected value is dropped; the values after it still decode."""
    values = dict(DEFAULT_SETTINGS) | {"DISPLAY": 999}
    data = b"".join(encode_value(values[name]) for name in LAYOUT)
    decoded = svs_decode(read_response(4, 0, data))["VALIDATED_VALUES"]
    assert "DISPLAY" not in decoded
    assert decoded["VOLUME"] == DEFAULT_SETTINGS["VOLUME"]
    assert decoded["PORTTUNING"] == DEFAULT_SETTINGS["PORTTUNING"]
    assert len(decoded) == 25


def test_frame_builder_matches_decoder() -> None:
    """The test helpers produce frames the integration accepts (sanity check)."""
    assert svs_decode(build_frame(b"\xf2\x00", b"\x00" * 3))["FRAME_RECOGNIZED"]
