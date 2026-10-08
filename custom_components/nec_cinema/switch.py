"""Switch entities for the NEC cinema projector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
            NecStartDarkSwitch(coordinator),
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
        """Light or extinguish the lamp now."""
        await self.async_guarded(self.coordinator.async_set_light, mode == "on")


class NecStartDarkSwitch(NecCinemaEntity, SwitchEntity):
    """Power the projector up without lighting the lamp.

    This is a preference for the next power-up, not a lamp control: turning it
    on or off never touches the lamp now.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "start_dark")

    @property
    def available(self) -> bool:
        """A preference can be changed whether or not the projector answers."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether power-ups start dark."""
        return self.coordinator.start_dark

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start dark from the next power-up on."""
        await self.coordinator.async_set_start_dark(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Light the lamp at power-up as usual."""
        await self.coordinator.async_set_start_dark(False)


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
