"""Read-only native integration. No live command transport is installed."""

from homeassistant.const import Platform

from .coordinator import ManagerCoordinator
from .services import async_register, async_unregister

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    coordinator = ManagerCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_listen()
    async_register(hass, coordinator)
    entry.async_on_unload(entry.add_update_listener(async_reload))
    return True


async def async_reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_save()
        async_unregister(hass)
        return True
    return False
