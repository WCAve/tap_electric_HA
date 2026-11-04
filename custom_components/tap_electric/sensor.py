"""Sensors for the active Tap Electric charging session."""
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
from .coordinator import TapCoordinator


def _loc(session: dict | None, key: str) -> Any:
    if not session:
        return None
    return (session.get("location_details") or {}).get(key)


def _start(session: dict | None) -> Any:
    if not session:
        return None
    raw = session.get("start_date_time") or session.get("created_date_time")
    return dt_util.parse_datetime(raw) if raw else None


def _price_per_kwh(session: dict | None) -> Any:
    if not session:
        return None
    tariff = (session.get("payment_details") or {}).get("session_tariff") or {}
    cents = tariff.get("price_per_kwh")
    return round(cents / 100, 2) if cents is not None else None


@dataclass(frozen=True, kw_only=True)
class TapSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor over the active session."""

    value_fn: Callable[[dict | None], Any]


SENSORS: tuple[TapSensorDescription, ...] = (
    TapSensorDescription(
        key="status",
        name="Charging status",
        icon="mdi:ev-station",
        value_fn=lambda s: (s.get("status") if s else "idle"),
    ),
    TapSensorDescription(
        key="energy",
        name="Session energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: (s.get("energy_kwh") if s else 0),
    ),
    TapSensorDescription(
        key="power",
        name="Charging power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda s: (s.get("speed_kw") if s else 0),
    ),
    TapSensorDescription(
        key="cost",
        name="Session cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        icon="mdi:cash",
        value_fn=lambda s: (round((s.get("current_costs") or 0) / 100, 2) if s else 0),
    ),
    TapSensorDescription(
        key="price_per_kwh",
        name="Price per kWh",
        native_unit_of_measurement="EUR/kWh",
        icon="mdi:tag",
        value_fn=_price_per_kwh,
    ),
    TapSensorDescription(
        key="charger",
        name="Charger",
        icon="mdi:ev-plug-type2",
        value_fn=lambda s: _loc(s, "charger_name"),
    ),
    TapSensorDescription(
        key="operator",
        name="Operator",
        icon="mdi:domain",
        value_fn=lambda s: _loc(s, "operator_name"),
    ),
    TapSensorDescription(
        key="location",
        name="Location",
        icon="mdi:map-marker",
        value_fn=lambda s: (
            ", ".join(p for p in (_loc(s, "address"), _loc(s, "city")) if p) or None
        ),
    ),
    TapSensorDescription(
        key="started",
        name="Session start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=_start,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TapCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        TapSensor(coordinator, entry, description) for description in SENSORS
    )


class TapSensor(CoordinatorEntity[TapCoordinator], SensorEntity):
    """A sensor reflecting the primary active charging session."""

    _attr_has_entity_name = True
    entity_description: TapSensorDescription

    def __init__(
        self,
        coordinator: TapCoordinator,
        entry: ConfigEntry,
        description: TapSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Tap Electric",
            manufacturer="Tap Electric",
            model="Charging session",
        )

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
