"""Media player entity representing the projector head."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NecCinemaConfigEntry, NecCinemaCoordinator
from .entity import NecCinemaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NecCinemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player.

    Its actions are registered once for the integration, in async_setup.
    """
    async_add_entities([NecProjectorMediaPlayer(entry.runtime_data)])


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
        """Power the projector on, keeping the light off if that was asked for.

        With "start dark" on, forced off is set just before the power command:
        the projector honours the light control mode at power-up when it was
        set shortly before.
        """
        await self.coordinator.async_prepare_dark_start()
        await self.async_run_command("power_on")

    async def async_turn_off(self) -> None:
        """Power the projector off."""
        await self.async_run_command("power_off")

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
