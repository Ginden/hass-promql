"""Config flow for PromQL integration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import slugify

from .const import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_NONE,
    AUTH_TYPES,
    CONF_AUTH_TYPE,
    CONF_DEVICE_CLASS,
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_SCAN_INTERVAL,
    CONF_STATE_CLASS,
    CONF_TOKEN,
    CONF_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATE_CLASS,
    DOMAIN,
    STATE_CLASS_NONE,
)
from .coordinator import PromQLCoordinator, _request_auth_kwargs

type QueryConfig = dict[str, str]


class PromQLConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial Prometheus connection setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_PROMETHEUS_URL].strip().rstrip("/")
            creds, errors = _validate_credentials(user_input)
            if not errors:
                errors = await _validate_connection(self.hass, url, creds)

            if not errors:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url,
                    data=_build_entry_data(url, creds, user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow editing the Prometheus URL, credentials, and scan interval."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_PROMETHEUS_URL].strip().rstrip("/")
            creds, errors = _validate_credentials(user_input)
            if not errors:
                errors = await _validate_connection(self.hass, url, creds)

            if not errors:
                await self.async_set_unique_id(url)
                if url != entry.unique_id:
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=url,
                    title=url,
                    data=_build_entry_data(url, creds, user_input),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(),
                user_input if user_input is not None else entry.data,
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
        menu_options.append("test_query")
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_test_query(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run an arbitrary PromQL expression against the entry's Prometheus."""
        default_query = user_input[CONF_QUERY].strip() if user_input else "1"
        placeholders = {"result": "No query run yet."}
        errors: dict[str, str] = {}

        if user_input is not None:
            if not default_query:
                errors[CONF_QUERY] = "required"
            elif self._config_entry.state is not ConfigEntryState.LOADED:
                errors["base"] = "entry_not_loaded"
            else:
                coordinator: PromQLCoordinator = self._config_entry.runtime_data
                result = await coordinator.async_query(default_query)
                placeholders["result"] = _format_query_result(result)

        return self.async_show_form(
            step_id="test_query",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUERY, default=default_query): TextSelector(
                        TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

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
                    CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS, ""),
                    CONF_STATE_CLASS: user_input.get(
                        CONF_STATE_CLASS, DEFAULT_STATE_CLASS
                    ),
                }
                return self._save_queries([*self._queries, query_config])

        return self.async_show_form(
            step_id="add_sensor",
            data_schema=self.add_suggested_values_to_schema(
                _sensor_schema(), user_input
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
                    vol.Required(CONF_QUERY_ID): _dropdown(
                        _query_selector(self._queries)
                    ),
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
                    CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS, ""),
                    CONF_STATE_CLASS: user_input.get(
                        CONF_STATE_CLASS, DEFAULT_STATE_CLASS
                    ),
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
            data_schema=self.add_suggested_values_to_schema(
                _sensor_schema(),
                user_input if user_input is not None else query_config,
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
                    vol.Required(CONF_QUERY_ID): _dropdown(
                        _query_selector(self._queries)
                    ),
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
                    CONF_DEVICE_CLASS: item.get(CONF_DEVICE_CLASS, "")
                    if isinstance(item.get(CONF_DEVICE_CLASS), str)
                    else "",
                    CONF_STATE_CLASS: item.get(CONF_STATE_CLASS, DEFAULT_STATE_CLASS)
                    if isinstance(item.get(CONF_STATE_CLASS), str)
                    else DEFAULT_STATE_CLASS,
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
    name_counts = Counter(query[CONF_NAME] for query in queries)
    return {
        query[CONF_QUERY_ID]: (
            f"{query[CONF_NAME]} ({query[CONF_QUERY_ID]})"
            if name_counts[query[CONF_NAME]] > 1
            else query[CONF_NAME]
        )
        for query in queries
    }


def _dropdown(options: dict[str, str]) -> SelectSelector:
    """Use a searchable dropdown with readable, sorted labels."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=value, label=label)
                for value, label in options.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
            sort=True,
        )
    )


def _sensor_schema() -> vol.Schema:
    """Share form controls between creating and editing sensors."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_QUERY): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(CONF_UNIT, default=""): str,
            vol.Optional(CONF_DEVICE_CLASS, default=""): _dropdown(
                _device_class_selector()
            ),
            vol.Optional(CONF_STATE_CLASS, default=DEFAULT_STATE_CLASS): SelectSelector(
                SelectSelectorConfig(
                    options=[STATE_CLASS_NONE, *SensorStateClass],
                    translation_key=CONF_STATE_CLASS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _device_class_selector() -> dict[str, str]:
    """Return sensor device class values mapped to display labels."""
    return {"": "None"} | {
        device_class.value: device_class.value.replace("_", " ").title()
        for device_class in SensorDeviceClass
    }


def _find_query(queries: list[QueryConfig], query_id: str | None) -> QueryConfig | None:
    """Find a query by ID."""
    for query in queries:
        if query[CONF_QUERY_ID] == query_id:
            return query
    return None


def _connection_schema() -> vol.Schema:
    """Return the schema for the URL/credentials/scan interval form."""
    password_input = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    return vol.Schema(
        {
            vol.Required(CONF_PROMETHEUS_URL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(
                CONF_AUTH_TYPE,
                default=AUTH_TYPE_NONE,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(AUTH_TYPES),
                    translation_key=CONF_AUTH_TYPE,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_USERNAME,
                default="",
            ): str,
            vol.Optional(
                CONF_PASSWORD,
                default="",
            ): password_input,
            vol.Optional(
                CONF_TOKEN,
                default="",
            ): password_input,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=DEFAULT_SCAN_INTERVAL,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


type Credentials = dict[str, str]


def _validate_credentials(
    user_input: Mapping[str, Any],
) -> tuple[Credentials, dict[str, str]]:
    """Return normalized credential fields plus any form errors."""
    auth_type = user_input.get(CONF_AUTH_TYPE, AUTH_TYPE_NONE)
    if auth_type == AUTH_TYPE_BASIC:
        username = (user_input.get(CONF_USERNAME) or "").strip()
        password = user_input.get(CONF_PASSWORD) or ""
        if not username:
            return {}, {CONF_USERNAME: "required"}
        return (
            {
                CONF_AUTH_TYPE: AUTH_TYPE_BASIC,
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
            },
            {},
        )
    if auth_type == AUTH_TYPE_BEARER:
        token = (user_input.get(CONF_TOKEN) or "").strip()
        if not token:
            return {}, {CONF_TOKEN: "required"}
        return {CONF_AUTH_TYPE: AUTH_TYPE_BEARER, CONF_TOKEN: token}, {}
    return {CONF_AUTH_TYPE: AUTH_TYPE_NONE}, {}


def _build_entry_data(
    url: str, creds: Credentials, user_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the data dict stored on the config entry."""
    return {
        CONF_PROMETHEUS_URL: url,
        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        **creds,
    }


def _format_query_result(result: Mapping[str, Any]) -> str:
    """Render a coordinator query result for display in the test-query form."""
    if result.get("status") == "success":
        raw = result.get("raw_value")
        if raw is None:
            return (
                "No sensor value. Return a scalar or exactly one time series; "
                "check the label filters or aggregate with sum() or avg()."
            )
        if result.get("value") is None:
            return f"No finite numeric value ({raw}). The sensor will be unavailable."
        return f"OK: {raw}"
    return f"Error: {result.get('error') or 'unknown error'}"


async def _validate_connection(
    hass: HomeAssistant, url: str, creds: Mapping[str, Any]
) -> dict[str, str]:
    """Probe the Prometheus instance and return form errors, if any."""
    try:
        session = async_get_clientsession(hass)
        async with session.get(
            f"{url}/api/v1/query",
            params={"query": "1"},
            timeout=aiohttp.ClientTimeout(total=5),
            **_request_auth_kwargs(creds),
        ) as resp:
            if resp.status in (401, 403):
                return {"base": "invalid_auth"}
            resp.raise_for_status()
            data = await resp.json()
            if data.get("status") != "success":
                return {"base": "cannot_connect"}
    except TimeoutError, aiohttp.ClientError, ValueError:
        return {"base": "cannot_connect"}
    return {}
