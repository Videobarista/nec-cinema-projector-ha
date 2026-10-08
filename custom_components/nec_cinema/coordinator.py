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
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import NecClient, NecError, NecLockedError, NecNakError, NecProjector
from .const import (
    COMMAND_ATTEMPTS,
    COMMAND_RETRY_DELAY,
    CONF_PROJECTOR_ID,
    DEFAULT_PORT_CODES,
    DEFAULT_SCAN_INTERVAL,
    DEFERRABLE_ACTIONS,
    DOMAIN,
    INPUT_STATUS_PORTS,
    LAMP_DETAIL_TYPES,
    LAMP_MODE_UNKNOWN,
    LAMP_MODES,
    LEGACY_LAMP_OUTPUT_TYPES,
    LEGACY_LAMP_TYPES,
    LEGACY_TEMP_NAMES,
    LIGHT_MODE_UNKNOWN,
    LIGHT_MODES,
    MODEL_TYPES,
    MODEL_VARIANTS,
    NC_PORT_CODES,
    PENDING_TIMEOUT,
    PORT_NAMES,
    PROCESS_STATUS,
    PROCESS_STATUS_UNKNOWN,
    RUNNING_STATUSES,
    SHUTDOWN_STATUSES,
    SLOW_POLL_EVERY,
    STARTUP_STATUSES,
    TRANSIENT_NAK_CODES,
)

_LOGGER = logging.getLogger(__name__)

MAX_ERROR_STRINGS = 6

STORAGE_VERSION = 1
SAVE_DELAY = 10

