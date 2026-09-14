"""Media player entity representing the projector head."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LENS_AXES
from .coordinator import NecCinemaCoordinator
from .entity import NecCinemaEntity

SERVICE_SELECT_TITLE = "select_title"
SERVICE_SELECT_MACRO = "select_macro"
SERVICE_LENS_CONTROL = "lens_control"
SERVICE_PICTURE_MUTE = "picture_mute"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NecProjectorMediaPlayer(coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SELECT_TITLE,
        {vol.Required("title"): vol.All(vol.Coerce(int), vol.Range(min=0, max=99))},
        "async_select_title",
    )
    platform.async_register_entity_service(
        SERVICE_SELECT_MACRO,
        {vol.Required("macro"): vol.All(vol.Coerce(int), vol.Range(min=1, max=20))},
        "async_select_macro",
    )
    platform.async_register_entity_service(
        SERVICE_LENS_CONTROL,
        {
            vol.Required("axis"): vol.In(list(LENS_AXES)),
            vol.Required("direction"): vol.In(["plus", "minus"]),
            vol.Optional("duration", default=0.25): vol.All(
                vol.Coerce(float), vol.In([0.25, 0.5, 1.0])
            ),
        },
        "async_lens_control",
    )
    platform.async_register_entity_service(
        SERVICE_PICTURE_MUTE,
        {vol.Required("enabled"): cv.boolean},
        "async_picture_mute",
    )


class NecProjectorMediaPlayer(NecCinemaEntity, MediaPlayerEntity):
    """The projector as a media player."""

    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the media player."""
        super().__init__(coordinator, "projector")
        self._attr_translation_key = None

    @property
    def available(self) -> bool:
        """Stay available while unreachable so the state can be shown as off."""
        return True

    @property
    def state(self) -> MediaPlayerState:
        """Return on when the projector is powered, off otherwise."""
        data = self.coordinator.data
        if not data.available:
            return MediaPlayerState.OFF
        return MediaPlayerState.ON if data.power_on else MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        """Return the installed input ports."""
        return list(self.coordinator.source_map)

    @property
    def source(self) -> str | None:
        """Return the port currently selected."""
        return self.coordinator.data.port

    @property
    def media_title(self) -> str | None:
        """Return the title currently loaded on the projector."""
        return self.coordinator.data.title_name or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the details that do not deserve their own entity."""
        data = self.coordinator.data
        return {
            "process_status": data.process_status,
            "light_on": data.light_on,
            "douser_closed": data.douser_closed,
            "picture_mute": data.picture_mute,
            "test_pattern": data.test_pattern,
            "title_number": data.title_number,
            "preset_number": data.preset_number,
            "external_control": data.external_control,
        }

    # --------------------------------------------------------------- commands

    async def async_turn_on(self) -> None:
        """Power the projector on, clearing any forced light mode first."""
        await self.coordinator.async_reset_light_mode()
        await self.async_run_command("power_on")

    async def async_turn_off(self) -> None:
        """Power the projector off and clear any forced light mode."""
        await self.async_run_command("power_off")
        await self.coordinator.async_reset_light_mode()

    async def async_select_source(self, source: str) -> None:
        """Switch the input port."""
        code = self.coordinator.source_map.get(source)
        if code is None:
            raise HomeAssistantError(f"Unknown source: {source}")
        await self.async_run_command("select_port", code)

    async def async_select_title(self, title: int) -> None:
        """Select a title from the projector's title list."""
        await self.async_run_command("select_title", title)

    async def async_select_macro(self, macro: int) -> None:
        """Press one of the preset (macro) keys."""
        await self.async_run_command("select_macro", macro)

    async def async_picture_mute(self, enabled: bool) -> None:
        """Blank or unblank the picture electronically."""
        await self.async_run_command("picture_mute_on" if enabled else "picture_mute_off")

    async def async_lens_control(self, axis: str, direction: str, duration: float) -> None:
        """Nudge zoom, focus or lens shift."""
        steps = {0.25: 0x03, 0.5: 0x02, 1.0: 0x01}
        value = steps[duration]
        if direction == "minus":
            value = {0x03: 0xFD, 0x02: 0xFE, 0x01: 0xFF}[value]
        await self.async_run_command("lens_control", axis, value)
