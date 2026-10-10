"""Fixtures for the Sharp NEC cinema projector tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nec_cinema.client import NecConnectionError, NecNakError
from custom_components.nec_cinema.const import CONF_PROJECTOR_ID, DOMAIN
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

# Documentation address (RFC 5737) and a made-up serial number.
HOST = "192.0.2.10"
PORT = 43728
SERIAL = "24A0000TEST"
ENTRY_ID = "nec_cinema_test_entry"
STORAGE_KEY = f"{DOMAIN}.{ENTRY_ID}.macros"

ENTRY_DATA: dict[str, Any] = {
    CONF_HOST: HOST,
    CONF_PORT: PORT,
    CONF_NAME: "Cinema projector",
    CONF_PROJECTOR_ID: 0,
}

# What an NC1200C reported on an earlier run, as the integration stores it.
STORED_DEVICE: dict[str, Any] = {
    "model": "NC1200C",
    "serial": SERIAL,
    "projector_type": [0x0C, 0x07, 0x0A],
    "model_subtype": 0,
    "legacy_lamp": True,
    "legacy_temps": True,
    "lamp_output_kind": "watt",
    "lamp_details": False,
    "has_lamp2": False,
    "has_lamp_mode": False,
    "sources": {"292-A": 0x1A, "292-B": 0x1B, "IMB": 0x3B},
    "thermal_names": [
        "LPSU Intake",
        "Temp 2",
        "Outside Air",
        "DMD-B",
        "Exhaust",
        "Temp 6",
        "Temp 7",
        "Temp 8",
    ],
}

UNSUPPORTED = NecNakError("this model does not support the function", (0x00, 0x01))


class FakeProjector:
    """An NC1200C running with its lamp on, answering like the real head.

    Set ``online`` to False to make every request fail the way an unreachable
    projector does. Commands are plain AsyncMocks so tests can inspect them.
    """

    def __init__(self) -> None:
        """Start in the running state."""
        self.online = True
        self.status = 0x04
        self.power = True
        self.light = True
        self.mode = 0x01
        self.douser_closed = False
        self.serial = SERIAL
        self.projector_type: tuple[int, int, int] = (0x0C, 0x07, 0x0A)
        self.reported_name = "NC-Series"
        self.power_on = AsyncMock()
        self.power_off = AsyncMock()
        self.douser_open = AsyncMock()
        self.douser_close = AsyncMock()
        self.picture_mute_on = AsyncMock()
        self.picture_mute_off = AsyncMock()
        self.select_port = AsyncMock()
        self.select_title = AsyncMock()
        self.select_macro = AsyncMock()
        self.lens_control = AsyncMock()
        self.set_lamp_mode = AsyncMock()

    def _check(self) -> None:
        if not self.online:
            raise NecConnectionError(f"cannot connect to {HOST}:{PORT}: no answer within 8 s")

    async def model_name(self) -> str:
        """MODEL NAME REQUEST."""
        self._check()
        return self.reported_name

    async def serial_number(self) -> str:
        """SERIAL NUMBER REQUEST."""
        self._check()
        return self.serial

    async def projector_info(self) -> tuple[tuple[int, int, int], int]:
        """SETTING REQUEST."""
        self._check()
        return self.projector_type, 0x00

    async def lamp_mode(self) -> int:
        """Single lamp head: not supported."""
        self._check()
        raise UNSUPPORTED

    async def lamp_info_modern(self) -> dict[str, int]:
        """LAMP INFORMATION REQUEST 3."""
        self._check()
        return {"hours": 1234}

    async def light_hours_legacy(self) -> float:
        """LAMP INFORMATION REQUEST 2."""
        self._check()
        return 1234.0

    async def light_power(self) -> float:
        """Not on this head."""
        self._check()
        raise UNSUPPORTED

    async def lamp_output(self) -> dict[str, float]:
        """LAMP PARAMETER: measured values."""
        self._check()
        return {"watt": 1700.0, "ampere": 60.0, "volt": 28.3}

    async def available_ports(self) -> list[int]:
        """INPUT TERMINAL REQUEST."""
        self._check()
        return [0x1A, 0x1B, 0x3B]

    async def thermal_sensor_count(self) -> int:
        """Older head: the parts count request is not answered."""
        self._check()
        raise UNSUPPORTED

    async def thermal_sensor_name(self, index: int) -> str:
        """Not reached on this head."""
        self._check()
        return f"Sensor {index + 1}"

    async def temperatures_legacy(self, count: int) -> list[float | None]:
        """TEMPERATURE STATUS REQUEST 3."""
        self._check()
        return [31.5] * count

    async def temperature_modern(self, index: int) -> float | None:
        """Not reached on this head."""
        self._check()
        return 31.5

    async def error_numbers(self) -> list[int]:
        """No errors."""
        self._check()
        return []

    async def error_string(self, code: int) -> str:
        """Not reached without errors."""
        self._check()
        return f"Error {code}"

    async def running_status(self) -> dict[str, Any]:
        """RUNNING STATUS REQUEST."""
        self._check()
        return {
            "external_control": False,
            "power_on": self.power,
            "cooling": self.status == 0x05,
            "power_processing": False,
            "process_status": self.status,
            "light_on": self.light,
            "lamps": 0x01 if self.light else 0x00,
            "light_processing": False,
            "lamp_mode": 0x00,
            "cooling_remaining": 0,
            "lockout_remaining": 0,
        }

    async def light_mode(self) -> int:
        """LAMP CONTROL MODE REQUEST."""
        self._check()
        return self.mode

    async def set_light_mode(self, mode: int) -> None:
        """LAMP CONTROL MODE SET."""
        self._check()
        self.mode = mode

    async def mute_status(self) -> dict[str, Any]:
        """MUTE STATUS REQUEST."""
        self._check()
        return {"douser_closed": self.douser_closed, "picture_mute": False}

    async def input_status(self) -> dict[str, Any]:
        """INPUT STATUS REQUEST: the IMB is selected."""
        self._check()
        return {
            "switching": False,
            "signal_number": 0,
            "port_key": (0x04, 0x0C),
            "test_pattern": False,
        }

    async def current_title(self) -> dict[str, Any]:
        """CURRENT TITLE STATUS REQUEST."""
        self._check()
        return {"title_number": 10, "preset_number": 1, "title_name": "2D Flat"}


class FakeDualLampProjector(FakeProjector):
    """An NC900C-A: two lamps, a lamp mode, lamp output in percent.

    ``lockout`` is the switching lockout the head reports after striking and
    after putting the lamp out; light commands are refused while it runs.
    """

    def __init__(self) -> None:
        """Start running on both lamps."""
        super().__init__()
        self.projector_type = (0x0C, 0x0C, 0x0A)
        self.lamp = 0x00
        self.lockout = 0

    async def lamp_mode(self) -> int:
        """LAMP MODE REQUEST."""
        self._check()
        return self.lamp

    async def running_status(self) -> dict[str, Any]:
        """RUNNING STATUS REQUEST with the dual lamp fields."""
        status = await super().running_status()
        status["lamps"] = 0x03 if self.light else 0x00
        status["lamp_mode"] = self.lamp
        status["lockout_remaining"] = self.lockout
        return status

    async def set_light_mode(self, mode: int) -> None:
        """LAMP CONTROL MODE SET, refused during the switching lockout."""
        self._check()
        if self.lockout:
            raise NecNakError("setting not possible right now", (0x02, 0x03))
        self.mode = mode

    async def light_power(self) -> float:
        """LAMP PARAMETER OUTPUT REQUEST 2: setting power in percent."""
        self._check()
        return 98.7


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def projector() -> Generator[FakeProjector]:
    """Patch the protocol layer everywhere it is created; return the fake head."""
    fake = FakeProjector()
    with (
        patch("custom_components.nec_cinema.config_flow.NecProjector", return_value=fake),
        patch("custom_components.nec_cinema.coordinator.NecProjector", return_value=fake),
    ):
        yield fake


@pytest.fixture
def dual_projector() -> Generator[FakeDualLampProjector]:
    """Like ``projector``, for a dual lamp head."""
    fake = FakeDualLampProjector()
    with (
        patch("custom_components.nec_cinema.config_flow.NecProjector", return_value=fake),
        patch("custom_components.nec_cinema.coordinator.NecProjector", return_value=fake),
    ):
        yield fake


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the entry, for config flow tests."""
    with patch(
        "custom_components.nec_cinema.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the projector."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="NC1200C",
        unique_id=SERIAL,
        entry_id=ENTRY_ID,
        data=dict(ENTRY_DATA),
    )


@pytest.fixture
def stored_device(hass_storage: dict[str, Any]) -> dict[str, Any]:
    """Pretend the projector answered on an earlier run."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "macros": {"1": "2D Flat"},
            "start_dark": False,
            "cooling_time": 300,
            "device": STORED_DEVICE,
        },
    }
    return hass_storage
