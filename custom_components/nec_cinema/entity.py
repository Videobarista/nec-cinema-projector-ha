"""Shared entity base for the NEC cinema projector."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import NecError, NecNakError
from .const import DOMAIN, TRANSIENT_NAK_CODES
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

    async def async_run_command(self, action: str, *args: Any) -> None:
        """Send a command, turning protocol errors into readable ones.

        A head that is still igniting or cooling refuses commands with a NAK
        that clears by itself. The coordinator retries those; if they still
        fail, say so plainly instead of quoting the protocol at the user.
        """
        try:
            await self.coordinator.async_send(action, *args)
        except NecNakError as err:
            if err.code in TRANSIENT_NAK_CODES:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_busy"
                ) from err
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_refused",
                translation_placeholders={"reason": str(err)},
            ) from err
        except NecError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"reason": str(err)},
            ) from err
