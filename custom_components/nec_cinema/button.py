"""Lens control buttons for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NecCinemaCoordinator
from .entity import NecCinemaEntity

# LENS CONTROL (053.) DATA02: 03H drives the motor for 0.25 s towards plus,
# FDH does the same towards minus. A short nudge per press is the useful
# granularity for a button; the lens_control action covers longer runs.
NUDGE_PLUS = 0x03
NUDGE_MINUS = 0xFD

LENS_BUTTONS: tuple[tuple[str, str, int], ...] = (
    ("lens_zoom_plus", "zoom", NUDGE_PLUS),
    ("lens_zoom_minus", "zoom", NUDGE_MINUS),
    ("lens_focus_plus", "focus", NUDGE_PLUS),
    ("lens_focus_minus", "focus", NUDGE_MINUS),
    ("lens_shift_h_plus", "shift_h", NUDGE_PLUS),
    ("lens_shift_h_minus", "shift_h", NUDGE_MINUS),
    ("lens_shift_v_plus", "shift_v", NUDGE_PLUS),
    ("lens_shift_v_minus", "shift_v", NUDGE_MINUS),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lens buttons."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [
        NecLensButton(coordinator, key, axis, value) for key, axis, value in LENS_BUTTONS
    ]
    entities.append(NecForgetMacrosButton(coordinator))
    async_add_entities(entities)


class NecLensButton(NecCinemaEntity, ButtonEntity):
    """Nudge one lens axis by a quarter of a second.

    The projector reports no lens position, so these are open loop: press,
    look at the screen, press again.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: NecCinemaCoordinator, key: str, axis: str, value: int
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, key)
        self._axis = axis
        self._value = value

    async def async_press(self) -> None:
        """Drive the lens motor briefly."""
        await self.async_run_command("lens_control", self._axis, self._value)


class NecForgetMacrosButton(NecCinemaEntity, ButtonEntity):
    """Drop the preset key names learned so far."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "forget_macros")

    async def async_press(self) -> None:
        """Clear the learned names so they are picked up again."""
        await self.coordinator.async_forget_macros()
