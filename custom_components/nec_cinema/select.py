"""Select entity for the projector's preset (macro) keys."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MACROS, DOMAIN, LIGHT_MODE_CODES, LIGHT_MODE_UNKNOWN, LIGHT_MODES
from .coordinator import NecCinemaCoordinator
from .entity import NecCinemaEntity


def parse_macros(raw: str | None) -> dict[int, str]:
    """Parse a macro definition such as "1: Flat, 2: Scope" into a mapping."""
    macros: dict[int, str] = {}
    for part in (raw or "").split(","):
        number, _, label = part.partition(":")
        number, label = number.strip(), label.strip()
        if not number.isdigit() or not label:
            continue
        index = int(number)
        if 1 <= index <= 20:
            macros[index] = label
    return macros


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the macro select, if any macros are configured."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = [NecLightModeSelect(coordinator)]
    macros = parse_macros(entry.options.get(CONF_MACROS))
    if macros:
        entities.append(NecMacroSelect(coordinator, macros))
    async_add_entities(entities)


class NecMacroSelect(NecCinemaEntity, SelectEntity):
    """Fire one of the preset keys by name."""

    def __init__(self, coordinator: NecCinemaCoordinator, macros: dict[int, str]) -> None:
        """Initialise the select."""
        super().__init__(coordinator, "macro")
        self._macros = macros
        self._attr_options = [macros[key] for key in sorted(macros)]

    @property
    def current_option(self) -> str | None:
        """Return the preset the projector reports for the current title."""
        return self._macros.get(self.coordinator.data.preset_number or 0)

    async def async_select_option(self, option: str) -> None:
        """Press the matching preset key."""
        number = next((key for key, label in self._macros.items() if label == option), None)
        if number is None:
            raise HomeAssistantError(f"Unknown macro: {option}")
        await self.async_run_command("select_macro", number)


class NecLightModeSelect(NecCinemaEntity, SelectEntity):
    """The light control mode: follow power, forced on, or forced off."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(LIGHT_MODES.values())

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the select."""
        super().__init__(coordinator, "light_mode")

    @property
    def current_option(self) -> str | None:
        """Return the mode the projector reports."""
        mode = self.coordinator.data.light_mode
        return None if mode == LIGHT_MODE_UNKNOWN else mode

    async def async_select_option(self, option: str) -> None:
        """Set the light control mode."""
        await self.async_run_command("set_light_mode", LIGHT_MODE_CODES[option])
