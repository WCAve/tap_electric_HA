"""The Tap Electric integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import TapElectricClient
from .const import (
    CONF_IDLE_SCAN_INTERVAL,
    CONF_NOTIFY_CLICK_ACTION,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_ENERGY_STEP,
    CONF_NOTIFY_TARGETS,
    CONF_PRECOND_MIN_POWER,
    CONF_PRECOND_SETTLE_MIN,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_IDLE_SCAN_INTERVAL,
    DEFAULT_PRECOND_MIN_POWER,
    DEFAULT_NOTIFY_ENERGY_STEP,
    DEFAULT_PRECOND_SETTLE_MIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import TapCoordinator, TapInsightsCoordinator
from .notifier import TapChargingNotifier

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

CARD_URL = "/tap_electric_frontend/tap-recent-sessions-card.js"
_CARD_REGISTERED = f"{DOMAIN}_card_registered"


def _card_version() -> str:
    """Integration version, read at import time for cache-busting the card."""
    try:
        import json

        manifest = Path(__file__).parent / "manifest.json"
        return json.loads(manifest.read_text()).get("version", "0")
    except Exception:  # noqa: BLE001
        return "0"


CARD_VERSION = _card_version()


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Serve the custom Lovelace card and auto-load it on the frontend.

    Registered once per HA start (guarded), so the card works with just
    `type: custom:tap-recent-sessions-card` - no manual resource setup.
    """
    if hass.data.get(_CARD_REGISTERED):
        return
    card_file = Path(__file__).parent / "www" / "tap-recent-sessions-card.js"
    if not card_file.is_file():
        _LOGGER.warning("Tap Electric card asset missing: %s", card_file)
        return
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_file), False)]
        )
    except (ImportError, AttributeError):  # older cores
        hass.http.register_static_path(CARD_URL, str(card_file), False)
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    hass.data[_CARD_REGISTERED] = True
    _LOGGER.debug("Registered Tap Electric Lovelace card at %s", CARD_URL)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _async_register_frontend_card(hass)
    session = async_get_clientsession(hass)
    client = TapElectricClient(session, refresh_token=entry.data[CONF_REFRESH_TOKEN])
    await client.async_fetch_account()

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    idle_interval = entry.options.get(CONF_IDLE_SCAN_INTERVAL, DEFAULT_IDLE_SCAN_INTERVAL)
    settle_seconds = entry.options.get(CONF_PRECOND_SETTLE_MIN, DEFAULT_PRECOND_SETTLE_MIN) * 60
    min_power = entry.options.get(CONF_PRECOND_MIN_POWER, DEFAULT_PRECOND_MIN_POWER)
    store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_precond")
    restored = await store.async_load()
    live = TapCoordinator(
        hass, client, scan_interval, idle_interval,
        settle_seconds, min_power, store, restored,
    )
    insights = TapInsightsCoordinator(hass, client)
    await live.async_config_entry_first_refresh()
    await insights.async_config_entry_first_refresh()

    notifier: TapChargingNotifier | None = None
    targets = entry.options.get(CONF_NOTIFY_TARGETS) or []
    if entry.options.get(CONF_NOTIFY_ENABLED) and targets:
        energy_step = entry.options.get(CONF_NOTIFY_ENERGY_STEP, DEFAULT_NOTIFY_ENERGY_STEP)
        click_action = entry.options.get(CONF_NOTIFY_CLICK_ACTION, "")
        notifier = TapChargingNotifier(hass, entry, live, targets, energy_step, click_action)
        notifier.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "live": live, "insights": insights, "notifier": notifier,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data[DOMAIN].get(entry.entry_id)
    if store and store.get("notifier"):
        store["notifier"].stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
