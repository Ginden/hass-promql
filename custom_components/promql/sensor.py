"""PromQL sensor platform."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_QUERIES, CONF_QUERY, CONF_QUERY_ID, CONF_UNIT, DOMAIN
from .coordinator import PromQLCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PromQL sensors from config entry options."""
    coordinator: PromQLCoordinator = entry.runtime_data
    async_add_entities(
        PromQLSensor(coordinator, query_config)
        for query_config in _query_configs(entry.options)
    )


class PromQLSensor(CoordinatorEntity[PromQLCoordinator], SensorEntity):
    """Sensor entity backed by a PromQL expression."""

    _attr_icon = "mdi:chart-line"

    def __init__(
        self, coordinator: PromQLCoordinator, query_config: dict[str, str]
    ) -> None:
        super().__init__(coordinator)
        self._query_id = query_config[CONF_QUERY_ID]
        self._attr_unique_id = f"{coordinator.config_entry_id}_{self._query_id}"
        self._attr_name = query_config[CONF_NAME]
        unit = query_config.get(CONF_UNIT, "")
        self._attr_native_unit_of_measurement = unit or None
        self._attr_state_class = SensorStateClass.MEASUREMENT if unit else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry_id)},
            name=coordinator.prometheus_url,
            manufacturer="Prometheus",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._query_id)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError, TypeError:
            return raw


def _query_configs(options: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return well-formed query configs from options."""
    queries = options.get(CONF_QUERIES, [])
    if not isinstance(queries, list):
        return []

    result: list[dict[str, str]] = []
    for item in queries:
        if (
            isinstance(item, Mapping)
            and isinstance(item.get(CONF_QUERY_ID), str)
            and isinstance(item.get(CONF_NAME), str)
            and isinstance(item.get(CONF_QUERY), str)
        ):
            result.append(
                {
                    CONF_QUERY_ID: item[CONF_QUERY_ID],
                    CONF_NAME: item[CONF_NAME],
                    CONF_QUERY: item[CONF_QUERY],
                    CONF_UNIT: item.get(CONF_UNIT, "")
                    if isinstance(item.get(CONF_UNIT), str)
                    else "",
                }
            )
    return result
