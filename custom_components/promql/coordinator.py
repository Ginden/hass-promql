"""PromQL data update coordinator."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_PROMETHEUS_URL,
    CONF_QUERY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_QUERY_TIMEOUT = aiohttp.ClientTimeout(total=10)


class PromQLCoordinator(DataUpdateCoordinator[dict[str, str | None]]):
    """Fetches PromQL query results for all sensor subentries."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            config_entry=entry,
        )
        self.prometheus_url = entry.data[CONF_PROMETHEUS_URL].rstrip("/")

    async def _async_update_data(self) -> dict[str, str | None]:
        sensor_subentries = [
            s
            for s in self.config_entry.subentries.values()
            if s.subentry_type == "sensor"
        ]
        if not sensor_subentries:
            return {}

        session = async_get_clientsession(self.hass)

        async def _fetch(subentry: Any) -> tuple[str, str | None]:
            query: str = subentry.data[CONF_QUERY]
            try:
                async with session.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=_QUERY_TIMEOUT,
                ) as resp:
                    resp.raise_for_status()
                    payload: dict[str, Any] = await resp.json()
                    return subentry.subentry_id, _extract_scalar(payload)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise UpdateFailed(f"Error querying Prometheus: {err}") from err

        pairs = await asyncio.gather(*(_fetch(s) for s in sensor_subentries))
        return dict(pairs)


def _extract_scalar(payload: dict[str, Any]) -> str | None:
    """Extract a single value from a Prometheus instant query response."""
    try:
        result_type: str = payload["data"]["resultType"]
        if result_type == "scalar":
            return payload["data"]["result"][1]
        if result_type == "vector":
            results = payload["data"]["result"]
            if len(results) == 1:
                return results[0]["value"][1]
    except (KeyError, IndexError, TypeError):
        pass
    return None
