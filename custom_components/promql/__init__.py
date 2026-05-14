"""PromQL integration for Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import PromQLCoordinator

PLATFORMS = [Platform.SENSOR]

type PromQLConfigEntry = ConfigEntry[PromQLCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PromQLConfigEntry) -> bool:
    """Set up PromQL from a config entry."""
    coordinator = PromQLCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        entry.add_update_listener(
            lambda hass, entry: hass.config_entries.async_schedule_reload(entry.entry_id)
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PromQLConfigEntry) -> bool:
    """Unload a PromQL config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
