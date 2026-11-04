"""Coordinators for Tap Electric."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TapApiError, TapAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TapCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /4.0/home for the live charging session(s)."""

    def __init__(self, hass, client, scan_interval: int) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
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
        return {"active_sessions": home.get("active_sessions") or [], "home": home}


def _ym(iso: str | None):
    dt = dt_util.parse_datetime(iso) if iso else None
    return (dt.year, dt.month) if dt else None


def _blank() -> dict[str, float]:
    return {"sessions": 0, "energy": 0.0, "cost": 0.0, "avg": 0.0}


def summarize_insights(data: Any) -> dict[str, dict]:
    """Reduce /insights to this-month / last-month / lifetime aggregates.

    Only totals are kept - the per-session list (with charger addresses) is
    intentionally dropped so location data never reaches Home Assistant.
    """
    result = {"this_month": _blank(), "last_month": _blank(), "lifetime": _blank()}
    if not isinstance(data, dict):
        return result
    summaries = data.get("summaries") or {}
    months = summaries.get("EUR")
    if months is None:
        months = next((v for v in summaries.values() if isinstance(v, list)), [])

    now = dt_util.utcnow()
    cur = (now.year, now.month)
    prev = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)

    life_sessions = 0
    life_kwh = 0.0
    life_cost_ct = 0
    for m in months or []:
        if not isinstance(m, dict):
            continue
        sessions = m.get("total_sessions") or 0
        kwh = m.get("total_kwh") or 0.0
        cost_ct = m.get("total_cost_ct") or 0
        life_sessions += sessions
        life_kwh += kwh
        life_cost_ct += cost_ct
        ym = _ym(m.get("interval_start"))
        bucket = "this_month" if ym == cur else "last_month" if ym == prev else None
        if bucket:
            avg = m.get("cost_per_kwh")
            if avg is None:
                avg = (cost_ct / 100 / kwh) if kwh else 0.0
            result[bucket] = {
                "sessions": sessions,
                "energy": round(kwh, 3),
                "cost": round(cost_ct / 100, 2),
                "avg": round(avg, 4),
            }
    result["lifetime"] = {
        "sessions": life_sessions,
        "energy": round(life_kwh, 3),
        "cost": round(life_cost_ct / 100, 2),
        "avg": round(life_cost_ct / 100 / life_kwh, 4) if life_kwh else 0.0,
    }
    return result


class TapInsightsCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Polls /1.0/insights hourly; exposes month + lifetime aggregates."""

    def __init__(self, hass, client) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_insights",
            update_interval=timedelta(hours=1),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            raw = await self.client.async_get_insights()
        except TapAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TapApiError as err:
            raise UpdateFailed(str(err)) from err
        return summarize_insights(raw)
