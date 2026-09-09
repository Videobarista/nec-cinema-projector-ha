"""Data coordinator for the NEC cinema projector."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import NecClient, NecError, NecNakError, NecProjector
from .const import (
    CONF_PROJECTOR_ID,
    DEFAULT_PORT_CODES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INPUT_STATUS_PORTS,
    LEGACY_LAMP_TYPES,
    LEGACY_TEMP_NAMES,
    NC_PORT_CODES,
    PORT_NAMES,
    PROCESS_STATUS,
    PROCESS_STATUS_UNKNOWN,
    SLOW_POLL_EVERY,
)

_LOGGER = logging.getLogger(__name__)

MAX_ERROR_STRINGS = 6


@dataclass
class ProjectorData:
    """Everything the entities read from."""

    available: bool = False
    last_seen: datetime | None = None

    power_on: bool = False
    light_on: bool = False
    process_status: str = PROCESS_STATUS_UNKNOWN
    process_status_raw: int | None = None
    power_processing: bool = False
    cooling: bool = False
    cooling_remaining: int | None = None
    external_control: bool = False

    douser_closed: bool | None = None
    picture_mute: bool | None = None

    port: str | None = None
    test_pattern: bool = False
    switching: bool = False

    title_number: int | None = None
    title_name: str | None = None
    preset_number: int | None = None

    errors: list[str] = field(default_factory=list)
    light_hours: float | None = None
    light_power: float | None = None
    temperatures: dict[str, float | None] = field(default_factory=dict)


class NecCinemaCoordinator(DataUpdateCoordinator[ProjectorData]):
    """Poll the projector and keep static information around."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = NecClient(
            entry.data[CONF_HOST],
            entry.data.get(CONF_PORT),
            entry.data.get(CONF_PROJECTOR_ID, 0),
        )
        self.projector = NecProjector(self.client)

        self.model: str = "Cinema projector"
        self.serial: str | None = None
        self.projector_type: tuple[int, int, int] | None = None
        self.source_map: dict[str, int] = {}
        self.thermal_names: list[str] = []
        self._legacy_lamp = False
        self._legacy_temps = False
        self._poll_count = 0
        self._first_poll_done = False

    # ------------------------------------------------------------------ setup

    async def async_probe(self) -> None:
        """Read the static information once, at config entry setup."""
        self.model = await self.projector.model_name() or self.model

        try:
            self.serial = await self.projector.serial_number()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("serial number unavailable: %s", err)

        try:
            self.projector_type = await self.projector.projector_type()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("projector type unavailable: %s", err)

        self._legacy_lamp = self.projector_type in LEGACY_LAMP_TYPES
        await self._probe_sources()
        await self._probe_thermal_sensors()

    async def _probe_sources(self) -> None:
        """Build the source list from the installed terminals."""
        codes: list[int] = []
        try:
            codes = [c for c in await self.projector.available_ports() if c in NC_PORT_CODES]
        except (NecError, NecNakError) as err:
            _LOGGER.debug("input terminal request failed: %s", err)
        if not codes:
            codes = list(DEFAULT_PORT_CODES)
        self.source_map = {PORT_NAMES.get(code, f"Port {code:02X}H"): code for code in codes}

    async def _probe_thermal_sensors(self) -> None:
        """Discover the thermal sensors, modern command first."""
        try:
            count = await self.projector.thermal_sensor_count()
        except (NecError, NecNakError):
            count = 0
        if count:
            names: list[str] = []
            for index in range(count):
                try:
                    names.append(await self.projector.thermal_sensor_name(index))
                except (NecError, NecNakError):
                    names.append(f"Sensor {index + 1}")
            self.thermal_names = names
            return

        legacy = LEGACY_TEMP_NAMES.get(self.projector_type or (0, 0, 0))
        if legacy:
            self.thermal_names = list(legacy)
            self._legacy_temps = True

    @property
    def device_identifier(self) -> str:
        """Stable identifier for the device registry."""
        return self.serial or f"{self.entry.data[CONF_HOST]}:{self.entry.data.get(CONF_PORT)}"

    # ---------------------------------------------------------------- polling

    async def _async_update_data(self) -> ProjectorData:
        """Fetch the current state; unreachable is reported as off, not as an error."""
        data = ProjectorData()
        try:
            await self._poll_fast(data)
        except (NecError, NecNakError) as err:
            if not self._first_poll_done:
                raise
            _LOGGER.debug("projector unreachable: %s", err)
            previous = self.data
            data.last_seen = previous.last_seen if previous else None
            return data

        self._first_poll_done = True
        data.available = True
        data.last_seen = dt_util.utcnow()

        self._poll_count += 1
        slow_due = self._poll_count % SLOW_POLL_EVERY == 1 or self._poll_count == 1
        previous = self.data
        if slow_due:
            await self._poll_slow(data)
        elif previous is not None:
            data.errors = previous.errors
            data.light_hours = previous.light_hours
            data.light_power = previous.light_power
            data.temperatures = previous.temperatures
        return data

    async def _poll_fast(self, data: ProjectorData) -> None:
        """Read the values that matter for control."""
        running = await self.projector.running_status()
        data.power_on = running["power_on"]
        data.light_on = running["light_on"]
        data.process_status_raw = running["process_status"]
        data.process_status = PROCESS_STATUS.get(
            running["process_status"], PROCESS_STATUS_UNKNOWN
        )
        data.power_processing = running["power_processing"]
        data.cooling = running["cooling"]
        data.cooling_remaining = running["cooling_remaining"]
        data.external_control = running["external_control"]

        for coro, keys in (
            (self.projector.mute_status(), ("douser_closed", "picture_mute")),
            (self.projector.input_status(), ("port_key", "test_pattern", "switching")),
            (
                self.projector.current_title(),
                ("title_number", "title_name", "preset_number"),
            ),
        ):
            try:
                result: dict[str, Any] = await coro
            except NecNakError as err:
                _LOGGER.debug("status query refused: %s", err)
                continue
            for key in keys:
                if key == "port_key":
                    data.port = INPUT_STATUS_PORTS.get(result[key])
                else:
                    setattr(data, key, result[key])

    async def _poll_slow(self, data: ProjectorData) -> None:
        """Read the housekeeping values."""
        try:
            if self._legacy_lamp:
                data.light_hours = await self.projector.light_hours_legacy()
            else:
                data.light_hours = await self.projector.light_hours_modern()
        except NecNakError:
            # Wrong command family for this model; switch over and retry next time.
            self._legacy_lamp = not self._legacy_lamp
        except NecError as err:
            _LOGGER.debug("lamp information failed: %s", err)

        try:
            data.light_power = await self.projector.light_power()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("lamp parameter failed: %s", err)

        try:
            data.errors = await self._read_errors()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("error request failed: %s", err)

        try:
            data.temperatures = await self._read_temperatures()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("temperature request failed: %s", err)

    async def _read_errors(self) -> list[str]:
        """Return the readable error messages currently reported."""
        codes = await self.projector.error_numbers()
        messages: list[str] = []
        for code in codes[:MAX_ERROR_STRINGS]:
            try:
                messages.append(await self.projector.error_string(code))
            except (NecError, NecNakError):
                messages.append(f"Error {code}")
        if len(codes) > MAX_ERROR_STRINGS:
            messages.append(f"... and {len(codes) - MAX_ERROR_STRINGS} more")
        return messages

    async def _read_temperatures(self) -> dict[str, float | None]:
        """Read every discovered thermal sensor."""
        if not self.thermal_names:
            return {}
        if self._legacy_temps:
            values = await self.projector.temperatures_legacy(len(self.thermal_names))
            return dict(zip(self.thermal_names, values, strict=False))
        result: dict[str, float | None] = {}
        for index, name in enumerate(self.thermal_names):
            try:
                result[name] = await self.projector.temperature_modern(index)
            except (NecError, NecNakError):
                result[name] = None
        return result

    # --------------------------------------------------------------- commands

    async def async_send(self, action: str, *args: Any) -> None:
        """Run a projector command and refresh straight away."""
        method = getattr(self.projector, action)
        async with asyncio.timeout(20):
            await method(*args)
        await self.async_request_refresh()
