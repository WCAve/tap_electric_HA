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


# Preconditioning state machine states
PC_DISCONNECTED = "disconnected"   # nothing plugged in
PC_AWAITING = "awaiting"           # plugged in, no charge drawn yet (delayed charge)
PC_CHARGING = "charging"           # the main charge is drawing power
PC_SETTLED = "settled"             # charge done (>= settle minutes with no power)
PC_PRECONDITIONING = "preconditioning"  # power after the charge settled = heat/cool


def _parse_dt(value):
    if not value:
        return None
    try:
        return dt_util.parse_datetime(value)
    except (ValueError, TypeError):
        return None


class TapCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /4.0/home, fast while power is flowing and slowly while idle.

    Also classifies post-charge power draws as cabin preconditioning: once a
    charge has run and then sat with no power for `settle_seconds`, any further
    draw within the same plugged-in session is treated as heating/cooling.
    """

    def __init__(
        self, hass, client, active_interval: int, idle_interval: int,
        settle_seconds: int, min_power: float, store=None, restored=None,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=idle_interval),
        )
        self.client = client
        self._active_interval = active_interval
        self._idle_interval = idle_interval
        self._settle_seconds = settle_seconds
        self._min_power = min_power
        self._store = store
        self._pc_state = PC_DISCONNECTED
        self._pc_zero_since = None
        self._pc_last = None
        self._pc_events: list = []
        if restored:
            self._pc_last = _parse_dt(restored.get("last"))
            self._pc_events = [
                d for d in (_parse_dt(x) for x in restored.get("events", [])) if d
            ]

    def _run_precond(self, sessions, now) -> bool:
        """Advance the state machine; return True if a new precond draw began."""
        connected = len(sessions) > 0
        power = max((s.get("speed_kw") or 0) for s in sessions) if sessions else 0.0
        drawing = power >= self._min_power

        if not connected:
            self._pc_state = PC_DISCONNECTED
            self._pc_zero_since = None
            return False
        if self._pc_state == PC_DISCONNECTED:
            self._pc_state = PC_AWAITING
            self._pc_zero_since = None

        if self._pc_state == PC_AWAITING:
            if drawing:
                self._pc_state = PC_CHARGING
                self._pc_zero_since = None
        elif self._pc_state == PC_CHARGING:
            if drawing:
                self._pc_zero_since = None
            elif self._pc_zero_since is None:
                self._pc_zero_since = now
            elif (now - self._pc_zero_since).total_seconds() >= self._settle_seconds:
                self._pc_state = PC_SETTLED
        elif self._pc_state == PC_SETTLED:
            if drawing:
                self._pc_state = PC_PRECONDITIONING
                self._pc_last = now
                self._pc_events.append(now)
                return True
        elif self._pc_state == PC_PRECONDITIONING:
            if not drawing:
                self._pc_state = PC_SETTLED
        return False

    def _precond_summary(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        self._pc_events = [e for e in self._pc_events if (now - e).days < 7]
        today = dt_util.as_local(now).date()
        return {
            "state": self._pc_state,
            "active": self._pc_state == PC_PRECONDITIONING,
            "last": self._pc_last,
            "today": sum(1 for e in self._pc_events if dt_util.as_local(e).date() == today),
            "week": len(self._pc_events),
        }

    async def _save_precond(self) -> None:
        if self._store is None:
            return
        await self._store.async_save({
            "last": self._pc_last.isoformat() if self._pc_last else None,
            "events": [e.isoformat() for e in self._pc_events],
        })

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            home = await self.client.async_get_home()
        except TapAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TapApiError as err:
            raise UpdateFailed(str(err)) from err
        sessions = home.get("active_sessions") or []
        now = dt_util.utcnow()

        if self._run_precond(sessions, now):
            await self._save_precond()

        power = max((s.get("speed_kw") or 0) for s in sessions) if sessions else 0.0
        drawing = power >= self._min_power
        # Poll quickly only while power is actually flowing; back off while idle
        # (even if still plugged in, since is_active stays true the whole time).
        self.update_interval = timedelta(
            seconds=self._active_interval if drawing else self._idle_interval
        )
        return {
            "active_sessions": sessions,
            "home": home,
            "precond": self._precond_summary(),
        }


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
