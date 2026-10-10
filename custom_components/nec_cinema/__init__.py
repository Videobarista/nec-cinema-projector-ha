"""The Sharp NEC cinema projector integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er, service
from homeassistant.helpers.typing import ConfigType

from .client import NecError
from .const import DOMAIN, LENS_AXES
from .coordinator import NecCinemaConfigEntry, NecCinemaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SELECT_TITLE = "select_title"
SERVICE_SELECT_MACRO = "select_macro"
SERVICE_LENS_CONTROL = "lens_control"
SERVICE_PICTURE_MUTE = "picture_mute"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, which act on the projector's media player."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SELECT_TITLE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={vol.Required("title"): vol.All(vol.Coerce(int), vol.Range(min=0, max=99))},
        func="async_select_title",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SELECT_MACRO,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={vol.Required("macro"): vol.All(vol.Coerce(int), vol.Range(min=1, max=20))},
        func="async_select_macro",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_LENS_CONTROL,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={
            vol.Required("axis"): vol.In(list(LENS_AXES)),
            vol.Required("direction"): vol.In(["plus", "minus"]),
            vol.Optional("duration", default=0.25): vol.All(
                vol.Coerce(float), vol.In([0.25, 0.5, 1.0])
            ),
        },
        func="async_lens_control",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_PICTURE_MUTE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={vol.Required("enabled"): cv.boolean},
        func="async_picture_mute",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NecCinemaConfigEntry) -> bool:
    """Set up a projector from a config entry.

    A projector that does not answer is set up from what it reported last
    time and shows as off until it does. Only one that has never answered
    keeps the entry waiting.
    """
    coordinator = NecCinemaCoordinator(hass, entry)
    try:
        await coordinator.async_probe()
    except NecError as err:
        await coordinator.client.close()
        raise ConfigEntryNotReady(str(err)) from err

    await coordinator.async_config_entry_first_refresh()
    _remove_unsupported_lamp_sensors(hass, coordinator)
    _remove_retired_entities(hass, coordinator)

    entry.runtime_data = coordinator
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


def _remove_retired_entities(hass: HomeAssistant, coordinator: NecCinemaCoordinator) -> None:
    """Drop entities that earlier versions created and this one no longer does.

    The Light control mode select was replaced in 1.11 by the Light source
    switch, for now, and the Start dark switch, for the next power-up.
    """
    registry = er.async_get(hass)
    for platform, key in (("select", "light_mode"),):
        entity_id = registry.async_get_entity_id(
            platform, DOMAIN, f"{coordinator.device_identifier}_{key}"
        )
        if entity_id:
            _LOGGER.debug("removing retired entity %s", entity_id)
            registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: NecCinemaConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: NecCinemaConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
