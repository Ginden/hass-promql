"""PromQL integration for Home Assistant."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import PromQLCoordinator

PLATFORMS = [Platform.SENSOR]

type PromQLConfigEntry = ConfigEntry[PromQLCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_QUERY = "query"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_QUERY = "query"

_SERVICE_QUERY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUERY): cv.string,
    }
)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register PromQL services."""

    async def _handle_query(call: ServiceCall) -> ServiceResponse:
        entry_id: str = call.data[ATTR_CONFIG_ENTRY_ID]
        query: str = call.data[ATTR_QUERY]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_entry",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
            )
        coordinator: PromQLCoordinator = entry.runtime_data
        return await coordinator.async_query(query)

    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY,
        _handle_query,
        schema=_SERVICE_QUERY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PromQLConfigEntry) -> bool:
    """Set up PromQL from a config entry."""
    coordinator = PromQLCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PromQLConfigEntry) -> bool:
    """Unload a PromQL config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
