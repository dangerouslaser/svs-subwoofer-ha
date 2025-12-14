# SVS Subwoofer Control

Control SVS subwoofers via Bluetooth using the same protocol as the official SVS app.

This repository contains:
1. **Home Assistant Integration** - HACS-compatible custom component
2. **pySVS** - Standalone Python GUI/CLI application by [Logon84](https://github.com/logon84/pySVS)

---

## Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Control your SVS subwoofer directly from Home Assistant with full parameter access.

### Features

- Bluetooth auto-discovery of SVS subwoofers
- Manual MAC address configuration
- Support for multiple subwoofers
- Full parameter control:
  - Volume (-60 to 0 dB)
  - Phase (0-180 degrees)
  - Low Pass Filter (enable, frequency, slope)
  - 3-Band Parametric EQ (frequency, boost, Q-factor)
  - Room Gain Compensation
  - Polarity
  - Presets (1-4)
  - Standby Mode

### Prerequisites

- **Home Assistant Bluetooth Integration** must be configured and working before adding SVS subwoofers
  - Go to **Settings** → **Devices & Services** → **Bluetooth**
  - Ensure your Bluetooth adapter is detected and operational
  - See [Home Assistant Bluetooth documentation](https://www.home-assistant.io/integrations/bluetooth/) for setup help

### Installation

#### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL and select "Integration" as the category
4. Click "Add"
5. Search for "SVS Subwoofer" and install
6. Restart Home Assistant

#### Manual Installation

1. Copy the `custom_components/svs_subwoofer` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

### Configuration

1. **Ensure Bluetooth is working** in Home Assistant (Settings → Devices & Services → Bluetooth)
2. **Disconnect the SVS app** on your phone (the subwoofer only allows one BLE connection)
3. Go to **Settings** → **Devices & Services**
4. Click **Add Integration**
5. Search for "SVS Subwoofer"
6. Either:
   - Select your subwoofer by name from the list (e.g., "RIGHTSUB", "LEFTSUB" - the name you set in the SVS app)
   - Devices marked with `[SVS]` are detected SVS subwoofers
   - Or choose "Enter MAC address manually" if your device isn't showing

### Finding Your Subwoofer

The integration will show all discovered Bluetooth devices by name. Your subwoofers will appear with the names you configured in the SVS app (e.g., "RIGHTSUB", "LEFTSUB").

**Tips for discovery:**
- Open the SVS app on your phone and connect to the subwoofer briefly - this helps activate Bluetooth advertising
- Make sure the subwoofer is powered on and within range
- Disconnect the SVS app before adding to Home Assistant

**Manual MAC address lookup (if needed):**

If you need to find the MAC address manually, you can use `bluetoothctl` on a Linux system:

```bash
bluetoothctl
[bluetooth]# scan on
# Look for your subwoofer by name:
# [NEW] Device 08:EB:ED:63:7E:00 RIGHTSUB
# [NEW] Device 08:EB:ED:69:3E:D0 LEFTSUB
[bluetooth]# scan off
[bluetooth]# exit
```

SVS subwoofers have MAC addresses starting with `08:EB:ED`.

### Entities

The integration creates the following entities for each subwoofer:

#### Numbers (Sliders)
| Entity | Description | Range |
|--------|-------------|-------|
| Volume | Main volume level | -60 to 0 dB |
| Phase | Phase adjustment | 0 to 180° |
| LPF Frequency | Low pass filter cutoff | 30-200 Hz |
| PEQ1/2/3 Frequency | Parametric EQ frequency | 20-200 Hz |
| PEQ1/2/3 Boost | Parametric EQ gain | -12 to +6 dB |
| PEQ1/2/3 Q-Factor | Parametric EQ bandwidth | 0.2-10.0 |

#### Selects (Dropdowns)
| Entity | Description | Options |
|--------|-------------|---------|
| LPF Slope | Low pass filter slope | 6/12/18/24 dB |
| Room Gain Frequency | Room gain corner frequency | 25/31/40 Hz |
| Room Gain Slope | Room gain slope | 6/12 dB |
| Standby Mode | Power mode | Auto ON/Trigger/ON |
| Preset | Load saved preset | 1/2/3/Default |

#### Switches (Toggles)
| Entity | Description |
|--------|-------------|
| Low Pass Filter | Enable/disable LPF |
| PEQ1/2/3 | Enable/disable parametric EQ bands |
| Room Gain Compensation | Enable/disable room gain |
| Polarity (Inverted) | Normal (+) or inverted (-) polarity |

### Dashboard Examples

#### Quick Control Card
A minimal card with just volume and preset - perfect for daily use:

```yaml
type: entities
title: SVS Subwoofer
entities:
  - entity: number.svs_subwoofer_volume
    name: Volume
  - entity: select.svs_subwoofer_preset
    name: Preset
```

#### Full Control Card
A comprehensive card with all main controls:

```yaml
type: entities
title: SVS Subwoofer - Full Control
entities:
  - type: section
    label: Status
  - entity: binary_sensor.svs_subwoofer_connected
  - entity: button.svs_subwoofer_reconnect
  - type: section
    label: Main
  - entity: number.svs_subwoofer_volume
  - entity: number.svs_subwoofer_phase
  - entity: select.svs_subwoofer_preset
  - entity: select.svs_subwoofer_standby_mode
  - entity: switch.svs_subwoofer_polarity_inverted
  - type: section
    label: Low Pass Filter
  - entity: switch.svs_subwoofer_low_pass_filter
  - entity: number.svs_subwoofer_low_pass_filter_frequency
  - entity: select.svs_subwoofer_low_pass_filter_slope
  - type: section
    label: Room Gain
  - entity: switch.svs_subwoofer_room_gain_compensation
  - entity: select.svs_subwoofer_room_gain_frequency
  - entity: select.svs_subwoofer_room_gain_slope
  - type: section
    label: PEQ Band 1
  - entity: switch.svs_subwoofer_peq1
  - entity: number.svs_subwoofer_peq1_frequency
  - entity: number.svs_subwoofer_peq1_boost
  - entity: number.svs_subwoofer_peq1_q_factor
```

> **Note:** Replace `svs_subwoofer` with your actual device name (e.g., `rightsub`, `leftsub`).

### Example Automations

#### Movie Mode - Load preset when watching movies

```yaml
alias: Movie Mode - SVS Cinema Preset
description: Load cinema preset when media player starts playing
triggers:
  - trigger: state
    entity_id: media_player.living_room_tv
    to: playing
actions:
  - action: select.select_option
    target:
      entity_id: select.svs_subwoofer_preset
    data:
      option: "Movie"  # Or use your custom preset name
```

#### Night Mode - Reduce volume after 10 PM

```yaml
alias: Night Mode - Lower Subwoofer Volume
description: Automatically reduce subwoofer volume at night
triggers:
  - trigger: time
    at: "22:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.svs_subwoofer_connected
    state: "on"
actions:
  - action: number.set_value
    target:
      entity_id: number.svs_subwoofer_volume
    data:
      value: -30
```

#### Restore Day Volume

```yaml
alias: Day Mode - Restore Subwoofer Volume
description: Restore normal subwoofer volume in the morning
triggers:
  - trigger: time
    at: "08:00:00"
actions:
  - action: number.set_value
    target:
      entity_id: number.svs_subwoofer_volume
    data:
      value: -15
```

#### Music Mode - Different EQ for music

```yaml
alias: Music Mode - Enhanced Bass
description: Enable PEQ boost when listening to music
triggers:
  - trigger: state
    entity_id: media_player.spotify
    to: playing
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.svs_subwoofer_peq1
  - action: number.set_value
    target:
      entity_id: number.svs_subwoofer_peq1_frequency
    data:
      value: 50
  - action: number.set_value
    target:
      entity_id: number.svs_subwoofer_peq1_boost
    data:
      value: 3
```

### Device Triggers & Actions

The integration supports device triggers and actions for more powerful automations.

#### Available Triggers

| Trigger | Description |
|---------|-------------|
| Subwoofer connected | Fires when the subwoofer connects via Bluetooth |
| Subwoofer disconnected | Fires when the subwoofer disconnects |
| Preset loaded | Fires when a preset is loaded (Preset 1, 2, 3, or Default) |

#### Available Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| Load preset | Load a preset on the subwoofer | `preset`: 1-4 |
| Save to preset | Save current settings to a preset slot | `preset`: 1-3 |
| Set volume | Set the volume level | `volume`: -60 to 0 |
| Reconnect | Reconnect to the subwoofer | - |

#### Device Trigger Example

```yaml
automation:
  - alias: "Notify when subwoofer disconnects"
    trigger:
      - platform: device
        device_id: <your_device_id>
        domain: svs_subwoofer
        type: disconnected
    action:
      - service: notify.mobile_app
        data:
          message: "SVS Subwoofer has disconnected"
```

#### Device Action Example

```yaml
automation:
  - alias: "Movie mode - load preset via device action"
    trigger:
      - platform: state
        entity_id: media_player.tv
        to: playing
    action:
      - device_id: <your_device_id>
        domain: svs_subwoofer
        type: load_preset
        preset: 2
```

> **Note:** Find your device_id in the automation UI when creating a new automation with device triggers/actions.

### Troubleshooting

**Device not discovered:**
- Ensure Bluetooth is enabled on your Home Assistant host
- Check that the subwoofer is powered on and in range
- Try adding manually using the MAC address

**Connection issues:**
- The subwoofer can only connect to one device at a time
- Disconnect from the SVS app on your phone if connected
- Power cycle the subwoofer

---

## pySVS Standalone Application

Original Python GUI/CLI application by Logon84.

![pySVS Screenshot](https://raw.githubusercontent.com/logon84/pySVS/main/pic.png)

### Requirements

```bash
pip3 install bleak
```

### Usage

```
pySVS.py <-b device> <-m MAC_Address> <parameter1> <value1> ...

Options:
  -b dev, --btiface=dev    BT interface (default: hci0)
  -m MAC, --mac=MAC        Device MAC address
  -h, --help               Show help
  -v, --version            Show version
  -e, --encode             Print built frames
  -d FRAME, --decode=FRAME Decode frame values
  -i, --info               Show subwoofer info

Parameters:
  -l X@Y@Z, --lpf=X@Y@Z       Low Pass Filter [enable@freq@slope]
  -q V@W@X@Y@Z, --peq=...     PEQ [band@enable@freq@boost@Q]
  -r X@Y@Z, --roomgain=...    Room Gain [enable@freq@slope]
  -o X, --volume=X            Volume level
  -f X, --phase=X             Phase level
  -k X, --polarity=X          Polarity [0(+) or 1(-)]
  -p X, --preset=X            Load preset [1-4]
```

Run without arguments to launch the GUI.

---

## Supported Devices

This integration works with any SVS subwoofer that supports the official SVS app, including:

**SB Series (Sealed Box)**
- SB-1000 Pro
- SB-2000 Pro
- SB-3000
- SB-4000

**PB Series (Ported Box)**
- PB-1000 Pro
- PB-2000 Pro
- PB-3000
- PB-4000

**Other**
- Micro 3000
- 3000 In-Wall

If your SVS subwoofer connects to the SVS app on your phone, it should work with this integration.

## Credits

- Original pySVS by [Logon84](https://github.com/logon84/pySVS)
- Home Assistant integration port

## License

See [LICENSE](LICENSE) file.

## Disclaimer

This software is provided as-is. Use at your own risk.
