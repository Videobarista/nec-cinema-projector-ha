"""Diagnostics support for the NEC cinema projector."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import NecCinemaCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: NecCinemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = asdict(coordinator.data) if coordinator.data else {}
    if data.get("last_seen"):
        data["last_seen"] = data["last_seen"].isoformat()
    return {
        "options": dict(entry.options),
        "model": coordinator.model,
        "projector_type": coordinator.projector_type,
        "sources": coordinator.source_map,
        "thermal_sensors": coordinator.thermal_names,
        "state": data,
    }
