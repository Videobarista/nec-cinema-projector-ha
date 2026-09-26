"""Sensor entities for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PROCESS_STATUS, PROCESS_STATUS_UNKNOWN
from .coordinator import NecCinemaCoordinator
from .entity import NecCinemaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        NecProcessStatus(coordinator),
        NecLightHours(coordinator),
        NecCoolingRemaining(coordinator),
        NecCurrentTitle(coordinator),
        NecErrors(coordinator),
        NecLastSeen(coordinator),
    ]
    if coordinator.lamp_output_kind == "percent":
        entities.append(NecLightPower(coordinator))
    elif coordinator.lamp_output_kind == "watt":
        entities.extend(
            [
                NecLampWatt(coordinator),
                NecLampAmpere(coordinator),
                NecLampVolt(coordinator),
            ]
        )
    entities.extend(
        NecTemperature(coordinator, index, name)
        for index, name in enumerate(coordinator.thermal_names)
    )
    async_add_entities(entities)


class NecProcessStatus(NecCinemaEntity, SensorEntity):
    """The projector process status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [*PROCESS_STATUS.values(), PROCESS_STATUS_UNKNOWN]

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "process_status")

    @property
    def native_value(self) -> str:
        """Return the current process status."""
        return self.coordinator.data.process_status


class NecLightHours(NecCinemaEntity, SensorEntity):
    """Lamp or light source usage time."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "light_hours")

    @property
    def native_value(self) -> float | None:
        """Return the usage time in hours."""
        return self.coordinator.data.light_hours


class NecLightPower(NecCinemaEntity, SensorEntity):
    """Light source power setting."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "light_power")

    @property
    def native_value(self) -> float | None:
        """Return the configured light output."""
        return self.coordinator.data.light_power


class NecLampWatt(NecCinemaEntity, SensorEntity):
    """Measured lamp power, reported by the lamp power supply."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "lamp_watt")

    @property
    def native_value(self) -> float | None:
        """Return the measured lamp power."""
        return self.coordinator.data.lamp_watt


class NecLampAmpere(NecCinemaEntity, SensorEntity):
    """Measured lamp current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "lamp_ampere")

    @property
    def native_value(self) -> float | None:
        """Return the measured lamp current."""
        return self.coordinator.data.lamp_ampere


class NecLampVolt(NecCinemaEntity, SensorEntity):
    """Measured lamp voltage, which climbs as a xenon bulb ages."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "lamp_volt")

    @property
    def native_value(self) -> float | None:
        """Return the measured lamp voltage."""
        return self.coordinator.data.lamp_volt


class NecCoolingRemaining(NecCinemaEntity, SensorEntity):
    """Remaining cooling time."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "cooling_remaining")

    @property
    def native_value(self) -> int | None:
        """Return the seconds of cooling left."""
        return self.coordinator.data.cooling_remaining


class NecCurrentTitle(NecCinemaEntity, SensorEntity):
    """The title currently selected on the projector."""

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "current_title")

    @property
    def native_value(self) -> str | None:
        """Return the title name."""
        return self.coordinator.data.title_name or None

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        """Return the title and preset numbers."""
        return {
            "title_number": self.coordinator.data.title_number,
            "preset_number": self.coordinator.data.preset_number,
        }


class NecErrors(NecCinemaEntity, SensorEntity):
    """Number of errors the projector reports."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "errors")

    @property
    def native_value(self) -> int:
        """Return how many errors are active."""
        return len(self.coordinator.data.errors)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Return the error messages."""
        return {"messages": self.coordinator.data.errors}


class NecLastSeen(NecCinemaEntity, SensorEntity):
    """When the projector last answered."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "last_seen")

    @property
    def available(self) -> bool:
        """Remain available while the projector is unreachable."""
        return True

    @property
    def native_value(self):
        """Return the last successful poll."""
        return self.coordinator.data.last_seen


class NecTemperature(NecCinemaEntity, SensorEntity):
    """One of the projector's thermal sensors."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: NecCinemaCoordinator, index: int, name: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, f"temperature_{index}")
        self._sensor_name = name
        self._attr_translation_key = None
        self._attr_name = name

    @property
    def native_value(self) -> float | None:
        """Return the measured temperature."""
        return self.coordinator.data.temperatures.get(self._sensor_name)
