"""Config flow for PromQL integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .const import (
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_SCAN_INTERVAL,
    CONF_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

type QueryConfig = dict[str, str]


class PromQLConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial Prometheus connection setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_PROMETHEUS_URL].rstrip("/")
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(
                    f"{url}/api/v1/query",
                    params={"query": "1"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if data.get("status") != "success":
                        errors["base"] = "cannot_connect"
            except TimeoutError, aiohttp.ClientError:
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url,
                    data={
                        CONF_PROMETHEUS_URL: url,
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROMETHEUS_URL): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(int, vol.Range(min=5)),
                }
            ),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_options_flow(cls, config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return PromQLOptionsFlow(config_entry)


class PromQLOptionsFlow(OptionsFlow):
    """Manage PromQL sensor definitions stored on the config entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._queries = _queries_from_options(config_entry.options)
        self._selected_query_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the PromQL sensor management menu."""
        menu_options = ["add_sensor"]
        if self._queries:
            menu_options.extend(("edit_sensor", "delete_sensor"))
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_add_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a PromQL sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            query = user_input[CONF_QUERY].strip()
            if not name:
                errors[CONF_NAME] = "required"
            if not query:
                errors[CONF_QUERY] = "required"
            if not errors:
                query_config = {
                    CONF_QUERY_ID: _new_query_id(name, self._queries),
                    CONF_NAME: name,
                    CONF_QUERY: query,
                    CONF_UNIT: user_input.get(CONF_UNIT, "").strip(),
                }
                return self._save_queries([*self._queries, query_config])

        return self.async_show_form(
            step_id="add_sensor",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_QUERY): str,
                    vol.Optional(CONF_UNIT, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_edit_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a PromQL sensor to edit."""
        if user_input is not None:
            self._selected_query_id = user_input[CONF_QUERY_ID]
            return await self.async_step_edit_sensor_details()

        return self.async_show_form(
            step_id="edit_sensor",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUERY_ID): vol.In(_query_selector(self._queries)),
                }
            ),
        )

    async def async_step_edit_sensor_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a PromQL sensor."""
        query_config = _find_query(self._queries, self._selected_query_id)
        if query_config is None:
            return self.async_abort(reason="query_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            query = user_input[CONF_QUERY].strip()
            if not name:
                errors[CONF_NAME] = "required"
            if not query:
                errors[CONF_QUERY] = "required"
            if not errors:
                updated_query = {
                    CONF_QUERY_ID: query_config[CONF_QUERY_ID],
                    CONF_NAME: name,
                    CONF_QUERY: query,
                    CONF_UNIT: user_input.get(CONF_UNIT, "").strip(),
                }
                return self._save_queries(
                    [
                        updated_query
                        if item[CONF_QUERY_ID] == query_config[CONF_QUERY_ID]
                        else item
                        for item in self._queries
                    ]
                )

        return self.async_show_form(
            step_id="edit_sensor_details",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=query_config[CONF_NAME]): str,
                    vol.Required(CONF_QUERY, default=query_config[CONF_QUERY]): str,
                    vol.Optional(
                        CONF_UNIT, default=query_config.get(CONF_UNIT, "")
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_delete_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a PromQL sensor."""
        if user_input is not None:
            query_id = user_input[CONF_QUERY_ID]
            return self._save_queries(
                [
                    query_config
                    for query_config in self._queries
                    if query_config[CONF_QUERY_ID] != query_id
                ]
            )

        return self.async_show_form(
            step_id="delete_sensor",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUERY_ID): vol.In(_query_selector(self._queries)),
                }
            ),
        )

    def _save_queries(self, queries: list[QueryConfig]) -> ConfigFlowResult:
        """Persist the query list."""
        return self.async_create_entry(
            title="",
            data={
                **self._config_entry.options,
                CONF_QUERIES: queries,
            },
        )


def _queries_from_options(options: Mapping[str, Any]) -> list[QueryConfig]:
    """Return well-formed query configs from options."""
    queries = options.get(CONF_QUERIES, [])
    if not isinstance(queries, list):
        return []

    result: list[QueryConfig] = []
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


def _new_query_id(name: str, queries: list[QueryConfig]) -> str:
    """Return a stable ID for a new query."""
    used_ids = {query[CONF_QUERY_ID] for query in queries}
    base = slugify(name) or "sensor"
    query_id = base
    suffix = 2
    while query_id in used_ids:
        query_id = f"{base}_{suffix}"
        suffix += 1
    return query_id


def _query_selector(queries: list[QueryConfig]) -> dict[str, str]:
    """Return query IDs mapped to display names for form selectors."""
    return {query[CONF_QUERY_ID]: query[CONF_NAME] for query in queries}


def _find_query(queries: list[QueryConfig], query_id: str | None) -> QueryConfig | None:
    """Find a query by ID."""
    for query in queries:
        if query[CONF_QUERY_ID] == query_id:
            return query
    return None
