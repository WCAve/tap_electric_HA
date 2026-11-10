"""The Tap Electric integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TapElectricClient
from .const import (
    CONF_IDLE_SCAN_INTERVAL,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_TARGETS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_IDLE_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import TapCoordinator, TapInsightsCoordinator
from .notifier import TapChargingNotifier

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = TapElectricClient(session, refresh_token=entry.data[CONF_REFRESH_TOKEN])
    await client.async_fetch_account()

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    idle_interval = entry.options.get(CONF_IDLE_SCAN_INTERVAL, DEFAULT_IDLE_SCAN_INTERVAL)
    live = TapCoordinator(hass, client, scan_interval, idle_interval)
    insights = TapInsightsCoordinator(hass, client)
    await live.async_config_entry_first_refresh()
    await insights.async_config_entry_first_refresh()

    notifier: TapChargingNotifier | None = None
    targets = entry.options.get(CONF_NOTIFY_TARGETS) or []
    if entry.options.get(CONF_NOTIFY_ENABLED) and targets:
        notifier = TapChargingNotifier(hass, entry, live, targets)
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
