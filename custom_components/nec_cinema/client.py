"""Asynchronous client for the NEC cinema projector control port (TCP 43728)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .const import LENS_AXES, TEMP_INVALID
from .protocol import (
    ACK_BIT,
    HEADER_LENGTH,
    Response,
    build_frame,
    cstring,
    data_length,
    parse_frame,
    s16le,
    u16le,
    u32le,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0


class NecError(Exception):
    """Communication with the projector failed."""


class NecNakError(NecError):
    """The projector refused the command."""

    def __init__(self, text: str, code: tuple[int, int] | None) -> None:
        """Store the decoded reason."""
        super().__init__(text)
        self.code = code


class NecClient:
    """Request/response client with a single, reused TCP connection."""

    def __init__(
        self,
        host: str,
        port: int,
        projector_id: int = 0x00,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialise the client."""
        self._host = host
        self._port = port
        self._projector_id = projector_id
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Whether a socket is currently open."""
        return self._writer is not None and not self._writer.is_closing()

    async def close(self) -> None:
        """Close the connection, ignoring errors."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("error while closing the connection: %s", err)

    async def _connect(self) -> None:
        """Open the socket if it is not open yet."""
        if self.connected:
            return
        await self.close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise NecError(f"cannot connect to {self._host}:{self._port}: {err}") from err

    async def request(self, id1: int, id2: int, data: bytes = b"") -> Response:
        """Send a command and return the matching response."""
        async with self._lock:
            try:
                return await self._request(id1, id2, data)
            except NecNakError:
                raise
            except NecError:
                # The link is in an unknown state; force a clean reconnect.
                await self.close()
                raise

    async def _request(self, id1: int, id2: int, data: bytes) -> Response:
        await self._connect()
        reader, writer = self._reader, self._writer
        if reader is None or writer is None:
            raise NecError("no connection available")
        frame = build_frame(id1, id2, data, projector_id=self._projector_id)
        _LOGGER.debug("-> %s", frame.hex(" "))
        try:
            writer.write(frame)
            await writer.drain()
        except (OSError, asyncio.TimeoutError) as err:
            raise NecError(f"send failed: {err}") from err

        # Skip any stale frame that does not belong to this request.
        for _ in range(4):
            response = await self._read_frame(reader)
            if response.id2 == (id2 & 0xFF) and (response.id1 & ACK_BIT):
                if response.is_nak:
                    raise NecNakError(response.error_text, response.error_code)
                return response
            _LOGGER.debug("discarding unexpected frame id1=%02X id2=%02X", response.id1, response.id2)
        raise NecError("no matching response")

    async def _read_frame(self, reader: asyncio.StreamReader) -> Response:
        try:
            header = await asyncio.wait_for(reader.readexactly(HEADER_LENGTH), self._timeout)
            tail = await asyncio.wait_for(
                reader.readexactly(data_length(header) + 1), self._timeout
            )
        except asyncio.IncompleteReadError as err:
            raise NecError("connection closed by projector") from err
        except (OSError, asyncio.TimeoutError) as err:
            raise NecError(f"no response: {err}") from err
        _LOGGER.debug("<- %s", (header + tail).hex(" "))
        try:
            return parse_frame(header, tail)
        except ValueError as err:
            raise NecError(str(err)) from err


