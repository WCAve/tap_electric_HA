"""Drives the Android companion-app charging notification.

Keeps a single ongoing (persistent, sticky) notification for as long as the car
is connected, with content driven by the preconditioning state machine
(charging / connected-idle / preconditioning). To stay well under the companion
app's 500-push/day cap, it only RE-SENDS when something meaningful changes: a
state transition, the station, or the session energy advancing by a configurable
step. While the car sits idle-plugged, nothing is sent and the pinned
notification simply stays put. On disconnect it posts a dismissable summary.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .coordinator import (
    PC_AWAITING,
    PC_CHARGING,
    PC_DISCONNECTED,
    PC_PRECONDITIONING,
    PC_SETTLED,
    TapCoordinator,
)

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
    ld = session.get("location_details") or {}
    return ld.get("address") or ld.get("charger_name")


def _where(session: dict) -> str:
    ld = session.get("location_details") or {}
    return " · ".join(p for p in (ld.get("operator_name"), ld.get("city")) if p)


class TapChargingNotifier:
    """Maintains one companion-app notification across a plugged-in session."""

    def __init__(self, hass, entry, coordinator: TapCoordinator, targets: list[str],
                 energy_step: float = 0.5) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.targets = targets
        self._energy_step = energy_step
        self._tag = f"tap_charging_{entry.entry_id}"
        self._unsub = None
        self._reset()

    def _reset(self) -> None:
        self._shown = False
        self._last_state = None
        self._last_station = None
        self._last_energy_sent = -1.0
        self._last_session: dict | None = None

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
        data = self.coordinator.data or {}
        state = (data.get("precond") or {}).get("state")
        sessions = data.get("active_sessions") or []
        session = sessions[0] if sessions else None

        if state in (None, PC_DISCONNECTED):
            if self._shown:
                self.hass.async_create_task(self._notify_finished(self._last_session))
            self._reset()
            return

        # Connected (plugged in). Decide whether anything worth re-sending changed.
        self._last_session = session
        energy = (session or {}).get("energy_kwh") or 0.0
        station = _station(session or {})
        advancing = state in (PC_CHARGING, PC_PRECONDITIONING)
        resend = (
            not self._shown
            or state != self._last_state
            or station != self._last_station
            or (advancing and energy - self._last_energy_sent >= self._energy_step)
        )
        if resend:
            self._last_state = state
            self._last_station = station
            self._last_energy_sent = energy
            self._shown = True
            self.hass.async_create_task(self._notify_connected(session, state))

    def _metrics(self, s: dict) -> str:
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

    def _complete_body(self, s: dict) -> str:
        energy = s.get("energy_kwh") or 0
        cost = (s.get("current_costs") or 0) / 100
        lines = [f"Charge complete · {energy:.2f} kWh · €{cost:.2f}"]
        where = _where(s)
        if where:
            lines.append(where)
        return "\n".join(lines)

    async def _notify_connected(self, s: dict | None, state: str) -> None:
        s = s or {}
        station = _station(s)
        if state == PC_CHARGING:
            emoji, label, body = "⚡", "Charging", self._metrics(s)
        elif state == PC_PRECONDITIONING:
            emoji, label, body = "🔥", "Preconditioning", self._metrics(s)
        elif state == PC_SETTLED:
            emoji, label, body = "🔌", "Connected", self._complete_body(s)
        else:  # PC_AWAITING
            emoji, label, body = "🔌", "Connected", "Plugged in — waiting to charge"
        title = f"{emoji} {label} — {station}" if station else f"{emoji} {label}"
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
        await self._send(title, body, data)

    async def _notify_finished(self, s: dict | None) -> None:
        if s:
            station = _station(s)
            title = f"✅ Charged — {station}" if station else "✅ Session finished"
            energy = s.get("energy_kwh") or 0
            cost = (s.get("current_costs") or 0) / 100
            message = f"{energy:.2f} kWh · €{cost:.2f} · {_duration(s)}"
            where = _where(s)
            if where:
                message += f"\n{where}"
        else:
            title, message = "✅ Session finished", "Unplugged."
        data = {
            "tag": self._tag,
            "persistent": False,
            "sticky": False,
            "alert_once": True,
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
