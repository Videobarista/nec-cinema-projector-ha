"""Diagnostics support for the NEC cinema projector."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import NecCinemaConfigEntry

# A diagnostics file is made to be attached to a public issue. The address
# and the serial number identify the installation and are not needed to find
# a fault, so they never leave Home Assistant.
TO_REDACT = {CONF_HOST, "serial"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NecCinemaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else {}
    if data.get("last_seen"):
        data["last_seen"] = data["last_seen"].isoformat()
    return async_redact_data(
        {
            "config": dict(entry.data),
            "options": dict(entry.options),
            "model": coordinator.model,
            "serial": coordinator.serial,
            "projector_type": coordinator.projector_type,
            "model_subtype": coordinator.model_subtype,
            "lamp_output_kind": coordinator.lamp_output_kind,
            "sources": coordinator.source_map,
            "thermal_sensors": coordinator.thermal_names,
            "set_up_offline": coordinator.set_up_offline,
            "state": data,
        },
        TO_REDACT,
    )
