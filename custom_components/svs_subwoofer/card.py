"""Serve the SVS Subwoofer dashboard card and its tile features.

The card ships with the integration, so it needs no separate install. It is
added to the dashboard resources (Settings > Dashboards > Resources), which
the frontend reads live from Home Assistant whenever a dashboard opens, so a
browser that shows a stored copy of the page still loads the card. Its
address includes a hash of the file, so browsers load a changed card at once
instead of an old cached copy.

Home Assistant has no public API for integrations to add dashboard
resources; this uses the dashboards' resource collection, the same one the
Resources page edits. If that is not available (dashboards in YAML mode, or
a change in Home Assistant), the card is loaded on every page instead, the
way Home Assistant offers integrations to add frontend code.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/svs_subwoofer/svs-subwoofer-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "svs-subwoofer-card.js"
LOVELACE = "lovelace"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it to the dashboards."""
    if "frontend" not in hass.config.components or hass.http is None:
        # No dashboards to serve (for example, in tests)
        return

    # Imported here because the frontend is optional (after_dependencies)
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    content = await hass.async_add_executor_job(CARD_FILE.read_bytes)
    url = f"{CARD_URL}?v={hashlib.sha256(content).hexdigest()[:12]}"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=True)]
    )
    if not await _async_set_resource(hass, url):
        add_extra_js_url(hass, url)


async def async_remove_card_resource(hass: HomeAssistant) -> None:
    """Remove the card from the dashboard resources."""
    await _async_set_resource(hass, None)


def _resource_collection(hass: HomeAssistant) -> Any | None:
    """Return the dashboards' resource collection, if it can be edited."""
    data = hass.data.get(LOVELACE)
    # An object in current Home Assistant, a dict in older versions
    resources = getattr(data, "resources", None)
    if resources is None and isinstance(data, dict):
        resources = data.get("resources")
    # Resources defined in YAML cannot be edited
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_set_resource(hass: HomeAssistant, url: str | None) -> bool:
    """Add or update the card's resource (or remove it, with no url).

    Return False if the resource could not be set.
    """
    resources = _resource_collection(hass)
    if resources is None:
        _LOGGER.debug(
            "Dashboard resources cannot be edited; loading the card on every page"
        )
        return False
    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        ours = [
            item
            for item in resources.async_items()
            if str(item.get("url", "")).split("?")[0] == CARD_URL
        ]
        if url is None:
            for item in ours:
                await resources.async_delete_item(item["id"])
            return True
        if not ours:
            await resources.async_create_item({"res_type": "module", "url": url})
            return True
        first, *extra = ours
        if first.get("url") != url or first.get("type") != "module":
            await resources.async_update_item(
                first["id"], {"res_type": "module", "url": url}
            )
        for item in extra:
            await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001 - Home Assistant internals; fall back rather than fail setup
        _LOGGER.warning(
            "Could not update the SVS Subwoofer card's dashboard resource",
            exc_info=True,
        )
        return False
    return True
