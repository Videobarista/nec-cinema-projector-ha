"""Switch entities for the NEC cinema projector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import NecError, NecNakError
from .const import DOMAIN
from .coordinator import NecCinemaCoordinator
from .entity import NecCinemaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NecPictureMute(coordinator), NecDouserSwitch(coordinator)])


class _NecSwitchBase(NecCinemaEntity, SwitchEntity):
    """Shared error handling."""

    async def _run(self, action: str) -> None:
        try:
            await self.coordinator.async_send(action)
        except NecNakError as err:
            raise HomeAssistantError(f"Projector refused the command: {err}") from err
        except NecError as err:
            raise HomeAssistantError(f"Projector communication failed: {err}") from err


class NecPictureMute(_NecSwitchBase):
    """Electronic picture mute (the douser stays where it is)."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "picture_mute")

    @property
    def is_on(self) -> bool | None:
        """Return whether the picture is blanked."""
        return self.coordinator.data.picture_mute

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Blank the picture."""
        await self._run("picture_mute_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Restore the picture."""
        await self._run("picture_mute_off")


class NecDouserSwitch(_NecSwitchBase):
    """The douser as a plain switch: on means open, light reaches the screen."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "douser_open")

    @property
    def is_on(self) -> bool | None:
        """Return whether the douser is open."""
        closed = self.coordinator.data.douser_closed
        return None if closed is None else not closed

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Open the douser."""
        await self._run("douser_open")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Close the douser."""
        await self._run("douser_close")