# Longest believable cooling timer, in seconds. The projector fills the field
# with FFFFH outside the cooling phase; anything this long is not a timer.
MAX_COOLING_TIME = 3600


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
    cooling_progress: int | None = None
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
    light_warning_hours: int | None = None
    light_remaining: int | None = None
    light_strikes: int | None = None
    lamp2_hours: int | None = None
    lamp2_remaining: int | None = None
    lamp2_strikes: int | None = None
    light_power: float | None = None
    light_mode: str = LIGHT_MODE_UNKNOWN
    lamp_mode: str = LAMP_MODE_UNKNOWN
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
        self.lamp_details = False
        self.has_lamp2 = False
        self.has_lamp_mode = False
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.macros")
        self._learned: dict[int, str] = {}
        self._pending: dict[str, tuple[str, tuple[Any, ...], float]] = {}
        self.last_command: dict[str, Any] | None = None
        self.start_dark = False
        self._light_override = False
        self._cooling_phase = False
        self._cooling_watched = False
        self._cooling_total = 0
        self._cooling_learned = 0
        self._poll_count = 0
        self._first_poll_done = False

    # ------------------------------------------------------------------ setup

    async def async_probe(self) -> None:
        """Read the static information once, at config entry setup."""
        await self._load_learned()
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
        self.lamp_details = self.projector_type in LAMP_DETAIL_TYPES
        try:
            await self.projector.lamp_mode()
        except (NecError, NecNakError) as err:
            _LOGGER.debug("no lamp mode support: %s", err)
        else:
            self.has_lamp_mode = True
        if self.lamp_details:
            try:
                self.has_lamp2 = bool((await self.projector.lamp_info_modern()).get("lamp2_hours"))
            except (NecError, NecNakError) as err:
                _LOGGER.debug("lamp detail probe failed: %s", err)
        await self._probe_lamp_output()
        await self._probe_sources()
        await self._probe_thermal_sensors()

    async def _load_learned(self) -> None:
        """Read the macro names learned in earlier sessions."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._learned = {
                int(key): str(value)
                for key, value in stored.get("macros", {}).items()
                if str(key).isdigit()
            }
            # Version 1.10 stored a wanted light control mode; "off" meant the
            # same as starting dark does now.
            self.start_dark = bool(
                stored.get("start_dark", stored.get("desired_light_mode") == "off")
            )
            learned = stored.get("cooling_time")
            if isinstance(learned, int) and 0 < learned <= MAX_COOLING_TIME:
                self._cooling_learned = learned

    @property
    def learned_macros(self) -> dict[int, str]:
        """Return the preset key names seen so far."""
        return dict(self._learned)

    def _learn_macro(self, data: ProjectorData) -> None:
        """Remember which name belongs to the preset key now active.

        The protocol cannot list the titles or preset keys, only report the one
        currently selected. Recording each one as it passes builds the list
        without ever switching the projector to find out.
        """
        number, name = data.preset_number, data.title_name
        if not number or not name or self._learned.get(number) == name:
            return
        self._learned[number] = name
        _LOGGER.debug("learned preset %s = %s", number, name)
        self._save()

    def _save(self) -> None:
        """Persist what the integration remembers on the user's behalf."""
        self._store.async_delay_save(
            lambda: {
                "macros": self._learned,
                "start_dark": self.start_dark,
                "cooling_time": self._cooling_learned,
            },
            SAVE_DELAY,
        )

    async def async_forget_macros(self) -> None:
        """Drop every learned preset name."""
        self._learned = {}
        self._save()
        self.async_update_listeners()

    def _track_cooling(self, data: ProjectorData, remaining: int) -> None:
        """Report cooling time only while cooling, plus how far along it is.

        Outside the cooling phase the projector's field holds nothing useful, so
        it reads as zero. The progress is the time left against the full cooling
        time, so a bar card empties from 100 to 0 without being told how long
        the projector takes to cool.

        The full time is the longest reading of the phase. When Home Assistant
        joins a phase already under way, for instance after a restart, its
        first reading is too short to be the full time, so the full time of the
        last phase watched from the start is used instead. That is remembered
        across restarts.
        """
        if data.process_status != "cooling":
            if (
                self._cooling_watched
                and self._cooling_total
                and self._cooling_total != self._cooling_learned
            ):
                self._cooling_learned = self._cooling_total
                _LOGGER.debug("learned cooling time: %s s", self._cooling_learned)
                self._save()
            self._cooling_phase = False
            self._cooling_watched = False
            self._cooling_total = 0
            data.cooling_remaining = 0
            data.cooling_progress = 0
            return

        if not self._cooling_phase:
            previous = self.data
            self._cooling_phase = True
            self._cooling_watched = (
                previous is not None
                and previous.available
                and previous.process_status != "cooling"
            )
            self._cooling_total = 0 if self._cooling_watched else self._cooling_learned

        if remaining <= MAX_COOLING_TIME:
            self._cooling_total = max(self._cooling_total, remaining)
        data.cooling_remaining = remaining
        data.cooling_progress = (
            min(100, round(remaining * 100 / self._cooling_total)) if self._cooling_total else 100
        )

    async def async_set_start_dark(self, enabled: bool) -> None:
        """Remember whether the projector should power up without lighting.

        This only affects the next power-up. Choosing it never touches the lamp
        now; the Light source switch is for that.
        """
        self.start_dark = enabled
        self._save()
        self.async_update_listeners()

    async def async_set_light(self, on: bool) -> None:
        """Light or extinguish the lamp now.

        A light command given by hand takes over from starting dark until the
        projector next shuts down, so the two never fight. It is set before the
        command because the refresh that follows runs the start dark upkeep, and
        undone if the projector did not take the command.
        """
        previous = self._light_override
        self._light_override = True
        try:
            await self.async_send("set_light_mode", 0x01 if on else 0x02)
        except Exception:
            self._light_override = previous
            raise

    async def async_prepare_dark_start(self) -> None:
        """Set forced off just before a power-on issued from here.

        The projector honours the light control mode at power-up when it was set
        shortly before, so this is the most reliable moment. Best effort: if it
        is refused, the standby upkeep below has usually set it already.

        Only from standby. Forced off on a running head puts the lamp out, and a
        turn on sent to a projector that is already on, for instance by an
        automation making sure, must leave the light alone.
        """
        if (
            not self.start_dark
            or self._light_override
            or not self.data
            or self.data.process_status != "standby"
        ):
            return
        try:
            await self.projector.set_light_mode(0x02)
        except (NecError, NecNakError) as err:
            _LOGGER.debug("forced off before power-on not accepted: %s", err)

    async def _keep_start_dark(self, data: ProjectorData) -> None:
        """Keep forced off in place while the projector waits in standby.

        The projector clears its light control mode by itself the moment it
        enters standby, but one set again in standby stays put and is honoured
        at power-up. Putting it back whenever it has been cleared means a
        power-up starts dark, including one from the touch panel.

        During a power-up only the projector's own default (standard) is
        overruled. Forced on means someone asked for light, from the Light
        source switch or the touch panel, and that is left alone. Once the head
        is running the lamp is left to the Light source switch.
        """
        previous = self.data
        if (
            data.process_status in SHUTDOWN_STATUSES
            and previous is not None
            and previous.process_status not in SHUTDOWN_STATUSES
        ):
            self._light_override = False
        if not self.start_dark or self._light_override:
            return
        if data.process_status == "standby":
            wanted = data.light_mode not in ("off", LIGHT_MODE_UNKNOWN)
        elif data.process_status in STARTUP_STATUSES:
            wanted = data.light_mode == "standard"
        else:
            wanted = False
        if not wanted:
            return
        try:
            await self.projector.set_light_mode(0x02)
        except (NecError, NecNakError) as err:
            _LOGGER.debug("could not set forced off for a dark start: %s", err)
        else:
            _LOGGER.debug("forced off set for a dark start")
            data.light_mode = "off"

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
    def light_hours_detailed(self) -> bool:
        """Whether this head answers the detailed lamp information command."""
        return not self._legacy_lamp

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
        await self._keep_start_dark(data)
        await self._apply_pending(data)
        self._learn_macro(data)
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
            data.light_warning_hours = previous.light_warning_hours
            data.light_remaining = previous.light_remaining
            data.light_strikes = previous.light_strikes
            data.lamp2_hours = previous.lamp2_hours
            data.lamp2_remaining = previous.lamp2_remaining
            data.lamp2_strikes = previous.lamp2_strikes
            data.light_power = previous.light_power
            data.lamp_mode = previous.lamp_mode
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
        self._track_cooling(data, running["cooling_remaining"])
        data.external_control = running["external_control"]

        try:
            data.light_mode = LIGHT_MODES.get(
                await self.projector.light_mode(), LIGHT_MODE_UNKNOWN
            )
        except NecNakError as err:
            _LOGGER.debug("lamp control mode refused: %s", err)

        if self.lamp_output_kind == "watt":
            try:
                output = await self.projector.lamp_output()
                data.lamp_watt = output["watt"]
                data.lamp_ampere = output["ampere"]
                data.lamp_volt = output["volt"]
            except NecNakError as err:
                _LOGGER.debug("lamp output refused: %s", err)

        # Pass the methods, not calls to them: a tuple of coroutines would
        # create all three up front, and any that is never reached because an
        # earlier one failed would be left un-awaited.
        for query, keys in (
            (self.projector.mute_status, ("douser_closed", "picture_mute")),
            (self.projector.input_status, ("port_key", "test_pattern", "switching")),
            (self.projector.current_title, ("title_number", "title_name", "preset_number")),
        ):
            try:
                result: dict[str, Any] = await query()
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
                info = await self.projector.lamp_info_modern()
                data.light_hours = info["hours"]
                data.light_warning_hours = info.get("warning_hours")
                data.light_strikes = info.get("strikes")
                if self.lamp_details:
                    data.light_remaining = info.get("remaining")
                    data.lamp2_hours = info.get("lamp2_hours")
                    data.lamp2_remaining = info.get("lamp2_remaining")
                    data.lamp2_strikes = info.get("lamp2_strikes")
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

        if self.has_lamp_mode:
            try:
                data.lamp_mode = LAMP_MODES.get(
                    await self.projector.lamp_mode(), LAMP_MODE_UNKNOWN
                )
            except (NecError, NecNakError) as err:
                _LOGGER.debug("lamp mode failed: %s", err)

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

    def _record(self, action: str, outcome: str, message: str) -> None:
        """Remember how the last command went, for the diagnostic sensor."""
        status = self.data.process_status if self.data else PROCESS_STATUS_UNKNOWN
        self.last_command = {
            "action": action,
            "outcome": outcome,
            "message": message,
            "code": None,
            "projector_status": status,
            "at": dt_util.utcnow(),
        }

    def _record_error(self, action: str, outcome: str, err: Exception) -> None:
        """Remember a failed command, including the projector's own wording."""
        self._record(action, outcome, f"{action}: {err}")
        if isinstance(err, NecNakError) and err.code and self.last_command:
            self.last_command["code"] = f"{err.code[0]:02X}H {err.code[1]:02X}H"

    @property
    def running(self) -> bool:
        """Whether the projector is up and running rather than in transition."""
        return bool(self.data and self.data.process_status in RUNNING_STATUSES)

    @property
    def shutting_down(self) -> bool:
        """Whether the projector is cooling down or in standby."""
        return bool(self.data and self.data.process_status in SHUTDOWN_STATUSES)

    @property
    def pending_actions(self) -> list[str]:
        """Return the commands waiting for the projector to settle."""
        return [held[0] for held in self._pending.values()]

    async def _apply_pending(self, data: ProjectorData) -> None:
        """Run commands that were refused while the projector was starting up.

        They are applied once it runs. If it shuts down instead they are dropped:
        the projector closes the douser by itself on the way to standby, and a
        held "douser open" carried into standby would expose the DMD in an empty
        auditorium.
        """
        if not self._pending:
            return
        if data.process_status in SHUTDOWN_STATUSES:
            for action, _args, _queued_at in self._pending.values():
                _LOGGER.info("dropping held command %s: the projector is shutting down", action)
                self._record(action, "skipped", f"{action}: dropped, the projector shut down")
            self._pending.clear()
            return
        if data.process_status not in RUNNING_STATUSES:
            return
        now = self.hass.loop.time()
        for group, (action, args, queued_at) in list(self._pending.items()):
            del self._pending[group]
            if now - queued_at > PENDING_TIMEOUT:
                _LOGGER.info("giving up on held command %s: projector stayed busy", action)
                self._record(action, "skipped", f"{action}: dropped, the projector stayed busy")
                continue
            try:
                await getattr(self.projector, action)(*args)
            except (NecError, NecNakError) as err:
                _LOGGER.warning("held command %s still refused: %s", action, err)
                self._record_error(action, "refused", err)
            else:
                _LOGGER.info("held command %s applied now the projector is ready", action)
                self._record(action, "ok", f"{action}: applied once the projector was ready")
        try:
            mute = await self.projector.mute_status()
        except (NecError, NecNakError):
            return
        data.douser_closed = mute["douser_closed"]
        data.picture_mute = mute["picture_mute"]

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
                if err.code not in TRANSIENT_NAK_CODES:
                    self._record_error(action, "refused", err)
                    raise
                # While the head is running the same code means manual control
                # is locked out, not that it is busy. Waiting will not help.
                if self.running:
                    locked = NecLockedError(str(err), err.code)
                    self._record_error(action, "locked", locked)
                    raise locked from err
                # Shutting down: the projector closes the douser by itself, and
                # nothing held now should be carried into standby.
                if self.shutting_down and action in DEFERRABLE_ACTIONS:
                    _LOGGER.info("%s not applied: the projector is shutting down", action)
                    reason = (
                        " and closes the douser by itself"
                        if DEFERRABLE_ACTIONS[action] == "douser"
                        else ""
                    )
                    self._record(
                        action,
                        "skipped",
                        f"{action}: not applied, the projector is shutting down{reason}",
                    )
                    return
                if attempt == COMMAND_ATTEMPTS:
                    if action in DEFERRABLE_ACTIONS:
                        self._pending[DEFERRABLE_ACTIONS[action]] = (
                            action,
                            args,
                            self.hass.loop.time(),
                        )
                        _LOGGER.info(
                            "projector busy (%s); holding %s until it is ready",
                            self.data.process_status if self.data else "unknown",
                            action,
                        )
                        self._record_error(action, "held", err)
                        return
                    self._record_error(action, "busy", err)
                    raise
                _LOGGER.debug(
                    "%s refused (%s), retry %s of %s", action, err, attempt, COMMAND_ATTEMPTS
                )
                await asyncio.sleep(COMMAND_RETRY_DELAY)
            except NecError as err:
                self._record_error(action, "failed", err)
                raise
            else:
                self._pending.pop(DEFERRABLE_ACTIONS.get(action, ""), None)
                self._record(action, "ok", f"{action}: accepted")
                break
        await self.async_refresh()
