"""The Sharp NEC cinema projector integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .client import NecError, NecNakError
from .const import DOMAIN
from .coordinator import NecCinemaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a projector from a config entry."""
    coordinator = NecCinemaCoordinator(hass, entry)
    try:
        await coordinator.async_probe()
    except (NecError, NecNakError) as err:
        await coordinator.client.close()
        raise ConfigEntryNotReady(str(err)) from err

    await coordinator.async_config_entry_first_refresh()
    _remove_unsupported_lamp_sensors(hass, coordinator)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


def _remove_unsupported_lamp_sensors(
    hass: HomeAssistant, coordinator: NecCinemaCoordinator
) -> None:
    """Drop lamp output sensors this head cannot feed.

    Which lamp output command a head answers is decided at setup, so entities
    left behind by an earlier version would otherwise sit in the UI forever
    showing "unavailable".
    """
    keep = {
        "percent": {"light_power"},
        "watt": {"lamp_watt", "lamp_ampere", "lamp_volt"},
    }.get(coordinator.lamp_output_kind or "", set())
    stale = {"light_power", "lamp_watt", "lamp_ampere", "lamp_volt"} - keep

    registry = er.async_get(hass)
    for key in stale:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{coordinator.device_identifier}_{key}"
        )
        if entity_id:
            _LOGGER.debug("removing unsupported entity %s", entity_id)
            registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: NecCinemaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
