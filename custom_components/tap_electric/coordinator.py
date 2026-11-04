"""DataUpdateCoordinator for Tap Electric."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TapApiError, TapAuthError, TapElectricClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TapCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /4.0/home and exposes the active charging session(s)."""

    def __init__(
        self, hass: HomeAssistant, client: TapElectricClient, scan_interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            home = await self.client.async_get_home()
        except TapAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TapApiError as err:
            raise UpdateFailed(str(err)) from err

        sessions = home.get("active_sessions") or []
        return {"active_sessions": sessions, "home": home}
