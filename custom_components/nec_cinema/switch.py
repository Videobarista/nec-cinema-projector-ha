"""Switch entities for the NEC cinema projector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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
    async_add_entities(
        [
            NecLightSwitch(coordinator),
            NecPictureMute(coordinator),
            NecDouserSwitch(coordinator),
        ]
    )


class NecLightSwitch(NecCinemaEntity, SwitchEntity):
    """Light the lamp or laser without cycling projector power.

    Uses LAMP CONTROL MODE SET (235-19), the only documented way to switch the
    light on its own. Note that switching it off puts the head in "light off
    mode": it stays off until this switch is turned on again, or the mode is
    put back to standard.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "light")

    @property
    def is_on(self) -> bool:
        """Return whether the light source is actually lit."""
        return self.coordinator.data.light_on

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the control mode the projector is in."""
        return {"light_control_mode": self.coordinator.data.light_mode}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Light the lamp or laser."""
        await self._set_mode("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Extinguish the lamp or laser."""
        await self._set_mode("off")

    async def _set_mode(self, mode: str) -> None:
        """Change the light control mode, and the standing choice with it.

        The switch and the Light control mode select drive the same setting, so
        the switch has to move the standing choice too. Leaving it behind would
        have the integration put the old mode back the next time the projector
        is starting or stopping.
        """
        try:
            await self.coordinator.async_set_desired_light_mode(mode)
        except NecNakError as err:
            raise HomeAssistantError(f"The projector refused the command: {err}") from err
        except NecError as err:
            raise HomeAssistantError(f"Could not reach the projector: {err}") from err


class NecPictureMute(NecCinemaEntity, SwitchEntity):
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
        await self.async_run_command("picture_mute_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Restore the picture."""
        await self.async_run_command("picture_mute_off")


class NecDouserSwitch(NecCinemaEntity, SwitchEntity):
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
        await self.async_run_command("douser_open")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Close the douser."""
        await self.async_run_command("douser_close")
