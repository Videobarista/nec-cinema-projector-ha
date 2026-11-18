"""Tests for the projector protocol client."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.nec_cinema.client import (
    MAX_NAME_LENGTH,
    NecClient,
    NecConnectionError,
    NecError,
    NecNakError,
    NecProjector,
)
from custom_components.nec_cinema.protocol import HEADER_LENGTH, Response, cstring, parse_frame

from .conftest import HOST, PORT, SERIAL


def _frame(id1: int, id2: int, data: bytes) -> bytes:
    """Build a response frame as the projector would send it."""
    body = bytes((id1, id2, 0x00, 0xC0 | (len(data) >> 8), len(data) & 0xFF)) + data
    return body + bytes((sum(body) & 0xFF,))


def _response(id1: int, id2: int, data: bytes) -> Response:
    """Build a parsed response frame as the projector would send it."""
    frame = _frame(id1, id2, data)
    return parse_frame(frame[:HEADER_LENGTH], frame[HEADER_LENGTH:])


def _projector(response: Response) -> tuple[NecProjector, AsyncMock]:
    """Return a projector whose client answers every request with ``response``."""
    client = MagicMock()
    client.request = AsyncMock(return_value=response)
    return NecProjector(client), client.request


@contextmanager
def _link(**kwargs: float) -> Generator[tuple[NecClient, asyncio.StreamReader, MagicMock]]:
    """Return a real client on a connection that exists only in memory.

    What the projector "sends" is fed into the reader; nothing touches the
    network. Call it from inside a test, so the reader binds to the test loop.
    """
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.is_closing.return_value = False
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    with patch(
        "custom_components.nec_cinema.client.asyncio.open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        yield NecClient(HOST, PORT, **kwargs), reader, writer


async def test_lamp_mode_request() -> None:
    """LAMP MODE REQUEST goes out as 03H B0H and reports the current mode."""
    projector, request = _projector(_response(0x23, 0xB0, bytes((0xD8, 0x01))))
    assert await projector.lamp_mode() == 0x01
    request.assert_awaited_once_with(0x03, 0xB0, bytes((0xD8,)))


async def test_lamp_mode_set_uses_setting_command() -> None:
    """LAMP MODE SET goes out as 03H B1H.

    The protocol document prints 03H B0H, which is the request: a head sent
    that only reports its current mode and changes nothing.
    """
    projector, request = _projector(_response(0x23, 0xB1, bytes((0xD8, 0x00))))
    await projector.set_lamp_mode(0x02)
    request.assert_awaited_once_with(0x03, 0xB1, bytes((0xD8, 0x02)))


@pytest.mark.parametrize(
    ("result", "message"),
    [(0x01, "reported an error"), (0x02, "cannot change the lamp mode right now")],
)
async def test_lamp_mode_set_refused(result: int, message: str) -> None:
    """A result other than success is raised as a refusal."""
    projector, _request = _projector(_response(0x23, 0xB1, bytes((0xD8, result))))
    with pytest.raises(NecNakError, match=message):
        await projector.set_lamp_mode(0x00)


def test_text_from_the_projector_is_cleaned() -> None:
    """Control characters are dropped, odd bytes replaced and long names cut off."""
    assert cstring(b"NC\x07-Series\x00left over") == "NC-Series"
    assert cstring(b"  Exhaust\t\r\n") == "Exhaust"
    assert cstring(b"DMD\xff") == "DMD�"
    assert cstring(b"A" * 300, limit=MAX_NAME_LENGTH) == "A" * MAX_NAME_LENGTH
    assert cstring(b"A" * 300) == "A" * 300


async def test_names_are_capped() -> None:
    """A model name or serial number of kilobytes does not end up in an identifier."""
    projector, _request = _projector(_response(0x20, 0x85, b"M" * 200))
    assert await projector.model_name() == "M" * MAX_NAME_LENGTH

    projector, _request = _projector(_response(0x20, 0x86, b"\x08" + b"S" * 200))
    assert await projector.serial_number() == "S" * MAX_NAME_LENGTH

    projector, _request = _projector(_response(0x20, 0x86, b"\x08" + SERIAL.encode() + b"\x00"))
    assert await projector.serial_number() == SERIAL


async def test_serial_number_stays_out_of_the_debug_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The answer holding the serial number is logged without its data."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nec_cinema.client")
    with _link() as (client, reader, _writer):
        reader.feed_data(_frame(0x20, 0x86, b"\x08" + SERIAL.encode() + b"\x00"))
        assert await NecProjector(client).serial_number() == SERIAL

        # Other answers are still logged in full, which is what a debug log is for.
        reader.feed_data(_frame(0x20, 0x85, b"NC-Series\x00"))
        assert await NecProjector(client).model_name() == "NC-Series"

    assert "data bytes not logged" in caplog.text
    assert SERIAL.encode().hex(" ") not in caplog.text
    assert b"NC-Series".hex(" ") in caplog.text


async def test_request_has_a_time_limit() -> None:
    """A projector that never finishes answering is given up on and disconnected."""
    with _link(timeout=5.0, request_timeout=0.05) as (client, reader, writer):
        # Half a header and then silence.
        reader.feed_data(b"\x20\x85")
        with pytest.raises(NecConnectionError, match="no complete answer within 0.05 s"):
            await NecProjector(client).model_name()
        writer.close.assert_called_once()
        assert not client.connected


async def test_frames_of_another_request_are_skipped() -> None:
    """Left-over frames are discarded, but only a few: then the request fails."""
    with _link() as (client, reader, _writer):
        reader.feed_data(_frame(0x20, 0xC1, b"\x00"))
        reader.feed_data(_frame(0x20, 0x85, b"NC-Series\x00"))
        assert await NecProjector(client).model_name() == "NC-Series"

    with _link() as (client, reader, writer):
        for _ in range(4):
            reader.feed_data(_frame(0x20, 0xC1, b"\x00"))
        with pytest.raises(NecError, match="no matching response"):
            await NecProjector(client).model_name()
        writer.close.assert_called_once()
