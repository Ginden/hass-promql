"""Regression tests for the PromQL configuration UI."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.promql.const import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
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
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://prometheus:9090",
        data={CONF_PROMETHEUS_URL: "http://prometheus:9090"},
        options={
            CONF_QUERIES: [
                {
                    CONF_QUERY_ID: "cpu",
                    CONF_NAME: "CPU",
                    CONF_QUERY: "cpu_usage",
                    CONF_UNIT: "%",
                    CONF_DEVICE_CLASS: "power_factor",
                    CONF_STATE_CLASS: "measurement",
                }
            ]
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_connection_error_preserves_entered_values(hass: HomeAssistant) -> None:
    user_input = {
        CONF_PROMETHEUS_URL: "http://prometheus:9090",
        CONF_AUTH_TYPE: AUTH_TYPE_BEARER,
        CONF_TOKEN: "example-token",
        CONF_SCAN_INTERVAL: 60,
    }
    with patch(
        "custom_components.promql.config_flow._validate_connection",
        return_value={"base": "cannot_connect"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=user_input
        )
    assert result["errors"] == {"base": "cannot_connect"}
    suggestions = {
        field.schema: field.description["suggested_value"]
        for field in result["data_schema"].schema
        if field.description and "suggested_value" in field.description
    }
    assert {key: suggestions[key] for key in user_input} == user_input


@pytest.mark.parametrize("step", ["add_sensor", "edit_sensor_details"])
async def test_sensor_errors_preserve_multiline_expression(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    step: str,
) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    if step == "edit_sensor_details":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "edit_sensor"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_QUERY_ID: "cpu"}
        )
    else:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": step}
        )
    expression = 'sum(\n  rate(requests_total{job="web"}[5m])\n)'
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME: " ", CONF_QUERY: expression, CONF_UNIT: "req/s"}
    )
    assert result["errors"] == {CONF_NAME: "required"}
    suggestions = {
        field.schema: field.description["suggested_value"]
        for field in result["data_schema"].schema
        if field.description and "suggested_value" in field.description
    }
    assert suggestions[CONF_QUERY] == expression
    assert suggestions[CONF_UNIT] == "req/s"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_NAME: "Requests", CONF_QUERY: expression, CONF_UNIT: "req/s"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    saved = next(q for q in entry.options[CONF_QUERIES] if q[CONF_NAME] == "Requests")
    assert saved[CONF_QUERY] == expression


async def test_edit_can_clear_optional_metadata_without_changing_identity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_sensor"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_QUERY_ID: "cpu"}
    )
    # The frontend omits optional fields when their suggested values are cleared.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_NAME: "Renamed", CONF_QUERY: "sum(cpu_usage)", CONF_STATE_CLASS: "none"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_QUERIES] == [
        {
            CONF_QUERY_ID: "cpu",
            CONF_NAME: "Renamed",
            CONF_QUERY: "sum(cpu_usage)",
            CONF_UNIT: "",
            CONF_DEVICE_CLASS: "",
            CONF_STATE_CLASS: "none",
        }
    ]


async def test_reconfigure_moves_server_and_clears_old_credentials(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_AUTH_TYPE: AUTH_TYPE_BASIC,
            CONF_USERNAME: "alice",
            CONF_PASSWORD: "old-password",
        },
    )
    with (
        patch(
            "custom_components.promql.config_flow._validate_connection", return_value={}
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PROMETHEUS_URL: " http://new-prometheus:9090/ ",
                CONF_AUTH_TYPE: AUTH_TYPE_BASIC,
                CONF_USERNAME: "alice",
                CONF_SCAN_INTERVAL: 45,
            },
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "http://new-prometheus:9090"
    assert entry.data[CONF_PROMETHEUS_URL] == entry.unique_id
    assert entry.data[CONF_PASSWORD] == ""
    assert entry.data[CONF_SCAN_INTERVAL] == 45
    assert entry.options[CONF_QUERIES][0][CONF_QUERY_ID] == "cpu"


async def test_reconfigure_rejects_another_configured_server(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://other:9090",
        data={CONF_PROMETHEUS_URL: "http://other:9090"},
    )
    other.add_to_hass(hass)
    with patch(
        "custom_components.promql.config_flow._validate_connection",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data={CONF_PROMETHEUS_URL: "http://other:9090"},
        )
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "http://prometheus:9090"


async def test_query_form_rejects_blank_input_and_unloaded_entry(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "test_query"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_QUERY: " \n "}
    )
    assert result["errors"] == {CONF_QUERY: "required"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_QUERY: "sum(up)"}
    )
    assert result["errors"] == {"base": "entry_not_loaded"}
