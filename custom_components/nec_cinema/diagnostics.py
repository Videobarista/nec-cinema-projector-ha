"""Diagnostics support for the NEC cinema projector."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import NecCinemaConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NecCinemaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else {}
    if data.get("last_seen"):
        data["last_seen"] = data["last_seen"].isoformat()
    return {
        "options": dict(entry.options),
        "model": coordinator.model,
        "projector_type": coordinator.projector_type,
        "model_subtype": coordinator.model_subtype,
        "lamp_output_kind": coordinator.lamp_output_kind,
        "sources": coordinator.source_map,
        "thermal_sensors": coordinator.thermal_names,
        "set_up_offline": coordinator.set_up_offline,
        "state": data,
    }
