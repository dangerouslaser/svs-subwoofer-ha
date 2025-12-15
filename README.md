# SVS Subwoofer Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Control your SVS subwoofer directly from Home Assistant via Bluetooth. Full parameter access using the same protocol as the official SVS app.

## Features

- Bluetooth auto-discovery of SVS subwoofers
- Manual MAC address configuration option
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
- Device triggers and actions for automations

## Prerequisites

- **Home Assistant 2024.4.0** or newer
- **Home Assistant Bluetooth Integration** must be configured and working
  - Go to **Settings** → **Devices & Services** → **Bluetooth**
  - Ensure your Bluetooth adapter is detected and operational
  - See [Home Assistant Bluetooth documentation](https://www.home-assistant.io/integrations/bluetooth/) for setup help

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL and select "Integration" as the category
4. Click "Add"
5. Search for "SVS Subwoofer" and install
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/svs_subwoofer` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. **Ensure Bluetooth is working** in Home Assistant (Settings → Devices & Services → Bluetooth)
2. **Disconnect the SVS app** on your phone (the subwoofer only allows one BLE connection)
3. Go to **Settings** → **Devices & Services**
4. Click **Add Integration**
5. Search for "SVS Subwoofer"
6. Either:
   - Select your subwoofer by name from the list (e.g., "RIGHTSUB", "LEFTSUB")
   - Devices marked with `[SVS]` are detected SVS subwoofers
   - Or choose "Enter MAC address manually" if your device isn't showing

### Finding Your Subwoofer

The integration shows all discovered Bluetooth devices by name. Your subwoofers will appear with the names you configured in the SVS app.

**Tips for discovery:**
- Open the SVS app briefly to activate Bluetooth advertising, then disconnect
- Make sure the subwoofer is powered on and within range
- Disconnect the SVS app before adding to Home Assistant

**Manual MAC address lookup:**

```bash
bluetoothctl
[bluetooth]# scan on
# Look for your subwoofer - SVS devices have MACs starting with 08:EB:ED
# [NEW] Device 08:EB:ED:63:7E:00 RIGHTSUB
[bluetooth]# scan off
[bluetooth]# exit
```

## Entities

### Numbers (Sliders)

| Entity | Description | Range |
|--------|-------------|-------|
| Volume | Main volume level | -60 to 0 dB |
| Phase | Phase adjustment | 0 to 180° |
| LPF Frequency | Low pass filter cutoff | 30-200 Hz |
| PEQ1/2/3 Frequency | Parametric EQ frequency | 20-200 Hz |
| PEQ1/2/3 Boost | Parametric EQ gain | -12 to +6 dB |
| PEQ1/2/3 Q-Factor | Parametric EQ bandwidth | 0.2-10.0 |

### Selects (Dropdowns)

| Entity | Description | Options |
|--------|-------------|---------|
| LPF Slope | Low pass filter slope | 6/12/18/24 dB |
| Room Gain Frequency | Room gain corner frequency | 25/31/40 Hz |
| Room Gain Slope | Room gain slope | 6/12 dB |
| Standby Mode | Power mode | Auto ON/Trigger/ON |
| Preset | Load saved preset | 1/2/3/Default |

### Switches (Toggles)

| Entity | Description |
|--------|-------------|
| Low Pass Filter | Enable/disable LPF |
| PEQ1/2/3 | Enable/disable parametric EQ bands |
| Room Gain Compensation | Enable/disable room gain |
| Polarity (Inverted) | Normal (+) or inverted (-) polarity |

### Buttons

| Entity | Description |
|--------|-------------|
| Reconnect | Reconnect to the subwoofer |

### Binary Sensors

| Entity | Description |
|--------|-------------|
| Connected | Connection status |

## Dashboard Examples

### Quick Control Card

```yaml
type: entities
title: SVS Subwoofer
entities:
  - entity: number.svs_subwoofer_volume
    name: Volume
  - entity: select.svs_subwoofer_preset
    name: Preset
```

### Full Control Card

```yaml
type: entities
title: SVS Subwoofer
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

## Example Automations

### Movie Mode - Load preset when watching movies

```yaml
alias: Movie Mode - SVS Cinema Preset
triggers:
  - trigger: state
    entity_id: media_player.living_room_tv
    to: playing
actions:
  - action: select.select_option
    target:
      entity_id: select.svs_subwoofer_preset
    data:
      option: "Preset 2"
```

### Night Mode - Reduce volume after 10 PM

```yaml
alias: Night Mode - Lower Subwoofer Volume
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

## Device Triggers & Actions

The integration supports device triggers and actions for automations.

### Available Triggers

| Trigger | Description |
|---------|-------------|
| Subwoofer connected | Fires when the subwoofer connects via Bluetooth |
| Subwoofer disconnected | Fires when the subwoofer disconnects |
| Preset loaded | Fires when a preset is loaded (Preset 1, 2, 3, or Default) |

### Available Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| Load preset | Load a preset on the subwoofer | `preset`: 1-4 |
| Save to preset | Save current settings to a preset slot | `preset`: 1-3 |
| Set volume | Set the volume level | `volume`: -60 to 0 |
| Reconnect | Reconnect to the subwoofer | - |

### Device Trigger Example

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

### Device Action Example

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

## Multi-Subwoofer Control

When you have multiple SVS subwoofers, you can control them together using custom services. These are available in **Developer Tools** → **Services**.

### Available Services

| Service | Description |
|---------|-------------|
| `svs_subwoofer.sync_from` | Copy all settings from one subwoofer to others |
| `svs_subwoofer.set_volume` | Set volume on multiple subwoofers (with optional offsets) |
| `svs_subwoofer.load_preset` | Load the same preset on multiple subwoofers |

### Sync Settings Between Subwoofers

Copy all settings (volume, phase, EQ, LPF, room gain, polarity, standby) from one subwoofer to another:

```yaml
service: svs_subwoofer.sync_from
data:
  source_device_id: <left_sub_device_id>
  target_device_ids:
    - <right_sub_device_id>
```

### Set Volume on Multiple Subwoofers

Set the same volume on all subwoofers, with optional per-device offsets for room correction:

```yaml
service: svs_subwoofer.set_volume
data:
  device_ids:
    - <left_sub_device_id>
    - <right_sub_device_id>
  volume: -25
  offsets:
    <right_sub_device_id>: -3  # Right sub 3dB quieter
```

### Load Preset on Multiple Subwoofers

Load the same preset on all subwoofers simultaneously:

```yaml
service: svs_subwoofer.load_preset
data:
  device_ids:
    - <left_sub_device_id>
    - <right_sub_device_id>
  preset: "2"  # or "Default"
```

### Multi-Sub Automation Example

```yaml
automation:
  - alias: "Movie Mode - Sync both subs"
    trigger:
      - platform: state
        entity_id: media_player.tv
        to: playing
        for:
          seconds: 5
    action:
      - service: svs_subwoofer.load_preset
        data:
          device_ids:
            - <left_sub_device_id>
            - <right_sub_device_id>
          preset: "2"
      - service: svs_subwoofer.set_volume
        data:
          device_ids:
            - <left_sub_device_id>
            - <right_sub_device_id>
          volume: -20
```

> **Tip:** Find device IDs in **Settings** → **Devices & Services** → **SVS Subwoofer** → click on a device → look at the URL or "Device info" section.

### Multi-Sub Dashboard Card

Create a dedicated control panel for managing multiple subwoofers together.

**Step 1: Create Helper** (Settings → Devices & Services → Helpers → Create Helper → Number)

- Name: `All Subwoofers Volume`
- Icon: `mdi:volume-high`
- Min: `-60`, Max: `0`, Step: `1`
- Unit: `dB`

**Step 2: Create Scripts** (Settings → Automations & Scenes → Scripts → Add Script)

```yaml
# Script 1: Sync Left to Right
alias: "Sync Left → Right Sub"
icon: mdi:sync
sequence:
  - service: svs_subwoofer.sync_from
    data:
      source_device_id: <left_sub_device_id>
      target_device_ids:
        - <right_sub_device_id>

# Script 2: Movie Mode
alias: "Movie Mode (All Subs)"
icon: mdi:movie
sequence:
  - service: svs_subwoofer.load_preset
    data:
      device_ids:
        - <left_sub_device_id>
        - <right_sub_device_id>
      preset: "2"

# Script 3: Music Mode
alias: "Music Mode (All Subs)"
icon: mdi:music
sequence:
  - service: svs_subwoofer.load_preset
    data:
      device_ids:
        - <left_sub_device_id>
        - <right_sub_device_id>
      preset: "1"

# Script 4: Default Settings
alias: "Reset to Default (All Subs)"
icon: mdi:restore
sequence:
  - service: svs_subwoofer.load_preset
    data:
      device_ids:
        - <left_sub_device_id>
        - <right_sub_device_id>
      preset: "Default"
```

**Step 3: Create Automation** (to sync volume slider)

```yaml
alias: "Sync group volume slider to all subs"
trigger:
  - platform: state
    entity_id: input_number.all_subwoofers_volume
action:
  - service: svs_subwoofer.set_volume
    data:
      device_ids:
        - <left_sub_device_id>
        - <right_sub_device_id>
      volume: "{{ states('input_number.all_subwoofers_volume') | int }}"
mode: single
```

**Step 4: Dashboard Card**

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: "## 🔊 Multi-Sub Control"

  - type: entities
    entities:
      - entity: input_number.all_subwoofers_volume
        name: Group Volume

  - type: horizontal-stack
    cards:
      - type: button
        name: Movie
        icon: mdi:movie
        tap_action:
          action: call-service
          service: script.movie_mode_all_subs
      - type: button
        name: Music
        icon: mdi:music
        tap_action:
          action: call-service
          service: script.music_mode_all_subs
      - type: button
        name: Default
        icon: mdi:restore
        tap_action:
          action: call-service
          service: script.reset_to_default_all_subs

  - type: horizontal-stack
    cards:
      - type: button
        name: Sync L→R
        icon: mdi:sync
        tap_action:
          action: call-service
          service: script.sync_left_to_right_sub

  - type: entities
    title: Individual Status
    entities:
      - entity: binary_sensor.leftsub_connected
        name: Left Sub
      - entity: binary_sensor.rightsub_connected
        name: Right Sub
```

> **Note:** Replace `<left_sub_device_id>` and `<right_sub_device_id>` with your actual device IDs, and adjust entity names to match your subwoofer names (e.g., `leftsub`, `rightsub`).

## Supported Devices

Works with any SVS subwoofer that supports the official SVS app:

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

## Troubleshooting

**Device not discovered:**
- Ensure Bluetooth is enabled on your Home Assistant host
- Check that the subwoofer is powered on and in range
- Try adding manually using the MAC address

**Connection issues:**
- The subwoofer can only connect to one device at a time
- Disconnect from the SVS app on your phone if connected
- Power cycle the subwoofer

**Commands not working:**
- Check the Home Assistant logs for errors
- Try using the Reconnect button
- Ensure you're not connected via the SVS app

## Credits

Protocol reverse-engineering based on [pySVS by Logon84](https://github.com/logon84/pySVS).

## License

See [LICENSE](LICENSE) file.
