"""Constants for SVS Subwoofer integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "svs_subwoofer"

# Configuration keys
CONF_MAC_ADDRESS: Final = "mac_address"

# BLE Constants
SVS_SERVICE_UUID: Final = "1fee6acf-a826-4e37-9635-4d8a01642c5d"
SVS_CHAR_UUID: Final = "6409d79d-cd28-479c-a639-92f9e1948b43"

# Parameter limits - Volume
VOLUME_MIN: Final = -60
VOLUME_MAX: Final = 0
VOLUME_STEP: Final = 1

# Parameter limits - Phase
PHASE_MIN: Final = 0
PHASE_MAX: Final = 180
PHASE_STEP: Final = 1

# Parameter limits - Low Pass Filter
LPF_FREQ_MIN: Final = 30
LPF_FREQ_MAX: Final = 200
LPF_FREQ_STEP: Final = 1
LPF_SLOPES: Final = [6, 12, 18, 24]

# Parameter limits - Parametric EQ
PEQ_FREQ_MIN: Final = 20
PEQ_FREQ_MAX: Final = 200
PEQ_FREQ_STEP: Final = 1
PEQ_BOOST_MIN: Final = -12.0
PEQ_BOOST_MAX: Final = 6.0
PEQ_BOOST_STEP: Final = 0.1
PEQ_Q_MIN: Final = 0.2
PEQ_Q_MAX: Final = 10.0
PEQ_Q_STEP: Final = 0.1

# Parameter limits - Room Gain
ROOM_GAIN_FREQUENCIES: Final = [25, 31, 40]
ROOM_GAIN_SLOPES: Final = [6, 12]

# Standby modes
STANDBY_MODES: Final = ["Auto ON", "Trigger", "ON"]
STANDBY_MODE_MAP: Final = {"Auto ON": 0, "Trigger": 1, "ON": 2}

# Presets
PRESETS: Final = ["Preset 1", "Preset 2", "Preset 3", "Default"]
PRESET_MAP: Final = {"Preset 1": 1, "Preset 2": 2, "Preset 3": 3, "Default": 4}

# Command rate limiting (seconds)
COMMAND_DELAY: Final = 0.2
