"""Select entities for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MACROS, DOMAIN, LAMP_MODE_CODES, LAMP_MODE_UNKNOWN, LAMP_MODES
from .coordinator import NecCinemaConfigEntry, NecCinemaCoordinator
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
    entry: NecCinemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        NecMacroSelect(coordinator, entry),
    ]
    if coordinator.has_lamp_mode:
        entities.append(NecLampModeSelect(coordinator))
    async_add_entities(entities)


class NecMacroSelect(NecCinemaEntity, SelectEntity):
    """Pick a preset (macro) key by the name the projector gave it.

    The protocol offers no way to list the preset keys, so the names are
    learned: every time a different title becomes active, whether through this
    integration, the touch panel or a theatre management system, the name and
    its preset number are recorded. Names configured by hand in the integration
    options take precedence.
    """

    def __init__(self, coordinator: NecCinemaCoordinator, entry: NecCinemaConfigEntry) -> None:
        """Initialise the select."""
        super().__init__(coordinator, "macro")
        self._entry = entry

    @property
    def _macros(self) -> dict[int, str]:
        """Return the known preset keys, hand written names winning."""
        macros = self.coordinator.learned_macros
        macros.update(parse_macros(self._entry.options.get(CONF_MACROS)))
        return macros

    @property
    def options(self) -> list[str]:
        """Return the preset names known so far."""
        macros = self._macros
        return [macros[key] for key in sorted(macros)]

    @property
    def current_option(self) -> str | None:
        """Return the preset the projector reports for the current title."""
        return self._macros.get(self.coordinator.data.preset_number or 0)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        """Expose the preset number behind the current name."""
        return {"preset_number": self.coordinator.data.preset_number}

    async def async_select_option(self, option: str) -> None:
        """Press the matching preset key."""
        number = next((key for key, label in self._macros.items() if label == option), None)
        if number is None:
            raise HomeAssistantError(f"Unknown macro: {option}")
        await self.async_run_command("select_macro", number)


# Process statuses in which a lamp is lit or being lit.
LAMP_LIT_STATUSES = frozenset({"ignition", "running_light_on", "lamp_retry"})


class NecLampModeSelect(NecCinemaEntity, SelectEntity):
    """Which lamp a dual lamp head runs on.

    Useful when the two bulbs have aged apart: run on the healthier one until
    the other is replaced. The projector only accepts a change while the lamp
    is off; with a lamp lit it answers 02H 03H.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(LAMP_MODES.values())

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the select."""
        super().__init__(coordinator, "lamp_mode")

    @property
    def current_option(self) -> str | None:
        """Return the lamp mode the projector reports."""
        mode = self.coordinator.data.lamp_mode
        return None if mode == LAMP_MODE_UNKNOWN else mode

    async def async_select_option(self, option: str) -> None:
        """Set the lamp mode, which the projector allows only with the lamp off."""
        data = self.coordinator.data
        if data.light_on or data.process_status in LAMP_LIT_STATUSES:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="lamp_mode_lamp_on",
            )
        await self.async_run_command("set_lamp_mode", LAMP_MODE_CODES[option])
