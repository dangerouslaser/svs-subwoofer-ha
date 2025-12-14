# SVS Subwoofer Control

Control SVS SB-1000 Pro and compatible subwoofers via Bluetooth.

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
   - Select a discovered subwoofer from the list, or
   - Enter the MAC address manually

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

- SVS SB-1000 Pro (tested)
- Other SVS Bluetooth-enabled subwoofers may work

## Credits

- Original pySVS by [Logon84](https://github.com/logon84/pySVS)
- Home Assistant integration port

## License

See [LICENSE](LICENSE) file.

## Disclaimer

This software is provided as-is. Use at your own risk.
