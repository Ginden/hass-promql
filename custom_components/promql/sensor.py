"""PromQL sensor platform."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_UNIT, DOMAIN
from .coordinator import PromQLCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up PromQL sensors from config entry subentries."""
    coordinator: PromQLCoordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type == "sensor":
            async_add_entities(
                [PromQLSensor(coordinator, subentry)],
                config_subentry_id=subentry.subentry_id,
            )


class PromQLSensor(CoordinatorEntity[PromQLCoordinator], SensorEntity):
    """Sensor entity backed by a PromQL expression."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: PromQLCoordinator, subentry: Any) -> None:
        super().__init__(coordinator)
        self._subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_name = None  # primary entity — display name comes from device
        unit: str = subentry.data.get(CONF_UNIT, "")
        self._attr_native_unit_of_measurement = unit or None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            model=coordinator.prometheus_url,
            manufacturer="Prometheus",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._subentry.subentry_id)
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return raw
