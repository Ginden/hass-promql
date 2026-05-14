"""Config flow for PromQL integration."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_PROMETHEUS_URL, CONF_QUERY, CONF_UNIT, DOMAIN


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
            except (aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url,
                    data={CONF_PROMETHEUS_URL: url},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PROMETHEUS_URL): str,
            }),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {"sensor": PromQLSensorSubentryFlow}


class PromQLSensorSubentryFlow(ConfigSubentryFlow):
    """Handle adding and reconfiguring a PromQL sensor subentry."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_QUERY: user_input[CONF_QUERY],
                    CONF_UNIT: user_input.get(CONF_UNIT, ""),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_QUERY): str,
                vol.Optional(CONF_UNIT, default=""): str,
            }),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME],
                data={
                    CONF_QUERY: user_input[CONF_QUERY],
                    CONF_UNIT: user_input.get(CONF_UNIT, ""),
                },
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=subentry.title): str,
                vol.Required(CONF_QUERY, default=subentry.data[CONF_QUERY]): str,
                vol.Optional(CONF_UNIT, default=subentry.data.get(CONF_UNIT, "")): str,
            }),
        )