class NecProjector:
    """High level commands, one method per documented command."""

    def __init__(self, client: NecClient) -> None:
        """Wrap a client."""
        self.client = client

    # ---------------------------------------------------------------- control

    async def power_on(self) -> None:
        """POWER ON (015.)."""
        await self.client.request(0x02, 0x00)

    async def power_off(self) -> None:
        """POWER OFF (016.)."""
        await self.client.request(0x02, 0x01)

    async def douser_close(self) -> None:
        """LENS MUTE ON / shutter close (051.)."""
        await self.client.request(0x02, 0x16)

    async def douser_open(self) -> None:
        """LENS MUTE OFF / shutter open (052.)."""
        await self.client.request(0x02, 0x17)

    async def picture_mute_on(self) -> None:
        """PICTURE MUTE ON (020.)."""
        await self.client.request(0x02, 0x10)

    async def picture_mute_off(self) -> None:
        """PICTURE MUTE OFF (021.)."""
        await self.client.request(0x02, 0x11)

    async def _input_sw_change(self, obj: int, number: int) -> None:
        """INPUT SW CHANGE (018.)."""
        response = await self.client.request(0x02, 0x03, bytes((obj, number)))
        if response.data and response.data[0] != 0x00:
            raise NecNakError("projector reported a switching error", None)

    async def select_port(self, code: int) -> None:
        """Switch the input port (switching object 05H)."""
        await self._input_sw_change(0x05, code)

    async def select_title(self, number: int) -> None:
        """Select a title from the title list (switching object 00H)."""
        await self._input_sw_change(0x00, number)

    async def select_macro(self, number: int) -> None:
        """Select a preset/macro key, 1 based (switching object 06H)."""
        await self._input_sw_change(0x06, number - 1)

    async def lens_control(self, axis: str, value: int) -> None:
        """LENS CONTROL (053.)."""
        await self.client.request(0x02, 0x18, bytes((LENS_AXES[axis], value & 0xFF)))

    # ------------------------------------------------------------ static info

    async def model_name(self) -> str:
        """MODEL NAME REQUEST (078-5.)."""
        response = await self.client.request(0x00, 0x85, bytes((0x04,)))
        return cstring(response.data)

    async def serial_number(self) -> str:
        """VERSION DATA REQUEST (005-2.), version type 08H."""
        response = await self.client.request(0x00, 0x86, bytes((0x08,)))
        return cstring(response.data, 1)

    async def projector_type(self) -> tuple[int, int, int]:
        """SETTING REQUEST (078-1.), DATA01-03."""
        response = await self.client.request(0x00, 0x85, bytes((0x00,)))
        data = response.data
        if len(data) < 3:
            raise NecError("short setting response")
        return (data[0], data[1], data[2])

    async def available_ports(self) -> list[int]:
        """INPUT TERMINAL REQUEST (068.)."""
        response = await self.client.request(0x00, 0xC1)
        data = response.data
        if not data:
            return []
        count = data[0]
        return list(data[1 : 1 + count])

    async def thermal_sensor_count(self) -> int:
        """PARTS COUNT REQUEST (305-1.), parts kind 03H."""
        response = await self.client.request(0x00, 0xD6, bytes((0x00, 0x03)))
        return response.data[2] if len(response.data) >= 3 else 0

    async def thermal_sensor_name(self, index: int) -> str:
        """PARTS PARAMETER REQUEST (305-2.)."""
        response = await self.client.request(0x00, 0xD6, bytes((0x01, 0x03, index)))
        data = response.data
        if len(data) < 18:
            return f"Sensor {index + 1}"
        length = data[16]
        return cstring(data, 17, length) or f"Sensor {index + 1}"

    # ---------------------------------------------------------------- polling

    async def running_status(self) -> dict[str, Any]:
        """RUNNING STATUS REQUEST (078-2.)."""
        data = (await self.client.request(0x00, 0x85, bytes((0x01,)))).data
        if len(data) < 16:
            raise NecError("short running status response")
        return {
            "external_control": data[1] == 0x01,
            "power_on": data[2] == 0x01,
            "cooling": data[3] == 0x01,
            "power_processing": data[4] == 0x01,
            "process_status": data[5],
            "light_on": data[9] != 0x00,
            "light_processing": data[10] == 0x01,
            "cooling_remaining": u16le(data, 12),
        }

    async def mute_status(self) -> dict[str, Any]:
        """MUTE STATUS REQUEST (078-4.).

        DATA01 is 81H when the douser is closed, 01H for an electronic picture
        mute and 00H when neither is active.
        """
        data = (await self.client.request(0x00, 0x85, bytes((0x03,)))).data
        if not data:
            raise NecError("short mute status response")
        return {
            "douser_closed": bool(data[0] & 0x80),
            "picture_mute": data[0] == 0x01,
        }

    async def input_status(self) -> dict[str, Any]:
        """INPUT STATUS REQUEST (078-3.)."""
        data = (await self.client.request(0x00, 0x85, bytes((0x02,)))).data
        if len(data) < 6:
            raise NecError("short input status response")
        return {
            "switching": data[0] == 0x01,
            "signal_number": data[1],
            "port_key": (data[2], data[3]),
            "test_pattern": data[5] == 0x01,
        }

    async def current_title(self) -> dict[str, Any]:
        """CURRENT TITLE STATUS REQUEST (078-206.)."""
        data = (await self.client.request(0x00, 0x85, bytes((0xE6,)))).data
        if len(data) < 4:
            raise NecError("short title response")
        number = data[1]
        preset = data[2]
        return {
            "title_number": None if number == 255 else number,
            "preset_number": None if preset == 255 else preset + 1,
            "title_name": cstring(data, 4, data[3]),
        }

    async def error_numbers(self) -> list[int]:
        """ERROR NUMBER REQUEST 3 (009-5.)."""
        data = (await self.client.request(0x02, 0xBC, bytes((0x00,)))).data
        if len(data) < 2:
            return []
        count = data[1]
        return [u16le(data, 2 + i * 2) for i in range(count) if len(data) >= 4 + i * 2]

    async def error_string(self, code: int) -> str:
        """ERROR STRING REQUEST 3 (009-6.)."""
        payload = bytes((0x00,)) + code.to_bytes(2, "little")
        data = (await self.client.request(0x02, 0xBD, payload)).data
        if len(data) < 5:
            return f"Error {code}"
        return cstring(data, 4, data[3]) or f"Error {code}"

    async def light_hours_modern(self) -> int:
        """LAMP INFORMATION REQUEST 3 (235-31.), light usage time in hours."""
        data = (await self.client.request(0x03, 0x2F, bytes((0x1E,)))).data
        if len(data) < 3:
            raise NecError("short lamp information response")
        return u16le(data, 1)

    async def light_hours_legacy(self) -> float:
        """LAMP INFORMATION REQUEST 2 (037-2.), usage time in seconds."""
        data = (await self.client.request(0x03, 0x94)).data
        if len(data) < 4:
            raise NecError("short lamp information response")
        return round(u32le(data, 0) / 3600, 1)

    async def light_power(self) -> float | None:
        """LAMP PARAMETER OUTPUT REQUEST 2 (235-29.), setting power in percent."""
        data = (await self.client.request(0x03, 0x2F, bytes((0x1C,)))).data
        if len(data) < 6:
            return None
        raw = u16le(data, 4)
        # Most heads report in 0.1%, but the ML series and NP-02HD/NP-42HD use
        # 0.01%. Setting power never exceeds 100%, so a value that would scale
        # past that identifies the finer unit.
        scale = 100 if raw / 10 > 100 else 10
        return round(raw / scale, 1)

    async def lamp_output(self) -> dict[str, float]:
        """LAMP PARAMETER OUTPUT REQUEST (235-1.).

        Only the older heads (NC3240S-A, NC3200S, NC2000C, NC1200C) answer this.
        It reports what the lamp power supply actually measures.
        """
        data = (await self.client.request(0x03, 0x2F, bytes((0x00,)))).data
        if len(data) < 7:
            raise NecError("short lamp parameter response")
        return {
            "watt": float(u16le(data, 1)),
            "ampere": float(u16le(data, 3)),
            "volt": round(u16le(data, 5) / 10, 1),
        }

    async def light_mode(self) -> int:
        """LAMP CONTROL MODE REQUEST (235-18.)."""
        data = (await self.client.request(0x03, 0x2F, bytes((0x11,)))).data
        if len(data) < 2:
            raise NecError("short lamp control mode response")
        return data[1]

    async def set_light_mode(self, mode: int) -> None:
        """LAMP CONTROL MODE SET (235-19.).

        Mode 01H lights the lamp or laser, 02H extinguishes it and 00H returns
        the head to following the power state. This is the only documented way
        to switch the light without cycling projector power.
        """
        data = (await self.client.request(0x03, 0x2F, bytes((0x12, mode)))).data
        if len(data) >= 2 and data[1] != 0x00:
            raise NecNakError("projector could not change the light control mode", None)

    async def light_on(self) -> None:
        """Light the lamp or laser."""
        await self.set_light_mode(0x01)

    async def light_off(self) -> None:
        """Extinguish the lamp or laser, leaving the projector powered."""
        await self.set_light_mode(0x02)

    async def temperature_modern(self, index: int) -> float | None:
        """COMMON CURRENT STATUS REQUEST (300-20.)."""
        data = (await self.client.request(0x00, 0xD3, bytes((0x20, 0x03, index)))).data
        if len(data) < 5:
            return None
        raw = s16le(data, 3)
        if raw == TEMP_INVALID:
            return None
        return round(raw / 10, 1)

    async def temperatures_legacy(self, count: int) -> list[float | None]:
        """TEMPERATURE STATUS REQUEST 3 (078-204.)."""
        data = (await self.client.request(0x00, 0x85, bytes((0xE4,)))).data
        values: list[float | None] = []
        for index in range(count):
            offset = 1 + index * 2
            if offset + 2 > len(data):
                values.append(None)
                continue
            raw = s16le(data, offset)
            values.append(None if raw == TEMP_INVALID else round(raw / 10, 1))
        return values
