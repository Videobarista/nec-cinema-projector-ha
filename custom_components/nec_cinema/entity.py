"""Shared entity base for the NEC cinema projector."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import NecError
from .const import DOMAIN
from .coordinator import NecCinemaCoordinator

_LOGGER = logging.getLogger(__name__)


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

    async def async_run_command(self, action: str, *args: Any) -> None:
        """Send a projector command; a refusal is recorded, not raised."""
        await self.async_guarded(self.coordinator.async_send, action, *args)

    async def async_guarded(self, call: Callable[..., Awaitable[None]], *args: Any) -> None:
        """Run a coordinator call; a refusal is recorded, not raised.

        The projector turning a command down is part of normal operation: it
        is starting up or cooling, the lamp may not be switched yet, manual
        control is locked, or it is switched off altogether. Raising would put
        an error in the Home Assistant log for every such press. The outcome,
        with the projector's own reason, is kept in the Last command sensor
        instead and only logged at debug level.
        """
        try:
            await call(*args)
        except NecError as err:
            _LOGGER.debug("%s: command not carried out: %s", self.entity_id, err)
            self.coordinator.async_update_listeners()
