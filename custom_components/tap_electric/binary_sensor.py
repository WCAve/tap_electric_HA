"""Binary sensor: is a charging session currently active."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TapCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TapChargingBinarySensor(coordinator, entry)])


class TapChargingBinarySensor(CoordinatorEntity[TapCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: TapCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_charging"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Tap Electric",
            manufacturer="Tap Electric",
            model="Charging session",
        )

    @property
    def is_on(self) -> bool:
        sessions = self.coordinator.data.get("active_sessions") or []
        return any(s.get("is_active") for s in sessions)
