"""PromQL data update coordinator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_QUERY_TIMEOUT = aiohttp.ClientTimeout(total=10)


class PromQLCoordinator(DataUpdateCoordinator[dict[str, str | None]]):
    """Fetches PromQL query results for all configured sensors."""

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
        self.config_entry_id = entry.entry_id
        self._entry = entry

    async def _async_update_data(self) -> dict[str, str | None]:
        queries = self._entry.options.get(CONF_QUERIES, [])
        if not isinstance(queries, list) or not queries:
            return {}

        session = async_get_clientsession(self.hass)

        async def _fetch(query_config: dict[str, Any]) -> tuple[str, str | None]:
            query_id: str = query_config[CONF_QUERY_ID]
            query: str = query_config[CONF_QUERY]
            try:
                async with session.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=_QUERY_TIMEOUT,
                ) as resp:
                    payload: dict[str, Any] = await resp.json()
                    if resp.status != 200 or payload.get("status") != "success":
                        _LOGGER.warning(
                            "Prometheus query failed for %s: %s",
                            query_id,
                            _prometheus_error(payload, resp.status),
                        )
                        return query_id, None
                    return query_id, _extract_scalar(payload)
            except (TimeoutError, aiohttp.ClientError) as err:
                _LOGGER.warning("Prometheus query failed for %s: %s", query_id, err)
                return query_id, None

        pairs = await asyncio.gather(
            *(
                _fetch(query_config)
                for query_config in queries
                if _is_query_config(query_config)
            )
        )
        return dict(pairs)


def _extract_scalar(payload: dict[str, Any]) -> str | None:
    """Extract a single value from a Prometheus instant query response."""
    try:
        result_type: str = payload["data"]["resultType"]
        if result_type == "scalar":
            value = payload["data"]["result"][1]
            return value if isinstance(value, str) else None
        if result_type == "vector":
            results = payload["data"]["result"]
            if len(results) == 1:
                value = results[0]["value"][1]
                return value if isinstance(value, str) else None
    except KeyError, IndexError, TypeError:
        pass
    return None


def _prometheus_error(payload: dict[str, Any], status: int) -> str:
    """Return a readable Prometheus API error."""
    error = payload.get("error")
    if isinstance(error, str):
        return error
    error_type = payload.get("errorType")
    if isinstance(error_type, str):
        return error_type
    return f"HTTP {status}"


def _is_query_config(value: Any) -> bool:
    """Return whether a value is a valid stored query config."""
    return (
        isinstance(value, Mapping)
        and isinstance(value.get(CONF_QUERY_ID), str)
        and isinstance(value.get(CONF_QUERY), str)
    )
