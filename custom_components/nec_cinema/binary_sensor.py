"""Binary sensor entities for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
    """Set up the binary sensors."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NecLightOn(coordinator),
            NecProblem(coordinator),
            NecTestPattern(coordinator),
            NecImbSelected(coordinator),
            NecConnectivity(coordinator),
        ]
    )


class NecLightOn(NecCinemaEntity, BinarySensorEntity):
    """Whether the lamp or laser light source is lit."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "light_on")

    @property
    def is_on(self) -> bool:
        """Return whether the light source is on."""
        return self.coordinator.data.light_on


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
