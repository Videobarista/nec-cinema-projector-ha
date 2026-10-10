"""Binary sensor entities for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NecCinemaConfigEntry, NecCinemaCoordinator
from .entity import NecCinemaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NecCinemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        NecLightOn(coordinator),
        NecProblem(coordinator),
        NecTestPattern(coordinator),
        NecImbSelected(coordinator),
        NecConnectivity(coordinator),
    ]
    if coordinator.lamp_details:
        entities.extend([NecLampLit(coordinator, 1), NecLampLit(coordinator, 2)])
    async_add_entities(entities)


class NecLightOn(NecCinemaEntity, BinarySensorEntity):
    """Whether the lamp or laser light source is lit."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "light_on")

    @property
    def is_on(self) -> bool:
        """Return whether the light source is on."""
        return self.coordinator.data.light_on


class NecLampLit(NecCinemaEntity, BinarySensorEntity):
    """Whether one lamp of a dual lamp head is lit."""

    def __init__(self, coordinator: NecCinemaCoordinator, lamp: int) -> None:
        """Initialise the sensor for lamp 1 or lamp 2."""
        super().__init__(coordinator, f"lamp{lamp}_on")
        self._lamp = lamp

    @property
    def is_on(self) -> bool | None:
        """Return whether this lamp is lit."""
        data = self.coordinator.data
        return data.lamp1_on if self._lamp == 1 else data.lamp2_on


class NecProblem(NecCinemaEntity, BinarySensorEntity):
    """Whether the projector reports any error."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool:
        """Return whether errors are active."""
        return bool(self.coordinator.data.errors)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Return the error messages."""
        return {"messages": self.coordinator.data.errors}


class NecTestPattern(NecCinemaEntity, BinarySensorEntity):
    """Whether a test pattern is on screen."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "test_pattern")

    @property
    def is_on(self) -> bool:
        """Return whether a test pattern is displayed."""
        return self.coordinator.data.test_pattern


class NecImbSelected(NecCinemaEntity, BinarySensorEntity):
    """Whether the media block port is the active input."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "imb_selected")

    @property
    def is_on(self) -> bool:
        """Return whether the IMB/IMS port is selected."""
        return self.coordinator.data.port == "IMB"


class NecConnectivity(NecCinemaEntity, BinarySensorEntity):
    """Whether the control port answers."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "connectivity")

    @property
    def available(self) -> bool:
        """Remain available while the projector is unreachable."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the projector answered the last poll."""
        return self.coordinator.data.available
