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
    COMMAND_ATTEMPTS,
    COMMAND_RETRY_DELAY,
    CONF_PROJECTOR_ID,
    DEFAULT_PORT_CODES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INPUT_STATUS_PORTS,
    LEGACY_LAMP_OUTPUT_TYPES,
    LEGACY_LAMP_TYPES,
    LEGACY_TEMP_NAMES,
    LIGHT_MODE_UNKNOWN,
    MODEL_TYPES,
    MODEL_VARIANTS,
    LIGHT_MODES,
    NC_PORT_CODES,
    PORT_NAMES,
    PROCESS_STATUS,
    PROCESS_STATUS_UNKNOWN,
    SLOW_POLL_EVERY,
    TRANSIENT_NAK_CODES,
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
    light_mode: str = LIGHT_MODE_UNKNOWN
    lamp_watt: float | None = None
    lamp_ampere: float | None = None
    lamp_volt: float | None = None
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
        self.model_subtype: int | None = None
        self.source_map: dict[str, int] = {}
        self.thermal_names: list[str] = []
        self._legacy_lamp = False
        self._legacy_temps = False
        self.lamp_output_kind: str | None = None
        self._poll_count = 0
        self._first_poll_done = False

    # ------------------------------------------------------------------ setup

    async def async_probe(self) -> None:
        """Read the static information once, at config entry setup."""
        reported = await self.projector.model_name()

        try:
            self.serial = await self.projector.serial_number()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("serial number unavailable: %s", err)

        try:
            self.projector_type, self.model_subtype = await self.projector.projector_info()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("projector type unavailable: %s", err)

        self.model = self._resolve_model(reported)

        self._legacy_lamp = self.projector_type in LEGACY_LAMP_TYPES
        await self._probe_lamp_output()
        await self._probe_sources()
        await self._probe_thermal_sensors()

    def _resolve_model(self, reported: str) -> str:
        """Return the most specific model name available.

        Some heads answer MODEL NAME REQUEST with a family label such as
        "NC-Series", so prefer the projector type from SETTING REQUEST and fall
        back to whatever the head called itself.
        """
        if self.projector_type is not None:
            variants = MODEL_VARIANTS.get(self.projector_type, {})
            if self.model_subtype is not None and self.model_subtype in variants:
                return variants[self.model_subtype]
            known = MODEL_TYPES.get(self.projector_type)
            if known:
                return known
        return reported or self.model

    async def _probe_lamp_output(self) -> None:
        """Find out which lamp output command this head answers.

        The document lists which models support which command, so use that
        first. Probing is only a fallback for a head not in the lists, and must
        not be trusted to distinguish "not supported" from "lamp is off".
        """
        if self.projector_type in LEGACY_LAMP_OUTPUT_TYPES:
            self.lamp_output_kind = "watt"
            return

        try:
            await self.projector.light_power()
        except NecNakError:
            pass
        except NecError as err:
            _LOGGER.debug("lamp power probe failed: %s", err)
            return
        else:
            self.lamp_output_kind = "percent"
            return

        try:
            await self.projector.lamp_output()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("no lamp output command supported: %s", err)
        else:
            self.lamp_output_kind = "watt"

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
            data.light_mode = previous.light_mode
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

        if self.lamp_output_kind == "watt":
            try:
                output = await self.projector.lamp_output()
                data.lamp_watt = output["watt"]
                data.lamp_ampere = output["ampere"]
                data.lamp_volt = output["volt"]
            except NecNakError as err:
                _LOGGER.debug("lamp output refused: %s", err)

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
            if self.lamp_output_kind == "percent":
                data.light_power = await self.projector.light_power()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("lamp parameter failed: %s", err)

        try:
            data.light_mode = LIGHT_MODES.get(
                await self.projector.light_mode(), LIGHT_MODE_UNKNOWN
            )
        except (NecError, NecNakError) as err:
            _LOGGER.debug("lamp control mode failed: %s", err)

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

    async def async_reset_light_mode(self) -> None:
        """Put the light control mode back to following projector power.

        The forced modes survive a power cycle, so a head left in "forced off"
        would refuse to light on the next start. Clearing it around every power
        switch keeps that from becoming a dark screen in a booth.
        """
        try:
            await self.projector.set_light_mode(0x00)
        except (NecError, NecNakError) as err:
            _LOGGER.debug("could not reset the light control mode: %s", err)

    async def async_send(self, action: str, *args: Any) -> None:
        """Run a projector command and refresh straight away.

        A head that is igniting, cooling or busy refuses commands with a NAK
        that clears by itself, so those are retried for a few seconds before
        giving up.
        """
        method = getattr(self.projector, action)
        for attempt in range(1, COMMAND_ATTEMPTS + 1):
            try:
                async with asyncio.timeout(20):
                    await method(*args)
            except NecNakError as err:
                if err.code not in TRANSIENT_NAK_CODES or attempt == COMMAND_ATTEMPTS:
                    raise
                _LOGGER.debug(
                    "%s refused (%s), retry %s of %s", action, err, attempt, COMMAND_ATTEMPTS
                )
                await asyncio.sleep(COMMAND_RETRY_DELAY)
            else:
                break
        await self.async_request_refresh()
