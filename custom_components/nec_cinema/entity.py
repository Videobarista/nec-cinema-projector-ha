"""Shared entity base for the NEC cinema projector."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NecCinemaCoordinator


class NecCinemaEntity(CoordinatorEntity[NecCinemaCoordinator]):
    """Base entity tied to one projector."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NecCinemaCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_identifier}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_identifier)},
            manufacturer="Sharp NEC Display Solutions",
            model=coordinator.model,
            name=coordinator.entry.title,
            serial_number=coordinator.serial,
            configuration_url=f"http://{coordinator.entry.data[CONF_HOST]}/",
        )

    @property
    def available(self) -> bool:
        """Entities other than the media player follow the projector's reachability."""
        return super().available and self.coordinator.data.available
