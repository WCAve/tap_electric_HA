"""Sensors for Tap Electric: the live session plus monthly/lifetime stats."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TapCoordinator, TapInsightsCoordinator

EUR = "EUR"
NOT_CHARGING = "Not charging"


def _device(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Tap Electric",
        manufacturer="Tap Electric",
        model="Charging session",
    )


# ---------------- live session sensors (/4.0/home) ----------------

def _loc(session: dict | None, key: str) -> Any:
    if not session:
        return None
    return (session.get("location_details") or {}).get(key)


def _text_loc(session: dict | None, key: str) -> str:
    if not session:
        return NOT_CHARGING
    return _loc(session, key) or NOT_CHARGING


def _location_text(session: dict | None) -> str:
    if not session:
        return NOT_CHARGING
    parts = [p for p in (_loc(session, "address"), _loc(session, "city")) if p]
    return ", ".join(parts) if parts else NOT_CHARGING


def _start_text(session: dict | None) -> str:
    if not session:
        return NOT_CHARGING
    raw = session.get("start_date_time") or session.get("created_date_time")
    dt = dt_util.parse_datetime(raw) if raw else None
    if not dt:
        return NOT_CHARGING
    local = dt_util.as_local(dt)
    if local.date() == dt_util.now().date():
        return local.strftime("%H:%M")
    return local.strftime("%d %b %H:%M")


def _price_text(session: dict | None) -> str:
    if not session:
        return NOT_CHARGING
    tariff = (session.get("payment_details") or {}).get("session_tariff") or {}
    cents = tariff.get("price_per_kwh")
    if cents is None:
        return NOT_CHARGING
    return f"€{cents / 100:.3f}/kWh"


@dataclass(frozen=True, kw_only=True)
class TapSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict | None], Any]


SENSORS: tuple[TapSensorDescription, ...] = (
    TapSensorDescription(
        key="status", name="Charging status", icon="mdi:ev-station",
        value_fn=lambda s: (s.get("status") if s else NOT_CHARGING)),
    TapSensorDescription(
        key="energy", name="Session energy",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: (s.get("energy_kwh") if s else 0)),
    TapSensorDescription(
        key="power", name="Charging power",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda s: (s.get("speed_kw") if s else 0)),
    TapSensorDescription(
        key="cost", name="Session cost",
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement=EUR, icon="mdi:cash",
        value_fn=lambda s: (round((s.get("current_costs") or 0) / 100, 2) if s else 0)),
    TapSensorDescription(
        key="price_per_kwh", name="Price per kWh", icon="mdi:tag",
        value_fn=_price_text),
    TapSensorDescription(
        key="charger", name="Charger", icon="mdi:ev-plug-type2",
        value_fn=lambda s: _text_loc(s, "charger_name")),
    TapSensorDescription(
        key="operator", name="Operator", icon="mdi:domain",
        value_fn=lambda s: _text_loc(s, "operator_name")),
    TapSensorDescription(
        key="location", name="Location", icon="mdi:map-marker",
        value_fn=_location_text),
    TapSensorDescription(
        key="started", name="Session start", icon="mdi:clock-start",
        value_fn=_start_text),
)


# ---------------- insights sensors (/1.0/insights) ----------------

@dataclass(frozen=True, kw_only=True)
class TapInsightsDescription(SensorEntityDescription):
    period: str  # this_month | last_month | lifetime
    metric: str  # sessions | energy | cost | avg


def _build_insights() -> list[TapInsightsDescription]:
    periods = [("this_month", "This month"), ("last_month", "Last month"), ("lifetime", "Lifetime")]
    out: list[TapInsightsDescription] = []
    for pkey, plabel in periods:
        out.append(TapInsightsDescription(
            key=f"{pkey}_sessions", name=f"{plabel} sessions", icon="mdi:counter",
            state_class=SensorStateClass.MEASUREMENT, period=pkey, metric="sessions"))
        out.append(TapInsightsDescription(
            key=f"{pkey}_energy", name=f"{plabel} energy",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL, suggested_display_precision=1,
            period=pkey, metric="energy"))
        out.append(TapInsightsDescription(
            key=f"{pkey}_spend", name=f"{plabel} spend",
            device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement=EUR,
            state_class=SensorStateClass.TOTAL, suggested_display_precision=2,
            icon="mdi:cash-multiple", period=pkey, metric="cost"))
        out.append(TapInsightsDescription(
            key=f"{pkey}_avg_price", name=f"{plabel} avg price",
            native_unit_of_measurement="EUR/kWh", icon="mdi:tag-multiple",
            state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=3,
            period=pkey, metric="avg"))
    return out


INSIGHTS_SENSORS: tuple[TapInsightsDescription, ...] = tuple(_build_insights())


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    live: TapCoordinator = data["live"]
    insights: TapInsightsCoordinator = data["insights"]
    entities: list[SensorEntity] = [TapSensor(live, entry, d) for d in SENSORS]
    entities += [TapInsightsSensor(insights, entry, d) for d in INSIGHTS_SENSORS]
    async_add_entities(entities)


class TapSensor(CoordinatorEntity[TapCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: TapSensorDescription

    def __init__(self, coordinator, entry, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device(entry)

    @property
    def _session(self) -> dict | None:
        sessions = self.coordinator.data.get("active_sessions") or []
        return sessions[0] if sessions else None

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._session)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "status":
            return None
        session = self._session
        if not session:
            return {"active_sessions": 0}
        loc = session.get("location_details") or {}
        return {
            "active_sessions": len(self.coordinator.data.get("active_sessions") or []),
            "session_id": session.get("id"),
            "charger_id": loc.get("charger_id"),
            "location_id": loc.get("location_id"),
            "outlet_name": loc.get("outlet_name"),
            "max_power_w": loc.get("max_power"),
            "is_active": session.get("is_active"),
            "is_stale": session.get("is_stale"),
            "next_update_expected": session.get("next_update_expected"),
        }


class TapInsightsSensor(CoordinatorEntity[TapInsightsCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: TapInsightsDescription

    def __init__(self, coordinator, entry, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device(entry)

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        period = data.get(self.entity_description.period) or {}
        return period.get(self.entity_description.metric)
