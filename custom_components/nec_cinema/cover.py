"""The douser (lens shutter) as a cover entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NecCinemaConfigEntry, NecCinemaCoordinator
from .entity import NecCinemaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NecCinemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the douser."""
    coordinator = entry.runtime_data
    async_add_entities([NecDouser(coordinator)])


class NecDouser(NecCinemaEntity, CoverEntity):
    """Open or close the mechanical douser in front of the lens."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, coordinator: NecCinemaCoordinator) -> None:
        """Initialise the douser."""
        super().__init__(coordinator, "douser")

    @property
    def is_closed(self) -> bool | None:
        """Return whether the douser blocks the light."""
        return self.coordinator.data.douser_closed

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the douser."""
        await self.async_run_command("douser_open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the douser."""
        await self.async_run_command("douser_close")
