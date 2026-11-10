"""Drives the Android companion-app live charging notification.

While a session is active it posts an ongoing (persistent, non-dismissable)
notification under a fixed tag, alerting once and then updating silently on each
poll. When charging stops it re-posts the same tag as a dismissable summary.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .coordinator import TapCoordinator

_LOGGER = logging.getLogger(__name__)


def _fmt_since(session: dict) -> str:
    raw = session.get("start_date_time") or session.get("created_date_time")
    dt = dt_util.parse_datetime(raw) if raw else None
    if not dt:
        return "-"
    local = dt_util.as_local(dt)
    return local.strftime("%H:%M") if local.date() == dt_util.now().date() else local.strftime("%a %H:%M")


def _duration(session: dict) -> str:
    raw = session.get("start_date_time")
    dt = dt_util.parse_datetime(raw) if raw else None
    if not dt:
        return "-"
    mins = max(0, int((dt_util.utcnow() - dt).total_seconds()) // 60)
    h, m = divmod(mins, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _price_per_kwh(session: dict) -> float | None:
    tariff = (session.get("payment_details") or {}).get("session_tariff") or {}
    cents = tariff.get("price_per_kwh")
    return cents / 100 if cents is not None else None


def _station(session: dict) -> str | None:
    """Human station name: street address, falling back to the charger code."""
    ld = session.get("location_details") or {}
    return ld.get("address") or ld.get("charger_name")


def _where(session: dict) -> str:
    """Secondary context line: operator and city."""
    ld = session.get("location_details") or {}
    parts = [ld.get("operator_name"), ld.get("city")]
    return " · ".join(p for p in parts if p)


class TapChargingNotifier:
    """Watches the live coordinator and maintains one companion-app notification."""

    def __init__(self, hass, entry, coordinator: TapCoordinator, targets: list[str]) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.targets = targets
        self._tag = f"tap_charging_{entry.entry_id}"
        self._was_charging = False
        self._last: dict | None = None
        self._unsub = None

    def start(self) -> None:
        self._unsub = self.coordinator.async_add_listener(self._handle)
        self._handle()

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle(self) -> None:
        if not self.targets:
            return
        sessions = (self.coordinator.data or {}).get("active_sessions") or []
        session = sessions[0] if sessions else None
        charging = bool(session and session.get("is_active"))
        if charging:
            self._last = session
            self._was_charging = True
            self.hass.async_create_task(self._notify_ongoing(session))
        elif self._was_charging:
            self._was_charging = False
            self.hass.async_create_task(self._notify_finished(session or self._last))

    def _summary_ongoing(self, s: dict) -> str:
        speed = s.get("speed_kw") or 0
        energy = s.get("energy_kwh") or 0
        cost = (s.get("current_costs") or 0) / 100
        price = _price_per_kwh(s)
        line1 = f"{speed:.1f} kW · {energy:.2f} kWh · €{cost:.2f}"
        second = [f"since {_fmt_since(s)}"]
        if price is not None:
            second.insert(0, f"€{price:.3f}/kWh")
        lines = [line1, " · ".join(second)]
        where = _where(s)
        if where:
            lines.append(where)
        return "\n".join(lines)

    async def _notify_ongoing(self, s: dict) -> None:
        station = _station(s)
        title = f"⚡ Charging — {station}" if station else "⚡ Charging"
        data = {
            "tag": self._tag,
            "persistent": True,
            "sticky": True,
            "alert_once": True,
            "channel": "Tap Electric charging",
            "importance": "high",
            "color": "#13C2C2",
            "notification_icon": "mdi:ev-station",
        }
        await self._send(title, self._summary_ongoing(s), data)

    async def _notify_finished(self, s: dict | None) -> None:
        if s:
            station = _station(s)
            title = f"✅ Charged — {station}" if station else "✅ Charging finished"
            energy = s.get("energy_kwh") or 0
            cost = (s.get("current_costs") or 0) / 100
            message = f"{energy:.2f} kWh · €{cost:.2f} · {_duration(s)}"
            where = _where(s)
            if where:
                message += f"\n{where}"
        else:
            title = "✅ Charging finished"
            message = "Session ended."
        data = {
            "tag": self._tag,
            "persistent": False,
            "sticky": False,
            "channel": "Tap Electric charging",
            "color": "#13C2C2",
            "notification_icon": "mdi:ev-station",
        }
        await self._send(title, message, data)

    async def _send(self, title: str, message: str, data: dict[str, Any]) -> None:
        for target in self.targets:
            service = target.split(".", 1)[1] if target.startswith("notify.") else target
            try:
                await self.hass.services.async_call(
                    "notify", service,
                    {"title": title, "message": message, "data": data},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Tap Electric: notify to %s failed: %s", target, err)
