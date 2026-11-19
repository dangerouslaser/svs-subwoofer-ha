"""Print the pip requirements needed to test the SVS Subwoofer integration.

Combines the integration's own requirements with those of the Home Assistant
components it depends on, taken from the installed Home Assistant version so
the versions always match.
"""

import json
from pathlib import Path

import homeassistant.components

COMPONENTS = ("bluetooth", "bluetooth_adapters", "usb")

base = Path(homeassistant.components.__file__).parent
manifest = Path("custom_components/svs_subwoofer/manifest.json")
requirements = set(json.loads(manifest.read_text())["requirements"])
for name in COMPONENTS:
    component = json.loads((base / name / "manifest.json").read_text())
    requirements.update(component.get("requirements", []))
print("\n".join(sorted(requirements)))
