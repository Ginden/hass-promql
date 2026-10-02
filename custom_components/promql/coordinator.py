"""PromQL data update coordinator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from math import isfinite
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_NONE,
    CONF_AUTH_TYPE,
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_QUERY_TIMEOUT = aiohttp.ClientTimeout(total=10)
_MAX_CONCURRENT_QUERIES = 4

type QueryResult = dict[str, Any]


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
            always_update=False,
        )
        self.prometheus_url = entry.data[CONF_PROMETHEUS_URL].rstrip("/")
        self.config_entry_id = entry.entry_id
        self._auth_kwargs = _request_auth_kwargs(entry.data)

    async def async_query(self, query: str) -> QueryResult:
        """Run a single PromQL query and return a structured result."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=_QUERY_TIMEOUT,
                **self._auth_kwargs,
            ) as resp:
                payload: dict[str, Any] = await resp.json()
                if resp.status != 200 or payload.get("status") != "success":
                    return _error_result(_prometheus_error(payload, resp.status))
                raw = _extract_scalar(payload)
                return _success_result(raw)
        except (TimeoutError, aiohttp.ClientError) as err:
            return _error_result(str(err) or err.__class__.__name__)
        except ValueError:
            return _error_result("Prometheus returned invalid JSON")

    async def _async_update_data(self) -> dict[str, str | None]:
        assert self.config_entry is not None
        queries = self.config_entry.options.get(CONF_QUERIES, [])
        if not isinstance(queries, list) or not queries:
            return {}

        active_query_ids = set(self.async_contexts())
        query_ids_by_expression: dict[str, list[str]] = {}
        for query_config in queries:
            if not _is_query_config(query_config):
                continue
            query_id = query_config[CONF_QUERY_ID]
            if active_query_ids and query_id not in active_query_ids:
                continue
            query_ids_by_expression.setdefault(query_config[CONF_QUERY], []).append(
                query_id
            )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_QUERIES)

        async def _fetch(
            expression: str, query_ids: list[str]
        ) -> dict[str, str | None]:
            async with semaphore:
                result = await self.async_query(expression)
            if result["status"] != "success":
                _LOGGER.warning(
                    "Prometheus query failed for %s: %s",
                    ", ".join(query_ids),
                    result["error"],
                )
            return dict.fromkeys(query_ids, result["raw_value"])

        results = await asyncio.gather(
            *(
                _fetch(expression, query_ids)
                for expression, query_ids in query_ids_by_expression.items()
            )
        )
        return {
            query_id: value for result in results for query_id, value in result.items()
        }


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


def _request_auth_kwargs(data: Mapping[str, Any]) -> dict[str, Any]:
    """Translate stored credentials into aiohttp request kwargs."""
    auth_type = data.get(CONF_AUTH_TYPE, AUTH_TYPE_NONE)
    if auth_type == AUTH_TYPE_BASIC:
        return {
            "auth": aiohttp.BasicAuth(
                data.get(CONF_USERNAME, ""),
                data.get(CONF_PASSWORD, ""),
            )
        }
    if auth_type == AUTH_TYPE_BEARER:
        return {"headers": {"Authorization": f"Bearer {data.get(CONF_TOKEN, '')}"}}
    return {}


def _success_result(raw: str | None) -> QueryResult:
    """Build a success result from the Prometheus raw scalar string."""
    value: float | None
    try:
        value = float(raw) if raw is not None else None
    except ValueError:
        value = None
    if value is not None and not isfinite(value):
        value = None
    return {
        "status": "success",
        "value": value,
        "raw_value": raw,
        "error": None,
    }


def _error_result(error: str) -> QueryResult:
    """Build an error result with a readable message."""
    return {
        "status": "error",
        "value": None,
        "raw_value": None,
        "error": error,
    }
